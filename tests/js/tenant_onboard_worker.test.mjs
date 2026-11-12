// Run: node --test tests/js/tenant_onboard_worker.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { provisionTenant, InviteClaim, renderOnboardPage } from "../../tools/nougen-fleet-mcp-patched.js";

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

test("the onboarding page is one button, with the code taken from the link", () => {
  const html = renderOnboardPage("abc123");
  assert.match(html, /const CODE = "abc123";/);
  assert.match(html, /fetch\("\/onboard\/redeem"/);
  assert.match(html, /textContent/);
  assert.doesNotMatch(html, /innerHTML/);
  assert.doesNotMatch(html, /<input/, "no typing for the person");
  assert.match(html, /prefers-reduced-motion/);
});

test("a hostile code in the link cannot break out of the script", () => {
  const html = renderOnboardPage('x</script><script>alert(1)</script>');
  assert.doesNotMatch(html, /<\/script><script>alert/);
});

test("GET /onboard/<code> serves the page with the code and sends no-referrer", async () => {
  const resp = await worker.fetch(new Request("https://join.test/onboard/abc123"), {});
  assert.equal(resp.status, 200);
  assert.equal(resp.headers.get("referrer-policy"), "no-referrer");
  assert.match(await resp.text(), /const CODE = "abc123";/);
});

test("POST /onboard/redeem is still the API route", async () => {
  const resp = await worker.fetch(new Request("https://join.test/onboard/redeem", { method: "GET" }), {});
  assert.equal(resp.status, 405, "the API path is POST only, never a page");
});

test("a claim is still held after 2 minutes, so a slow run cannot be overlapped", async () => {
  const realNow = Date.now;
  let t = 1_000_000;
  Date.now = () => t;
  try {
    const data = new Map();
    const obj = new InviteClaim({ storage: { get: async (k) => data.get(k), put: async (k, v) => { data.set(k, v); } } });
    const claim = () => obj.fetch(new Request("https://x/claim", { method: "POST", body: "{}" }));
    assert.equal((await claim()).status, 200);
    t += 2 * 60 * 1000; // 2 minutes later
    assert.equal((await claim()).status, 409, "still leased at 2 minutes");
    t += 11 * 60 * 1000; // past the 10-minute lease
    assert.equal((await claim()).status, 200, "a crashed claim recovers after the lease");
  } finally {
    Date.now = realNow;
  }
});

test("an invitee cannot take over another tenant by naming its id", async () => {
  const log = [];
  const kv = memKv({
    "invite:evil": JSON.stringify({ eml: "mallory@example.com", exp: Date.now() / 1000 + 3600 }),
    "tenant-owner:victim-shards": "victim@example.com",
    "tenant-digest:victim-shards": "victim-digest",
    "tunnel:victim@example.com": JSON.stringify({ tunnel_token: "victim-tunnel", hostname: "victim.example.test" }),
  });
  await assert.rejects(
    withFetch(fakeCloudflare(log), () => provisionTenant(env(kv, log), { code: "evil", tenant_id: "victim-shards", name: "Victim" })),
    /already in use/);
  assert.equal(log.length, 0, "no Cloudflare call may happen");
  assert.equal(kv.m.get("tenant-owner:victim-shards"), "victim@example.com");
  assert.equal(kv.m.get("tenant-digest:victim-shards"), "victim-digest");
  assert.ok(kv.m.has("invite:evil"), "the invite is not consumed by a refused attempt");
});

test("a caller-supplied tenant_id is ignored; the tenant id comes from the invitee", async () => {
  const log = [];
  const kv = memKv({
    "invite:pat": JSON.stringify({ eml: "pat@example.com", exp: Date.now() / 1000 + 3600 }),
    "tenant-owner:victim-shards": "victim@example.com",
  });
  const res = await withFetch(fakeCloudflare(log), () =>
    provisionTenant(env(kv, log), { code: "pat", tenant_id: "victim-shards", name: "Pat" }));
  assert.equal(res.tenant_id, "pat-shards");
  assert.equal(kv.m.get("tenant-owner:victim-shards"), "victim@example.com");
});
