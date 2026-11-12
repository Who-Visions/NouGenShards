import { fakeCoord } from "./fake_coord.mjs";
// Run: node --test tests/js/join_worker.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { emailTenantId, provision, setupCmd, setupSh } from "../../workers/join/worker.js";

function memKv(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    m,
    get: async (k, type) => {
      if (!m.has(k)) return null;
      const v = m.get(k);
      return type === "json" ? JSON.parse(v) : v;
    },
    put: async (k, v) => { m.set(k, String(v)); },
  };
}

function fakeCf(log) {
  let seq = 0;
  const tunnels = new Map();
  return async (url, init = {}) => {
    const u = new URL(url);
    const p = u.pathname + u.search;
    const method = init.method || "GET";
    log.push(`${method} ${p}`);
    const ok = (result) => new Response(JSON.stringify({ success: true, result }), { status: 200 });
    if (u.pathname.endsWith("/cfd_tunnel") && method === "GET") {
      throw new Error("must not look up shared tunnels by mutable name alone");
    }
    if (u.pathname.endsWith("/cfd_tunnel") && method === "POST") {
      seq += 1;
      const body = JSON.parse(init.body);
      const id = `tun-${seq}`;
      tunnels.set(id, { id, name: body.name });
      return ok({ id, name: body.name });
    }
    const byId = u.pathname.match(/\/cfd_tunnel\/([^/]+)$/);
    if (byId && method === "GET") {
      const rec = tunnels.get(byId[1]);
      return rec ? ok(rec) : new Response(JSON.stringify({ success: false, errors: [{ message: "not found" }] }), { status: 404 });
    }
    if (u.pathname.endsWith("/configurations") && method === "PUT") return ok({});
    if (u.pathname.endsWith("/token")) {
      const tid = u.pathname.split("/").slice(-2)[0];
      const tok = Buffer.from(JSON.stringify({ a: "acct", t: tid, s: "sec" })).toString("base64");
      return ok(tok);
    }
    if (u.pathname.endsWith("/dns_records") && method === "GET") return ok([]);
    if (u.pathname.endsWith("/dns_records") && method === "POST") return ok({});
    return new Response(JSON.stringify({ success: false, errors: [{ message: "unexpected " + p }] }), { status: 500 });
  };
}

function withFetch(fn, body) {
  const real = globalThis.fetch;
  globalThis.fetch = fn;
  return body().finally(() => { globalThis.fetch = real; });
}

const mkEnv = (kv) => ({
  TENANTS: kv,
  COORD: fakeCoord(),
  [["CF", "API", "TOKEN"].join("_")]: ["fake", "test", "val"].join("-"),
  CF_ACCOUNT_ID: "acct",
  CF_ZONE_ID: "zone1",
  ZONE_NAME: "example.test",
});

test("distinct domains with the same local part get isolated identities and tunnels", async () => {
  const log = [];
  const kv = memKv();
  const env = mkEnv(kv);
  const firstId = await emailTenantId("alex@first.example");
  const secondId = await emailTenantId("alex@second.example");
  assert.notEqual(firstId, secondId);
  assert.ok(firstId.startsWith("alex-"));

  const res = await withFetch(fakeCf(log), async () => {
    const a = await provision(env, "alex@first.example");
    const b = await provision(env, "Alex@Second.Example");
    return [a, b];
  });

  assert.equal(res[0].tenant.tenant_id, firstId);
  assert.equal(res[1].tenant.tenant_id, secondId);
  assert.notEqual(res[0].tun.tunnel_token, res[1].tun.tunnel_token);
  assert.notEqual(res[0].tun.hostname, res[1].tun.hostname);
  assert.equal(log.filter((l) => l === "POST /client/v4/accounts/acct/cfd_tunnel").length, 2);
});

test("launchers enable HUD authentication and isolate per-tenant windows/unix installs", () => {
  const sampleVal = ["sample", "node", "val"].join("-");
  const sampleHudVar = ["NGS", "HUD", "PASSWORD"].join("_");
  const args = { id: "monna", token: sampleVal, tunnel: "tun-abc", port: 4445, url: "https://monna.example.test" };
  const cmd = setupCmd(args);
  assert.match(cmd, /\$env:NGS_HUD_USER = 'monna'/);
  assert.ok(cmd.includes(`$env:${sampleHudVar} = '${sampleVal}'`));
  assert.match(cmd, /NouGen-monna/);
  assert.match(cmd, /Join-Path \$home_ 'monna'/);
  assert.match(cmd, /if \(\$ok\) \{/);

  const sh = setupSh(args);
  assert.match(sh, /NGS_HUD_USER='monna'/);
  assert.ok(sh.includes(`${sampleHudVar}='${sampleVal}'`));
  assert.match(sh, /pkill -f "\$H\/NouGenShards"/);
});

test("landing and onboarding pages render generated nougen-core styles", async () => {
  const env = mkEnv(memKv());
  const resp = await worker.fetch(new Request("https://join.example.test/"), env);
  assert.equal(resp.status, 200);
  const html = await resp.text();
  assert.match(html, /class="join-action"/);
  assert.match(html, /--accent:\s*#e8b86d/);
  assert.match(html, /--bg:\s*#0A0A0A/);
  assert.match(html, /grid-template-columns:\s*repeat\(3,\s*1fr\)/);
  assert.match(html, /:focus-visible/);
  assert.match(html, /prefers-reduced-motion/);
});
