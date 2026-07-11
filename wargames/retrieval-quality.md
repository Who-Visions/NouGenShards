# WAR-GAME: retrieval-quality

**Mission**: Get the Move-2 paraphrase probe from 2/10 to ≥8/10 — make semantic recall surface operational/doctrine shards instead of drowning them in arXiv volume. This unblocks the nougen-beats-fable Move-5 scoreboard.
**Authored by**: Claude Fable 5 (Coach), 2026-07-11, from live diagnosis.
**Executor**: Coach patches (precision code edits, small surface); local gemma + probe script verify. Probe: `move2_probe.py` (scratchpad; promote to tools/ on first use).

## Ground truth (verified)
- Embeddings current (0 pending, all 9 DBs). Query auto-embed fires (768-dim). MMR (536d342) + auto-embed (a54a51e) live on branch.
- Probe 2/10; 8 misses return unrelated arXiv abstracts top-3. Vault composition: ~6.6K arXiv shards vs a few hundred operational shards — candidate-pool swamping is the prime suspect (H1); score-fusion miscalibration secondary (H2); probe needle strictness minor (H3).

## Move 1 — Instrument the pool
- Action: for 3 failing queries, log per-lane candidates (FTS5 list, vector list, post-fusion list) with scores and domain/event_type mix.
- Expect: vector lane top-20 is >80% arXiv for doctrine queries (confirms H1) OR operational shards rank high pre-fusion but die in fusion (confirms H2).
- Failure signal: operational shards absent even from FTS5 lane → the target shards may not exist as DB shards at all (journal-only) — that's H4: coverage, not ranking.
- Countermove (H4): ingest codex_memory_journal.jsonl records as first-class shards, then re-instrument.

## Move 2 — The fix, by hypothesis
- H1 swamping → per-domain candidate quotas (e.g. cap arXiv at 40% of pool pre-MMR) and/or event_type boost for OPERATIONAL/DOCTRINE/CORRECTION shards. Env-tunable per Rule 0.2 (`NOUGEN_RECALL_ARXIV_CAP`, `NOUGEN_RECALL_TYPE_BOOSTS`).
- H2 fusion → expose fusion weight as env, sweep 3 values with the probe as scorer.
- H4 coverage → journal→shard ingestion lane, then re-run from Move 1.
- Expect: each patch is ≤50 lines, env-tunable, committed separately with probe deltas in the message.

## Move 3 — Re-probe gate
- Action: run the 10-probe set after each patch; also re-run the 2 original hits (no regressions).
- Expect: ≥8/10, hits stay hits.
- Failure signal: plateau <8/10 after H1+H2 patches → escalate: needle audit (H3) then GM review of probe set.

## Move 4 — Capture + unblock
- Action: probe results to ledger, milestone shard, flip nougen-beats-fable Move 5 to unblocked; run the scoreboard benchmark.
- Abort conditions: any patch degrades the 2 existing hits; vault write errors; mesh health fails post-patch (acceptance QUICK before ship).
