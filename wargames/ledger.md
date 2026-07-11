# War-Game Ledger — blocked variables needing GM input

## Probe results: nougen-beats-fable Move 2 (2026-07-11)
- **SCORE 2/10 (bar ≥8/10) — FAIL.** Semantic recall must NOT be advertised as working; FTS5 stays primary.
- Countermove findings: commits 536d342 (MMR) + a54a51e (auto-embed) ARE live; query embedding fires (768-dim); core.retrieve consumes it. Failure layer = ranking/fusion — arXiv volume (6.6K+ shards) swamps operational shards on doctrine queries (8 of 10 misses returned unrelated arXiv papers top-3).
- Exact misses: MMR-dedup, auto-embed, Rule 0.0/0.1 preflight, Fable cutoff, float32 false-alarm, Open Engine queue, handoff-guard hooks, mesh write-auth. Hits: arXiv lane health, DPAPI credentials.
- Fix mission authored: `wargames/retrieval-quality.md`. Move 5 scoreboard is BLOCKED until re-probe ≥8/10.

## Mission: nougen-beats-fable
- `(top_missions_to_wargame)` — which standing NouGen missions get Fable-tier war-games first (window: before Jul 7). Candidates from handoffs: prototype→public migration pipeline, HARDENING.md direction, embed/semantic-recall hardening, arXiv ingestion evolution, Open Engine task-queue expansion.
- `(fable_credit_budget)` — usage-credit ceiling for post-Jul-7 single-move Fable escalations. Until set: escalate only on explicit GM call.

## Resolved (2026-07-11, GM: "War game it now")
- `(eval_task_set)` — LOCKED to the Move-2 draft: 10 paraphrase probes against known shards (MMR diversification commit, auto-embed fix, arXiv lane health, DPAPI vault doctrine, Rule 0.0/0.1, Fable redeployment facts, float32 false-alarm, Open Engine queue, handoff guard hooks, mesh write-auth). Benchmark mission for Move 5: the 2026-07-11 fix-all mission re-run as a scored comparison. GM ordered execution; draft stands unless overridden.

## Resolved
- `(backfill_depth)` [arxiv-evolution] — GM ordered backfill 2026-07-11 ("start with backfilling arxiv"). Executed: Jul 7-10 gap filled (409 daily docs + shard parity) via tools/arxiv_gap_backfill.py; daily-doc lane made unconditional in the arxiv-daily-scan scheduled task. The 6,604-shard *digest* backlog remains forward-only per Stadium physics.
