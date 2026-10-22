'use strict';

/**
 * AragonMovie desktop shell.
 *
 * Boot sequence
 *   1. splash window ("正在启动本地服务")
 *   2. ServiceManager starts the Python backend + Next.js standalone server
 *   3. gate: first launch (or missing credentials) -> setup wizard, otherwise
 *      straight into the product UI
 *   4. credentials entered in the wizard are persisted by the backend itself
 *      (backend/data/model_settings.json inside the user workspace), so every
 *      later launch skips onboarding.
 */
const fs = require('node:fs');
const path = require('node:path');
const { app, BrowserWindow, ipcMain, shell, dialog, nativeTheme } = require('electron');

const logger = require('./logger');
const { resolve } = require('./paths');
const { ServiceManager } = require('./services');
const { SettingsBridge, evaluate } = require('./settings-api');
const { applyMenu } = require('./menu');

const pkg = require('../package.json');
const isDev = process.argv.includes('--dev') || !app.isPackaged;

let logFile = null;
const log = () => logger.scoped('main');

/** @type {{ runtime: any, services: ServiceManager|null, bridge: SettingsBridge|null, ready: boolean, bootError: string|null }} */
const state = {
  runtime: null,
  services: null,
  bridge: null,
  ready: false,
  bootError: null,
};

let splashWindow = null;
let mainWindow = null;
let wizardWindow = null;
const pendingSplashEvents = [];
let splashLoaded = false;

// ---------------------------------------------------------------------------
// persisted desktop state
// ---------------------------------------------------------------------------

function stateFile() {
  return state.runtime?.stateFile || path.join(app.getPath('userData'), 'desktop-state.json');
}

function readDesktopState() {
  try {
    return JSON.parse(fs.readFileSync(stateFile(), 'utf8'));
  } catch {
    return {};
  }
}

function writeDesktopState(patch) {
  const next = { ...readDesktopState(), ...patch };
  try {
    fs.mkdirSync(path.dirname(stateFile()), { recursive: true });
    fs.writeFileSync(stateFile(), JSON.stringify(next, null, 2), 'utf8');
  } catch (error) {
    logger.scoped('main').error(`failed to persist desktop state: ${error.message}`);
  }
  return next;
}

// ---------------------------------------------------------------------------
// windows
// ---------------------------------------------------------------------------

function commonWebPreferences(extra) {
  return {
    preload: path.join(__dirname, 'preload.js'),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    spellcheck: false,
    backgroundThrottling: false,
    ...extra,
  };
}

function hardenWebContents(contents, allowedOrigins) {
  contents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url) && !allowedOrigins.some((origin) => url.startsWith(origin))) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  contents.on('will-navigate', (event, url) => {
    const allowed =
      url.startsWith('file://') || allowedOrigins.some((origin) => url.startsWith(origin));
    if (!allowed) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    }
  });

  contents.on('render-process-gone', (_event, details) => {
    logger.scoped('main').error(`renderer gone: ${JSON.stringify(details)}`);
  });
}

function createSplash() {
  splashWindow = new BrowserWindow({
    width: 560,
    height: 400,
    frame: false,
    resizable: false,
    movable: true,
    show: true,
    backgroundColor: '#0A0A0B',
    center: true,
    title: 'AragonMovie',
    webPreferences: commonWebPreferences(),
  });
  splashWindow.loadFile(path.join(__dirname, '..', 'ui', 'splash.html'));
  splashWindow.webContents.on('did-finish-load', () => {
    splashLoaded = true;
    pendingSplashEvents.splice(0).forEach((payload) => sendSplash(payload));
  });
  splashWindow.on('closed', () => {
    splashWindow = null;
    splashLoaded = false;
  });
}

function sendSplash(payload) {
  if (splashWindow && splashLoaded && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('startup:progress', payload);
  } else {
    pendingSplashEvents.push(payload);
  }
}

function closeSplash() {
  if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
}

function createMainWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1080,
    minHeight: 700,
    show: false,
    backgroundColor: '#0A0A0B',
    title: 'AragonMovie',
    autoHideMenuBar: false,
    titleBarStyle: 'default',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: commonWebPreferences(),
  });

  hardenWebContents(mainWindow.webContents, [url]);
  mainWindow.loadURL(url);
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (isDev && process.argv.includes('--dev')) mainWindow.webContents.openDevTools({ mode: 'detach' });
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  return mainWindow;
}

function createWizardWindow(query = {}) {
  wizardWindow = new BrowserWindow({
    width: 1120,
    height: 780,
    minWidth: 940,
    minHeight: 640,
    show: false,
    backgroundColor: '#0A0A0B',
    title: 'AragonMovie · 初始配置',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: commonWebPreferences(),
  });

  hardenWebContents(wizardWindow.webContents, []);
  wizardWindow.loadFile(path.join(__dirname, '..', 'ui', 'setup.html'), { query });
  wizardWindow.once('ready-to-show', () => wizardWindow.show());
  wizardWindow.on('closed', () => {
    wizardWindow = null;
  });
  return wizardWindow;
}

function openWizard({ fromMenu = false } = {}) {
  if (wizardWindow && !wizardWindow.isDestroyed()) {
    wizardWindow.focus();
    return wizardWindow;
  }
  return createWizardWindow(fromMenu ? { mode: 'reconfigure' } : {});
}

function openMain(options = {}) {
  if (!state.ready || !state.services?.webUrl) {
    openWizard();
    return undefined;
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    return mainWindow;
  }
  return createMainWindow(state.services.webUrl + (options.route || ''));
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------

async function boot() {
  state.bootError = null;
  try {
    if (!state.runtime) {
      state.runtime = resolve();
      state.runtime.version = pkg.version;
      logger.init(state.runtime.logDir);
      logFile = logger.getLogFile();
      log().info(
        `desktop ${pkg.version} starting | packaged=${state.runtime.packaged} | python=${state.runtime.pythonExe} | app=${state.runtime.appHome} | web=${state.runtime.webHome}`
      );
    }

    if (!state.services) {
      state.services = new ServiceManager(state.runtime, (payload) => sendSplash(payload));
      state.services.setCrashHandler((crash) => handleServiceCrash(crash));
    }

    const { backendUrl } = await state.services.start();
    state.runtime.backendUrl = backendUrl;
    state.bridge = new SettingsBridge(state.runtime);
    state.ready = true;

    const settings = await state.bridge.getSettings();
    const status = evaluate(settings.settings);
    const desktopState = readDesktopState();
    const onboarded = Boolean(desktopState.onboardedAt);

    log().info(`settings evaluation: configured=${status.configured} missing=${status.missing.join(',')} onboarded=${onboarded}`);

    closeSplash();

    if (!onboarded || !status.configured) {
      openWizard();
    } else {
      openMain();
    }
  } catch (error) {
    state.bootError = error.message;
    log().error(`boot failed: ${error.message}`);
    sendSplash({
      stage: 'error',
      status: 'error',
      message: '启动失败',
      detail: error.message,
    });
  }
}

function handleServiceCrash(crash) {
  log().error(`service crash: ${crash.stage} code=${crash.code} log=${crash.logFile}`);
  const windows = BrowserWindow.getAllWindows();
  const target = mainWindow || wizardWindow || windows[0];
  if (target) target.webContents.send('service:error', crash);
  if (!target) {
    dialog.showErrorBox('AragonMovie 服务异常', `${crash.message}\n\n日志：${crash.logFile}`);
  }
}

// ---------------------------------------------------------------------------
// IPC
// ---------------------------------------------------------------------------

function registerIpc() {
  ipcMain.on('runtime:sync-info', (event) => {
    event.returnValue = {
      apiBase: state.runtime?.backendUrl || state.services?.backendUrl || '',
      appVersion: pkg.version,
    };
  });

  ipcMain.handle('shell:info', () => ({
    appVersion: pkg.version,
    apiBase: state.runtime?.backendUrl || state.services?.backendUrl || '',
    webUrl: state.services?.webUrl || '',
    userData: state.runtime?.userData || app.getPath('userData'),
    logDir: state.runtime?.logDir || '',
    logFile,
    settingsFile: state.runtime?.settingsFile || '',
    ffmpegDir: state.runtime?.ffmpegDir || '',
    isPackaged: Boolean(state.runtime?.packaged),
    ready: state.ready,
    bootError: state.bootError,
  }));

  ipcMain.handle('settings:get', async () => {
    if (!state.bridge) throw new Error('服务尚未就绪');
    const payload = await state.bridge.getSettings();
    return { ...payload, status: evaluate(payload.settings) };
  });

  ipcMain.handle('settings:update', async (_event, { category, payload }) => {
    if (!state.bridge) throw new Error('服务尚未就绪');
    const response = await state.bridge.update(category, payload);
    return { ...response, status: evaluate(response.settings) };
  });

  ipcMain.handle('settings:test', async (_event, category) => {
    if (!state.bridge) throw new Error('服务尚未就绪');
    return state.bridge.test(category);
  });

  ipcMain.handle('settings:save-and-test', async (_event, { category, payload }) => {
    if (!state.bridge) throw new Error('服务尚未就绪');
    return state.bridge.saveAndTest(category, payload);
  });

  ipcMain.handle('setup:complete', () => {
    writeDesktopState({
      onboardedAt: new Date().toISOString(),
      appVersion: pkg.version,
    });
    if (wizardWindow && !wizardWindow.isDestroyed()) wizardWindow.close();
    openMain();
    return { ok: true };
  });

  ipcMain.handle('setup:skip', () => {
    writeDesktopState({ skippedAt: new Date().toISOString() });
    if (wizardWindow && !wizardWindow.isDestroyed()) wizardWindow.close();
    openMain();
    return { ok: true };
  });

  ipcMain.handle('shell:open-path', async (_event, kind) => {
    const runtime = state.runtime;
    const targets = {
      data: runtime?.userData || app.getPath('userData'),
      logs: runtime?.logDir || '',
      settings: runtime?.settingsFile || '',
      workspace: runtime?.appHome || '',
    };
    const target = targets[kind];
    if (!target) return { ok: false, message: `未知路径：${kind}` };
    if (kind === 'settings') {
      if (!fs.existsSync(target)) return { ok: false, message: '配置文件尚未生成，请先保存一次设置。' };
      shell.showItemInFolder(target);
      return { ok: true };
    }
    fs.mkdirSync(target, { recursive: true });
    await shell.openPath(target);
    return { ok: true };
  });

  ipcMain.handle('shell:open-external', async (_event, url) => {
    if (/^https?:\/\//i.test(url)) await shell.openExternal(url);
    return { ok: true };
  });

  ipcMain.handle('app:retry', async () => {
    if (state.services) await state.services.stop();
    state.ready = false;
    state.runtime = null;
    state.services = null;
    await boot();
    return { ok: !state.bootError, message: state.bootError };
  });

  ipcMain.handle('app:relaunch', () => {
    app.relaunch();
    app.exit(0);
  });

  ipcMain.handle('app:quit', () => {
    app.quit();
  });

  // Screenshot helper for the verification suite. Writes into the app's own
  // data directory; never used by the product UI itself.
  ipcMain.handle('debug:capture', async (_event, { target, name } = {}) => {
    const windows = { main: mainWindow, wizard: wizardWindow, splash: splashWindow };
    const win = windows[target] || BrowserWindow.getFocusedWindow();
    if (!win || win.isDestroyed()) return { ok: false, message: 'window not available' };
    try {
      const image = await win.webContents.capturePage();
      const dir = path.join(app.getPath('userData'), 'captures');
      fs.mkdirSync(dir, { recursive: true });
      const file = path.join(dir, `${name || `capture-${Date.now()}`}.png`);
      fs.writeFileSync(file, image.toPNG());
      return { ok: true, file };
    } catch (error) {
      return { ok: false, message: error.message };
    }
  });
}

// ---------------------------------------------------------------------------
// lifecycle
// ---------------------------------------------------------------------------

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  // Deterministic, product-named data location (dev and packaged builds agree).
  app.setName('AragonMovie');
  try {
    app.setPath('userData', path.join(app.getPath('appData'), 'AragonMovie'));
  } catch {
    /* keep the default */
  }

  app.on('second-instance', () => {
    const target = mainWindow || wizardWindow;
    if (target) {
      if (target.isMinimized()) target.restore();
      target.focus();
    }
  });

  app.whenReady().then(async () => {
    nativeTheme.themeSource = 'dark';
    app.setAppUserModelId('com.aragon.movie');
    app.setName('AragonMovie');

    applyMenu({
      openWizard,
      openPath: (kind) => {
        const runtime = state.runtime;
        if (!runtime) return;
        if (kind === 'logs') shell.openPath(runtime.logDir);
        if (kind === 'data') shell.openPath(runtime.userData);
        if (kind === 'settings') {
          if (fs.existsSync(runtime.settingsFile)) shell.showItemInFolder(runtime.settingsFile);
          else shell.openPath(runtime.userData);
        }
      },
      backendUrl: () => state.services?.backendUrl || '',
      info: () => ({
        appVersion: pkg.version,
        apiBase: state.services?.backendUrl || '',
        webUrl: state.services?.webUrl || '',
        userData: state.runtime?.userData || app.getPath('userData'),
        logDir: state.runtime?.logDir || '',
        logFile,
        electron: process.versions.electron,
        chrome: process.versions.chrome,
        node: process.versions.node,
      }),
    });

    registerIpc();
    createSplash();
    await boot();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) openMain();
  });

  app.on('window-all-closed', () => {
    app.quit();
  });

  app.on('before-quit', async () => {
    if (state.services) await state.services.stop();
    logger.close();
  });

  process.on('uncaughtException', (error) => {
    logger.scoped('main').error(`uncaughtException: ${error.stack || error.message}`);
  });
  process.on('unhandledRejection', (reason) => {
    logger.scoped('main').error(`unhandledRejection: ${reason}`);
  });
}
