// Tests for the #1079 follow-ups: private-repo lane filter, truncated-diff APPROVE, no-primary no-post.
import { describe, expect, test } from "bun:test";
import { allowedLanes, finalVerdict } from "./gate";

const LANES = ["huggingface", "openrouter", "ollama-cloud", "local-e2b", "agy"] as const;
const YES = { agree: true, verdict: "APPROVE" };

describe("private repos stay local", () => {
  test("public repo keeps every lane", () => {
    expect(allowedLanes(LANES, false)).toEqual([...LANES]);
  });
  test("private repo drops every cloud lane and agy, keeps local-e2b", () => {
    expect(allowedLanes(LANES, true)).toEqual(["local-e2b"]);
  });
  test("private repo with no local lane available leaves nothing to send to", () => {
    expect(allowedLanes(["huggingface", "agy"] as const, true)).toEqual([]);
  });
});

describe("finalVerdict", () => {
  test("truncated diff: APPROVE is downgraded even when the supervisor agrees", () => {
    expect(finalVerdict({ primaryOk: true, verdict: "APPROVE", sup: YES, findings: [], truncated: true })).toBe("COMMENT");
  });
  test("full diff with agreeing supervisor: APPROVE stands", () => {
    expect(finalVerdict({ primaryOk: true, verdict: "APPROVE", sup: YES, findings: [], truncated: false })).toBe("APPROVE");
  });
  test("truncated diff still allows REQUEST_CHANGES on a P1", () => {
    expect(finalVerdict({ primaryOk: true, verdict: "REQUEST_CHANGES", sup: { agree: true, verdict: "REQUEST_CHANGES" }, findings: [{ severity: "P1" }], truncated: true })).toBe("REQUEST_CHANGES");
  });
  test("no primary lane answered: nothing is posted", () => {
    expect(finalVerdict({ primaryOk: false, verdict: "APPROVE", sup: YES, findings: [], truncated: false })).toBeNull();
  });
  test("no supervisor: APPROVE and REQUEST_CHANGES become COMMENT", () => {
    expect(finalVerdict({ primaryOk: true, verdict: "APPROVE", sup: null, findings: [], truncated: false })).toBe("COMMENT");
    expect(finalVerdict({ primaryOk: true, verdict: "REQUEST_CHANGES", sup: null, findings: [{ severity: "P1" }], truncated: false })).toBe("COMMENT");
  });
});
