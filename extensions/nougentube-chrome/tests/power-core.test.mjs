// Tests for power-core.js: a powerSaveBlocker for the extension.
// Model taken from Electron's powerSaveBlocker: start(type) returns an id, stop(id) says whether it stopped, isStarted(id)
// says whether it still holds, several blockers can overlap, and when they disagree the stronger type wins
// (prevent-display-sleep over prevent-app-suspension) until it stops, then the weaker one applies again.
// chrome.power has no ids and one global request, so this module keeps the books and tells it only what changes.
// Run: node --test extensions/nougentube-chrome/tests/power-core.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { createPowerBlocker } = createRequire(import.meta.url)('../power-core.js');
const APP = 'prevent-app-suspension', DISPLAY = 'prevent-display-sleep';

// A stand-in for chrome.power that writes down what the OS was asked.
const fakePower = () => { const log = []; return { log, requestKeepAwake: l => log.push('request:' + l), releaseKeepAwake: () => log.push('release') }; };

test('start gives each blocker its own id, isStarted follows it, stop says whether it stopped', () => {
  const b = createPowerBlocker(fakePower());
  const a = b.start(APP), c = b.start(APP);
  assert.notEqual(a, c);
  assert.equal(b.isStarted(a), true);
  assert.equal(b.stop(a), true);
  assert.equal(b.isStarted(a), false);
  assert.equal(b.stop(a), false);            // already stopped
  assert.equal(b.isStarted(c), true);        // the other one is untouched
});

test('the first blocker keeps the system awake, a second one adds no new request, the last stop releases', () => {
  const p = fakePower(), b = createPowerBlocker(p);
  const a = b.start(APP), c = b.start(APP);
  assert.deepEqual(p.log, ['request:system']);
  b.stop(a);
  assert.deepEqual(p.log, ['request:system']);            // c still holds
  b.stop(c);
  assert.deepEqual(p.log, ['request:system', 'release']);
});

test('display sleep outranks app suspension until it stops, then the weaker hold applies again', () => {
  const p = fakePower(), b = createPowerBlocker(p);
  const weak = b.start(APP), strong = b.start(DISPLAY);
  assert.deepEqual(p.log, ['request:system', 'request:display']);
  b.stop(strong);
  assert.deepEqual(p.log, ['request:system', 'request:display', 'request:system']);
  b.stop(weak);
  assert.equal(p.log.at(-1), 'release');
});

test('stopping an unknown id is false and does not touch the system', () => {
  const p = fakePower(), b = createPowerBlocker(p);
  assert.equal(b.stop(999), false);
  assert.deepEqual(p.log, []);
});

test('an unknown type is refused before anything is held', () => {
  const p = fakePower(), b = createPowerBlocker(p);
  assert.throws(() => b.start('prevent-everything'), /unknown/i);
  assert.deepEqual(p.log, []);
});

test('a missing or refusing power API never breaks the caller', () => {
  const broken = createPowerBlocker({ requestKeepAwake() { throw new Error('no permission'); }, releaseKeepAwake() { throw new Error('no permission'); } });
  const id = broken.start(APP);
  assert.equal(broken.isStarted(id), true);
  assert.equal(broken.stop(id), true);
  const none = createPowerBlocker(undefined);
  assert.equal(none.stop(none.start(APP)), true);
});

test('reset lets go of a hold left behind by a worker that died, and forgets every holder', () => {
  const p = fakePower(), b = createPowerBlocker(p);
  const id = b.start(APP);
  p.log.length = 0;
  b.reset();
  assert.deepEqual(p.log, ['release']);
  assert.equal(b.isStarted(id), false);
});
