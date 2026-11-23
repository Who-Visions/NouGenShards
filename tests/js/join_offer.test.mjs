// Founders offer: nougenai.com/shards links join.nougenai.com/?offer=founders.
// The offer rides inside the signed Google state and is recorded once on the
// tenant, so the owner can see who joined from it and honour the locked price.
import test from "node:test";
import assert from "node:assert/strict";
import worker, { markOffer, offerOf } from "../../workers/join/worker.js";

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
const b64url = (buf) => Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const idToken = (email) => "h." + b64url(JSON.stringify({ iss: "https://accounts.google.com", aud: "cid", email, email_verified: true })) + ".s";
const existing = () => ({
  GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "test-client-secret",
  TENANTS: kvStore({
    "tenant:pat@example.com": JSON.stringify({ tenant_id: "pat", token: "node-token-123", node_url: "https://pat-ab12.example.com", port: 4500 }),
    "tunnel:pat@example.com": JSON.stringify({ tunnel_token: "t", hostname: "pat-ab12.example.com" }),
  }),
});
const stateOf = (res) => res.headers.get("set-cookie").match(/__Host-nj_state=([^;]+)/)[1];
async function callback(env, state, email) {
  const real = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ id_token: idToken(email) }));
  try {
    return await worker.fetch(new Request(`https://join.example/google/callback?state=${encodeURIComponent(state)}&code=x`,
      { headers: { cookie: `__Host-nj_state=${state}` } }), env);
  } finally { globalThis.fetch = real; }
}

test("only known offers are accepted", () => {
  assert.equal(offerOf("founders"), "founders");
  for (const bad of ["", "open", "join", "toString", "__proto__", "founders<script>"]) assert.equal(offerOf(bad), "");
});

test("the landing page carries the offer into the Google button, and ignores unknown ones", async () => {
  const founders = await (await worker.fetch(new Request("https://join.example/?offer=founders"), existing())).text();
  assert.match(founders, /href="\/google\/start\?offer=founders"/);
  assert.match(founders, /Founders offer/);
  const plain = await (await worker.fetch(new Request("https://join.example/?offer=%3Cx%3E"), existing())).text();
  assert.match(plain, /href="\/google\/start"/);
  assert.doesNotMatch(plain, /Founders offer|%3Cx|<x>/);
});

test("landing copy has no em dashes", async () => {
  const html = await (await worker.fetch(new Request("https://join.example/"), existing())).text();
  assert.doesNotMatch(html, /—/);
});

test("a founders sign-in is signed as such and records the offer once on the tenant", async () => {
  const env = existing();
  const start = await worker.fetch(new Request("https://join.example/google/start?offer=founders"), env);
  assert.equal(start.status, 302);
  const state = stateOf(start);
  assert.match(state, /^founders\./);
  const res = await callback(env, state, "Pat@Example.com");
  assert.equal(res.status, 302);
  assert.match(new URL(res.headers.get("location")).pathname, /^\/j\//);
  const t = JSON.parse(env.TENANTS.m.get("tenant:pat@example.com"));
  assert.equal(t.offer, "founders");
  assert.ok(t.offer_at);
  assert.equal(t.token, "node-token-123", "the node token is untouched");
  assert.equal(env.TENANTS.m.get("offer:founders:pat@example.com"), t.offer_at);
});

test("a plain join records no offer", async () => {
  const env = existing();
  const res = await callback(env, stateOf(await worker.fetch(new Request("https://join.example/google/start"), env)), "pat@example.com");
  assert.equal(res.status, 302);
  assert.equal(JSON.parse(env.TENANTS.m.get("tenant:pat@example.com")).offer, undefined);
});

test("a join state relabelled as founders is refused (the offer is inside the signature)", async () => {
  const env = existing();
  const state = stateOf(await worker.fetch(new Request("https://join.example/google/start"), env));
  const forged = "founders." + state;
  const res = await callback(env, forged, "pat@example.com");
  assert.match(await res.text(), /sign-in expired/);
  assert.equal(JSON.parse(env.TENANTS.m.get("tenant:pat@example.com")).offer, undefined);
});

test("the first offer wins", async () => {
  const env = existing();
  await markOffer(env, "pat@example.com", "founders");
  const first = JSON.parse(env.TENANTS.m.get("tenant:pat@example.com")).offer_at;
  await markOffer(env, "pat@example.com", "founders");
  assert.equal(JSON.parse(env.TENANTS.m.get("tenant:pat@example.com")).offer_at, first);
});

test("/open still works and is not treated as an offer", async () => {
  const env = existing();
  const res = await callback(env, stateOf(await worker.fetch(new Request("https://join.example/open"), env)), "pat@example.com");
  assert.equal(new URL(res.headers.get("location")).pathname, "/hud/ticket");
  assert.equal(JSON.parse(env.TENANTS.m.get("tenant:pat@example.com")).offer, undefined);
});
