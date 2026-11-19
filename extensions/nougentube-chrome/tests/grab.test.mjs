// Regression tests for content.js's string-aware grab() JSON extractor.
// Braces inside JSON strings (e.g. video titles containing "}" or escaped quotes)
// must not prematurely terminate the object scan.
// Run: node --test extensions/nougentube-chrome/tests/grab.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../content.js', import.meta.url), 'utf8');
const match = src.match(/const grab = k => \{[\s\S]*?\n\s*return null; \};/);
assert.ok(match, 'could not locate grab() in content.js');

const makeGrab = html => new Function('html', `${match[0]}\nreturn grab;`)(html);

test('ignores closing and opening braces inside JSON string values', () => {
  const payload = { videoDetails: { title: 'C++ } struct { init } demo' }, ok: true };
  const html = `<script>var ytInitialPlayerResponse = ${JSON.stringify(payload)};</script>`;
  assert.deepEqual(makeGrab(html)('ytInitialPlayerResponse'), payload);
});

test('handles escaped quotes around braces inside strings', () => {
  const payload = { title: 'Quote \\"}\\" and \\"{\\" inside', count: 3 };
  const html = `var ytInitialPlayerResponse = ${JSON.stringify(payload)}; var other = {};`;
  assert.deepEqual(makeGrab(html)('ytInitialPlayerResponse'), payload);
});

test('handles escaped backslash immediately before closing quote', () => {
  const payload = { path: 'C:\\Users\\demo\\', nested: { a: 1 } };
  const html = `var ytInitialPlayerResponse = ${JSON.stringify(payload)};`;
  assert.deepEqual(makeGrab(html)('ytInitialPlayerResponse'), payload);
});

test('extracts independent top-level objects from the same HTML page', () => {
  const pr = { title: 'First } video' };
  const data = { contents: [{ text: 'Second { data }' }] };
  const html = `var ytInitialPlayerResponse = ${JSON.stringify(pr)};\nvar ytInitialData = ${JSON.stringify(data)};`;
  const grab = makeGrab(html);
  assert.deepEqual(grab('ytInitialPlayerResponse'), pr);
  assert.deepEqual(grab('ytInitialData'), data);
});

test('returns null on missing key, truncated object, or malformed JSON', () => {
  assert.equal(makeGrab('<html>no player data</html>')('ytInitialPlayerResponse'), null);
  assert.equal(makeGrab('var ytInitialPlayerResponse = {"a": 1')('ytInitialPlayerResponse'), null);
  assert.equal(makeGrab('var ytInitialPlayerResponse = {bad json};')('ytInitialPlayerResponse'), null);
});
