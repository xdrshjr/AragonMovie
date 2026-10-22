'use strict';

/**
 * Copies the Python pipeline into build/desktop/app so electron-builder can
 * ship it as an extra resource.
 *
 * Never copies: user data (backend/data, backend/projects, temp_projects),
 * logs, outputs, the virtualenv, node_modules, tests, docs, or any .env file.
 */
const fs = require('node:fs');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const TARGET = path.join(REPO_ROOT, 'build', 'desktop', 'app');

const DIRS = ['agents', 'backend', 'config', 'core', 'models', 'services', 'utils', 'templates'];
const FILES = ['cli.py', 'requirements.txt', 'README.md'];
const EXCLUDED_DIR_NAMES = new Set([
  '__pycache__',
  'data',
  'projects',
  'temp_projects',
  'node_modules',
  '.pytest_cache',
]);
const EXCLUDED_FILE_MATCHERS = [/\.pyc$/i, /^\.env(\..*)?$/i];

function shouldSkip(name) {
  return EXCLUDED_DIR_NAMES.has(name) || EXCLUDED_FILE_MATCHERS.some((re) => re.test(name));
}

function copyTree(source, target) {
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    if (shouldSkip(entry.name)) continue;
    const src = path.join(source, entry.name);
    const dst = path.join(target, entry.name);
    if (entry.isDirectory()) {
      fs.mkdirSync(dst, { recursive: true });
      copyTree(src, dst);
    } else if (entry.isFile()) {
      fs.copyFileSync(src, dst);
    }
  }
}

function main() {
  fs.mkdirSync(TARGET, { recursive: true });

  // `bin/` (ffmpeg + ffprobe) is produced by build-python-runtime.ps1 and must
  // survive this step, so only the Python trees are replaced.
  for (const dir of DIRS) {
    const source = path.join(REPO_ROOT, dir);
    if (!fs.existsSync(source)) continue;
    const target = path.join(TARGET, dir);
    fs.rmSync(target, { recursive: true, force: true });
    fs.mkdirSync(target, { recursive: true });
    copyTree(source, target);
    console.log(`  + ${dir}/`);
  }

  for (const file of FILES) {
    const source = path.join(REPO_ROOT, file);
    if (!fs.existsSync(source)) continue;
    fs.copyFileSync(source, path.join(TARGET, file));
    console.log(`  + ${file}`);
  }

  // The pipeline root must be importable as a package root (agents., backend.,
  // config., core., models., services., utils.).
  const marker = path.join(TARGET, '.app-ready');
  fs.writeFileSync(marker, new Date().toISOString(), 'utf8');

  const size = measure(TARGET);
  console.log(`build/desktop/app ready — ${(size / 1024 / 1024).toFixed(1)} MB`);
}

function measure(dir) {
  let total = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) total += measure(full);
    else total += fs.statSync(full).size;
  }
  return total;
}

main();
