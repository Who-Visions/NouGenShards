#!/usr/bin/env node

const path = require('path');
const { spawnSync } = require('child_process');

const args = process.argv.slice(2);
const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
const rootDir = path.resolve(__dirname, '..');
const cliScript = path.join(rootDir, 'src', 'nougen_shards', 'cli.py');

const result = spawnSync(pythonExecutable, [cliScript, ...args], {
  stdio: 'inherit',
  cwd: rootDir
});

if (result.error) {
  console.error(`Failed to start python process: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status);
