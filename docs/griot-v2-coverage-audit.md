# Griot v2 Coverage Audit

Audit date: 2026-09-16. This note records what the current implementation proves, rather than treating the relay's requested 28-class scope as completed by the existing skeleton.

## Verified and hardened

- A fleet node is covered only when the caller supplies an attempted, successful 2xx `NodeCoverageStatus`. Missing receipts are reported as unprobed; simulation failures remain useful for tests but cannot manufacture success for other nodes.
- All nine expected local shard DBs are considered. Missing files and query/schema errors appear in `coverage.failures`; only DBs whose query completed appear in `vault_dbs_scanned`.
- The local path resolves from `Path.home() / ".nougen" / "shards"`, and SQLite is opened read-only.
- Queries use the actual shard schema (`timestamp`, `title`, `content`, `tags`) and the `shards_fts` table. Matched totals come from a count query, separately from deterministic top-k materialization.
- Bounded temporal intent (currently YTD, MTD, and today as emitted by Retrieval v2) is applied to `shards.timestamp` before candidate counts and ranking, rather than relying on text relevance to recover the intended era.
- Per-DB FTS rankings are fused through Retrieval v2's deterministic RRF; cross-database raw BM25 scores are not compared directly.
- Returned artifacts preserve compound `id@dbN` identity, full selected content, and a SHA-256 of that content.
- A no-hit local FTS result is not an absence proof. Missing node receipts or vaults force `PARTIAL`/`DEGRADED` and the state-driven recovery path.

## Remaining scope

This module still does not perform remote node probes itself; callers must provide real receipts. Its coverage matrix currently reports remote nodes and local nine-DB coverage as separate dimensions, not a per-machine/per-vault matrix. Retrieval is a deterministic local FTS + bounded date-filter lane, not the full exact + lexical + trigram + semantic + graph + temporal + relay sweep described in relay 20260916T231614Z. It does not yet implement full amendment/retraction resolution, corpus identity validation, arbitrary historical date-window parsing, cursor continuation, evidence hydration from external pointers, or per-arm query-receipt persistence. Therefore the 28-class relay should not be reported fully resolved from these changes alone.

## Verification

`tests/test_griot_v2.py` uses temporary SQLite FTS databases to cover injected node failures, absent node receipts, missing expected DBs, unsuccessful HTTP status, exact candidate totals, deterministic top-k, compound IDs, and content hashes. No machine archive contents are required for those tests.
