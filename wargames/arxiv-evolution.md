# WAR-GAME: arxiv-evolution

**Mission**: Evolve the arXiv RSS lane from raw ingestion into a digest pipeline (per-paper summaries, semantic tags, weekly digest), free lanes only. Brief: `tasks/arxiv-evolution.md` (note Coach corrections in its header — 6,604 is TOTAL arxiv shards, daily volume is dozens).
**Authored by**: Claude Fable 5, 2026-07-06.
**Executor**: gemma4:31b-cloud orchestrates; iris-ai:e4b / gemma4:12b summarize (fact-check iris per reliability log); nomic-embed-text tags. Tool moves via tool-bearing lane.

## Move 1 — Recon: lane ground truth
- **Action**: locate `arxiv_rss_scanner.py` (Sol-Ai tools dir per prior handoffs — verify), read its shard write format, and count TRUE daily volume from the last week of arxiv-tagged shards.
- **Expect**: script path, shard schema fields (title/abstract/link present?), real papers/day number (order: dozens).
- **Failure signal**: shards store only titles/links, no abstracts.
- **Countermove**: extend scanner to capture abstracts from the RSS payload before building summaries; do not fetch full PDFs (rate-limit risk).

## Move 2 — Digest prototype (one day's papers)
- **Action**: pull one recent day's arxiv shards; local gemma summarizes each to ≤3 sentences; assemble `digest-YYYY-MM-DD.md`.
- **Expect**: digest ≤500 tokens, every entry keeps arxiv ID + shard handle (evidence-preserving compression).
- **Failure signal**: summaries hallucinate content beyond the abstract (iris failure mode).
- **Countermove**: constrain prompt to "compress ONLY the provided abstract; no outside knowledge"; spot-check 3 entries against source shards.

## Move 3 — Semantic tagging pass
- **Action**: tag each paper shard with 3-5 topic tags (embedding-nearest existing tags first, new tags only when distance is large).
- **Expect**: tags written back via capture/update path; recall by topic works in a probe query.
- **Failure signal**: tag explosion (every paper mints new tags).
- **Countermove**: cap new-tag creation per batch; reuse-first policy.

## Move 4 — Weekly digest + capture
- **Action**: aggregate the daily digests into a Monday weekly intelligence digest; capture it as a shard (INTELLIGENCE type).
- **Fork**: IF automating the weekly run needs a scheduled task → that is a `(gm_scheduling_approval)` ledger variable (timers only on explicit GM ask); ELSE run it as a manual Monday play alongside the existing scanner run.

## Open variables → ledger.md
- `(gm_scheduling_approval)`, `(digest_distribution)` (stays in vault? posted where?), `(backfill_depth)` (digest the 6,604 backlog or forward-only?).

## 2nd/3rd-order
- Summarizing the 6,604 backlog on local models is days of compute — Stadium physics says forward-only unless GM prioritizes backfill.
- Weekend zero-volume days must produce "no papers" digests, not STALE alarms (known probe false-alarm).

## Abort conditions
- arXiv rate-limiting or ToS friction on any fetch step — stop fetching, work from stored shards only.
- Vault write errors mid-batch — stop, report count written vs pending.
