#!/usr/bin/env node

const path = require('path');
const { spawnSync } = require('child_process');

const args = process.argv.slice(2);
const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
const rootDir = path.resolve(__dirname, '..');
const srcDir = path.join(rootDir, 'src');

const result = spawnSync(pythonExecutable, ['-m', 'nougen_shards.cli', ...args], {
  stdio: 'inherit',
  cwd: rootDir,
  env: {
    ...process.env,
    PYTHONPATH: process.env.PYTHONPATH ? `${srcDir}${path.delimiter}${process.env.PYTHONPATH}` : srcDir
  }
});

if (result.error) {
  console.error(`Failed to start python process: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status);
