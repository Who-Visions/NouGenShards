// Parses the output of `make -C engine/ngs check test crash` into the
// suites -> tests shape the Test Results pattern renders. Pure: no I/O.

export type GateTest = {
  name: string
  status: "passed" | "failed" | "skipped"
  error?: string
}

export type GateSuite = { name: string; tests: GateTest[] }

export type GateRun = {
  ok: boolean
  exitCode: number
  suites: GateSuite[]
  totals: { passed: number; failed: number }
  log: string
  ms?: number
  mocked?: boolean
}

export function parseGates(log: string, exitCode: number): GateRun {
  const lines = log.split(/\r?\n/)
  const header: GateSuite = { name: "Header gate (ngs.h)", tests: [] }
  const unit: GateSuite = { name: "Unit and behaviour suite (test_m1)", tests: [] }
  const crash: GateSuite[] = []
  let current: GateSuite | null = null
  let afterHeaderCheck = false

  for (const raw of lines) {
    const line = raw.trimEnd()

    if (/ngs_header_check$/.test(line) && !line.startsWith("cc ")) {
      afterHeaderCheck = true
      continue
    }
    if (afterHeaderCheck && line.trim() === "ok") {
      header.tests.push({ name: "Spec header gate, ngs_header_check.c", status: "passed" })
      afterHeaderCheck = false
      continue
    }
    if (/^header contract \(C11 \+ C\+\+11\): OK/.test(line)) {
      header.tests.push({ name: "Header contract compiles as C11 and C++11", status: "passed" })
      continue
    }

    const unitFail = line.match(/^FAIL: (.+) \((.+:\d+)\)$/)
    if (unitFail) {
      unit.tests.push({ name: unitFail[1], status: "failed", error: unitFail[2] })
      continue
    }
    const unitSummary = line.match(/^TESTS: (\d+) passed, (\d+) failed/)
    if (unitSummary) {
      // test_m1 prints only failures, so passes are summarised as one line.
      unit.tests.unshift({ name: `${unitSummary[1]} checks passed`, status: "passed" })
      continue
    }

    const scenario = line.match(/^scenario \d+: (.+)$/)
    if (scenario) {
      current = { name: `Crash: ${scenario[1]}`, tests: [] }
      crash.push(current)
      continue
    }
    const ok = line.match(/^ {2}ok: (.+)$/)
    if (ok && current) {
      current.tests.push({ name: ok[1], status: "passed" })
      continue
    }
    const bad = line.match(/^ {2}FAIL: (.+) \((.+:\d+)\)$/)
    if (bad && current) {
      current.tests.push({ name: bad[1], status: "failed", error: bad[2] })
    }
  }

  if (exitCode !== 0 && header.tests.length < 2) {
    header.tests.push({
      name: "Header gate did not finish",
      status: "failed",
      error: lines.filter((l) => /error|Error/.test(l)).slice(0, 12).join("\n") || "make exited " + exitCode,
    })
  }

  const suites = [header, unit, ...crash].filter((s) => s.tests.length > 0)
  let passed = 0
  let failed = 0
  for (const s of suites)
    for (const t of s.tests) {
      if (t.status === "failed") failed++
      else if (t.status === "passed") {
        const m = t.name.match(/^(\d+) checks passed$/)
        passed += m ? Number(m[1]) : 1
      }
    }

  return { ok: exitCode === 0 && failed === 0, exitCode, suites, totals: { passed, failed }, log }
}
