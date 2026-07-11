# WAR-GAME: fix-all-backfill-dream

**Mission**: Fix all 5 attention items from the 2026-07-11 token/status report, starting with arXiv backfill (Jul 7–10 gap) and a full dream-consolidation pass over all docs.
**Authored by**: Claude Fable 5 (Coach), 2026-07-11.
**Executor**: Coach orchestrates; OpenRouter free gemma + fallback parser do the dream heavy lifting (already wired in `dream_all.py`); arXiv API does backfill fetch. Resolves `(backfill_depth)` from arxiv-evolution ledger: GM ordered backfill.

## Ground truth (verified this session)
- Daily arxiv docs stop at **2026-07-06** in both vault and NouGen root (8,541 files each, mirrored). RSS scanner (`Sol-Ai/tools/arxiv_rss_scanner.py`) is today-only; RSS has no history → backfill needs `export.arxiv.org/api/query` by submittedDate.
- Scanner dedupes on `intelligence_shard_arxiv_{base_id}_*` glob → API backfill in same format is idempotent-safe.
- `dream_all.py` consolidates `event_type='DOCUMENTATION' AND consolidated=0` shards → semantic_knowledge. Free lanes only.
- Handoff-lane "182h STALE" is a sensor bug: handoffs live in subdirs, old glob was flat. Uncommitted `tools/lane_freshness.py` diff adds `**` pattern — must verify `glob(recursive=True)` in `_mtimes` or the fix is inert.
- nougen-shards MCP: `recall_memory` → "Connection closed" this session; fleet-registry MCP works.

## Move 1 — Today's scan (Jul 11)
- Action: run `arxiv_rss_scanner.py` as-is.
- Expect: JSON with ingested_count > 0 (weekday).
- Failure: fetch error / 0 new on a weekday → check RSS reachability; if arXiv unreachable, ABORT fetch moves, continue Moves 3+.

## Move 2 — Backfill Jul 7–10 via API
- Action: one-off script (scratchpad, env-resolved vault dir, UA w/ contact, ≥3s between pages, paged 100/call) querying cat:cs.AI submittedDate [20260707 → 20260711], writing scanner-identical shards.
- Expect: hundreds of new `intelligence_shard_arxiv_26/07.*` files; dedupe skips existing.
- Failure: HTTP 429/503 → back off 30s, halve page size; if still failing, ABORT (arXiv friction = abort condition from arxiv-evolution).
- Note: weekend Jul 4–5 announce gap is normal — zero papers for those submit days is not failure.

## Move 3 — Deep dream all docs
- Action: `python dream_all.py` in push-main workspace (background; OpenRouter free lane, 2s rate-limit built in).
- Expect: "Found N unconsolidated" then steady consolidation; exit with counts.
- Failure: OpenRouter auth/quota errors → regex shards fall back per-call already; if client init fails outright, switch model to local ollama gemma or run fallback parser only.
- Fork: if N > ~500 regex shards (2s each ⇒ >17min), let it run in background and proceed to Moves 4–5 in parallel.

## Move 4 — Handoff lane sensor fix
- Action: verify `_mtimes` uses `recursive=True`; run `lane_freshness.py --json`; expect handoffs OK (newest ≈ this session's handoff). Commit the file.
- Failure: still STALE → fix glob call, rerun, then commit.

## Move 5 — nougen-shards MCP probe
- Action: retry a nougen-shards tool; if dead, find server entry (.mcp.json / user config), probe its command manually, report root cause. Fix config if config-shaped; if process/env-shaped, document restart path.
- Failure signal: server binary/env path stale (Rule 0.2: suspect the value first).

## Move 6 — Codex leak + fleet under-use (process fixes)
- Action: add context-compaction guidance to AGENTS.md (Codex lane) + capture routing directive shard. No code.

## Abort conditions
- arXiv rate-limit friction persisting after backoff → stop fetch, report written vs pending.
- Vault write errors mid-batch → stop, report counts.
- dream_all DB lock contention with live mesh → stop dream, report, rerun after mesh idle.
