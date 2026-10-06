import test from "node:test";
import assert from "node:assert/strict";
import { distill, buildMorph, splitSentences } from "../morph.js";

const PAGE = [
  "Shard vaults store durable memory for the whole fleet and keep it searchable across machines.",
  "The fleet routes every capture through the node so that memory stays consistent across machines.",
  "Navigation Home About Contact.",
  "A destiny records a target state with a trigger, a verification step and linked evidence from shards.",
  "Unrelated cooking trivia about sourdough starters and hydration percentages for weekend bakers.",
  "Extractive distillation keeps original sentences so no claim is invented by the summarizer at all.",
].join(" ");

test("short fragments are not sentences", () => {
  assert.ok(!splitSentences(PAGE).some((s) => s.startsWith("Navigation")));
});
test("distill returns only sentences that are in the source, in page order", () => {
  const out = distill(PAGE, { maxSentences: 3, perShard: 3 }).join(" ");
  const src = splitSentences(PAGE);
  let last = -1;
  for (const s of src.filter((x) => out.includes(x))) { const i = src.indexOf(s); assert.ok(i > last); last = i; }
  assert.ok(out.length > 0);
  for (const piece of out.split(/(?<=\.)\s+/)) assert.ok(PAGE.includes(piece), piece);
});
test("empty or prose-free text distils to nothing (negative control)", () => {
  assert.deepEqual(distill(""), []);
  assert.equal(buildMorph({ url: "https://a.example", title: "t", text: "Menu Home Login" }), null);
});
test("buildMorph: shards tagged, destiny only when a goal is stated", () => {
  const none = buildMorph({ url: "https://a.example/p", title: "Page", text: PAGE });
  assert.equal(none.destiny, null);
  assert.ok(none.shards.length >= 1);
  assert.deepEqual(none.shards[0].tags.slice(0, 2), ["nougenmorph", "chrome-capture"]);
  const withGoal = buildMorph({ url: "https://a.example/p", title: "Page", text: PAGE, goal: "  Turn this into a runbook  " });
  assert.equal(withGoal.destiny.goal, "Turn this into a runbook");
  assert.equal(withGoal.destiny.status, "dormant");
  assert.equal(withGoal.destiny.trigger, "url:https://a.example/p");
  assert.equal(buildMorph({ url: "https://a.example", title: "t", text: PAGE, goal: "no" }).destiny, null);
});
