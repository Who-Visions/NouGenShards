# NouGenShards Hardening Invariants

Born 2026-07-01, the night the vault went quiet for 3 days and nobody noticed.
Each entry is a class of failure observed in production, the invariant that
prevents it, and status. Agents: do not ship features that violate an invariant.

## 1. Capture must be structural, never voluntary
**Failure observed:** vault distillation lane stale since Jun 27; a used HF
credential (`NouGenShards_hgf_key`, 22 days old) never sharded. Manual capture
== eventual amnesia.
**Invariant:** every session leaves a trace with zero human/agent cooperation.
**Status:** ✅ agent lane — `tools/handoff_guard.py` writes a vault intelligence
shard on every sessionend (deduped, stdlib-only, exception-swallowed).
⬜ product lane — app session close must call the same unconditional capture.

## 2. Shards are born recallable (embed at ingest)
**Failure observed:** ~27k shards across 3 clusters with `embedding=NULL`;
semantic recall returned nothing while claiming "no relevant shards."
**Invariant:** `core.capture()` embeds at write time (local ollama,
`NOUGEN_EMBED_MODEL`, 10s timeout); failure degrades to keyword-only for that
shard, never blocks capture. Backfill sweeps stragglers.
**Status:** ✅ embed-at-ingest in `core.capture()` (283 tests green).
✅ backfill tool (`embedding_backfill.py`). ⬜ scheduled weekly backfill sweep.

## 3. Pipelines must announce their own death
**Failure observed:** sync agent dead since May 9, arxiv scanner dead since
Jun 18 — both failed silently for weeks.
**Invariant:** every ingestion lane exposes last-success age; the startup probe
reports any lane stale > 48h as a warning, not silence.
**Status:** ✅ `tools/lane_freshness.py` — stdlib-only sensor (never raises,
exits 0, ASCII output) reporting newest-artifact age for arxiv / vault-intel /
handoff lanes with per-lane thresholds; `--json` for probes. ✅ daily 8 AM
scheduled task runs the arxiv RSS scan + freshness report with 30-day API
backfill as the recovery path (2026-07-06: backfilled 4,645 papers after the
lane sat dead for 19 days). ⬜ wire `lane_freshness.py --json` into
`sol_hi_probe.ps1` / `mesh_health` for session-start visibility.

## 4. Empty result ≠ healthy "no match"
**Failure observed:** recall lanes answered "no relevant shards" while the
semantic index was 100% dead — a broken sensor reporting absence as fact.
**Invariant:** recall responses carry lane health (embedding coverage %, FTS
reachable). Agents must not assert absence from a degraded lane.
**Status:** ✅ `core.lane_health()` reports total shards + embedding coverage %
across the DB grid; both empty-recall paths (`compile_recall_packet`,
`compile_recall_packet_dual`) now emit that coverage instead of a bare marker,
flagging "DEGRADED SEMANTIC LANE — absence unverified" below the
`NOUGEN_MIN_COVERAGE_PCT` threshold (default 50, env-discovered per Rule 0.2).
Regression suite `tests/test_lane_health.py`. ⬜ surface the same metadata in
`federated_retrieve` cross-node returns.
**Known flaky:** `tests/test_graph.py::test_related_relation_filter` leaks/depends
on global DB state under `pytest-randomly` order (passes isolated + with fixed
order); pre-existing, unrelated to this invariant.

## 5. Multi-term queries must not silently AND
**Failure observed:** FTS returned 0 for "huggingface nougenai token" but
thousands for "huggingface" — conversational queries die on AND semantics.
**Invariant:** FTS falls back to ranked OR when the AND query returns empty.
**Status:** ✅ two-pass MATCH in `_keyword_retrieve` (AND → ranked OR → LIKE);
regression suite `tests/test_fts_or_fallback.py` (4 tests, incl. AND-preferred
and bm25 coverage-ordering guards). War-game: `wargames/fts-or-fallback.md`.

## 6. No machine paths in code
**Failure observed:** hardcoded machine-specific user paths in scanner + hook meant
public users would write junk dirs; scripts break on any other machine.
**Invariant:** resolution chain only: `NOUGEN_VAULT_DIR` env →
`~/.nougen/config.json` → repo-local `.vault` → `~/.nougen/shards`.
**Status:** ✅ handoff_guard, arxiv scanner, lane_freshness. ✅ repo-wide code
audit (2026-07-06): no machine-specific path literals remain in `src/` or
`tools/` outside resolution fallbacks. ⬜ periodic re-audit in CI to prevent
regression.

## 7. The substrate is not a landfill
**Failure observed:** lockfiles, base64 blobs, and SVG JSON sharded as
"knowledge" — polluting recall and wasting embeddings.
**Invariant:** ingest gate rejects/flags low-signal content (density_score
threshold + extension/shape denylist); bulk importers must classify before
capture.
**Status:** ✅ structural blob gate in `core.capture()` — `_looks_like_blob`
rejects base64/hex/minified dumps (longest whitespace-free run > `NOUGEN_JUNK_MAX_TOKEN`
that is ≥ `NOUGEN_JUNK_ALPHABET_RATIO` base64/hex charset); same skip contract
as dedup. Opt-in density floor (`NOUGEN_MIN_DENSITY`, default 0.0 = off) for
stricter filtering. All thresholds env-discovered. `tests/test_ingest_junk_gate.py`
(4 tests); war-game `wargames/ingest-junk-gate.md`. ⬜ one-time read-only audit
of existing blob-shaped shards before any live-vault purge (GM sign-off).

## 8. Credentials live in the Keymaker, never in shards
**Failure observed:** key events were neither sharded (amnesia) nor vaulted
(until asked) — and shards must never hold the fix (plaintext secrets).
**Invariant:** secret values → DPAPI vault (`agent_secrets.db`) + fingerprint
ledger only. Shards may reference key *names* and fingerprints, never values.
**Status:** ✅ doctrine + Atibon flow. ✅ structural pre-capture guard —
`core.capture()` runs `brain_scan.redaction.redact_content` over title/content/
tags before hashing, embedding, or writing (redacts `hf_`/`sk-`/`AIza`/JWT/DB-URL/
private-key shapes), so every write path (MCP `capture_experience`, hooks, fleet)
is covered, not just bulk import. Regression suite `tests/test_capture_secret_guard.py`;
war-game `wargames/capture-secret-guard.md`. ⬜ backfill sweep to redact any
pre-guard shards already in the substrate.
