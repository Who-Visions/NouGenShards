// /open: a tenant who already joined is signed into their own node by the Google
// account they joined with, never by a password they were never given.
import test from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import worker, { hudTicket, setupCmd, setupSh, TICKET_TTL_S } from "../../workers/join/worker.js";

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
const b64url = (buf) => Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const idToken = (email) => "h." + b64url(JSON.stringify({ iss: "https://accounts.google.com", aud: "cid", email, email_verified: true })) + ".s";

async function signIn(env, startPath, email) {
  const start = await worker.fetch(new Request("https://join.example" + startPath), env);
  const state = start.headers.get("set-cookie").match(/__Host-nj_state=([^;]+)/)[1];
  const real = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ id_token: idToken(email) }));
  try {
    return await worker.fetch(new Request(`https://join.example/google/callback?state=${encodeURIComponent(state)}&code=x`,
      { headers: { cookie: `__Host-nj_state=${state}` } }), env);
  } finally { globalThis.fetch = real; }
}

const tenantEnv = () => ({
  GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: SECRET,
  TENANTS: kvStore({
    "tenant:pat@example.com": JSON.stringify({ tenant_id: "pat", token: "node-token-123", node_url: "https://pat-ab12.example.com", port: 4500 }),
    "tunnel:pat@example.com": JSON.stringify({ tunnel_token: "t", hostname: "pat-ab12.example.com" }),
  }),
});

test("hudTicket: body.sig, HMAC-SHA256 over 'hud-ticket:'+body with the node token, short-lived", async () => {
  const now = Date.UTC(2026, 10, 22, 19, 0, 0);
  const tk = await hudTicket({ id: "pat", token: "node-token-123" }, now);
  const [body, sig] = tk.split(".");
  assert.equal(sig, b64url(createHmac("sha256", "node-token-123").update("hud-ticket:" + body).digest()));
  const claims = JSON.parse(Buffer.from(body, "base64url").toString());
  assert.equal(claims.sub, "pat");
  assert.equal(claims.exp, Math.floor(now / 1000) + TICKET_TTL_S);
  assert.ok(claims.n.length >= 8);
});

test("/open starts Google with an 'open' state and no forced account picker", async () => {
  const res = await worker.fetch(new Request("https://join.example/open"), tenantEnv());
  assert.equal(res.status, 302);
  assert.match(res.headers.get("set-cookie"), /^__Host-nj_state=open\.[^;]+; Path=\/;.*HttpOnly; Secure/);
  const loc = new URL(res.headers.get("location"));
  assert.equal(loc.searchParams.get("prompt"), null);
  assert.equal(loc.searchParams.get("redirect_uri"), "https://join.example/google/callback");
});

test("an open sign-in sends the browser to its own node with a one-time ticket, and provisions nothing", async () => {
  const env = tenantEnv();
  const before = env.TENANTS.m.size;
  const res = await signIn(env, "/open", "Pat@Example.com");
  assert.equal(res.status, 302);
  const loc = new URL(res.headers.get("location"));
  assert.equal(loc.origin, "https://pat-ab12.example.com");
  assert.equal(loc.pathname, "/hud/ticket");
  const [body, sig] = loc.searchParams.get("t").split(".");
  assert.equal(sig, b64url(createHmac("sha256", "node-token-123").update("hud-ticket:" + body).digest()));
  assert.equal(JSON.parse(Buffer.from(body, "base64url").toString()).sub, "pat");
  assert.equal(res.headers.get("referrer-policy"), "no-referrer");
  assert.equal(env.TENANTS.m.size, before, "opening a node writes nothing");
});

test("an open sign-in for an email that never joined gets the join page, not a node", async () => {
  const res = await signIn(tenantEnv(), "/open", "stranger@example.com");
  assert.equal(res.status, 200);
  assert.match(await res.text(), /No node for this account yet/);
});

test("a join state relabelled as 'open' is refused (purpose is inside the signature)", async () => {
  const env = tenantEnv();
  const start = await worker.fetch(new Request("https://join.example/google/start"), env);
  const join = start.headers.get("set-cookie").match(/__Host-nj_state=([^;]+)/)[1];
  const forged = "open." + join;
  const res = await worker.fetch(new Request(`https://join.example/google/callback?state=${encodeURIComponent(forged)}&code=x`,
    { headers: { cookie: `__Host-nj_state=${forged}` } }), env);
  assert.match(await res.text(), /sign-in expired/);
});

test("setup ends by opening the Join page's /open, so the tenant lands signed in", () => {
  const t = { id: "pat", token: "tok", tunnel: "tun", port: 4500, url: "https://pat-ab12.example.com", open_url: "https://join.example/open" };
  assert.ok(setupCmd(t).includes("Start-Process 'https://join.example/open'"));
  const sh = setupSh({ ...t, code: "A".repeat(24), origin: "https://join.example" });
  assert.ok(sh.includes("open 'https://join.example/open'") && sh.includes("xdg-open 'https://join.example/open'"));
  // Anything that is not a plain https .../open is ignored: the node address is opened instead.
  assert.ok(setupCmd({ ...t, open_url: "https://evil.example/x';calc'" }).includes("Start-Process 'https://pat-ab12.example.com'"));
});

test("the served Windows setup file carries the /open address", async () => {
  const env = tenantEnv();
  env.TENANTS.m.set("enroll:" + "C".repeat(24), "pat@example.com");
  const res = await worker.fetch(new Request(`https://join.example/j/${"C".repeat(24)}/setup`), env);
  assert.ok((await res.text()).includes("Start-Process 'https://join.example/open'"));
});
