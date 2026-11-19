// Mechanisms the free fleet extracted from donor CODE (analysis/awesome-rsi-reverse/fleet_raw.json), ported + proven.
import { describe, expect, test } from "bun:test";
import { dgmParent, driftViolations, judgeFindings, pickParent, validFinding, type Checklist } from "./rsi";

const seq = (...xs: number[]) => { let i = 0; return () => xs[i++ % xs.length]; };

describe("DGM score_child_prop parent selection", () => {
  const arch: Checklist[] = [
    { version: 1, items: [], gate: { after: 0.9 } },
    { version: 2, items: [], parent: 1, gate: { after: 0.9 } },
    { version: 3, items: [], parent: 1, gate: { after: 0.9 } },
    { version: 4, items: [], parent: 1, gate: { after: 0.2 } }];
  test("equal scores: a parent with many children yields to childless siblings", () => {
    const n = 4000; let v1 = 0;
    let r = 12345; const rand = () => ((r = (r * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
    for (let i = 0; i < n; i++) if (dgmParent(arch, rand).version === 1) v1++;
    expect(v1 / n).toBeLessThan(0.2); // v1 has 3 children -> weight /4
  });
  test("low-scoring versions are rarely chosen", () => {
    let low = 0; let r = 7; const rand = () => ((r = (r * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
    for (let i = 0; i < 4000; i++) if (dgmParent(arch, rand).version === 4) low++;
    expect(low / 4000).toBeLessThan(0.05);
  });
  test("pickParent uses DGM only once stalled", () => {
    expect(pickParent(arch, 0, 3, seq(0)).version).toBe(4);
    expect(pickParent(arch, 3, 3, seq(0)).version).toBe(1);
  });
});

describe("harness-zero drift guard", () => {
  const prev: Checklist = { version: 1, items: [{ id: "a", check: "A", weight: 0.5 }, { id: "b", check: "B", weight: 0.5 }] };
  test("weight changes are allowed", () => {
    expect(driftViolations(prev, { version: 2, items: [{ id: "a", check: "A", weight: 0.7 }, { id: "b", check: "B", weight: 0.2 }] })).toEqual([]);
  });
  test("rewritten text, dropped, invented or out-of-range items are refused", () => {
    const v = driftViolations(prev, { version: 2, items: [{ id: "a", check: "A, but lenient", weight: 0.5 }, { id: "z", check: "Z", weight: 1.5 }] });
    expect(v.join("|")).toMatch(/check text of a changed/);
    expect(v.join("|")).toMatch(/new item z/);
    expect(v.join("|")).toMatch(/out of \[0,1\]/);
    expect(v.join("|")).toMatch(/item b dropped/);
  });
});

describe("DGM validity check", () => {
  test("malformed findings are skipped, not scored as dismissed", () => {
    expect(validFinding({ path: "a", line: 3, checklist: "x" })).toBe(true);
    for (const bad of [null, { line: 3, checklist: "x" }, { path: "a", line: "?", checklist: "x" }, { path: "a", line: 0, checklist: "x" }, { path: "a", line: 2 }])
      expect(validFinding(bad)).toBe(false);
    const s = judgeFindings([{ path: "a", line: "nope", checklist: "x", body: "b" }, { path: "a", line: 4, checklist: "x", body: "c" }], [], { repo: "o/r", pr: 1 });
    expect(s).toHaveLength(1);
  });
});
