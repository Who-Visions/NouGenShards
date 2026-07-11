# War-Game Ledger — blocked variables needing GM input

## Mission: nougen-beats-fable
- `(top_missions_to_wargame)` — which standing NouGen missions get Fable-tier war-games first (window: before Jul 7). Candidates from handoffs: prototype→public migration pipeline, HARDENING.md direction, embed/semantic-recall hardening, arXiv ingestion evolution, Open Engine task-queue expansion.
- `(eval_task_set)` — the 10-query paraphrase probe set + 1-2 benchmark missions used for the raw-vs-NouGen scoreboard. Draft exists in the war-game (Move 2); GM can override.
- `(fable_credit_budget)` — usage-credit ceiling for post-Jul-7 single-move Fable escalations. Until set: escalate only on explicit GM call.

## Resolved
- `(backfill_depth)` [arxiv-evolution] — GM ordered backfill 2026-07-11 ("start with backfilling arxiv"). Executed: Jul 7-10 gap filled (409 daily docs + shard parity) via tools/arxiv_gap_backfill.py; daily-doc lane made unconditional in the arxiv-daily-scan scheduled task. The 6,604-shard *digest* backlog remains forward-only per Stadium physics.
