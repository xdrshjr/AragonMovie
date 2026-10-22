'use strict';

/**
 * Path resolution for both flavours of the app:
 *
 *  - development: `npm start` inside desktop/ -> run straight from the repo
 *    (venv python, repo sources, build/desktop/web)
 *  - packaged:    the installer ships resources/{python,app,web}; user-writable
 *    copies live under <userData>/workspace so upgrades never destroy data.
 *
 * Every location can be overridden with an env var, which is what the CI /
 * verification scripts use to attach the packaged shell to a dev tree.
 */
const fs = require('node:fs');
const path = require('node:path');
const { app } = require('electron');

const DEV_REPO_ROOT = path.resolve(__dirname, '..', '..');

function firstExisting(candidates) {
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      if (fs.existsSync(candidate)) return candidate;
    } catch {
      /* ignore */
    }
  }
  return null;
}

function resolve() {
  const packaged = app.isPackaged;
  const resources = packaged ? process.resourcesPath : null;
  const userData = app.getPath('userData');
  const workspaceRoot = path.join(userData, 'workspace');

  const pythonExe =
    process.env.ARAGON_PYTHON ||
    firstExisting([
      packaged ? path.join(resources, 'python', 'python.exe') : null,
      path.join(DEV_REPO_ROOT, 'venv', 'Scripts', 'python.exe'),
      path.join(DEV_REPO_ROOT, '.venv', 'Scripts', 'python.exe'),
    ]);

  // Source of the Python pipeline (copied into the workspace when packaged).
  const appSourceDir =
    process.env.ARAGON_APP_SOURCE ||
    (packaged ? path.join(resources, 'app') : DEV_REPO_ROOT);

  const appHome = packaged
    ? process.env.ARAGON_APP_HOME || path.join(workspaceRoot, 'app')
    : appSourceDir;

  const webSourceDir =
    process.env.ARAGON_WEB_SOURCE ||
    firstExisting([
      packaged ? path.join(resources, 'web') : null,
      path.join(DEV_REPO_ROOT, 'build', 'desktop', 'web'),
    ]);

  const webHome = packaged
    ? process.env.ARAGON_WEB_HOME || path.join(workspaceRoot, 'web')
    : webSourceDir;

  const ffmpegDir =
    process.env.ARAGON_FFMPEG_DIR ||
    firstExisting([
      packaged ? path.join(resources, 'app', 'bin') : null,
      path.join(DEV_REPO_ROOT, 'build', 'desktop', 'app', 'bin'),
    ]);

  return {
    packaged,
    repoRoot: DEV_REPO_ROOT,
    resources,
    userData,
    workspaceRoot,
    logDir: path.join(userData, 'logs'),
    stateFile: path.join(userData, 'desktop-state.json'),
    settingsFile: path.join(appHome, 'backend', 'data', 'model_settings.json'),
    pythonExe,
    appSourceDir,
    appHome,
    webSourceDir,
    webHome,
    ffmpegDir,
    // Optional: attach to services that are already running (dev / e2e).
    externalBackendUrl: process.env.ARAGON_BACKEND_URL || null,
    externalWebUrl: process.env.ARAGON_WEB_URL || null,
  };
}

module.exports = { resolve };
