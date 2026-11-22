// Tests for batch-core.js: reading video ids and building what a Batch item saves to the vault.
// Run: node --test extensions/nougentube-chrome/tests/batch-core.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const core = createRequire(import.meta.url)('../batch-core.js');
const VID = 'jNQXAC9IVRw';

test('ids are read from every common link form and from a bare id', () => {
  for (const s of [VID, 'https://youtu.be/' + VID + '?si=x', 'https://www.youtube.com/watch?v=' + VID + '&t=30s', 'https://www.youtube.com/shorts/' + VID, 'https://www.youtube.com/embed/' + VID, 'https://www.youtube.com/live/' + VID]) {
    assert.equal(core.idOf(s), VID, s);
  }
});

test('anything that is not a video link or id gives null', () => {
  for (const s of ['', '   ', 'hello', 'https://example.com/watch?v=short', 'https://www.youtube.com/', null, undefined]) assert.equal(core.idOf(s), null, String(s));
});

test('an id that could carry markup or attributes is never accepted', () => {
  assert.equal(core.isVideoId(VID), true);
  for (const s of ['"><img src=x onerror=alert(1)>', "jNQXAC9IVR'", 'jNQXAC9IVRw ', 'jNQXAC9IVRwx', 'jNQXAC9IVR', 'a b c d e f g', '../../etc/pa', '<b>NQXAC9IVR', '']) assert.equal(core.isVideoId(s), false, JSON.stringify(s));
});

test('a saved item carries its transcript when it is still in memory', () => {
  const r = core.shardContent({ title: 'T', text: 'Summary body' }, 'https://www.youtube.com/watch?v=' + VID, '(0:00) hello');
  assert.equal(r.summaryOnly, false);
  assert.equal(r.content, 'T - YouTube\nhttps://www.youtube.com/watch?v=' + VID + '\n\nSummary body\n\n---\n\nTranscript:\n(0:00) hello');
});

test('after a reload the transcript is gone, and the item says it saves the summary only', () => {
  for (const gone of ['', null, undefined]) {
    const r = core.shardContent({ title: 'T', text: 'Summary body' }, 'u', gone);
    assert.equal(r.summaryOnly, true);
    assert.equal(r.content, 'T - YouTube\nu\n\nSummary body');
  }
});
