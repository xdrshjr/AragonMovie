'use strict';

/**
 * One-shot packaging driver.
 *
 *   node scripts/dist.js            # full NSIS installer
 *   node scripts/dist.js --dir      # unpacked app (fast smoke test)
 *   node scripts/dist.js --portable # portable single-file exe
 *   node scripts/dist.js --skip-web # reuse an existing build/desktop/web
 *   node scripts/dist.js --skip-python
 */
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const DESKTOP = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(DESKTOP, '..');
const BUILD = path.join(REPO_ROOT, 'build', 'desktop');
const isWindows = process.platform === 'win32';

const args = process.argv.slice(2);
const has = (flag) => args.includes(flag);

function step(label, command, commandArgs, cwd) {
  console.log(`\n=== ${label} ===`);
  const result = spawnSync(command, commandArgs, {
    cwd,
    stdio: 'inherit',
    shell: isWindows,
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' },
  });
  if (result.status !== 0) {
    console.error(`\n[dist] ${label} failed (exit ${result.status})`);
    process.exit(result.status || 1);
  }
}

function assertExists(relative, hint) {
  const full = path.join(BUILD, relative);
  if (!fs.existsSync(full)) {
    console.error(`\n[dist] missing ${full}\n        ${hint}`);
    process.exit(1);
  }
  return full;
}

// ---------------------------------------------------------------- app code
step('Copying Python pipeline', process.execPath, [path.join(DESKTOP, 'scripts', 'build-app-code.js')], DESKTOP);

// ------------------------------------------------------------------- web
if (has('--skip-web')) {
  assertExists('web/server.js', 'run without --skip-web to build the Next.js bundle');
  console.log('\n[dist] skipping web build (--skip-web)');
} else {
  step('Building Next.js standalone bundle', process.execPath, [path.join(DESKTOP, 'scripts', 'build-web.js')], DESKTOP);
}

// ---------------------------------------------------------------- python
if (has('--skip-python')) {
  assertExists(path.join('python', 'python.exe'), 'run without --skip-python to build the portable interpreter');
  console.log('\n[dist] skipping python runtime build (--skip-python)');
} else {
  step(
    'Building portable Python runtime',
    'powershell',
    ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(BUILD, 'build-python-runtime.ps1')],
    REPO_ROOT
  );
}

assertExists(path.join('app', 'bin', 'ffmpeg.exe'), 'ffmpeg must be bundled — re-run the python runtime build');
assertExists(path.join('python', 'python.exe'), 'portable interpreter missing');

// --------------------------------------------------------------- electron-builder
if (!fs.existsSync(path.join(DESKTOP, 'node_modules', 'electron-builder'))) {
  step('Installing desktop dependencies', 'npm', ['install', '--no-audit', '--no-fund'], DESKTOP);
}

const builderArgs = ['electron-builder', '--win'];
if (has('--dir')) builderArgs.push('--dir');
if (has('--portable')) builderArgs.push('portable', 'nsis');
if (!has('--dir') && !has('--portable')) builderArgs.push('nsis');

console.log(`\n=== Packaging (${builderArgs.join(' ')}) ===`);
step('electron-builder', isWindows ? 'npx.cmd' : 'npx', builderArgs, DESKTOP);

console.log('\n[dist] done. Artifacts:');
const releaseDir = path.join(DESKTOP, 'release');
if (fs.existsSync(releaseDir)) {
  for (const entry of fs.readdirSync(releaseDir, { withFileTypes: true })) {
    if (entry.isFile() && /\.(exe|zip|7z|blockmap|yml)$/i.test(entry.name)) {
      const size = fs.statSync(path.join(releaseDir, entry.name)).size / 1024 / 1024;
      console.log(`  - ${entry.name}  (${size.toFixed(1)} MB)`);
    }
  }
}
