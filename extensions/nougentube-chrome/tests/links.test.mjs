// Every link the extension opens in a new tab must open without a referrer.
// Lesson from Electron's shell.openExternal guidance: what leaves the app is the app's decision. A link in the panel is
// clicked from a YouTube watch page, so without this the destination site learns exactly which video is being watched.
// Run: node --test extensions/nougentube-chrome/tests/links.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = name => readFileSync(new URL('../' + name, import.meta.url), 'utf8');
const FILES = ['content.js', 'options.js', 'options.html', 'providers.js', 'background.js'];

test('there are external links to protect (so this test cannot pass by finding none)', () => {
  const n = FILES.map(read).join('\n').match(/<a\b[^>]*target="_blank"[^>]*>/g) || [];
  assert.ok(n.length >= 4, 'expected at least 4 external anchors, found ' + n.length);
});

test('every link that opens a new tab is noopener, noreferrer and sends no referrer', () => {
  for (const f of FILES) {
    for (const tag of read(f).match(/<a\b[^>]*target="_blank"[^>]*>/g) || []) {
      assert.match(tag, /rel="noopener noreferrer"/, f + ': ' + tag.slice(0, 120));
      assert.match(tag, /referrerpolicy="no-referrer"/, f + ': ' + tag.slice(0, 120));
    }
  }
});

test('nothing opens a window from script without noopener', () => {
  for (const f of FILES) {
    for (const call of read(f).match(/window\.open\([^)]*\)/g) || []) assert.match(call, /noopener/, f + ': ' + call);
  }
});
