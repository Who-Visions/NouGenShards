// Tests for the "awake" port in background.js: a long job in the panel keeps the computer awake, and the hold ends
// the moment the panel goes away (port closed, tab navigated, crash), however the job ended.
// Run: node --test extensions/nougentube-chrome/tests/background-awake.test.mjs
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const SRC = readFileSync(new URL('../background.js', import.meta.url), 'utf8');
const dir = new URL('../', import.meta.url);
const T = { timeout: 5000 };
const live = [];   // every interval a test's worker starts, cleared after each test so none can keep node alive
afterEach(() => { live.splice(0).forEach(clearInterval); });

function load({ withPower = true } = {}) {
  let onConnect; const log = [];
  const chrome = {
    runtime: { onMessage: { addListener() {} }, onConnect: { addListener: f => { onConnect = f; } }, onInstalled: { addListener() {} } },
    storage: { sync: { get: async () => ({}) }, local: { get: async () => ({}), set: async () => {} } },
    sidePanel: { setPanelBehavior: async () => {} },
  };
  if (withPower) chrome.power = { requestKeepAwake: l => log.push('request:' + l), releaseKeepAwake: () => log.push('release') };
  const ctx = { chrome, fetch: async () => ({ ok: true, json: async () => ({}) }), AbortController, AbortSignal, TextDecoder, setTimeout, clearTimeout, console, URL,
    setInterval: (fn, ms) => { const t = setInterval(fn, ms / 1000); live.push(t); return t; }, clearInterval };
  ctx.globalThis = ctx;
  ctx.importScripts = (...names) => { for (const n of names) vm.runInContext(readFileSync(new URL(n, dir), 'utf8'), ctx); };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return {
    log,
    open(name) {
      const onMsg = [], onDisc = [];
      const port = { name, postMessage() {}, onMessage: { addListener: f => onMsg.push(f) }, onDisconnect: { addListener: f => onDisc.push(f) } };
      onConnect(port);
      return { send: m => onMsg.forEach(f => f(m)), close: () => onDisc.forEach(f => f()) };
    },
  };
}

test('a worker that starts always lets go of any hold an earlier one left behind', T, () => {
  const { log } = load();
  assert.deepEqual(log, ['release']);
});

test('a panel that asks to stay awake keeps the system awake, and closing the panel releases it', T, () => {
  const w = load(), p = w.open('awake');
  p.send({ start: 'prevent-app-suspension' });
  assert.equal(w.log.at(-1), 'request:system');
  p.close();
  assert.equal(w.log.at(-1), 'release');
});

test('two panels overlap: the hold lasts until the last one closes', T, () => {
  const w = load(), a = w.open('awake'), b = w.open('awake');
  a.send({ start: 'prevent-app-suspension' }); b.send({ start: 'prevent-app-suspension' });
  a.close();
  assert.notEqual(w.log.at(-1), 'release');
  b.close();
  assert.equal(w.log.at(-1), 'release');
});

test('a panel that opens the port and never asks, or only pings, holds nothing', T, () => {
  const w = load(), p = w.open('awake');
  p.send({ ping: 1 });
  assert.deepEqual(w.log, ['release']);          // only the start-up release
  p.close();
  assert.deepEqual(w.log, ['release']);
});

test('asking twice on one port does not stack holds: one close ends it', T, () => {
  const w = load(), p = w.open('awake');
  p.send({ start: 'prevent-app-suspension' }); p.send({ start: 'prevent-app-suspension' });
  p.close();
  assert.equal(w.log.at(-1), 'release');
});

test('an unknown request type holds nothing', T, () => {
  const w = load(), p = w.open('awake');
  p.send({ start: 'prevent-everything' });
  assert.deepEqual(w.log, ['release']);
});

test('a browser without the power API still loads and the port does not throw', T, () => {
  const w = load({ withPower: false }), p = w.open('awake');
  assert.doesNotThrow(() => { p.send({ start: 'prevent-app-suspension' }); p.close(); });
});
