// Tests for the background worker's side of long jobs, from Electron's BrowserWindow doc:
//  - backgroundThrottling: a hidden tab's timers slow down, so a worker that lives on the page's pings can die mid-job.
//    While a job holds, the worker keeps itself alive from its own side.
//  - setProgressBar: a long job shows its progress on the toolbar button, from any tab, and clears it when the job ends.
//  - focus/show: clicking the toolbar button brings the panel forward.
// Run: node --test extensions/nougentube-chrome/tests/background-badge.test.mjs
// Timers inside the sandbox run 1000x faster, so a 20 s self-ping plays out every 20 ms.
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const SRC = readFileSync(new URL('../background.js', import.meta.url), 'utf8');
const dir = new URL('../', import.meta.url);
const T = { timeout: 5000 };
const live = [];   // every interval a test's worker starts, cleared after each test so none can keep node alive
afterEach(() => { live.splice(0).forEach(clearInterval); });
const sleep = ms => new Promise(r => setTimeout(r, ms));

function load({ withAction = true } = {}) {
  let onConnect, clicked = null;
  const w = { badge: [], color: [], sent: [], pings: 0, optionsOpened: 0, sendFails: false };
  const chrome = {
    runtime: {
      onMessage: { addListener() {} }, onConnect: { addListener: f => { onConnect = f; } }, onInstalled: { addListener() {} },
      getPlatformInfo: async () => { w.pings++; return {}; }, openOptionsPage: () => { w.optionsOpened++; },
    },
    storage: { sync: { get: async () => ({}) }, local: { get: async () => ({}), set: async () => {} } },
    sidePanel: { setPanelBehavior: async () => {} },
    power: { requestKeepAwake() {}, releaseKeepAwake() {} },
    tabs: { sendMessage: (id, msg) => { w.sent.push([id, msg]); return w.sendFails ? Promise.reject(new Error('Receiving end does not exist')) : Promise.resolve({ ok: true }); } },
  };
  if (withAction) chrome.action = { setBadgeText: ({ text }) => w.badge.push(text), setBadgeBackgroundColor: ({ color }) => w.color.push(color), onClicked: { addListener: f => { clicked = f; } } };
  const ctx = { chrome, fetch: async () => ({ ok: true, json: async () => ({}) }), AbortController, AbortSignal, TextDecoder, console, URL,
    setTimeout, clearTimeout, setInterval: (fn, ms) => { const t = setInterval(fn, ms / 1000); live.push(t); return t; }, clearInterval };
  ctx.globalThis = ctx;
  ctx.importScripts = (...names) => { for (const n of names) vm.runInContext(readFileSync(new URL(n, dir), 'utf8'), ctx); };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return {
    w, click: tab => clicked && clicked(tab), hasClick: () => !!clicked,
    open(name = 'awake') {
      const onMsg = [], onDisc = [];
      const port = { name, postMessage() {}, onMessage: { addListener: f => onMsg.push(f) }, onDisconnect: { addListener: f => onDisc.push(f) } };
      onConnect(port);
      return { send: m => onMsg.forEach(f => f(m)), close: () => onDisc.forEach(f => f()) };
    },
  };
}

test('while a hold is open the worker pings itself, so a throttled background tab cannot let it die', T, async () => {
  const k = load(), p = k.open();
  p.send({ start: 'prevent-app-suspension' });
  await sleep(90);
  assert.ok(k.w.pings >= 2, 'expected repeated self-pings, got ' + k.w.pings);
  p.close();
});

test('the self-ping stops when the last hold ends, and never starts without one', T, async () => {
  const idle = load();
  await sleep(60);
  assert.equal(idle.w.pings, 0);
  const k = load(), a = k.open(), b = k.open();
  a.send({ start: 'prevent-app-suspension' }); b.send({ start: 'prevent-app-suspension' });
  a.close(); await sleep(60);
  const whileHeld = k.w.pings;
  assert.ok(whileHeld >= 1, 'one hold left, still pinging');
  b.close(); await sleep(20);
  const atEnd = k.w.pings; await sleep(70);
  assert.equal(k.w.pings, atEnd, 'no pings once nothing holds');
});

test('progress sent on the port becomes the toolbar badge', T, () => {
  const k = load(), p = k.open();
  p.send({ start: 'prevent-app-suspension' });
  p.send({ progress: '3/12' });
  assert.equal(k.w.badge.at(-1), '3/12');
  assert.ok(k.w.color.length >= 1, 'the badge gets the Mono Violet colour');
});

test('a badge only has room for four characters', T, () => {
  const k = load(), p = k.open();
  p.send({ progress: '100/200' });
  assert.equal(k.w.badge.at(-1), '100/');
});

test('the badge clears when the panel goes away, however the job ended', T, () => {
  const k = load(), p = k.open();
  p.send({ progress: '5/9' });
  p.close();
  assert.equal(k.w.badge.at(-1), '');
});

test('with two jobs open the badge shows the latest and clears only when the last one ends', T, () => {
  const k = load(), a = k.open(), b = k.open();
  a.send({ progress: '1/4' }); b.send({ progress: '2/2' });
  a.close();
  assert.notEqual(k.w.badge.at(-1), '', 'one job is still running');
  b.close();
  assert.equal(k.w.badge.at(-1), '');
});

test('clicking the toolbar button asks that tab to bring the panel forward', T, () => {
  const k = load();
  k.click({ id: 7 });
  assert.deepEqual(JSON.parse(JSON.stringify(k.w.sent)), [[7, { type: 'focus-panel' }]]);
});

test('on a tab with no panel the toolbar button opens settings instead of doing nothing', T, async () => {
  const k = load(); k.w.sendFails = true;
  k.click({ id: 9 });
  await sleep(20);
  assert.equal(k.w.optionsOpened, 1);
});

test('a browser without the action API still loads and the port does not throw', T, () => {
  const k = load({ withAction: false }), p = k.open();
  assert.doesNotThrow(() => { p.send({ progress: '1/2' }); p.close(); });
});
