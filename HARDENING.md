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
**Failure observed:** a large share of shards across multiple clusters carried
`embedding=NULL`; semantic recall returned nothing while claiming "no relevant
shards."
**Invariant:** `core.capture()` embeds at write time (local ollama,
`NOUGEN_EMBED_MODEL`, `NOUGEN_EMBED_TIMEOUT` fallback 10s); failure degrades to
keyword-only for that shard, never blocks capture. Backfill sweeps stragglers.

**⚠️ This section claimed ✅ for two months while the code did not implement it.**
Corrected 2026-08-14. `core.capture()` accepted `embedding` as an optional
*parameter* and stored whatever it was handed; it never called an embedder, and
`NOUGEN_EMBED_MODEL` appeared nowhere in `core.py` — only in the backfill tool.
So coverage tracked *backfill runs and ollama uptime*, not writes. Measured
consequence, as a share of shards written in each month:

| month | `embedding IS NULL` |
|---|---|
| 2026-06 | 0.0% |
| 2026-07 | 47.5% |
| 2026-08 | 63.6% |

June read 0% because a backfill had been run, which is exactly what made the
false ✅ look earned. Just under **half the corpus** was invisible to semantic
recall — and the rate was still climbing month over month, so this was an
actively widening gap rather than settled legacy debt.

Note the irony against §3 below: the embed path failed silently for two months
while the section one heading down demands pipelines announce their own death.

**Status:** ✅ embed-at-ingest genuinely wired into `core.capture()` — a miss is
now counted in `core.EMBED_AT_CAPTURE_MISSES` and logged at WARNING rather than
swallowed, and is verified three ways (embedder up → 0 NULL; embedder down →
shard still captured, warning raised, counter incremented; `NOUGEN_EMBED_AT_CAPTURE=0`
kill switch honored). ✅ backfill tool (`embedding_backfill.py`), which no longer
spawns `nvidia-smi` per row (`NOUGEN_VRAM_CHECK_EVERY`, fallback 64).
⬜ scheduled weekly backfill sweep.

**Lesson for future entries in this file:** a ✅ here must cite the mechanism, not
the intent. "Embeds at write time" was aspirational; the check that would have
caught it is "does the write path call an embedder at all."

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
**Status:** ✅ executed 2026-08-16: two-pass MATCH in `_keyword_retrieve`
(AND → ranked OR → LIKE), with OR-retry hits tiered BELOW full-coverage
AND/LIKE hits so a one-token OR match can never displace an all-token match
(the naive retry regressed 5 ranking tests on small corpora where trigram
bm25 is ~1e-6 and rounds away). Regression suite
`tests/test_fts_or_fallback.py` (single-token survival + bm25
coverage-ordering). War-game: `wargames/fts-or-fallback.md`.

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

## 9. Stored embeddings are not plaintext (CANDIDATE — dream-surfaced 2026-07-07)
**Failure model (not yet observed here):** dense embeddings invert back to their
source text with high fidelity (arXiv 2606.26373). Invariant 8 redacts the *text*
field at capture, but the `embedding` BLOB is stored raw — so a leaked
`nougen_shards_*.db` could reconstruct redacted/sensitive content from its vectors.
Document-side embedding protection is empirical obfuscation, not a cryptographic
primitive (known-plaintext Procrustes recovers a rotation from ~retained-dim pairs).
**Invariant:** a leaked vault must not trivially invert to its source text.
**Status:** ⬜ war-game first (`wargames/embedding-inversion.md`, TODO). Candidate
mitigation: SVD-truncate + owner-held orthogonal rotation of stored vectors,
env-gated (`NOUGEN_EMBED_ROTATION`), applied symmetrically on read/write so cosine
ranking is preserved. Must not regress retrieval determinism or the tests. Connects
to invariant 8 (secret-guard) and the "not a black box" sovereignty thesis.

## 10. Runtime source and liveness must be recoverable
**Failure observed:** the origin supervisor lived only under a machine-local
`.nougen` directory, and `/health` alone could report green while authenticated
MCP calls were broken.
**Invariant:** the supervisor is versioned, installed atomically from the
checkout, and a scheduled probe exercises an authenticated MCP recall.
**Status:** ✅ `tools/start_grid.py` is the source of truth; `tools/install_grid_supervisor.ps1`
backs up and hash-verifies the runtime copy at `%USERPROFILE%/.nougen/bin/start_grid.py`.
`tools/gateway_probe.py` resolves its target from env/config, records a
non-secret JSON result plus a `.alert` marker, and returns non-zero on any
auth/MCP failure. `tools/install_gateway_probe_task.ps1` installs the bounded,
CPU-only scheduled probe. ✅ `tools/vault_backup_restore.py` makes online SQLite
snapshots and runs a temporary restore/integrity-check drill. ⬜ external backup
volume and notification transport remain operator choices. The drill was
validated against `graph.db`; the larger shard stores can be resumed safely in
chunks with repeated `--only nougen_shards_N.db` invocations.
