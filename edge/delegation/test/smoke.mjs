// End-to-end check against a running `wrangler dev` (real workerd + Durable Object SQLite).
//   BASE=http://127.0.0.1:8799 TOKEN=<DELEGATION_TOKEN> node test/smoke.mjs
// Expects SWEEP_SECONDS to be small (the dev default in .dev.vars is 2).
import assert from "node:assert/strict";

const BASE = process.env.BASE || "http://127.0.0.1:8799";
const TOKEN = process.env.TOKEN;
if (!TOKEN) throw new Error("set TOKEN");

async function call(method, path, body, token = TOKEN) {
  const res = await fetch(BASE + path, {
    method,
    headers: { ...(token ? { authorization: `Bearer ${token}` } : {}), "content-type": "application/json" },
    body: body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body),
  });
  return { status: res.status, body: await res.json().catch(() => null) };
}
const post = (op, body, token) => call("POST", `/v1/${op}`, body, token);
const ok = (r, status = 200) => { assert.equal(r.status, status, JSON.stringify(r.body)); return r.body.result; };
const run = `smoke-${Date.now()}`;
let n = 0;
const step = async (name, fn) => { await fn(); n += 1; console.log(`ok ${n} ${name}`); };

await step("health needs no token", async () => assert.equal((await call("GET", "/health", undefined, null)).status, 200));
await step("missing or wrong token is 401", async () => {
  assert.equal((await post("take", { msg_id: run, lane: "a" }, null)).status, 401);
  assert.equal((await post("take", { msg_id: run, lane: "a" }, "wrong")).status, 401);
});
await step("bad input is 400, unknown route 404, wrong method 405", async () => {
  assert.equal((await post("take", { lane: "a" })).status, 400);
  assert.equal((await post("take", "not json")).status, 400);
  assert.equal((await post("nosuchop", {})).status, 404);
  assert.equal((await call("GET", "/v1/take")).status, 405);
  assert.equal((await post("take", { msg_id: "bad id!", lane: "a" })).status, 400);
});

const id = `${run}-full`;
let epoch;
await step("take issues epoch 1 and CLAIMED", async () => {
  const c = ok(await post("take", { msg_id: id, lane: "laneA", lease_seconds: 60 }));
  assert.equal(c.state, "CLAIMED");
  epoch = c.fencing_epoch;
  assert.equal(epoch, 1);
});
await step("another lane is refused with 409 while the lease is live", async () =>
  assert.equal((await post("take", { msg_id: id, lane: "laneB" })).status, 409));
await step("complete before verify and commit is refused", async () =>
  assert.equal((await post("complete", { msg_id: id, epoch, proof: { a: 1 } })).status, 409));
await step("checkpoint, verify, commit, complete", async () => {
  assert.equal(ok(await post("checkpoint", { msg_id: id, epoch, evidence: { step: 1 } })).progress_count, 1);
  assert.equal(ok(await post("verify", { msg_id: id, epoch, evidence: { tests: "pass" } })).state, "VERIFYING");
  assert.equal(ok(await post("commit", { msg_id: id, epoch, idempotency_key: "k1" })).state, "COMMITTING");
  const done = ok(await post("complete", { msg_id: id, epoch, proof: { merged: "abc" } }));
  assert.equal(done.state, "COMPLETE");
  assert.deepEqual(done.verification_proof, { merged: "abc" });
});
await step("a terminal task cannot be taken again", async () =>
  assert.equal((await post("take", { msg_id: id, lane: "laneB" })).status, 409));

const stale = `${run}-stale`;
await step("the watchdog alarm reclaims an expired lease and the old worker is fenced", async () => {
  const c = ok(await post("take", { msg_id: stale, lane: "laneA", lease_seconds: 1 }));
  await new Promise((r) => setTimeout(r, 6000));
  const row = ok(await call("GET", `/v1/claim?msg_id=${stale}`));
  assert.equal(row.state, "SUBMITTED", "the alarm should have returned it to SUBMITTED");
  assert.equal((await post("heartbeat", { msg_id: stale, epoch: c.fencing_epoch })).status, 409);
  const b = ok(await post("take", { msg_id: stale, lane: "laneB" }));
  assert.equal(b.fencing_epoch, c.fencing_epoch + 1);
});
await step("open lists unfinished work", async () => {
  const open = ok(await call("GET", "/v1/open"));
  assert.ok(open.some((t) => t.msg_id === stale));
  assert.ok(!open.some((t) => t.msg_id === id));
});
console.log(`\nall ${n} smoke checks passed`);
