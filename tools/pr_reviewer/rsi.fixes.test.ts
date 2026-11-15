// Regression tests for the #1079 review findings (agy, 11/15) and the RSI CLI helpers.
import { describe, expect, test } from "bun:test";
import { mkdtempSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { collectPages, consensusFindings, normVerdict, parseJsonl, rollbackTo, rsiStatus, seenKeys, withLock } from "./rsi";

describe("P2 ledger robustness", () => {
  test("a truncated JSONL line is skipped, not fatal", () => {
    expect(parseJsonl('{"a":1}\n{"b":2\n\n"str"\n{"c":3}\n')).toEqual([{ a: 1 }, { c: 3 }]);
  });
  test("withLock serialises writers and releases the lock", () => {
    const p = join(mkdtempSync(join(tmpdir(), "rsi-")), "l.lock");
    const order: number[] = [];
    withLock(p, () => { order.push(1); expect(() => withLock(p, () => order.push(9), 60_000, 100)).toThrow(/lock busy/); order.push(2); });
    expect(existsSync(p)).toBe(false);
    expect(withLock(p, () => 42)).toBe(42);
    expect(order).toEqual([1, 2]);
  });
});

describe("P2 poll retry after transient failure", () => {
  const now = Date.parse("2026-11-15T18:00:00Z");
  test("posted is always seen; no-verdict only inside the cooldown", () => {
    const s = seenKeys([
      { repo: "o/r", pr: 1, sha: "a", posted: true, started: "2026-01-01T00:00:00Z" },
      { repo: "o/r", pr: 2, sha: "b", outcome: "no-verdict", finished: "2026-11-15T17:00:00Z" },
      { repo: "o/r", pr: 3, sha: "c", outcome: "no-verdict", finished: "2026-11-15T01:00:00Z" },
    ], now);
    expect([...s].sort()).toEqual(["o/r#1@a", "o/r#2@b"]);
  });
});

describe("P3 fixes", () => {
  test("pagination follows full pages and stops on a short one", async () => {
    const pages: number[] = [];
    const all = await collectPages(async (p) => { pages.push(p); return Array(p < 3 ? 100 : 7).fill(p); });
    expect(all.length).toBe(207); expect(pages).toEqual([1, 2, 3]);
  });
  test("supervisor verdicts are compared case-insensitively", () => {
    expect(normVerdict(" approve ")).toBe("APPROVE"); expect(normVerdict(undefined)).toBe("");
  });
});

describe("3-vendor consensus", () => {
  test("majority of three: 2 of 3 lanes keeps a finding, 1 of 3 drops it", () => {
    const out = consensusFindings([
      { lane: "openrouter", findings: [{ path: "a", line: 5, confidence: 90, body: "x" }, { path: "c", line: 1, body: "lonely" }] },
      { lane: "huggingface", findings: [{ path: "a", line: 6, confidence: 85, body: "x'" }] },
      { lane: "agy", findings: [{ path: "b", line: 9, body: "other" }] },
    ], 2);
    expect(out.map((f) => f.path)).toEqual(["a"]); expect(out[0].votes).toBe(2);
  });
});

describe("rsi CLI helpers", () => {
  const arch = [
    { version: 1, items: [{ id: "a", check: "a", weight: 0.5 }], lessons: ["l1"] },
    { version: 2, items: [{ id: "a", check: "a", weight: 0.9 }], parent: 1, gate: { after: 0.4 } }];
  test("rollback re-issues an old version as a new one, keeping history", () => {
    const n = rollbackTo(arch, 1);
    expect(n.version).toBe(3); expect(n.parent).toBe(1); expect(n.items[0].weight).toBe(0.5); expect(n.lessons).toEqual(["l1"]);
    expect(() => rollbackTo(arch, 7)).toThrow(/no checklist v7/);
  });
  test("status reports active version, streak, judged/held and rejections", () => {
    const st = rsiStatus(arch, 2, [{ checklist: "a", held: true }, { checklist: "a", held: false }, { gate: "rejected", version: 3 }]);
    expect(st).toMatchObject({ active: 2, rejected_streak: 2, judged: 2, held: 1 });
    expect(st.rejections).toHaveLength(1); expect(st.weights[0]).toMatchObject({ id: "a", weight: 0.9 });
  });
});

import { compareFilesOrNull } from "./rsi";
describe("re-review P2: failed compare is not a dismissal", () => {
  test("null / error bodies / missing files mean retry later", () => {
    for (const bad of [null, undefined, { message: "Not Found" }, { files: "x" }]) expect(compareFilesOrNull(bad)).toBeNull();
    expect(compareFilesOrNull({ files: [] })).toEqual([]);
  });
});
