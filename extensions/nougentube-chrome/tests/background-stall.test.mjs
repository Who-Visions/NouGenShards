// Regression tests for the stream deadlines in background.js.
// Run: node --test extensions/nougentube-chrome/tests/background-stall.test.mjs
// NG_BACKGROUND_JS points the suite at another copy of background.js (used to prove the tests fail on old code).
// Timers inside the sandbox run 1000x faster, so the real 200s/90s limits play out in 200ms/90ms.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const SRC = readFileSync(process.env.NG_BACKGROUND_JS ?? new URL('../background.js', import.meta.url), 'utf8');
const dir = new URL('../', import.meta.url);
const enc = new TextEncoder();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const line = (text, done = false) => enc.encode(JSON.stringify({ model: 'm', message: { content: text }, done, ...(done ? { eval_count: 3 } : {}) }) + '\n');
const abortError = () => new DOMException('aborted', 'AbortError');
const fast = (fn, ms, ...a) => setTimeout(fn, ms / 1000, ...a);

function load(fetchImpl) {
  let onConnect;
  const chrome = {
    runtime: { onMessage: { addListener() {} }, onConnect: { addListener: f => { onConnect = f; } }, onInstalled: { addListener() {} } },
    storage: { sync: { get: async () => ({ model: 'test-local', host: 'http://ollama.test' }) }, local: { get: async () => ({}), set: async () => {} } },
    sidePanel: { setPanelBehavior: async () => {} },
  };
  const ctx = { chrome, fetch: fetchImpl, AbortController, AbortSignal, TextDecoder, setTimeout: fast, clearTimeout, console, URL };
  ctx.globalThis = ctx;
  ctx.importScripts = (...names) => { for (const n of names) vm.runInContext(readFileSync(new URL(n, dir), 'utf8'), ctx); };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  const posted = [], listeners = [];
  const port = { name: 'chat', postMessage: m => posted.push(m), onMessage: { addListener: f => listeners.push(f) }, onDisconnect: { addListener() {} } };
  onConnect(port);
  return { posted, send: () => listeners[0]({ messages: [{ role: 'user', content: 'hi' }] }) };
}

async function until(posted, pred, ms = 3000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (posted.some(pred)) return true; await sleep(10); }
  return false;
}

// A body whose reader hands out `chunks` (Uint8Array or ms delay numbers) and then never ends until aborted.
function streamBody(signal, chunks, { end = false } = {}) {
  const queue = [...chunks];
  return { getReader: () => ({ read: async () => {
    while (typeof queue[0] === 'number') await sleep(queue.shift());
    if (queue.length) return { done: false, value: queue.shift() };
    if (end) return { done: true };
    return new Promise((_, reject) => { if (signal.aborted) reject(abortError()); signal.addEventListener('abort', () => reject(abortError())); });
  } }) };
}

test('text starts, then the body stalls: the route is aborted as gone quiet', async () => {
  const fetchImpl = (_u, { signal }) => Promise.resolve({ ok: true, status: 200, body: streamBody(signal, [line('Hello')]) });
  const { posted, send } = load(fetchImpl);
  send();
  assert.ok(await until(posted, m => typeof m.error === 'string' && /went quiet/.test(m.error)), 'expected a mid-answer stall error, got ' + JSON.stringify(posted));
  assert.ok(posted.some(m => m.delta === 'Hello'));
});

test('nothing ever arrives: aborted with the first-answer message', async () => {
  const fetchImpl = (_u, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(abortError())));
  const { posted, send } = load(fetchImpl);
  send();
  assert.ok(await until(posted, m => typeof m.error === 'string' && /no answer within/.test(m.error)), 'got ' + JSON.stringify(posted));
});

test('a slow but steady stream longer than the idle window still completes', async () => {
  const chunks = [];
  for (const t of ['a', 'b', 'c', 'd', 'e', 'f']) chunks.push(50, line(t));
  chunks.push(50, line('', true));
  const fetchImpl = (_u, { signal }) => Promise.resolve({ ok: true, status: 200, body: streamBody(signal, chunks, { end: true }) });
  const { posted, send } = load(fetchImpl);
  send();
  assert.ok(await until(posted, m => m.done === true), 'expected completion, got ' + JSON.stringify(posted));
  assert.equal(posted.filter(m => m.delta).map(m => m.delta).join(''), 'abcdef');
  assert.ok(!posted.some(m => m.error));
});
