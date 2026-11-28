import { test } from "node:test"
import assert from "node:assert/strict"

import { plan } from "./agent.ts"

const tools = (s: string) => plan(s).calls.map((c) => c.tool)

test("routes plain words to engine calls", () => {
  assert.deepEqual(tools("remember that the stopgap comes out after PR 1200"), ["remember", "verify"])
  assert.deepEqual(tools("verify the chain"), ["verify"])
  assert.deepEqual(tools("run the judge gates"), ["gates"])
  assert.deepEqual(tools("recall Blade"), ["recall", "scan"])
  assert.deepEqual(tools("show the last 5 facts"), ["scan"])
  assert.deepEqual(tools("engine status"), ["stats"])
  assert.equal(plan("hello").intent, "help")
})

test("bench counts are parsed and capped", () => {
  assert.deepEqual(plan("bench 5,000 facts").calls[0].args, ["5000"])
  assert.deepEqual(plan("bench 2k").calls[0].args, ["2000"])
  assert.deepEqual(plan("benchmark 900000").calls[0].args, ["50000"])
})

test("remember keeps the user's words as the body", () => {
  const c = plan("Remember: Blade D: needs a replug").calls[0]
  assert.equal(c.args[c.args.indexOf("--body") + 1], "Blade D: needs a replug")
})
