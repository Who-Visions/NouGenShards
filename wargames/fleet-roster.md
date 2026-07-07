# NouGen Fleet Roster — 15 Free Agents (Coach: Claude)

**Stadium physics**: 8GB VRAM — local models load ONE at a time; ollama queues requests serially. Cloud lanes (10, 12-15) run truly parallel at zero VRAM. Cost of every agent below: $0.

**Executor contract (all agents)**: compressed returns only — summary, top-3 evidence, confidence, next action. Report observations against the war-game's Expect lines before taking the next move. Never dump raw logs at the Coach.

| # | Agent | Model / Lane | Role | Standing assignment |
|---|-------|--------------|------|---------------------|
| 1 | Sol-Ai | sol-ai:e4b (local) | Player #1 — first-pass reasoning, task triage | First look at every new mission; route or attempt |
| 2 | Kaedra | kaedra:e4b (local) | Code reviewer | Review fleet-drafted patches before Coach sees them |
| 3 | Iris | iris-ai:e4b (local) | Docs & summarization | arXiv shard digests; mission brief drafting |
| 4 | Rhea-Noir | rhea-noir:e2b (local) | Test-failure interpreter | Read pytest output, return diagnosis + suspect lines |
| 5 | Griot | griot:e2b (local) | Report & handoff drafting | Draft handoff bodies and canonical reports for Coach review |
| 6 | Dav1d | dav1d:e2b (local) | Patch drafter | Boilerplate and first-draft diffs per routing rule 5 |
| 7 | DavOs | DavOs:latest (local) | Repo reasoner | Grep-synthesis and repo-specific questions |
| 8 | Gemma-12 | gemma4:12b (local) | Bulk generator | Volume drafts: briefs, docstrings, test skeletons |
| 9 | Nomic | nomic-embed-text (local) | Embedding worker | Semantic recall + auto-embed (already on the field — 9,972 shards embedded) |
| 10 | Gemma-31 | gemma4:31b-cloud (ollama-cloud) | Heavy reasoner | Cheap-lane executor for war-games (Move 4 harness) |
| 11 | Scout | openrouter free tier | Research runner | Fetch-and-digest jobs where local context is missing |
| 12 | Adversary | openrouter free tier | Adversarial reviewer | Second-opinion attacks on fleet patches (cross-model review) |
| 13 | Verifier | openrouter free tier | Plan checker | Verify war-game fork coverage before execution |
| 14 | Harvester | HF free inference | Dataset/arXiv worker | Batch classification/tagging of shard clusters |
| 15 | Judge | HF free inference | Eval scorer | Score raw-vs-NouGen scoreboard runs (Move 5), rubric from success.md |

## Reliability log (Coach-verified, first live dispatch 2026-07-06)
- **gemma-31**: 2/2 clean briefs, ~10-17s, faithful to (variable) discipline → trusted for structured drafting. Move-2 execution (2026-07-06): decision quality GOOD (right pick, sound ranking) but **hallucinated test evidence** ("packet truncation suite" that didn't exist) → trust its decisions, always verify its cited evidence.
- **iris**: 1/1 usable with corrections — good structure, but hallucinated a stat and wrong model names; verify facts in her returns.
- **dav1d**: 1/1 REJECTED — returned roleplay/fake progress output instead of the deliverable. Needs narrower rails (one section per prompt) before re-trusting with structured tasks.

## Dispatch mechanics
- **Local + ollama-cloud (1-10)**: `POST http://127.0.0.1:11434/api/generate` (or chat), `stream:false`, cap `num_predict`. Locals serialize; don't fan out more than ~2 local jobs at once.
- **Queue lane**: cross-provider tickets via `nougen queue add` (see CLAUDE.md Task Queue).
- **Liveness rule**: an agent is "working" only when it has a completed job artifact on disk or a queue receipt — a roster row is not work.
