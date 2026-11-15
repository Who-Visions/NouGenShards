import { describe, expect, test } from "bun:test";
import { consensusFindings, curateLessons, evolve, isHoldout, judgeFindings, pickParent, touchedOldLines, type Checklist, type Score } from "./rsi";

const ctx = { repo: "o/r", pr: 1 };
const ck = (w: Record<string, number>, version = 1): Checklist => ({ version, items: Object.entries(w).map(([id, weight]) => ({ id, check: id, weight })) });

describe("judgeFindings", () => {
  const patch = "@@ -10,3 +10,3 @@\n ctx\n-old\n+new\n ctx";
  test("finding near a touched line is held, far one dismissed", () => {
    expect([...touchedOldLines(patch)]).toEqual([11]);
    const s = judgeFindings([{ path: "a.ts", line: 12, checklist: "x", body: "b" }, { path: "a.ts", line: 90, checklist: "x", body: "c" }],
      [{ filename: "a.ts", patch }], ctx);
    expect(s.map((x) => x.held)).toEqual([true, false]);
  });
  test("reward-hacking guard: wholesale rewrite gives no credit", () => {
    const big = "@@ -1,400 +1,400 @@\n" + Array.from({ length: 400 }, (_, i) => `-l${i}`).join("\n");
    expect(judgeFindings([{ path: "a.ts", line: 5, checklist: "x", body: "b" }], [{ filename: "a.ts", patch: big }], ctx)).toEqual([]);
  });
  test("file without a patch (binary/huge) is ambiguous", () => {
    expect(judgeFindings([{ path: "a.bin", line: 1, checklist: "x", body: "b" }], [{ filename: "a.bin" }], ctx)).toEqual([]);
  });
  test("untouched file counts as dismissed", () => {
    expect(judgeFindings([{ path: "z.ts", line: 1, checklist: "x", body: "b" }], [], ctx)[0].held).toBe(false);
  });
});

describe("evolve", () => {
  const rows = (id: string, held: number, total: number, tag = ""): Score[] =>
    Array.from({ length: total }, (_, i) => ({ checklist: id, held: i < held, repo: "o/r", pr: i, body: `${id}${tag}-${i}` }));
  test("holdout is deterministic and ~20%", () => {
    const r = rows("a", 0, 500);
    expect(r.filter(isHoldout).length).toBeGreaterThan(60);
    expect(r.filter(isHoldout).length).toBeLessThan(140);
    expect(r.map(isHoldout)).toEqual(r.map(isHoldout));
  });
  test("weight steps are bounded and anchored", () => {
    const { next } = evolve(ck({ a: 0.9 }), rows("a", 0, 60));
    expect(next.items[0].weight).toBeGreaterThanOrEqual(0.9 - 0.15 - 1e-9);
    expect(next.items[0].weight).toBeLessThan(0.9);
    expect(next.items[0].seed_weight).toBe(0.9);
    expect(next.parent).toBe(1);
  });
  test("precise items gain weight relative to noisy ones", () => {
    const { next } = evolve(ck({ good: 0.5, bad: 0.5 }), [...rows("good", 18, 20), ...rows("bad", 2, 20)]);
    const w = Object.fromEntries(next.items.map((i) => [i.id, i.weight]));
    expect(w.good).toBeGreaterThan(w.bad);
  });
  test("gate rejects a version that ranks held-out findings worse", () => {
    // train says 'a' is bad, holdout says 'a' is the only one that holds -> downweighting a hurts holdout precision
    const all = [...rows("a", 0, 200, "t"), ...rows("b", 200, 200, "t")];
    const flipped = all.map((s) => (isHoldout(s) ? { ...s, held: s.checklist === "a" } : s));
    const r = evolve(ck({ a: 0.8, b: 0.3 }), flipped);
    expect(r.gate.holdout).toBeGreaterThanOrEqual(5);
    expect(r.adopt).toBe(false);
  });
  test("small holdout bootstraps (adopts)", () => {
    expect(evolve(ck({ a: 0.5 }), rows("a", 1, 3)).adopt).toBe(true);
  });
});

describe("curateLessons", () => {
  test("near-duplicates merge, newest wins, capped", () => {
    const out = curateLessons(["Dismissed in o/r#1 [null-check]: missing null check on user input"],
      ["Dismissed in o/r#2 [null-check]: missing null check on user input field"], 20);
    expect(out.length).toBe(1);
    expect(out[0]).toContain("#2");
    expect(curateLessons([], Array.from({ length: 30 }, (_, i) => `lesson${i} alpha${i} beta${i} gamma${i}`), 5).length).toBe(5);
  });
});

describe("consensusFindings", () => {
  test("keeps only findings >= k lanes agree on, highest confidence copy", () => {
    const out = consensusFindings([
      { lane: "hf", findings: [{ path: "a", line: 10, confidence: 80, body: "x" }, { path: "b", line: 1, confidence: 99, body: "solo" }] },
      { lane: "or", findings: [{ path: "a", line: 12, confidence: 90, body: "y" }] },
      { lane: "agy", findings: [] },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ path: "a", body: "y", votes: 2 });
  });
  test("one lane repeating itself is not consensus", () => {
    expect(consensusFindings([{ lane: "hf", findings: [{ path: "a", line: 1 }, { path: "a", line: 2 }] }])).toEqual([]);
  });
});

describe("pickParent", () => {
  const arch: Checklist[] = [
    { version: 1, items: [], gate: { after: 0.4 } }, { version: 2, items: [], gate: { after: 0.7 } }, { version: 3, items: [], gate: { after: 0.5 } }];
  test("latest unless stalled, then best archived", () => {
    expect(pickParent(arch, 0).version).toBe(3);
    expect(pickParent(arch, 3, 3, () => 0.5).version).toBe(2); // DGM draw, pinned rand lands on the 0.7 version
  });
});
