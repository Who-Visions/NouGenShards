// Run: node --test tests/js/relay_worker.test.mjs
// NouGen Relay Worker + Durable Object, with the Workers runtime pieces faked in-process.
import { test } from "node:test";
import assert from "node:assert/strict";

// --- runtime fakes -----------------------------------------------------------
class FakeSocket {
  constructor() { this.sent = []; this.closed = null; this.peer = null; this.att = null; }
  send(m) { if (this.closed) throw new Error("closed"); this.sent.push(m); }
  close(code, reason) { this.closed = { code, reason }; }
  serializeAttachment(a) { this.att = a; }
  deserializeAttachment() { return this.att; }
}
globalThis.WebSocketPair = class { constructor() { this[0] = new FakeSocket(); this[1] = new FakeSocket(); } };
const RealResponse = globalThis.Response;
globalThis.Response = class extends RealResponse {
  constructor(body, init = {}) {
    if (init.status === 101) { super(null, { status: 200 }); this.upgraded = true; this.webSocket = init.webSocket; return; }
    super(body, init);
  }
};

const { default: worker, RelaySession, route, relayAuthRecord, sha256Hex, validId } = await import("../../workers/relay/worker.js");

function fakeState() {
  const socks = [];
  return {
    socks,
    acceptWebSocket(ws, tags) { ws.tags = tags; socks.push(ws); },
    getWebSockets(tag) { return socks.filter((s) => !s.closed && (!tag || (s.tags || []).includes(tag))); },
    setWebSocketAutoResponse() {},
  };
}

function fakeEnv(seed = {}) {
  const kv = new Map(Object.entries(seed));
  const objects = new Map();
  const env = {
    RELAY_AUTH: { get: async (k) => kv.get(k) ?? null, put: async (k, v) => kv.set(k, v) },
    RELAY_HOST_SUFFIX: ".nougenai.com",
    RELAY_REQUEST_TIMEOUT_MS: "300",
    RELAY: {
      idFromName: (n) => n,
      get: (n) => {
        if (!objects.has(n)) objects.set(n, new RelaySession(fakeState(), env));
        return objects.get(n);
      },
    },
  };
  return { env, objects };
}

const TOKEN = "join-token-abcdefghijklmnop";
async function seeded() { const r = await relayAuthRecord({ id: "Alice", token: TOKEN }); return fakeEnv({ [r.key]: r.value }); }
const connectReq = (token = TOKEN, id = "alice") => new Request(`https://relay.example/_relay/connect?id=${id}`, {
  headers: { upgrade: "websocket", authorization: `Bearer ${token}` } });

// Node side: answer every req frame the DO sends with a canned response.
function autoAnswer(sock, fn) {
  const orig = sock.send.bind(sock);
  sock.send = (m) => {
    orig(m);
    const f = JSON.parse(m);
    if (f.t === "req") queueMicrotask(() => sock.do.webSocketMessage(sock, JSON.stringify({ t: "res", rid: f.rid, ...fn(f) })));
  };
}

async function connect(env, objects, id = "alice") {
  const r = await worker.fetch(connectReq(TOKEN, id), env);
  assert.equal(r.upgraded, true);
  const dobj = objects.get(id);
  const server = dobj.state.socks.at(-1);
  server.do = dobj;
  return { r, dobj, server };
}

// --- tests -------------------------------------------------------------------
test("routes host and preview-path forms; rejects junk ids", () => {
  const env = { RELAY_HOST_SUFFIX: ".nougenai.com" };
  assert.deepEqual(route(new URL("https://alice.nougenai.com/mcp?x=1"), env), { id: "alice", path: "/mcp?x=1" });
  assert.deepEqual(route(new URL("https://r.workers.dev/n/bob-2/api"), {}), { id: "bob-2", path: "/api" });
  assert.deepEqual(route(new URL("https://r.workers.dev/n/bob"), {}), { id: "bob", path: "/" });
  assert.equal(route(new URL("https://a.b.nougenai.com/"), env), null);
  assert.equal(route(new URL("https://r.workers.dev/other"), {}), null);
  assert.equal(validId("../x"), false);
});

test("auth record stores only a hash of the join token", async () => {
  const r = await relayAuthRecord({ id: "Alice", token: TOKEN });
  assert.equal(r.key, "relay:alice");
  assert.equal(r.value, await sha256Hex(TOKEN));
  assert.ok(!r.value.includes(TOKEN));
});

test("connect requires the node's token", async () => {
  const { env } = await seeded();
  assert.equal((await worker.fetch(connectReq("wrong"), env)).status, 401);
  assert.equal((await worker.fetch(new Request("https://relay.example/_relay/connect?id=alice", { headers: { upgrade: "websocket" } }), env)).status, 401);
  assert.equal((await worker.fetch(connectReq(TOKEN, "mallory"), env)).status, 401);
  assert.equal((await worker.fetch(connectReq(TOKEN, "bad/id"), env)).status, 400);
});

test("public request is piped over the socket and back", async () => {
  const { env, objects } = await seeded();
  const { server } = await connect(env, objects);
  assert.equal(JSON.parse(server.sent[0]).t, "ready");
  autoAnswer(server, (f) => ({ status: 201, headers: { "content-type": "text/plain", "x-path": f.path },
    body: btoa(`${f.method} ${atob(f.body)}`) }));
  const res = await worker.fetch(new Request("https://alice.nougenai.com/mcp?q=1", { method: "POST", body: "hi" }), env);
  assert.equal(res.status, 201);
  assert.equal(res.headers.get("x-path"), "/mcp?q=1");
  assert.equal(res.headers.get("x-nougen-transport"), "relay");
  assert.equal(await res.text(), "POST hi");
});

test("status reports live transport; offline node gets a clear 502", async () => {
  const { env, objects } = await seeded();
  let s = await (await worker.fetch(new Request("https://relay.example/_relay/status?id=alice"), env)).json();
  assert.deepEqual([s.live, s.transport], [false, "relay"]);
  const off = await worker.fetch(new Request("https://alice.nougenai.com/"), env);
  assert.equal(off.status, 502);
  assert.match(await off.text(), /offline/);
  await connect(env, objects);
  s = await (await worker.fetch(new Request("https://relay.example/_relay/status?id=alice"), env)).json();
  assert.equal(s.live, true);
  assert.ok(s.since > 0);
});

test("re-register is idempotent: one node, one session", async () => {
  const { env, objects } = await seeded();
  const a = await connect(env, objects);
  const b = await connect(env, objects);
  assert.equal(a.server.closed.code, 4000);
  assert.equal(b.dobj.state.getWebSockets("node").length, 1);
  autoAnswer(b.server, () => ({ status: 200, headers: {}, body: btoa("from b") }));
  assert.equal(await (await worker.fetch(new Request("https://alice.nougenai.com/"), env)).text(), "from b");
  // The old socket closing must not tear down the new session.
  a.dobj.webSocketClose(a.server, 4000);
  assert.equal(b.dobj.state.getWebSockets("node").length, 1);
});

test("heartbeat ping is answered; slow node gets 504", async () => {
  const { env, objects } = await seeded();
  const { dobj, server } = await connect(env, objects);
  dobj.webSocketMessage(server, '{"t":"ping"}');
  assert.equal(server.sent.at(-1), '{"t":"pong"}');
  const res = await worker.fetch(new Request("https://alice.nougenai.com/slow"), env);
  assert.equal(res.status, 504);
});

test("oversized body is refused before it reaches the socket", async () => {
  const { env, objects } = await seeded();
  env.RELAY_MAX_BODY_BYTES = "4";
  const { server } = await connect(env, objects);
  const n = server.sent.length;
  const res = await worker.fetch(new Request("https://alice.nougenai.com/up", { method: "POST", body: "too big" }), env);
  assert.equal(res.status, 413);
  assert.equal(server.sent.length, n);
});

test("repeated Set-Cookie headers from the node all reach the browser", async () => {
  const { env, objects } = await seeded();
  const { server } = await connect(env, objects);
  autoAnswer(server, () => ({ status: 200, headers: [["set-cookie", "a=1"], ["set-cookie", "b=2"], ["content-type", "text/plain"]], body: btoa("ok") }));
  const res = await worker.fetch(new Request("https://alice.nougenai.com/login"), env);
  assert.deepEqual(res.headers.getSetCookie(), ["a=1", "b=2"]);
});
