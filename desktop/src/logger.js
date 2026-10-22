'use strict';

/**
 * Structured file + console logger for the desktop shell and its child
 * processes. Everything lands in <userData>/logs/desktop.log so the user can
 * open it from the app menu when a service misbehaves.
 */
const fs = require('node:fs');
const path = require('node:path');

let logFile = null;
let logStream = null;

function pad(n) {
  return String(n).padStart(2, '0');
}

function stamp() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, '0')}`;
}

function init(logDir) {
  fs.mkdirSync(logDir, { recursive: true });
  logFile = path.join(logDir, 'desktop.log');

  // Keep the previous session around, but do not let the file grow forever.
  try {
    const stat = fs.statSync(logFile);
    if (stat.size > 8 * 1024 * 1024) {
      fs.rmSync(`${logFile}.1`, { force: true });
      fs.renameSync(logFile, `${logFile}.1`);
    }
  } catch {
    /* first run */
  }

  logStream = fs.createWriteStream(logFile, { flags: 'a' });
  return logFile;
}

function write(level, scope, args) {
  const line = `${stamp()} [${level}] [${scope}] ${args
    .map((a) => (typeof a === 'string' ? a : safeJson(a)))
    .join(' ')}`;
  const consoleFn = level === 'ERROR' ? console.error : level === 'WARN' ? console.warn : console.log;
  consoleFn(line);
  if (logStream) logStream.write(`${line}\n`);
}

function safeJson(value) {
  if (value instanceof Error) return `${value.name}: ${value.message}\n${value.stack || ''}`;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function scoped(scope) {
  return {
    info: (...a) => write('INFO', scope, a),
    warn: (...a) => write('WARN', scope, a),
    error: (...a) => write('ERROR', scope, a),
    debug: (...a) => write('DEBUG', scope, a),
  };
}

module.exports = {
  init,
  scoped,
  getLogFile: () => logFile,
  close: () => {
    if (logStream) {
      logStream.end();
      logStream = null;
    }
  },
};
