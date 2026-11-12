// Regression tests for the Codex review of PR #1026 (2026-11-11):
// %~f0 injection, login-CSRF state, port allocation, provisioning recovery.
import test from "node:test";
import assert from "node:assert/strict";
import { setupCmd, provision } from "../../workers/join/worker.js";
import worker from "../../workers/join/worker.js";

const t = { id: "abc", token: "tok", tunnel: "tun", port: 4500, url: "https://abc.example" };

test("setup.cmd never puts the script path into PowerShell source", () => {
  const cmd = setupCmd(t);
  const launcher = cmd.split("\r\n").find((l) => l.startsWith("powershell"));
  assert.ok(launcher, "launcher line exists");
  assert.ok(!launcher.includes("%~f0"), "path must not be interpolated into -Command");
  assert.ok(launcher.includes("$env:NG_SELF"), "path comes from an env var");
  assert.ok(cmd.includes('set "NG_SELF=%~f0"'), "env var is set from cmd");
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

test("google start sets a __Host- cookie and server-side single-use state", async () => {
  const kv = kvStore();
  const env = { TENANTS: kv, GOOGLE_CLIENT_ID: "cid" };
  const res = await worker.fetch(new Request("https://join.example/google/start"), env);
  const cookie = res.headers.get("set-cookie");
  assert.match(cookie, /^__Host-nj_state=[^;]+; Path=\/;/);
  const state = cookie.match(/__Host-nj_state=([^;]+)/)[1];
  assert.equal(kv.m.get("oauthstate:" + state), "1");
});

test("callback rejects a state that only exists as a planted cookie", async () => {
  const env = { TENANTS: kvStore(), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "s" };
  const req = new Request("https://join.example/google/callback?state=PLANTED&code=x", {
    headers: { cookie: "__Host-nj_state=PLANTED" } });
  const res = await worker.fetch(req, env);
  const body = await res.text();
  assert.match(body, /sign-in expired/);
});

test("callback rejects a non-__Host cookie even with matching state", async () => {
  const env = { TENANTS: kvStore({ "oauthstate:S": "1" }), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "s" };
  const req = new Request("https://join.example/google/callback?state=S&code=x", { headers: { cookie: "nj_state=S" } });
  assert.match(await (await worker.fetch(req, env)).text(), /sign-in expired/);
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
    env: { TENANTS: kv, CF_API_TOKEN: "x", CF_ACCOUNT_ID: "a", CF_ZONE_ID: "z", ZONE_NAME: "example.com" } };
}

test("ports are per-email, distinct, reserved, and stable on retry", async () => {
  const kv = kvStore();
  const calls = [];
  const { env, restore } = cfStubEnv(kv, calls);
  try {
    const [a, b] = await Promise.all([provision(env, "one@x.org"), provision(env, "two@x.org")]);
    assert.notEqual(a.tenant.port, b.tenant.port, "concurrent sign-ups get different ports");
    assert.equal(kv.m.get("port:" + a.tenant.port), "one@x.org");
    assert.ok(a.tenant.port >= 4445, "4444 stays reserved for legacy installs");
  } finally { restore(); }
});

test("a retry after a half-finished provision reuses the tunnel instead of creating another", async () => {
  const kv = kvStore({ "tunnelid:three@x.org": "tid-existing" });
  const calls = [];
  const { env, restore } = cfStubEnv(kv, calls);
  try {
    await provision(env, "three@x.org");
    assert.ok(!calls.some((c) => c.startsWith("POST") && /cfd_tunnel$/.test(c.split("?")[0])), "no second tunnel created");
  } finally { restore(); }
});
