import test from "node:test";
import assert from "node:assert/strict";
import { buildPayload, normalizeEndpoint, MAX_CONTENT } from "../capture.js";

const now = new Date("2026-10-05T23:59:00Z");

test("selection wins over page text and is tagged", () => {
  const p = buildPayload({ selection: " hello ", pageText: "PAGE", url: "https://a.example/x", title: "T", now });
  assert.equal(p.event_type, "KNOWLEDGE");
  assert.match(p.content, /Kind: selection/);
  assert.ok(p.content.endsWith("hello"));
  assert.deepEqual(p.tags, ["chrome-capture", "selection", "a.example"]);
});
test("page text used when no selection", () => {
  const p = buildPayload({ selection: "  ", pageText: "PAGE", url: "https://a.example/", title: "", now });
  assert.match(p.content, /Kind: page/);
  assert.equal(p.title, "Web: a.example");
});
test("empty input yields null (negative control)", () => {
  assert.equal(buildPayload({ selection: "", pageText: "  ", url: "https://a.example", title: "t", now }), null);
});
test("long content is truncated and flagged", () => {
  const p = buildPayload({ selection: "x".repeat(MAX_CONTENT + 50), url: "https://a.example", title: "t", now });
  assert.match(p.content, /truncated/);
  assert.ok(p.content.length < MAX_CONTENT + 300);
});
test("endpoint: https ok, path stripped; plain http only on localhost", () => {
  assert.equal(normalizeEndpoint("https://phoebus.nougenai.com/capture?x=1"), "https://phoebus.nougenai.com");
  assert.equal(normalizeEndpoint("http://localhost:4444/"), "http://localhost:4444");
  assert.equal(normalizeEndpoint("http://evil.example"), null);
  assert.equal(normalizeEndpoint("javascript:alert(1)"), null);
  assert.equal(normalizeEndpoint(""), null);
});
test("endpoint with embedded credentials is reduced to origin", () => {
  assert.equal(normalizeEndpoint("https://u:p@h.example/a"), "https://h.example");
});
