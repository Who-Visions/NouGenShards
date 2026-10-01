import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { ClaimLifecycle, LifecycleError } from "../src/lifecycle.js";

// The real SQL runs on node:sqlite, the same dialect Durable Object storage uses.
function make({ authorityCheck = null } = {}) {
  const db = new DatabaseSync(":memory:");
  const clock = { t: 1_000_000 };
  const sql = (q, ...p) => {
    const stmt = db.prepare(q);
    return /^\s*(select|with|pragma)/i.test(q) || /returning/i.test(q) ? stmt.all(...p) : (stmt.run(...p), []);
  };
  const tx = (fn) => {
    db.exec("BEGIN");
    try { const r = fn(); db.exec("COMMIT"); return r; } catch (e) { db.exec("ROLLBACK"); throw e; }
  };
  const life = new ClaimLifecycle({ sql, tx, now: () => clock.t, authorityCheck });
  life.init();
  return { life, clock };
}
const code = (fn) => { try { fn(); } catch (e) { assert.ok(e instanceof LifecycleError, String(e)); return e.code; } return null; };

test("take creates a claim at epoch 1 and re-take by the same lane is idempotent", () => {
  const { life } = make();
  const a = life.takeMsg("m1", "laneA");
  assert.equal(a.state, "CLAIMED");
  assert.equal(a.fencing_epoch, 1);
  assert.equal(life.takeMsg("m1", "laneA").fencing_epoch, 1);
});

test("a second lane cannot take work that is under a live lease", () => {
  const { life } = make();
  life.takeMsg("m1", "laneA");
  assert.equal(code(() => life.takeMsg("m1", "laneB")), "FENCING");
});

test("after the lease expires another lane takes it at a higher epoch and the old worker is fenced", () => {
  const { life, clock } = make();
  const a = life.takeMsg("m1", "laneA", 10);
  clock.t += 11;
  const b = life.takeMsg("m1", "laneB", 10);
  assert.equal(b.fencing_epoch, a.fencing_epoch + 1);
  assert.equal(code(() => life.heartbeat("m1", a.fencing_epoch)), "FENCING");
  assert.equal(code(() => life.checkpoint("m1", a.fencing_epoch, { x: 1 })), "FENCING");
  assert.equal(code(() => life.commitStep("m1", a.fencing_epoch, "k")), "FENCING");
});

test("the full path claim -> checkpoint -> verify -> commit -> complete", () => {
  const { life } = make();
  const { fencing_epoch: e } = life.takeMsg("m1", "laneA");
  assert.equal(life.checkpoint("m1", e, { step: "edit" }).progress_count, 1);
  assert.equal(life.verifyStep("m1", e, { tests: "pass" }).state, "VERIFYING");
  assert.equal(life.commitStep("m1", e, "pr-1").state, "COMMITTING");
  const done = life.complete("m1", e, { merged: "abc123" });
  assert.equal(done.state, "COMPLETE");
  assert.equal(done.lease_expires_at, 0);
  assert.deepEqual(done.verification_proof, { merged: "abc123" });
  assert.equal(code(() => life.takeMsg("m1", "laneB")), "INVALID_STATE");
});

test("completion cannot skip verification, commit or proof", () => {
  const { life } = make();
  const { fencing_epoch: e } = life.takeMsg("m1", "laneA");
  assert.equal(code(() => life.complete("m1", e, { a: 1 })), "INVALID_STATE");
  assert.equal(code(() => life.commitStep("m1", e, "k")), "INVALID_STATE");
  assert.equal(code(() => life.verifyStep("m1", e, {})), "INVALID_STATE");
  life.checkpoint("m1", e, { a: 1 });
  life.verifyStep("m1", e, { a: 1 });
  assert.equal(code(() => life.commitStep("m1", e, "  ")), "INVALID_STATE");
  life.commitStep("m1", e, "k1");
  assert.equal(code(() => life.complete("m1", e, {})), "INVALID_STATE");
});

test("a heartbeat cannot complete work", () => {
  const { life } = make();
  const { fencing_epoch: e } = life.takeMsg("m1", "laneA");
  assert.equal(code(() => life.heartbeat("m1", e, "COMPLETE")), "INVALID_STATE");
  assert.equal(life.heartbeat("m1", e, "WORKING"), true);
});

test("a different idempotency key cannot be bound to a claim that already has one", () => {
  const { life } = make();
  const { fencing_epoch: e } = life.takeMsg("m1", "laneA");
  life.checkpoint("m1", e, { a: 1 });
  life.verifyStep("m1", e, { a: 1 });
  life.commitStep("m1", e, "key-1");
  assert.equal(life.commitStep("m1", e, "key-1").state, "COMMITTING");
  assert.equal(code(() => life.commitStep("m1", e, "key-2")), "FENCING");
});

test("authority is re-checked at commit and complete, and a throwing check denies", () => {
  let allow = true;
  const { life } = make({ authorityCheck: () => [allow, "operator revoked"] });
  const { fencing_epoch: e } = life.takeMsg("m1", "laneA");
  life.checkpoint("m1", e, { a: 1 });
  life.verifyStep("m1", e, { a: 1 });
  life.commitStep("m1", e, "k");
  allow = false;
  assert.equal(code(() => life.complete("m1", e, { ok: 1 })), "AUTHORITY");
  assert.equal(life.getClaim("m1").state, "COMMITTING");
  const broken = make({ authorityCheck: () => { throw new Error("service down"); } });
  const t = broken.life.takeMsg("m2", "laneA");
  broken.life.checkpoint("m2", t.fencing_epoch, { a: 1 });
  broken.life.verifyStep("m2", t.fencing_epoch, { a: 1 });
  assert.equal(code(() => broken.life.commitStep("m2", t.fencing_epoch, "k")), "AUTHORITY");
});

test("detectAndReclaimStale returns expired active work to SUBMITTED and takes nothing live", () => {
  const { life, clock } = make();
  life.takeMsg("old", "laneA", 5);
  life.takeMsg("fresh", "laneA", 500);
  clock.t += 10;
  assert.deepEqual(life.detectAndReclaimStale().map((r) => r.msg_id), ["old"]);
  assert.equal(life.getClaim("old").state, "SUBMITTED");
  assert.equal(life.getClaim("fresh").state, "CLAIMED");
});

test("a worker that heartbeats forever without a checkpoint is detected as stalled and fenced out", () => {
  const { life, clock } = make();
  const { fencing_epoch: e } = life.takeMsg("m1", "laneA", 100);
  clock.t += 60; life.heartbeat("m1", e, "WORKING", 100);
  clock.t += 60; life.heartbeat("m1", e, "WORKING", 100);
  const stalled = life.detectStalled(100);
  assert.equal(stalled.length, 1);
  assert.equal(stalled[0].progress_count, 0);
  assert.equal(life.reclaimStalled("m1", e, "no progress"), true);
  assert.equal(code(() => life.heartbeat("m1", e)), "FENCING");
  assert.equal(life.reclaimStalled("m1", e, "again"), false);
});

test("a checkpoint counts as progress and clears the stall", () => {
  const { life, clock } = make();
  const { fencing_epoch: e } = life.takeMsg("m1", "laneA", 1000);
  clock.t += 200;
  life.checkpoint("m1", e, { did: "x" }, 1000);
  assert.equal(life.detectStalled(100).length, 0);
});

test("requeue is bounded and cancel fences the worker", () => {
  const { life } = make();
  for (let i = 0; i < 3; i++) {
    const c = life.takeMsg("m1", "laneA");
    life.fail("m1", c.fencing_epoch, `try ${i}`);
    life.requeue("m1", "retry");
  }
  const c = life.takeMsg("m1", "laneA");
  life.fail("m1", c.fencing_epoch, "again");
  assert.equal(code(() => life.requeue("m1", "retry")), "INVALID_STATE");

  const x = life.takeMsg("m2", "laneA");
  assert.equal(life.cancel("m2", "not needed").state, "CANCELED");
  assert.equal(code(() => life.heartbeat("m2", x.fencing_epoch)), "FENCING");
  assert.equal(code(() => life.cancel("m2", "again")), "INVALID_STATE");
});

test("interrupt states are valid and the task can be re-taken at a new epoch", () => {
  const { life } = make();
  const a = life.takeMsg("m1", "laneA");
  assert.equal(life.interrupt("m1", a.fencing_epoch, "INPUT_REQUIRED", "need answer").state, "INPUT_REQUIRED");
  assert.equal(code(() => life.interrupt("m1", a.fencing_epoch, "COMPLETE", "x")), "BAD_REQUEST");
  assert.equal(life.takeMsg("m1", "laneB").fencing_epoch, a.fencing_epoch + 1);
});

test("an unknown task is NOT_FOUND and listOpen flags stale leases", () => {
  const { life, clock } = make();
  assert.equal(code(() => life.heartbeat("nope", 1)), "NOT_FOUND");
  assert.equal(code(() => life.cancel("nope", "x")), "NOT_FOUND");
  life.takeMsg("m1", "laneA", 5);
  clock.t += 10;
  const open = life.listOpen();
  assert.equal(open.length, 1);
  assert.equal(open[0].stale, true);
});
