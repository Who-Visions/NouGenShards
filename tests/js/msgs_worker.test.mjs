// Run: node --test tests/js/msgs_worker.test.mjs
// NouGen msgs Worker: native accept, pass-through fallback, queue delivery, mailbox DO.
import { test } from "node:test";
import assert from "node:assert/strict";

const { default: worker, LaneMailbox, laneKey, sha256Hex, VIA } = await import("../../workers/msgs/worker.js");

let sqliteMod = null;
try { sqliteMod = await import("node:sqlite"); } catch {}

// SQL storage fake backed by node:sqlite, shaped like the DO storage.sql cursor.
function fakeSql() {
  const db = new sqliteMod.DatabaseSync(":memory:");
  return {
    exec(q, ...args) {
      const st = db.prepare(q);
      const rows = /^\s*(SELECT|INSERT[\s\S]*RETURNING)/i.test(q) ? st.all(...args) : (st.run(...args), []);
      return { one: () => rows[0], toArray: () => rows };
    },
  };
}

function mailboxNs() {
  const boxes = new Map();
  return {
    boxes,
    idFromName: (n) => n,
    get: (id) => {
      if (!boxes.has(id)) boxes.set(id, new LaneMailbox({ storage: { sql: fakeSql() } }));
      const b = boxes.get(id);
      return { fetch: (u, init) => b.fetch(new Request(u, init)) };
    },
  };
}

const TOKEN = "test-token-not-real";
async function env(extra = {}) {
  const sent = [];
  return {
    MSGS_NATIVE_TOKEN_SHA256: await sha256Hex(TOKEN),
    MSGS_ORIGIN_URL: "https://origin.example.test",
    MSGS_ORIGIN_TOKEN: "origin-token-not-real",
    MAILBOX: mailboxNs(),
    FANOUT: { sent, send: async (m) => { sent.push(m); } },
    ...extra,
  };
}

function withFetch(fn) {
  const seen = [];
  const real = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const r = input instanceof Request ? input : new Request(input, init);
    seen.push({ url: r.url, via: r.headers.get("x-nougen-via"), auth: r.headers.get("authorization") });
    return fn(r);
  };
  return { seen, restore: () => { globalThis.fetch = real; } };
}

const post = (path, body, token = TOKEN) =>
  new Request("https://msgs.example.test" + path, {
    method: "POST",
    headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}) },
    body: JSON.stringify(body),
  });

test("laneKey resolves lanes from the request and rejects junk", () => {
  assert.equal(laneKey("@Phoebus"), "phoebus");
  assert.equal(laneKey(undefined), "all");
  assert.equal(laneKey("bad lane!"), null);
});

test("native POST /msg lands in the lane mailbox and the queue, honest receipt", { skip: !sqliteMod }, async () => {
  const e = await env();
  const f = withFetch(() => new Response("origin"));
  try {
    const r1 = await worker.fetch(post("/msg", { target: "@lane-a", message: "one" }), e);
    const r2 = await worker.fetch(post("/msg", { target: "@lane-a", message: "two" }), e);
    assert.equal(r1.status, 202);
    const b1 = await r1.json(), b2 = await r2.json();
    assert.equal(b1.delivered, false);
    assert.equal(b1.status, "unverified");
    assert.equal(b1.via, VIA);
    assert.ok(b2.seq > b1.seq, "per-lane order is strictly increasing");
    assert.equal(e.FANOUT.sent.length, 2);
    assert.equal(f.seen.length, 0, "native path never touches the origin inline");
  } finally { f.restore(); }
});

test("unknown token on /msg passes through to the origin (tunnel fallback)", async () => {
  const e = await env();
  const f = withFetch(() => new Response('{"delivered":true}', { status: 200 }));
  try {
    const r = await worker.fetch(post("/msg", { target: "@x" }, "someone-else"), e);
    assert.equal(r.status, 200);
    assert.equal(f.seen.length, 1);
    assert.equal(e.FANOUT.sent.length, 0);
  } finally { f.restore(); }
});

test("binding failure falls back to the origin instead of dropping the message", async () => {
  const e = await env({ MAILBOX: { idFromName: (n) => n, get: () => ({ fetch: async () => { throw new Error("do down"); } }) } });
  const f = withFetch(() => new Response("origin ok"));
  try {
    const r = await worker.fetch(post("/msg", { target: "@x", message: "hi" }), e);
    assert.equal(await r.text(), "origin ok");
    assert.equal(f.seen.length, 1);
  } finally { f.restore(); }
});

test("non-native paths (/wire, /health, GET /msg) pass through", async () => {
  const e = await env();
  const f = withFetch(() => new Response("origin"));
  try {
    for (const p of ["/wire", "/health", "/status", "/msg"]) await worker.fetch(new Request("https://msgs.example.test" + p), e);
    assert.equal(f.seen.length, 4);
  } finally { f.restore(); }
});

test("loop guard: our own delivery header always reaches the origin", async () => {
  const e = await env();
  const f = withFetch(() => new Response("origin"));
  try {
    const req = new Request("https://msgs.example.test/msg", { method: "POST", headers: { authorization: "Bearer " + TOKEN, "x-nougen-via": VIA }, body: "{}" });
    await worker.fetch(req, e);
    assert.equal(f.seen.length, 1);
    assert.equal(e.FANOUT.sent.length, 0);
  } finally { f.restore(); }
});

test("mailbox read/ack requires native auth and keeps order", { skip: !sqliteMod }, async () => {
  const e = await env();
  for (const m of ["a", "b", "c"]) await worker.fetch(post("/msg", { target: "@lane-b", message: m }), e);
  const unauth = await worker.fetch(new Request("https://msgs.example.test/mailbox/lane-b"), e);
  assert.equal(unauth.status, 401);
  const get = (q = "") => worker.fetch(new Request("https://msgs.example.test/mailbox/lane-b" + q, { headers: { authorization: "Bearer " + TOKEN } }), e);
  const all = (await (await get()).json()).messages;
  assert.deepEqual(all.map((m) => m.payload.message), ["a", "b", "c"]);
  const after = (await (await get("?after=" + all[0].seq)).json()).messages;
  assert.equal(after.length, 2);
  const ack = await worker.fetch(post("/mailbox/lane-b/ack", { upto: all[1].seq }), e);
  assert.equal(ack.status, 200);
  const again = (await (await get()).json()).messages;
  assert.deepEqual(again.map((m) => m.acked), [true, true, false]);
});

function qmsg(body, attempts = 1) {
  const m = { body, attempts, acked: false, retried: null, ack() { this.acked = true; }, retry(o) { this.retried = o; } };
  return m;
}

test("queue consumer delivers to the origin with its token and marks delivered", { skip: !sqliteMod }, async () => {
  const e = await env();
  const f0 = withFetch(() => new Response("x"));
  const accepted = await (await worker.fetch(post("/msg", { target: "@lane-c", message: "q" }), e)).json();
  f0.restore();
  const f = withFetch(() => new Response('{"delivered":true}', { status: 200 }));
  try {
    const m = qmsg(e.FANOUT.sent[0]);
    await worker.queue({ messages: [m] }, e);
    assert.equal(m.acked, true);
    assert.equal(f.seen[0].url, "https://origin.example.test/msg");
    assert.equal(f.seen[0].via, VIA);
    assert.equal(f.seen[0].auth, "Bearer origin-token-not-real");
    const list = await e.MAILBOX.get("lane-c").fetch("https://mailbox/list?after=0");
    const [row] = (await list.json()).messages;
    assert.equal(row.seq, accepted.seq);
    assert.equal(row.delivered, true);
  } finally { f.restore(); }
});

test("queue consumer retries with backoff when the origin is down", async () => {
  const e = await env();
  const f = withFetch(() => new Response("bad gateway", { status: 530 }));
  try {
    const m = qmsg({ lane: "lane-d", seq: 1, payload: {} }, 3);
    await worker.queue({ messages: [m] }, e);
    assert.equal(m.acked, false);
    assert.equal(m.retried.delaySeconds, 20);
  } finally { f.restore(); }
});
