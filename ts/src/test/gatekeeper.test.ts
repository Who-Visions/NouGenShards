/**
 * Tests for the DavOs Gatekeeper mutation gate. (TS mirror of tests/test_gatekeeper.py)
 */
import test from "node:test";
import assert from "node:assert/strict";
import { check_mutation_gate } from "../nougen_shards/gatekeeper.js";

test("allowed safe inputs", () => {
  let res = check_mutation_gate("SELECT * FROM shards;");
  assert.equal(res.allowed, true);
  assert.equal(res.gate, null);

  res = check_mutation_gate("SELECT * FROM shards", { dry_run: true });
  assert.equal(res.allowed, true);
});

test("blocked schema modifications", () => {
  for (const cmd of [
    "CREATE TABLE test (id int)",
    "ALTER TABLE shards ADD COLUMN x TEXT",
    "DROP TABLE history",
    "CREATE INDEX idx_test ON shards (id)",
    "DROP INDEX idx_test",
  ]) {
    const res = check_mutation_gate(cmd);
    assert.equal(res.allowed, false);
    assert.equal(res.gate, "schema_change");
  }
});

test("blocked destructive cleanups", () => {
  for (const cmd of [
    "DELETE FROM shards",
    "rm -rf /path/to/something",
    "DROP DATABASE production",
    "TRUNCATE table",
  ]) {
    const res = check_mutation_gate(cmd);
    assert.equal(res.allowed, false);
    assert.equal(res.gate, "destructive_cleanup");
  }
});

test("blocked obfuscated destructive commands (normalization)", () => {
  for (const cmd of [
    "RM   -RF /var/data",
    "rm\t-rf\t/tmp/x",
    "shutil.rmtree('/data')",
    "os.unlink('/etc/passwd')",
    "dd if=/dev/zero of=/dev/sda",
    ":(){ :|:& };:",
  ]) {
    const res = check_mutation_gate(cmd);
    assert.equal(res.allowed, false, `expected block for: ${cmd}`);
    assert.equal(res.gate, "destructive_cleanup");
  }
});

test("blocked dry_run=false", () => {
  const res = check_mutation_gate("safe query", { dry_run: false });
  assert.equal(res.allowed, false);
  assert.equal(res.gate, "dry_run_false");
});

test("blocked billing/budget", () => {
  for (const cmd of [
    "modify billing quota",
    "increase subscription budget",
    "change paid-tier limit",
  ]) {
    const res = check_mutation_gate(cmd);
    assert.equal(res.allowed, false);
    assert.equal(res.gate, "billing_quota_paid_tier_change");
  }
});

test("blocked deployment + obfuscated git push", () => {
  for (const cmd of [
    "git push origin main",
    "npm publish --access public",
    "deploy to prod",
    "register-node http://localhost:8000",
  ]) {
    const res = check_mutation_gate(cmd);
    assert.equal(res.allowed, false);
    assert.equal(res.gate, "deployment_target_change");
  }
  const res = check_mutation_gate("git\tpush   --force origin main");
  assert.equal(res.allowed, false);
  assert.equal(res.gate, "deployment_target_change");
});
