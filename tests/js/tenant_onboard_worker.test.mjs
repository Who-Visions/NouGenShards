// Run: node --test tests/js/tenant_onboard_worker.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { provisionTenant, InviteClaim } from "../../tools/nougen-fleet-mcp-patched.js";

// Fake Durable Object namespace: one real InviteClaim instance per invite code.
function claimNamespace() {
  const objects = new Map();
  return {
    idFromName: (name) => name,
    get: (id) => {
      if (!objects.has(id)) {
        const data = new Map();
        const state = { storage: {
          get: async (k) => data.get(k),
          put: async (k, v) => { data.set(k, v); },
        } };
        objects.set(id, new InviteClaim(state));
      }
      const obj = objects.get(id);
      return { fetch: (url, init) => obj.fetch(new Request(url, init)) };
    },
  };
}

function memKv(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    m,
    get: async (k) => (m.has(k) ? m.get(k) : null),
    put: async (k, v) => { m.set(k, v); },
    delete: async (k) => { m.delete(k); },
  };
}

// Fake Cloudflare: zones, tunnels, DNS. Records every mutating call.
function fakeCloudflare(log) {
  const tunnelToken = Buffer.from(JSON.stringify({ a: "acct", t: "tun-123", s: "x" })).toString("base64");
  return async (url, init = {}) => {
    const u = new URL(url);
    const p = u.pathname;
    const method = init.method || "GET";
    log.push(`${method} ${p}`);
    const ok = (result) => new Response(JSON.stringify({ success: true, result }), { status: 200 });
    if (p.endsWith("/zones")) return ok([{ id: "zone-1" }]);
    if (p.endsWith("/cfd_tunnel") && method === "GET") return ok([]);
    if (p.endsWith("/cfd_tunnel") && method === "POST") return ok({ id: "tun-123" });
    if (p.endsWith("/configurations") && method === "GET") return ok({ config: { ingress: [] } });
    if (p.endsWith("/configurations") && method === "PUT") return ok({});
    if (p.endsWith("/token")) return new Response(JSON.stringify({ success: true, result: tunnelToken }), { status: 200 });
    if (p.endsWith("/dns_records") && method === "GET") return ok([]);
    if (p.endsWith("/dns_records") && method === "POST") return ok({});
    return new Response(JSON.stringify({ success: false, errors: [{ message: "unexpected" }] }), { status: 500 });
  };
}

const env = (kv, log, claims = claimNamespace()) => ({
  TENANTS: kv,
  INVITE_CLAIMS: claims,
  CLOUDFLARE_API_TOKEN_NOUGEN_FULL: "test-token",
  CLOUDFLARE_ACCOUNT_ID: "acct",
  CLOUDFLARE_API_BASE: "https://cf.test/client/v4",
  NOUGEN_TENANT_DOMAIN: "example.test",
});

function withFetch(fn, body) {
  const real = globalThis.fetch;
  globalThis.fetch = fn;
  return body().finally(() => { globalThis.fetch = real; });
}

test("redeems a valid invite, provisions, and consumes the invite", async () => {
  const log = [];
  const kv = memKv({ "invite:abc": JSON.stringify({ eml: "Pat@Example.com", exp: Date.now() / 1000 + 3600 }) });
  const res = await withFetch(fakeCloudflare(log), () =>
    provisionTenant(env(kv, log), { code: "abc", name: "Pat Smith", port: 4444 }));
  assert.equal(res.email, "pat@example.com");
  assert.equal(res.tenant_id, "pat-smith-shards");
  assert.match(res.node_url, /^https:\/\/pat-smith-shards-[a-z0-9_-]{4}\.example\.test$/);
  assert.ok(res.token && res.tunnel_token);
  assert.equal(kv.m.get("allow:pat@example.com"), "1");
  assert.ok(kv.m.has("tenant-digest:pat-smith-shards"));
  assert.ok(!kv.m.has("invite:abc"), "invite must be consumed");
  assert.ok(log.some((l) => l.startsWith("POST /client/v4/accounts/acct/cfd_tunnel")));
});

test("an invite cannot be used twice", async () => {
  const log = [];
  const kv = memKv({ "invite:abc": JSON.stringify({ eml: "pat@example.com", exp: Date.now() / 1000 + 3600 }) });
  await withFetch(fakeCloudflare(log), () => provisionTenant(env(kv, log), { code: "abc", name: "Pat" }));
  await assert.rejects(
    withFetch(fakeCloudflare(log), () => provisionTenant(env(kv, log), { code: "abc", name: "Pat" })),
    /not valid or was already used|already used/);
});

test("two simultaneous redemptions of one invite: exactly one succeeds", async () => {
  const log = [];
  const kv = memKv({ "invite:race": JSON.stringify({ eml: "pat@example.com", exp: Date.now() / 1000 + 3600 }) });
  const e = env(kv, log);
  const results = await withFetch(fakeCloudflare(log), () =>
    Promise.allSettled([
      provisionTenant(e, { code: "race", name: "Pat" }),
      provisionTenant(e, { code: "race", name: "Pat" }),
    ]));
  const fulfilled = results.filter((r) => r.status === "fulfilled");
  assert.equal(fulfilled.length, 1, "only one redemption may succeed");
  assert.match(results.find((r) => r.status === "rejected").reason.message, /being redeemed|already used/);
});

test("a failed run releases the claim so the invite can be retried", async () => {
  const log = [];
  const kv = memKv({ "invite:retry": JSON.stringify({ eml: "pat@example.com", exp: Date.now() / 1000 + 3600 }) });
  const e = env(kv, log);
  const failing = async () => new Response("nope", { status: 500 });
  await assert.rejects(withFetch(failing, () => provisionTenant(e, { code: "retry", name: "Pat" })));
  assert.ok(kv.m.has("invite:retry"), "invite survives a failed run");
  const res = await withFetch(fakeCloudflare(log), () => provisionTenant(e, { code: "retry", name: "Pat" }));
  assert.equal(res.email, "pat@example.com");
});

test("an expired invite is refused before any Cloudflare call", async () => {
  const log = [];
  const kv = memKv({ "invite:old": JSON.stringify({ eml: "pat@example.com", exp: 1 }) });
  await assert.rejects(
    withFetch(fakeCloudflare(log), () => provisionTenant(env(kv, log), { code: "old" })),
    /expired/);
  assert.equal(log.length, 0);
});

test("a missing token fails with a clear message and keeps the invite", async () => {
  const kv = memKv({ "invite:abc": JSON.stringify({ eml: "pat@example.com", exp: Date.now() / 1000 + 3600 }) });
  const e = { ...env(kv, []), CLOUDFLARE_API_TOKEN_NOUGEN_FULL: undefined };
  await assert.rejects(provisionTenant(e, { code: "abc" }), /must be set/);
  assert.ok(kv.m.has("invite:abc"), "invite survives a failed run so it can be retried");
});

test("the Cloudflare error does not echo the response body", async () => {
  const kv = memKv({ "invite:abc": JSON.stringify({ eml: "pat@example.com", exp: Date.now() / 1000 + 3600 }) });
  const leaky = async () => new Response("secret-body-value", { status: 403 });
  await assert.rejects(
    withFetch(leaky, () => provisionTenant(env(kv, []), { code: "abc" })),
    (err) => /HTTP 403/.test(err.message) && !/secret-body-value/.test(err.message));
});
