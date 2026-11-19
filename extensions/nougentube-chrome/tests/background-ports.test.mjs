// Tests for the request/response ports from the panel to the NouGenOpen bridge in background.js (map, recall, tube, web, shard).
// The lesson from Electron's MessagePorts tutorial: when the other end of a port closes, settle and clean up. Never keep
// working for a dead port, and never post to one.
// Run: node --test extensions/nougentube-chrome/tests/background-ports.test.mjs
// NG_BACKGROUND_JS points the suite at another copy of background.js. Timers inside the sandbox run 1000x faster,
// so a 110 s limit plays out in 110 ms.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const SRC = readFileSync(process.env.NG_BACKGROUND_JS ?? new URL('../background.js', import.meta.url), 'utf8');
const dir = new URL('../', import.meta.url);
const sleep = ms => new Promise(r => setTimeout(r, ms));
// Objects made inside the vm sandbox have another realm's prototypes; compare plain copies.
const plain = x => JSON.parse(JSON.stringify(x));
const T = { timeout: 5000 };   // a request that hangs fails in 5 s instead of stalling the run
const abortError = () => new DOMException('aborted', 'AbortError');
const fast = (fn, ms, ...a) => setTimeout(fn, ms / 1000, ...a);
const reply = (body, ok = true, status = 200) => ({ ok, status, json: async () => body, text: async () => JSON.stringify(body) });
// A request that never answers; it fails with an AbortError only if the caller aborts it.
const hangs = seen => (_u, { signal } = {}) => new Promise((_, reject) => { seen.signal = signal; signal?.addEventListener('abort', () => reject(abortError())); });

function load(fetchImpl) {
  let onConnect;
  const chrome = {
    runtime: { onMessage: { addListener() {} }, onConnect: { addListener: f => { onConnect = f; } }, onInstalled: { addListener() {} } },
    storage: { sync: { get: async () => ({}) }, local: { get: async () => ({}), set: async () => {} } },
    sidePanel: { setPanelBehavior: async () => {} },
  };
  const ctx = { chrome, fetch: fetchImpl, AbortController, AbortSignal, TextDecoder, setTimeout: fast, clearTimeout, console, URL };
  ctx.globalThis = ctx;
  ctx.importScripts = (...names) => { for (const n of names) vm.runInContext(readFileSync(new URL(n, dir), 'utf8'), ctx); };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return {
    open(name) {
      const posted = [], late = [], onMsg = [], onDisc = []; let dead = false;   // late: posts attempted after the port closed
      const port = {
        name,
        postMessage: m => { if (dead) { late.push(m); throw new Error('Attempting to use a disconnected port object'); } posted.push(m); },
        onMessage: { addListener: f => onMsg.push(f) }, onDisconnect: { addListener: f => onDisc.push(f) },
      };
      onConnect(port);
      return { posted, late, send: m => onMsg[0](m), close() { dead = true; onDisc.forEach(f => f()); } };
    },
  };
}

// An unhandled rejection is how a throw inside a port handler shows up.
function watchRejections() {
  const seen = [], on = e => seen.push(e);
  process.on('unhandledRejection', on);
  return { seen, stop: () => process.off('unhandledRejection', on) };
}

test('recall: a good answer is passed on', T, async () => {
  const p = load(async () => reply({ shards: [{ id: 1 }], failed: [] })).open('recall');
  await p.send({ body: { queries: ['x'] } });
  assert.deepEqual(plain(p.posted), [{ ok: true, shards: [{ id: 1 }], failed: [] }]);
});

test('tube: every field of a transcript comes through', T, async () => {
  const p = load(async () => reply({ ok: true, source: 'captions', lines: [{ t: 0, text: 'hi' }] })).open('tube');
  await p.send({ kind: 'transcript', body: { video_id: 'jNQXAC9IVRw' } });
  assert.equal(p.posted[0].ok, true);
  assert.equal(p.posted[0].source, 'captions');
  assert.deepEqual(plain(p.posted[0].lines), [{ t: 0, text: 'hi' }]);
});

test('shard: a bridge error is passed on with its own message', T, async () => {
  const p = load(async () => reply({ error: { message: 'content is over 600000 characters' } }, false, 413)).open('shard');
  await p.send({ doc: { title: 't' } });
  assert.equal(p.posted[0].ok, false);
  assert.match(p.posted[0].error, /over 600000/);
});

test('a bridge that is not running is said plainly', T, async () => {
  const p = load(async () => { throw new TypeError('fetch failed'); }).open('recall');
  await p.send({ body: {} });
  assert.match(p.posted[0].error, /not running/);
});

test('keepalive pings are ignored', T, async () => {
  let calls = 0;
  const p = load(async () => { calls++; return reply({}); }).open('web');
  await p.send({ ping: 1 });
  assert.equal(calls, 0);
  assert.deepEqual(p.posted, []);
});

test('closing the port mid-request aborts the request and posts nothing', T, async () => {
  const w = watchRejections(), seen = {};
  const p = load(hangs(seen)).open('tube');
  const run = p.send({ kind: 'transcript', body: { video_id: 'jNQXAC9IVRw' } });
  await sleep(20);
  p.close();
  await sleep(30);                    // well inside the 1.5 s limit: only the close can have aborted it
  const abortedByClose = seen.signal?.aborted;
  await run;
  w.stop();
  assert.equal(abortedByClose, true, 'the in-flight request should be aborted as soon as the panel goes away');
  assert.deepEqual(p.posted, []);
  assert.deepEqual(p.late, [], 'nothing may be posted to a closed port');
  assert.deepEqual(w.seen, [], 'a handler must not throw on a dead port');
});

test('an answer that arrives after the port closed is dropped without throwing', T, async () => {
  const w = watchRejections();
  const p = load(async () => { await sleep(40); return reply({ shards: [] }); }).open('recall');
  const run = p.send({ body: {} });
  await sleep(10);
  p.close();
  await run;
  await sleep(30);
  w.stop();
  assert.deepEqual(p.posted, []);
  assert.deepEqual(p.late, [], 'the late answer must not even be posted to the closed port');
  assert.deepEqual(w.seen, []);
});

test('web: a request that never answers ends with a clear timeout, on the scaled clock', T, async () => {
  const p = load(hangs({})).open('web');
  await p.send({ body: { queries: ['x'] } });
  assert.equal(p.posted[0].ok, false);
  assert.match(p.posted[0].error, /took too long/);
});

test('recall, map and shard: a bridge that accepts the request but never answers ends with a clear timeout', T, async () => {
  for (const [name, msg] of [['recall', { body: { queries: ['x'] } }], ['map', { prompts: ['x'] }], ['shard', { doc: { title: 'tttt', content: 'cccccccccc' } }]]) {
    const p = load(hangs({})).open(name);
    await p.send(msg);
    assert.equal(p.posted[0].ok, false, name);
    assert.match(p.posted[0].error, /took too long/, name);
  }
});
