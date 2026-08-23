## 🔴 Active Incidents
- None. Node restarted on :4444 (venv + src), tunnel re-registered 4 connections, https://shards.nougenai.com/health = 200.

## 🟡 Ongoing Investigations
- (stale-dedup-ghosts) NEW in wargames/ledger.md: central dedup hash index held a ghost (hash -> db5, no such row) silently blocking a re-capture; one entry repaired, sweep needed.
- (coverage-count-discrepancy) still open: 151,203 total vs 237 for 2026-08; not chased per war-game.

## 📋 Recent Changes
- Executed wargames/recall-domain-mask.md + wargames/fts-or-fallback.md. All in src/nougen_shards/core.py:
  - D1 domain mask: implicit CWD-domain now fuses scoped+whole-brain (scoped x NOUGEN_DOMAIN_BOOST, fallback 1.2); explicit domain_key stays exclusive. Coordinator's missing-FTS-row branch DISPROVEN by probe (all triggers/FTS rows/embeddings present on all 9 DBs); the 12 "invisible" 08-16 shards were domain-masked (domain_key='global' vs node's repo domain).
  - D2 FTS AND starvation: ranked-OR retry before LIKE; OR hits tiered below AND/LIKE hits (naive retry regressed 5 graph/ranking tests: tiny-corpus bm25 ~1e-6 rounds away at 6 decimals; bm25 now breaks sub-round ties).
  - D4 bm25 saturation: logistic replaced with strength/(strength+NOUGEN_BM25_HALF_SCORE) (fallback 20.0, measured span); likelihood=norm_bm25 when caller passes no embedding. final_score in /search responses is post-RRF rank score 1/(60+rank) — NOT per-partition normalization (see FIX shard for provenance; align with remote shard 16849).
- Tests: baseline 531 passed/4 skipped -> 536 passed/4 skipped. New: tests/test_recall_domain_mask.py (2), tests/test_fts_or_fallback.py (2), test_fresh_near_exact_outranks_stale_high_utility in test_shards.py.
- Live probes (node /search, token fp 9c67af03a9da): Q "named tunnel SHARD_GATEWAY repointed connector end-to-end" -> 16971 rank 3, above 16847 rank 5 (success criterion met). Q "connector fix shards.nougenai.com" -> 16971/16844 reachable (ranks ~4/8 at limit 10), top-5 all fresh in-domain connector shards; masking eliminated, remainder is ranking competition.
- Move 5 / D3: singular nougen_shards.db (6 unique Jun-9 rows) migrated into the grid via capture() with orig-ts tags, stub + wal/shm deleted.
- HARDENING.md invariant 5 -> executed/✅ with tiering caveat; wargames/ledger.md updated (NOUGEN_DOMAIN_BOOST resolved, NOUGEN_SCOPED_MIN_SCORE retired, NOUGEN_BM25_HALF_SCORE new, or-retry penalty resolved via tiering).
- Changes are UNCOMMITTED in the working tree by instruction (core.py, HARDENING.md, wargames/ledger.md, 2 new test files, test_shards.py).

## ⚠️ Known Issues & Workarounds
- Whole-brain pass now always runs on implicit-domain recall (2x DB fan-out); watch node search latency, fork to quality-gated fallback if p95 degrades.
- Old node process was running system Python; start_grid.py relaunched it on the repo venv with PYTHONPATH=src (patched code live).

## 📅 Upcoming Events
- GM review + commit of the working-tree changes; dedup-ghost reconciliation sweep; coverage-discrepancy recon.
