import { expect, test } from "bun:test";
import { normalize, parseJson } from "../../tools/aiwithdav3_review_lib.ts";

test("takes the last JSON verdict out of chatty output", () => {
  const o = parseJson('thinking {"x":1} ... final:\n{"verdict":"READY","findings":[]} trailing');
  expect(o.verdict).toBe("READY");
});
test("reads a fenced JSON answer", () => {
  expect(parseJson('```json\n{"verdict":"CHANGES","findings":[{"file":"a.js","line":3,"severity":"blocking","confidence":90,"claim":"x"}]}\n```').verdict).toBe("CHANGES");
});
test("no JSON fails closed", () => { expect(() => parseJson("looks good to me")).toThrow(); });
test("a verdict other than READY/CHANGES fails closed", () => { expect(() => normalize("l", { verdict: "LGTM" })).toThrow(); });
test("findings are clamped and malformed ones dropped", () => {
  const r = normalize("codex", { verdict: "CHANGES", findings: [
    { file: "a.js", line: "7", severity: "blocking", confidence: 400, claim: "bad" },
    { claim: "no file" }, { file: "b.js", severity: "weird", confidence: -3, claim: "c" }] });
  expect(r.findings.length).toBe(2);
  expect(r.findings[0]).toMatchObject({ line: 7, confidence: 100, severity: "blocking", lane: "codex" });
  expect(r.findings[1]).toMatchObject({ severity: "minor", confidence: 0 });
});

test("reads a pretty-printed verdict", () => {
  expect(parseJson('{\n  "verdict": "CHANGES",\n  "findings": []\n}').verdict).toBe("CHANGES");
});

test("braces inside strings do not end the object", () => {
  const o = parseJson('{"verdict":"CHANGES","findings":[{"file":"a.go","severity":"blocking","confidence":90,"claim":"map {x} is nil }"}]}');
  expect(o.findings[0].claim).toBe("map {x} is nil }");
});
test("a truncated answer fails closed", () => { expect(() => parseJson('{"verdict":"CHANGES","findings":[{"file":"a"')).toThrow(); });
