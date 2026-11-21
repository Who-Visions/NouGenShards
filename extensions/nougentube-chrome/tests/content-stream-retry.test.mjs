// stream() in content.js reconnects once when Chrome stops the background worker mid-answer.
// A bound stream (the open video's summary or chat) resets its own view and asks again. An unbound job (batch, morph)
// must never touch the open video's hooks, and must not retry once it has written text it has no way to take back.
// Run: node --test extensions/nougentube-chrome/tests/content-stream-retry.test.mjs
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const SRC = readFileSync(new URL('../content.js', import.meta.url), 'utf8');
const start = SRC.indexOf('  function stream(messages, onDelta, onDone, bound) {');
const stop = SRC.indexOf('\n  }\n', start);
assert.ok(start > 0 && stop > start, 'stream() not found in content.js');
const FN = SRC.slice(start, stop + 4);

const timers = [];
afterEach(() => { timers.splice(0).forEach(clearInterval); });

function harness() {
  const ports = [];
  const calls = { stage: [], reset: 0 };
  const S = { vid: 'v1', gen: 1, port: null, onStage: s => calls.stage.push(s), onReset: () => { calls.reset++; } };
  const chrome = { runtime: { connect: () => {
    const p = { sent: [], msg: [], disc: [],
      postMessage(m) { this.sent.push(m); }, disconnect() {},
      onMessage: { addListener: f => p.msg.push(f) }, onDisconnect: { addListener: f => p.disc.push(f) } };
    ports.push(p); return p;
  } } };
  const ctx = { S, chrome, setInterval: (f, t) => { const h = setInterval(f, t); timers.push(h); return h; }, clearInterval };
  vm.runInNewContext(FN + '\nthis.stream = stream;', ctx);
  return { stream: ctx.stream, ports, calls, S };
}
const say = (p, m) => p.msg.forEach(f => f(m));
const drop = p => p.disc.forEach(f => f());

test('bound stream: one silent retry that resets its own view, then the answer lands', () => {
  const h = harness(); let text = '', done = null;
  h.stream([{ role: 'user', content: 'q' }], d => { text += d; }, e => { done = e; }, true);
  say(h.ports[0], { delta: 'half' }); drop(h.ports[0]);
  assert.equal(h.ports.length, 2); assert.equal(h.calls.reset, 1); assert.equal(done, null);
  say(h.ports[1], { delta: 'full' }); say(h.ports[1], { done: 1 });
  assert.equal(done, '');
});

test('bound stream: a second stop ends with the message', () => {
  const h = harness(); let done = null;
  h.stream([], () => {}, e => { done = e; }, true);
  drop(h.ports[0]); drop(h.ports[1]);
  assert.match(done, /stopped twice/); assert.equal(h.ports.length, 2);
});

test('unbound job before any text: retries without touching the open video', () => {
  const h = harness(); let done = null;
  h.stream([], () => {}, e => { done = e; }, false);
  drop(h.ports[0]);
  assert.equal(h.ports.length, 2); assert.equal(h.calls.reset, 0); assert.deepEqual(h.calls.stage, []);
  say(h.ports[1], { done: 1 }); assert.equal(done, '');
});

test('unbound job after text: no retry, no duplicated answer, open video untouched', () => {
  const h = harness(); let text = '', done = null;
  h.stream([], d => { text += d; }, e => { done = e; }, false);
  say(h.ports[0], { delta: 'partial' }); drop(h.ports[0]);
  assert.equal(h.ports.length, 1); assert.equal(h.calls.reset, 0);
  assert.equal(text, 'partial'); assert.match(done, /stopped/);
});
