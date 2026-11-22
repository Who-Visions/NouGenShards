// Join provisioning for the relay: the auth record the relay checks, and the
// address written into node.json. Everything here is dormant unless the join
// deployment is given both RELAY_URL and the RELAY_AUTH store.
import test from "node:test";
import assert from "node:assert/strict";
import worker, { nodeJson, relayId, relayAuthRecordFor, relayProvision, setupSh, setupArgs } from "../../workers/join/worker.js";
import { relayAuthRecord, sha256Hex } from "../../workers/relay/worker.js";

const CODE = "C".repeat(24);
const TOKEN = "join-token-value-for-tests";
const RELAY = "wss://relay.example.test/_relay/connect";

function kv(seed = {}) {
  const m = new Map(Object.entries(seed));
  const calls = [];
  return {
    m, calls,
    get: async (k, type) => (m.has(k) ? (type === "json" ? JSON.parse(m.get(k)) : m.get(k)) : null),
    put: async (k, v) => { calls.push(k); m.set(k, v); },
  };
}

function tenants() {
  return kv({
    ["enroll:" + CODE]: "someone@example.test",
    "tenant:someone@example.test": JSON.stringify({ tenant_id: "sample-acct", token: TOKEN, port: 4567, name: "Sam" }),
    "tunnel:someone@example.test": JSON.stringify({ tunnel_token: "tun", hostname: "sample-acct-d334.example.test" }),
  });
}

const get = (env, path) => worker.fetch(new Request("https://join.example.test" + path), env);
const nodeJsonIn = (script) => JSON.parse(script.match(/<<'NODE'\n(.*)\nNODE/)[1]);
const T = { id: "sample-acct", port: 4567, token: TOKEN, tunnel: "tun", url: "https://sample-acct-d334.example.test" };

test("the record is keyed by the public hostname label, the id the relay routes on", async () => {
  assert.equal(relayId(T), "sample-acct-d334");
  assert.equal(relayId({ id: "Plain-ID", url: "" }), "plain-id");
  assert.equal(relayId({ id: "x", url: "not a url" }), "x");
  const rec = await relayAuthRecordFor(T);
  assert.deepEqual(rec, { key: "relay:sample-acct-d334", value: await sha256Hex(TOKEN) });
  assert.ok(!rec.value.includes(TOKEN), "the token itself must never be written");
});

test("same shape as the relay worker's own relayAuthRecord for the same id", async () => {
  const ours = await relayAuthRecordFor({ id: "sample-acct", token: TOKEN, url: "" });
  assert.deepEqual(ours, await relayAuthRecord({ id: "sample-acct", token: TOKEN }));
});

test("setup.sh download writes the record once and puts the address in node.json", async () => {
  const env = { TENANTS: tenants(), RELAY_AUTH: kv(), RELAY_URL: RELAY };
  const r = await get(env, `/j/${CODE}/setup.sh`);
  assert.equal(r.status, 200);
  assert.equal(nodeJsonIn(await r.text()).relay_url, RELAY);
  assert.equal(env.RELAY_AUTH.m.get("relay:sample-acct-d334"), await sha256Hex(TOKEN));
  // A second download finds the record already right and does not write again.
  await get(env, `/j/${CODE}/setup.sh`);
  assert.deepEqual(env.RELAY_AUTH.calls, ["relay:sample-acct-d334"]);
});

test("a rotated token replaces the stale record", async () => {
  const env = { TENANTS: tenants(), RELAY_AUTH: kv({ "relay:sample-acct-d334": "stale" }), RELAY_URL: RELAY };
  await get(env, `/j/${CODE}/setup.sh`);
  assert.equal(env.RELAY_AUTH.m.get("relay:sample-acct-d334"), await sha256Hex(TOKEN));
});

test("control: without RELAY_URL or without RELAY_AUTH nothing is written and node.json has no relay address", async () => {
  for (const extra of [{}, { RELAY_URL: RELAY }, { RELAY_AUTH: kv() }]) {
    const env = { TENANTS: tenants(), ...extra };
    const script = await (await get(env, `/j/${CODE}/setup.sh`)).text();
    assert.ok(!("relay_url" in nodeJsonIn(script)), JSON.stringify(Object.keys(extra)));
    if (env.RELAY_AUTH) assert.equal(env.RELAY_AUTH.calls.length, 0);
  }
});

test("an address that is not TLS, or is not URL-safe, is never handed out", async () => {
  for (const bad of ["ws://relay.example.test/x", "http://relay.example.test/x", "relay.example.test",
    "wss://relay.example.test/x\nNODE\nrm -rf ~", "wss://relay.example.test/$(id)", "wss://relay.example.test/a b", "wss://relay.example.test/'x"]) {
    const store = kv();
    assert.equal(await relayProvision({ RELAY_AUTH: store, RELAY_URL: bad }, T), "", bad);
    assert.equal(store.calls.length, 0, "a record was written for an address that is refused");
    assert.equal(setupArgs({ ...T, relay_url: bad }).relay_url, "", bad);
    assert.ok(!setupSh({ ...T, relay_url: bad }).includes("relay_url\":"), bad);
  }
});

test("a store that fails means no address, so setup never points a node at a relay that would refuse it", async () => {
  const broken = { get: async () => { throw new Error("kv down"); }, put: async () => { throw new Error("kv down"); } };
  assert.equal(await relayProvision({ RELAY_AUTH: broken, RELAY_URL: RELAY }, T), "");
  const env = { TENANTS: tenants(), RELAY_AUTH: broken, RELAY_URL: RELAY };
  const r = await get(env, `/j/${CODE}/setup.sh`);
  assert.equal(r.status, 200, "a relay store outage must not break setup");
  assert.ok(!("relay_url" in nodeJsonIn(await r.text())));
});

test("the Windows setup is not given a relay address and writes no record", async () => {
  const env = { TENANTS: tenants(), RELAY_AUTH: kv(), RELAY_URL: RELAY };
  const r = await get(env, `/j/${CODE}/setup`);
  assert.equal(r.status, 200);
  assert.ok(!(await r.text()).includes("relay_url"));
  assert.equal(env.RELAY_AUTH.calls.length, 0);
});

test("nodeJson leaves relay_url out unless it is set", () => {
  assert.ok(!("relay_url" in JSON.parse(nodeJson(T))));
  assert.equal(JSON.parse(nodeJson({ ...T, relay_url: RELAY })).relay_url, RELAY);
});
