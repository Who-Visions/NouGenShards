import { test } from "node:test"
import assert from "node:assert/strict"

import { parseGates } from "./gates.ts"

const LOG = `cc -std=c11 ... -o build/ngs_header_check
./build/ngs_header_check
ok
header contract (C11 + C++11): OK
FAIL: verify rejects a torn record (tests/test_m1.c:812)
TESTS: 116 passed, 1 failed
scenario 1: kill-mid-write
  ok: reopen recovers the durable prefix
scenario 2: header tamper
  FAIL: open refuses a bad magic (tests/crash.c:301)
CRASH HARNESS: 1 passed, 1 failed`

test("parses header, unit and crash suites", () => {
  const run = parseGates(LOG, 2)
  assert.equal(run.ok, false)
  assert.deepEqual(run.suites.map((s) => s.name), [
    "Header gate (ngs.h)",
    "Unit and behaviour suite (test_m1)",
    "Crash: kill-mid-write",
    "Crash: header tamper",
  ])
  assert.deepEqual(run.totals, { passed: 2 + 116 + 1, failed: 2 })
  assert.equal(run.suites[1].tests[1].error, "tests/test_m1.c:812")
})

test("a clean run is ok", () => {
  const run = parseGates("TESTS: 117 passed, 0 failed\nscenario 1: torn tail\n  ok: tail dropped", 0)
  assert.equal(run.ok, true)
  assert.deepEqual(run.totals, { passed: 118, failed: 0 })
})
