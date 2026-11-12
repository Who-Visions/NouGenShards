// Regression tests for the Codex reviews of PR #1026 (2026-11-11):
// %~f0 injection, login-CSRF state, signup-quota race, port race, provisioning recovery.
import test from "node:test";
import assert from "node:assert/strict";
import worker, { setupCmd, provision } from "../../workers/join/worker.js";
import { fakeCoord } from "./fake_coord.mjs";

const t = { id: "abc", token: "tok", tunnel: "tun", port: 4500, url: "https://abc.example" };

test("setup.cmd never puts the script path into PowerShell source", () => {
  const cmd = setupCmd(t);
  const launcher = cmd.split("\r\n").find((l) => l.startsWith("powershell"));
  assert.ok(launcher && !launcher.includes("%~f0"), "path must not be interpolated into -Command");
  assert.ok(launcher.includes("$env:NG_SELF") && cmd.includes('set "NG_SELF=%~f0"'));
});

function kvStore(init = {}) {
  const m = new Map(Object.entries(init));
  return {
    m,
    get: async (k, type) => { const v = m.get(k) ?? null; return type === "json" && v ? JSON.parse(v) : v; },
    put: async (k, v) => { m.set(k, String(v)); },
    delete: async (k) => { m.delete(k); },
    list: async () => ({ keys: [], list_complete: true }),
  };
}
const SECRET = "test-client-secret";

test("google start: __Host- cookie carrying a signed state, no storage needed", async () => {
  const env = { TENANTS: kvStore(), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: SECRET };
  const res = await worker.fetch(new Request("https://join.example/google/start"), env);
  const cookie = res.headers.get("set-cookie");
  assert.match(cookie, /^__Host-nj_state=[^;]+\.\d+\.[^;]+; Path=\/;/);
  assert.equal(env.TENANTS.m.size, 0, "state is not written to eventually-consistent KV");
});

test("callback rejects a planted, unsigned state even if cookie and query match", async () => {
  const env = { TENANTS: kvStore(), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: SECRET };
  const req = new Request("https://join.example/google/callback?state=a.1.b&code=x", { headers: { cookie: "__Host-nj_state=a.1.b" } });
  assert.match(await (await worker.fetch(req, env)).text(), /sign-in expired/);
});

test("callback rejects a non-__Host cookie even with a validly signed state", async () => {
  const env = { TENANTS: kvStore(), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: SECRET };
  const start = await worker.fetch(new Request("https://join.example/google/start"), env);
  const state = start.headers.get("set-cookie").match(/__Host-nj_state=([^;]+)/)[1];
  const req = new Request(`https://join.example/google/callback?state=${encodeURIComponent(state)}&code=x`, { headers: { cookie: `nj_state=${state}` } });
  assert.match(await (await worker.fetch(req, env)).text(), /sign-in expired/);
});

test("a validly signed state with the matching __Host- cookie reaches Google's token step", async () => {
  const env = { TENANTS: kvStore(), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: SECRET };
  const start = await worker.fetch(new Request("https://join.example/google/start"), env);
  const state = start.headers.get("set-cookie").match(/__Host-nj_state=([^;]+)/)[1];
  let calledGoogle = false;
  const real = globalThis.fetch;
  globalThis.fetch = async (u) => { calledGoogle = String(u).includes("oauth2.googleapis.com/token"); return new Response(JSON.stringify({})); };
  try {
    const req = new Request(`https://join.example/google/callback?state=${encodeURIComponent(state)}&code=x`, { headers: { cookie: `__Host-nj_state=${state}` } });
    await worker.fetch(req, env);
  } finally { globalThis.fetch = real; }
  assert.ok(calledGoogle, "state accepted, sign-in proceeds (no eventual-consistency failure)");
});

test("coordinator: 20 concurrent sign-ups from one IP never exceed the daily cap", async () => {
  const COORD = fakeCoord();
  const stub = COORD.get();
  const results = await Promise.all(Array.from({ length: 20 }, () =>
    stub.fetch("x", { method: "POST", body: JSON.stringify({ op: "rate", ip: "1.2.3.4", day: "d", limit: 5 }) }).then((r) => r.json())));
  assert.equal(results.filter((r) => r.ok).length, 5, "exactly the limit is admitted");
});

test("coordinator: concurrent emails that hash to the same port get different ports", async () => {
  const COORD = fakeCoord();
  const stub = COORD.get();
  const emails = Array.from({ length: 12 }, (_, i) => `u${i}@x.org`);
  const ports = await Promise.all(emails.map((email) =>
    stub.fetch("x", { method: "POST", body: JSON.stringify({ op: "port", email, base: 7 }) }).then((r) => r.json()).then((j) => j.port)));
  assert.equal(new Set(ports).size, emails.length, "all ports distinct despite identical base");
  const again = await stub.fetch("x", { method: "POST", body: JSON.stringify({ op: "port", email: "u3@x.org", base: 99 }) }).then((r) => r.json());
  assert.equal(again.port, ports[3], "an email keeps its port");
});

function cfStubEnv(kv, calls) {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    const u = String(url);
    calls.push(`${init.method || "GET"} ${u.replace("https://api.cloudflare.com/client/v4", "")}`);
    let result = {};
    if (/cfd_tunnel$/.test(u.split("?")[0]) && init.method === "POST") result = { id: "tid-" + calls.length };
    else if (/\/token$/.test(u)) result = "tunnel-token";
    else if (/dns_records\?/.test(u)) result = [];
    else if (/cfd_tunnel\/[^/]+$/.test(u.split("?")[0])) result = { id: u.split("/").pop() };
    return new Response(JSON.stringify({ success: true, result }));
  };
  return { restore: () => { globalThis.fetch = realFetch; },
    env: { TENANTS: kv, COORD: fakeCoord(), CF_API_TOKEN: "x", CF_ACCOUNT_ID: "a", CF_ZONE_ID: "z", ZONE_NAME: "example.com" } };
}

test("concurrent provisions get distinct ports at or above 4445", async () => {
  const calls = [];
  const { env, restore } = cfStubEnv(kvStore(), calls);
  try {
    const [a, b] = await Promise.all([provision(env, "one@x.org"), provision(env, "two@x.org")]);
    assert.notEqual(a.tenant.port, b.tenant.port);
    assert.ok(a.tenant.port >= 4445 && b.tenant.port >= 4445);
  } finally { restore(); }
});

test("a retry after a half-finished provision reuses the recorded tunnel", async () => {
  const calls = [];
  const { env, restore } = cfStubEnv(kvStore(), calls);
  try {
    await env.COORD.get().fetch("x", { method: "POST", body: JSON.stringify({ op: "tunnel-set", email: "three@x.org", id: "tid-existing" }) });
    await provision(env, "three@x.org");
    assert.ok(!calls.some((c) => c.startsWith("POST") && /cfd_tunnel$/.test(c.split("?")[0])), "no second tunnel created");
  } finally { restore(); }
});

test("legacy KV port reservations are imported before any newcomer is assigned a port", async () => {
  const calls = [];
  const kv = kvStore({ "port:4445": "mom@x.org", "port:4446": "mom2@x.org" });
  kv.list = async ({ prefix }) => ({ keys: [...kv.m.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true });
  const { env, restore } = cfStubEnv(kv, calls);
  try {
    const stub = env.COORD.get();
    // Force the newcomer's hash start onto 4445: probe the coordinator directly after seeding.
    await provision(env, "newcomer@x.org");
    const r = await stub.fetch("x", { method: "POST", body: JSON.stringify({ op: "port", email: "late@x.org", base: 0 }) }).then((x) => x.json());
    assert.notEqual(r.port, 4445, "legacy owner keeps 4445");
    assert.notEqual(r.port, 4446, "legacy owner keeps 4446");
  } finally { restore(); }
});
