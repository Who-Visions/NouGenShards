# War-Game: FTS Ranked-OR Fallback (HARDENING invariant 5)

**Author tier:** Fable/Coach (this file)
**Executor:** Coach-direct — small precision edit in `core.py` per routing rule 5
**Mission:** conversational multi-term queries must never die on FTS5 implicit-AND
semantics. Observed kill: "huggingface nougenai token" → 0 rows while
"huggingface" alone → thousands. Today the empty AND pass falls straight to a
LIKE `%whole query string%` scan, which is even stricter — the lane reports
"no relevant shards" while the data is sitting right there (broken-sensor
absence, invariant 4's cousin).

## Move 1 — Baseline red test
Write `tests/test_fts_or_fallback.py`: seed shards where only *one* token of a
multi-term query matches; assert retrieval still returns it.
- **Expected if it works:** test FAILS against current code (AND → empty →
  LIKE `%full query%` → empty).
- **Failure signal:** test passes pre-patch → my model of the bug is wrong.
- **Countermove:** inspect `_keyword_retrieve` trace; if LIKE somehow hits,
  the invariant is already satisfied — update HARDENING.md and stand down.

## Move 2 — Patch `_build_fts_match_query` + `_keyword_retrieve`
Add `joiner` param (default `" "` = implicit AND). In `_keyword_retrieve`,
when the AND pass returns 0 rows and the query has ≥2 tokens, retry the same
safe-quoted tokens joined with `" OR "` (bm25-ranked, so best-covering rows
still rank first). Only then fall to LIKE.
- **Expected:** red test goes green; all 293 existing tests stay green
  (single-token queries produce an identical expression → OR retry skipped).
- **Failure signal:** any existing retrieval test regresses.
- **Fork:** if regression is in ranking tests → OR pass is polluting results
  that AND used to scope; countermove: keep OR results but verify bm25
  ordering, don't touch scoring. If regression is OperationalError → quoting
  bug; countermove: reuse the exact same token-quoting path, no new escaping.

## Move 3 — Verify + land
Full suite, update HARDENING.md invariant 5 → ✅, commit pending diff + this
work on `claude-cli/atom-audit-fixes`, capture vault shard, leave handoff.
- **Expected:** 294+ passed, clean `git status` except intentional untracked.
- **Abort conditions:** (a) suite reveals the OR pass changes ranking of
  existing green tests — revert patch, ship red test as `xfail` + ledger note;
  (b) 30-min box expires mid-patch — commit war-game + red test only, hand off.

## Ledger
- (variable) Should OR-fallback results be score-penalized vs AND hits?
  Deferred — bm25 already ranks multi-token coverage higher. GM input welcome.
