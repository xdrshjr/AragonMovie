'use strict';

/**
 * Local service supervisor.
 *
 * Two child processes power the desktop app:
 *   1. the Python FastAPI backend (portable interpreter + bundled pipeline)
 *   2. the Next.js standalone server (runs inside Electron's own Node runtime
 *      via ELECTRON_RUN_AS_NODE, so no external Node install is required)
 *
 * Both are started on free loopback ports and stopped (process-tree kill) when
 * the app exits.
 */
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { spawn, execFile } = require('node:child_process');
const { scoped } = require('./logger');

const log = scoped('services');

// Directories inside the copied Python app tree that hold USER data and must
// survive an app upgrade.
const PRESERVED_DIRS = [
  path.join('backend', 'data'),
  path.join('backend', 'projects'),
  path.join('backend', 'temp_projects'),
  'logs',
  'output',
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitForHttp(url, { timeoutMs = 120_000, intervalMs = 500, deadlineMessage } = {}) {
  const deadline = Date.now() + timeoutMs;
  let lastError = 'not started';
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(4000) });
      if (response.ok) return response;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error && error.message ? error.message : String(error);
    }
    await sleep(intervalMs);
  }
  throw new Error(deadlineMessage || `Timed out waiting for ${url} (${lastError})`);
}

function killTree(pid) {
  if (!pid) return;
  if (process.platform === 'win32') {
    try {
      execFile('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true }, () => {});
    } catch {
      /* ignore */
    }
  } else {
    try {
      process.kill(-pid, 'SIGTERM');
    } catch {
      try {
        process.kill(pid, 'SIGTERM');
      } catch {
        /* ignore */
      }
    }
  }
}

/**
 * Copy `source` into `target`, leaving user data alone.
 */
function syncTree(source, target, markerName, markerValue) {
  if (!source || !fs.existsSync(source)) {
    throw new Error(`Missing application files: ${source}`);
  }
  fs.mkdirSync(target, { recursive: true });

  const stats = fs.statSync(source);

  if (stats.isDirectory()) {
    copyDirPreserving(source, target, target);
  } else {
    fs.copyFileSync(source, target);
  }

  if (markerName) {
    fs.writeFileSync(path.join(target, markerName), String(markerValue || '1'), 'utf8');
  }
}

function isPreserved(targetRoot, candidate) {
  const rel = path.relative(targetRoot, candidate);
  if (!rel || rel.startsWith('..')) return false;
  // `bin/` holds the bundled ffmpeg/ffprobe binaries; they are executed from
  // resources/ and never need a user-writable copy.
  if (rel === 'bin') return true;
  return PRESERVED_DIRS.some((dir) => rel === dir || rel.startsWith(`${dir}${path.sep}`));
}

function copyDirPreserving(sourceDir, targetDir, targetRoot) {
  for (const entry of fs.readdirSync(sourceDir, { withFileTypes: true })) {
    if (entry.name === '__pycache__' || entry.name.endsWith('.pyc')) continue;
    const src = path.join(sourceDir, entry.name);
    const dst = path.join(targetDir, entry.name);

    if (entry.isDirectory()) {
      if (isPreserved(targetRoot, dst)) continue;
      fs.mkdirSync(dst, { recursive: true });
      copyDirPreserving(src, dst, targetRoot);
    } else if (entry.isFile()) {
      if (isPreserved(targetRoot, dst)) continue;
      fs.copyFileSync(src, dst);
    }
  }
}

function tailOf(buffer) {
  return buffer.length > 4000 ? `…${buffer.slice(-4000)}` : buffer;
}

function needsSync(target, markerName, version) {
  try {
    return fs.readFileSync(path.join(target, markerName), 'utf8').trim() !== String(version);
  } catch {
    return true;
  }
}

class ServiceManager {
  constructor(runtime, onProgress) {
    this.runtime = runtime;
    this.onProgress = onProgress || (() => {});
    this.backend = null;
    this.web = null;
    this.backendUrl = runtime.externalBackendUrl || null;
    this.webUrl = runtime.externalWebUrl || null;
    this.logs = { backend: null, web: null };
    this.stopping = false;
    this.crashHandler = null;
  }

  progress(stage, status, message, extra) {
    this.onProgress({ stage, status, message, ...(extra || {}) });
    const writer = status === 'error' ? log.error : log.info;
    writer(`${stage}: ${status} — ${message}`);
  }

  setCrashHandler(handler) {
    this.crashHandler = handler;
  }

  async start() {
    if (this.runtime.packaged) {
      const appStale = needsSync(this.runtime.appHome, '.app-version', this.runtime.version);
      const webStale =
        this.runtime.webSourceDir && needsSync(this.runtime.webHome, '.web-version', this.runtime.version);

      if (appStale || webStale) {
        this.progress('files', 'running', '准备工作区文件…');
        if (appStale || !fs.existsSync(this.runtime.appHome)) {
          syncTree(this.runtime.appSourceDir, this.runtime.appHome, '.app-version', this.runtime.version);
        }
        if (webStale && this.runtime.webSourceDir) {
          syncTree(this.runtime.webSourceDir, this.runtime.webHome, '.web-version', this.runtime.version);
        }
        this.progress('files', 'done', '工作区就绪');
      } else {
        this.progress('files', 'done', '工作区已是最新');
      }
    }

    if (!this.backendUrl) {
      await this.startBackend();
    } else {
      this.progress('backend', 'done', `复用已运行的后端服务 ${this.backendUrl}`);
    }

    if (!this.webUrl) {
      await this.startWeb();
    } else {
      this.progress('web', 'done', `复用已运行的前端服务 ${this.webUrl}`);
    }

    this.progress('ready', 'done', '全部服务已就绪');
    return { backendUrl: this.backendUrl, webUrl: this.webUrl };
  }

  backendEnv() {
    const env = {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONUTF8: '1',
      PYTHONDONTWRITEBYTECODE: '1',
      ARAGON_DESKTOP: '1',
      ARAGON_DESKTOP_VERSION: this.runtime.version,
      LOG_LEVEL: process.env.LOG_LEVEL || 'INFO',
      HOST: '127.0.0.1',
    };
    delete env.PYTHONHOME;
    delete env.PYTHONPATH;
    if (this.runtime.ffmpegDir) {
      env.PATH = `${this.runtime.ffmpegDir}${path.delimiter}${env.PATH || ''}`;
      env.IMAGEIO_FFMPEG_EXE = path.join(this.runtime.ffmpegDir, 'ffmpeg.exe');
    }
    return env;
  }

  async startBackend() {
    if (!this.runtime.pythonExe) {
      throw new Error(
        '找不到 Python 运行时。请先运行 build/desktop/build-python-runtime.ps1（开发环境请确认 venv 存在）。'
      );
    }
    const port = await getFreePort();
    this.backendUrl = `http://127.0.0.1:${port}`;
    const logFile = path.join(this.runtime.logDir, 'backend.log');
    fs.mkdirSync(this.runtime.logDir, { recursive: true });
    const stream = fs.createWriteStream(logFile, { flags: 'a' });
    this.logs.backend = logFile;

    this.progress('backend', 'running', '启动本地推理与生成服务…', { detail: `端口 ${port}` });

    const args = [
      '-m',
      'uvicorn',
      'backend.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      String(port),
      '--app-dir',
      this.runtime.appHome,
      '--log-level',
      (process.env.LOG_LEVEL || 'info').toLowerCase(),
    ];

    log.info(`spawning backend: ${this.runtime.pythonExe} ${args.join(' ')} (cwd=${this.runtime.appHome})`);

    const child = spawn(this.runtime.pythonExe, args, {
      cwd: this.runtime.appHome,
      env: this.backendEnv(),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    this.backend = child;

    child.stdout.on('data', (chunk) => stream.write(chunk));
    child.stderr.on('data', (chunk) => stream.write(chunk));
    child.on('exit', (code, signal) => {
      stream.write(`\n[desktop] backend exited code=${code} signal=${signal}\n`);
      stream.end();
      if (!this.stopping) {
        log.error(`backend exited unexpectedly code=${code} signal=${signal}`);
        this.reportCrash('backend', code, logFile);
      }
    });

    try {
      await waitForHttp(`${this.backendUrl}/health`, {
        timeoutMs: 180_000,
        deadlineMessage: '本地服务启动超时。',
      });
    } catch (error) {
      log.error(`backend health check failed: ${error.message}`);
      throw new Error(`${error.message} 详见日志：${logFile}`);
    }

    this.progress('backend', 'done', '本地服务已就绪', { detail: `端口 ${port}` });
  }

  async startWeb() {
    const webDir = this.runtime.webHome;
    const serverJs = path.join(webDir, 'server.js');
    if (!fs.existsSync(serverJs)) {
      throw new Error(`缺少前端构建产物：${serverJs}。请先运行 npm run build:web。`);
    }

    const port = await getFreePort();
    this.webUrl = `http://127.0.0.1:${port}`;
    const logFile = path.join(this.runtime.logDir, 'web.log');
    fs.mkdirSync(this.runtime.logDir, { recursive: true });
    const stream = fs.createWriteStream(logFile, { flags: 'a' });
    this.logs.web = logFile;

    this.progress('web', 'running', '加载界面…', { detail: `端口 ${port}` });

    const child = spawn(process.execPath, [serverJs], {
      cwd: webDir,
      env: {
        ...process.env,
        ELECTRON_RUN_AS_NODE: '1',
        NODE_ENV: 'production',
        NEXT_TELEMETRY_DISABLED: '1',
        PORT: String(port),
        HOSTNAME: '127.0.0.1',
      },
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    this.web = child;

    child.stdout.on('data', (chunk) => stream.write(chunk));
    child.stderr.on('data', (chunk) => stream.write(chunk));
    child.on('exit', (code, signal) => {
      stream.write(`\n[desktop] web exited code=${code} signal=${signal}\n`);
      stream.end();
      if (!this.stopping) {
        log.error(`web exited unexpectedly code=${code} signal=${signal}`);
        this.reportCrash('web', code, logFile);
      }
    });

    try {
      await waitForHttp(this.webUrl, {
        timeoutMs: 90_000,
        deadlineMessage: '界面服务启动超时。',
      });
    } catch (error) {
      log.error(`web health check failed: ${error.message}`);
      throw new Error(`${error.message} 详见日志：${logFile}`);
    }

    this.progress('web', 'done', '界面已就绪', { detail: `端口 ${port}` });
  }

  reportCrash(stage, code, logFile) {
    if (this.crashHandler) {
      this.crashHandler({
        stage,
        code,
        logFile,
        message: stage === 'backend' ? '本地服务已退出。' : '界面服务已退出。',
      });
    }
  }

  async restart() {
    await this.stop();
    this.stopping = false;
    this.backendUrl = this.runtime.externalBackendUrl || null;
    this.webUrl = this.runtime.externalWebUrl || null;
    return this.start();
  }

  async stop() {
    this.stopping = true;
    for (const [name, child] of [
      ['web', this.web],
      ['backend', this.backend],
    ]) {
      if (child && child.pid) {
        log.info(`stopping ${name} (pid ${child.pid})`);
        killTree(child.pid);
      }
    }
    this.backend = null;
    this.web = null;
    await sleep(150);
  }
}

module.exports = { ServiceManager, getFreePort, waitForHttp, tailOf };
