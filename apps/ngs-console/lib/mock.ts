// Used only when engine/ngs/build/ngs_cli is missing (for example on a host
// that cannot build C). Every value here was recorded from a real run of the
// CLI in a cloud session on Nov 23, 2026, 9:20 PM ET, and every response that
// uses it is flagged `mocked: true` so the UI says so.

const ID = "843d5e89c7569192dd98d4e3204f322fb86db8bb3e3701281c60dd4f3c89d6b7"

export const MOCK = {
  version: { ok: true, op: "version", version: "0.3.1-draft", version_number: 3001 },
  stats: {
    ok: true,
    op: "stats",
    version: "0.3.1-draft",
    node_pubkey: "34d5a86dc2872b22fc434a11f059a5842d9a10923b22caf067f2186a50fde7f8",
    facts: 1,
    text_bytes: 36,
    scan_ms: 0.004,
  },
  remember: { ok: true, op: "remember", id: ID, durable: true, ms: 1.998 },
  scan: {
    ok: true,
    op: "scan",
    total: 1,
    facts: [
      {
        id: ID,
        ns: "fleet",
        kind: "semantic",
        seq: 1,
        t_event_us: 1795486775579618,
        t_record_us: 1795486775579619,
        title: "NGS console smoke",
        body: "first fact",
        tags: ["ngs"],
        invalidated: false,
        redacted: false,
      },
    ],
  },
  get: { ok: false, op: "get", error: "mock has no fact log" },
  verify: {
    ok: true,
    op: "verify",
    chain_and_signatures: "ok",
    checkpoint: "ok",
    checkpoint_bytes: 230,
    verify_ms: 1.782,
    checkpoint_verify_ms: 4.641,
  },
  recall: {
    ok: false,
    op: "recall",
    rc: 11,
    code: "ngs: API misuse",
    error: "ngs_recall: not in M1 (fused recall is M4)",
  },
  bench: {
    ok: true,
    op: "bench",
    facts: 50000,
    scanned: 50000,
    write_ms: 44852.871,
    flush_ms: 15.203,
    scan_ms: 3.442,
    verify_ms: 61462.703,
    write_per_sec: 1114.8,
    scan_per_sec: 14524818.5,
    verify_per_sec: 813.5,
  },
  gates: {
    ok: true,
    exitCode: 0,
    totals: { passed: 148, failed: 0 },
    log: "(recorded run)",
    suites: [
      {
        name: "Header gate (ngs.h)",
        tests: [
          { name: "Spec header gate, ngs_header_check.c", status: "passed" as const },
          { name: "Header contract compiles as C11 and C++11", status: "passed" as const },
        ],
      },
      { name: "Unit and behaviour suite (test_m1)", tests: [{ name: "117 checks passed", status: "passed" as const }] },
      { name: "Crash harness", tests: [{ name: "29 checks over 6 scenarios", status: "passed" as const }] },
    ],
  },
}
