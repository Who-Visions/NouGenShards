// A chat answer in flight keeps the background worker alive from its own side (self-ping), so a slow local model
// is not cut off when the page's pings are throttled; the self-ping stops when the answer ends.
// Run: node --test extensions/nougentube-chrome/tests/background-inflight.test.mjs
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const SRC = readFileSync(new URL('../background.js', import.meta.url), 'utf8');
const dir = new URL('../', import.meta.url);
const live = [];
afterEach(() => { live.splice(0).forEach(clearInterval); });

function load(fetchImpl) {
  let onConnect; const pings = { n: 0 };
  const chrome = {
    runtime: { onMessage: { addListener() {} }, onConnect: { addListener: f => { onConnect = f; } }, onInstalled: { addListener() {} }, getPlatformInfo: () => { pings.n++; } },
    storage: { sync: { get: async () => ({ model: 'auto' }) }, local: { get: async () => ({}), set: async () => {} } },
    sidePanel: { setPanelBehavior: async () => {} },
  };
  const ctx = { chrome, fetch: fetchImpl, AbortController, AbortSignal, TextDecoder, setTimeout, clearTimeout, console, URL,
    setInterval: (fn, ms) => { const t = setInterval(fn, 5); live.push(t); return t; }, clearInterval };
  ctx.globalThis = ctx;
  ctx.importScripts = (...names) => { for (const n of names) vm.runInContext(readFileSync(new URL(n, dir), 'utf8'), ctx); };
  vm.createContext(ctx); vm.runInContext(SRC, ctx);
  return { pings, open(name) {
    const onMsg = [], out = [];
    const port = { name, postMessage: m => out.push(m), onMessage: { addListener: f => onMsg.push(f) }, onDisconnect: { addListener() {} } };
    onConnect(port);
    return { out, send: m => onMsg.forEach(f => f(m)) };
  } };
}
const wait = ms => new Promise(r => setTimeout(r, ms));

test('the worker self-pings while a chat answer is pending, and stops once it settles', { timeout: 5000 }, async () => {
  let release; const gate = new Promise(r => { release = r; });
  const w = load(async () => { await gate; throw new Error('no route'); });
  const p = w.open('chat');
  p.send({ messages: [{ role: 'user', content: 'hi' }] });
  await wait(60);
  assert.ok(w.pings.n > 0, 'self-ping ran while the answer was pending');
  release();
  await wait(60);
  const n = w.pings.n; await wait(40);
  assert.equal(w.pings.n, n, 'self-ping stopped after the answer settled');
  assert.ok(p.out.some(m => m.error), 'the panel got an answer (an error here)');
});
