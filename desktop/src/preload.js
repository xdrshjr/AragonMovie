'use strict';

/**
 * Preload bridge.
 *
 * `window.aragonDesktop` is what the Next.js UI reads to discover the backend
 * base URL at runtime (see frontend/src/lib/api.ts -> getApiBase()).
 * `window.aragonShell` powers the first-run setup wizard and is intentionally
 * narrow: no direct filesystem or network access from the renderer.
 */
const { contextBridge, ipcRenderer } = require('electron');

let syncInfo = { apiBase: '', appVersion: '' };
try {
  syncInfo = ipcRenderer.sendSync('runtime:sync-info') || syncInfo;
} catch {
  /* main process not ready - the UI falls back to localhost:8000 */
}

contextBridge.exposeInMainWorld('aragonDesktop', {
  isDesktop: true,
  apiBase: syncInfo.apiBase,
  appVersion: syncInfo.appVersion,
  platform: process.platform,
});

contextBridge.exposeInMainWorld('aragonShell', {
  info: () => ipcRenderer.invoke('shell:info'),
  getSettings: () => ipcRenderer.invoke('settings:get'),
  saveCategory: (category, payload) => ipcRenderer.invoke('settings:update', { category, payload }),
  testCategory: (category) => ipcRenderer.invoke('settings:test', category),
  saveAndTest: (category, payload) => ipcRenderer.invoke('settings:save-and-test', { category, payload }),
  completeSetup: () => ipcRenderer.invoke('setup:complete'),
  skipSetup: () => ipcRenderer.invoke('setup:skip'),
  openPath: (kind) => ipcRenderer.invoke('shell:open-path', kind),
  openExternal: (url) => ipcRenderer.invoke('shell:open-external', url),
  retry: () => ipcRenderer.invoke('app:retry'),
  relaunch: () => ipcRenderer.invoke('app:relaunch'),
  quit: () => ipcRenderer.invoke('app:quit'),
  capture: (target, name) => ipcRenderer.invoke('debug:capture', { target, name }),
  onStartup: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('startup:progress', listener);
    return () => ipcRenderer.removeListener('startup:progress', listener);
  },
  onServiceError: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('service:error', listener);
    return () => ipcRenderer.removeListener('service:error', listener);
  },
});
