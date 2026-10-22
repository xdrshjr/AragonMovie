'use strict';

/**
 * Produces the Next.js standalone bundle that the Electron shell serves at
 * runtime:  build/desktop/web/{server.js,node_modules,.next,public}
 */
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND = path.join(REPO_ROOT, 'frontend');
const OUT = path.join(REPO_ROOT, 'build', 'desktop', 'web');

const isWindows = process.platform === 'win32';

function run(command, args, cwd, extraEnv) {
  console.log(`> ${command} ${args.join(' ')} (${cwd})`);
  const result = spawnSync(command, args, {
    cwd,
    stdio: 'inherit',
    env: { ...process.env, ...extraEnv },
    shell: isWindows,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed with exit code ${result.status}`);
  }
}

function copyDir(source, target) {
  fs.mkdirSync(target, { recursive: true });
  fs.cpSync(source, target, { recursive: true, force: true });
}

function main() {
  if (!fs.existsSync(path.join(FRONTEND, 'node_modules'))) {
    throw new Error('frontend/node_modules is missing — run `npm install` in frontend/ first.');
  }

  run('npm', ['run', 'build'], FRONTEND, {
    NEXT_TELEMETRY_DISABLED: '1',
    NODE_ENV: 'production',
  });

  const standalone = path.join(FRONTEND, '.next', 'standalone');
  if (!fs.existsSync(path.join(standalone, 'server.js'))) {
    throw new Error(
      'next build did not produce .next/standalone/server.js — is `output: "standalone"` still set in frontend/next.config.js?'
    );
  }

  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });

  // 1. server.js + minimal node_modules + .next/server
  copyDir(standalone, OUT);

  // 2. static chunks (Next does not copy these into standalone)
  const staticSource = path.join(FRONTEND, '.next', 'static');
  if (fs.existsSync(staticSource)) copyDir(staticSource, path.join(OUT, '.next', 'static'));

  // 3. public assets
  const publicSource = path.join(FRONTEND, 'public');
  if (fs.existsSync(publicSource)) copyDir(publicSource, path.join(OUT, 'public'));

  const size = measure(OUT);
  console.log(`build/desktop/web ready — ${(size / 1024 / 1024).toFixed(1)} MB`);
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

try {
  main();
} catch (error) {
  console.error(`\n[build-web] ${error.message}`);
  process.exit(1);
}
