# Changelog

All notable changes to NouGenShards will be documented in this file.

## [Unreleased]
### Added
- **NouGenMsg session uptime + universal title discovery** (`nougenmsg.py`, stacked on the runtime-sender branch): origin envelopes now stamp `session_started_at`, discovered at runtime (a SESSION+START env var, a time-shaped field on the session's discovered record, or the record file's own creation time), and `display_sender` renders the age at display time (`· up 2d4h`) so a stored message never shows a stale age. Title resolution is now a universal discovery pass: session stores are found at runtime (env-named `*SESSIONS_DIR`/`*SESSION_DIR` directories, then any "session"-named directory under the home dot-dirs), records are matched by whichever id-shaped field they carry, and titles are read from whichever title-shaped field the record carries — providers that expose no session title are covered with no provider named in the code. Tenant scope still blocks every discovery read.
- **NouGenTube Chrome extension** (`extensions/nougentube-chrome`, 0.16.1): YouTube side panel with transcript, summary, chat, highlights and a Morph tab. Morph cross-references the NouGenShards vault and the live web (Google via SerpAPI, Exa, Tavily, Context.dev, keyless DuckDuckGo last) and writes a plan with the Valerion 21-step pass, then checks every shard, web and timestamp citation in code. Routes: local Ollama, the NouGenOpen free fleet, or any provider key the user adds. Also: toolbar progress and a close guard for long jobs, long jobs keep the computer awake (power permission, setting to turn off), panel stays visible in narrow windows and high zoom, native controls follow the theme, external links send no referrer, Auto theme that follows YouTube then the system live, high-contrast and forced-colors support, extension icons, transcription of videos with no captions (local faster-whisper through the bridge), a Batch tab for up to 20 videos or a playlist, transcript translation, chat across the saved library, and Obsidian, HTML, CSV and JSON exports (feature comparison in `extensions/nougentube-chrome/docs/feature-matrix.md`). Search keys stay on the NouGenOpen bridge. Spec: `extensions/nougentube-chrome/docs/morph-spec.md`.
- **P1 FTS5 benchmark** (`tools/fts_bench.py`, `tools/fts_seed_corpus.json`): per-lane timings (raw FTS MATCH vs keyword vs vector vs hybrid), index-size tracking via `dbstat`, trigram-vs-plain comparison on one fixed corpus (60 shards, seed 20261116), and an `EXPLAIN QUERY PLAN` audit. Measured on this Linux VM: unicode61 is −52% FTS bytes, faster, and ranks better on whole-word queries than trigram — but the default stays trigram because the corpus has no substring/typo tier (trigram's purpose); see `docs/native-memory-p1-fts.md`. BM25 weight experiments (1.0/1.0, 10.0/1.0, 5.0/2.0) showed no variant beating the 5.0/1.0 default on both tiers, so weights are unchanged.
- **FTS env knobs** (`NOUGEN_FTS_TOKENIZER`, `NOUGEN_FTS_BM25_TITLE_WEIGHT`, `NOUGEN_FTS_BM25_BODY_WEIGHT`): tokenizer and BM25 weights are now env-selectable in `core.py`, defaults unchanged (trigram, 5.0/1.0); tokenizer is a vault-creation-time choice and a mismatch with an existing vault is logged, never silently rebuilt.
- **Native Memory Engine P0 — preservation (directive shard 31235@db6)**: `core.lane_health()` sensor (HARDENING §4, atlas 201/511) — read-only, never raising, reports per-DB health, embedding coverage %, durability contract, embedding provider status, and vector-cache freshness, with a `NOUGEN_MIN_COVERAGE_PCT` degraded threshold (default 50); regression suites `tests/test_lane_health.py` and `tests/test_p0_preservation.py` lock the schema, WAL + explicit `synchronous=FULL` durability contract, FTS5 sync triggers, tenant fail-closed boundaries, RRF fusion, and embed-at-ingest degradation to keyword-only. Durability contract documented in `docs/native-memory-durability.md`. No behaviour change: `lane_health` is additive and does not touch the recall path.
- **MCP Events wake transport** (#620): `FutureMCPNativeWakeTransport` sends a signed minimal wake envelope (Standard Webhooks v1, one event per request, stable event id, bounded retry, no retry on 410/413, 2xx = receipt only) to each active subscription and stays `unconfigured` when none exists. Plan eligibility is reported as `plan_eligible=None` (docs conflict); fallback transports remain the default notify order.
- **`voice_persona`** (#612): character briefs bound to `persona.py`.
- **Elevation Atlas** (`docs/elevation-atlas.md`): a 1000-step, repository-grounded elevation roadmap in ten zones (memory physics, capture, retrieval, graph, temporal/Griot, federation, truth/canon, security, scale, autonomous memory). Every step carries a status: ✅ only when a file and function implement it, 🟡 for partial with the gap named, ⬜ for missing with a landing spot. Steps cross-reference #551 and #550. It includes a ground-truth table that corrects the draft plan against main @ ae40d10, and the first five verified moves.

### Fixed
- **Tenant isolation in the NouGenMsg target resolver (#1100 follow-up)**: `build_target_table` put every other node in a tenant's table with `reachable=None`, which the resolver's None-means-reachable contract reads as reachable, so a tenant could resolve `@<other-node>`, `@all`/`@fleet`, and `@<lane-on-other-node>`; groups were built from the unscoped registry. The registry view is now tenant-scoped (`_registry_node_names()` returns only this node for a tenant, so no other node is in the table at all), groups expand from the scoped registry, and presence claims are validated against the full registry — a tenant can only plant presence on its own node, and no fleet node's name, alias, group, or self-alias can be smuggled in as a lane. Owner tables keep the None-means-reachable contract unchanged.
- **Destiny task reconciler durability gaps (#1096)**: publish/DONE crash window now re-publishes with a stable per-task `idempotency_key` (sinks dedupe on it) instead of double-publishing; a lease heartbeat renews the claim while `execute` runs so a long run is not re-queued mid-flight; `all_routes_down` burns an attempt and fails at `max_attempts` instead of re-queueing forever; destiny-less intents are skipped (`skipped_no_destiny`) instead of queued; `create_destiny` supersede runs under `BEGIN IMMEDIATE` and a refused `_transition` now rolls the new row back instead of leaving a dangling `superseded_by`.
- **`vault_put` on headless Linux (leg 20261116T165939Z)**: `keymaker._protect()` failed closed with `RuntimeError` whenever the `keyring` package was absent (or its backend unusable) and the plaintext escape hatch was unset, so every `vault_put` on the HF Space errored with "Error executing tool vault_put" while `vault_list` and shard writes kept working. The write path now falls back to machine-local AES-256-GCM (`enc1:` rows, 32-byte key in a 0600 file in the vault dir itself, tenant-scoped), so the secret still lands encrypted and round-trips through `get_secret`/`vault_list`. Plaintext is still only stored with explicit `NOUGEN_ALLOW_PLAINTEXT_VAULT=1`.
- **Codex P2 follow-ups on the `enc1:` fallback (same leg)**: (1) `_read_secret_row()` now decrypts under the key file beside the store the row was read from, so an `enc1:` row adopted from a diverged store no longer fails authentication against the active vault's key; (2) the local key is published atomically (temp file + hard link, never overwriting a competing writer's key) and a not-yet-populated key file is retried briefly, so concurrent first writes can no longer fail `vault_put` with `RuntimeError`.

## [1.3.1] - 2026-08-20
### Added
- **Dynamic Reasoning & Live Token Stream**: `OllamaClient` and `OpenAIClient` stream reasoning/thinking tokens live in dimmed ANSI styling with unbuffered real-time stdout delivery.
- **Predictive Relay Foresight in Chat**: Integrated active fleet handoffs directly into the chat prompt context, enabling proactive next-step anticipation.
- **Parallel Multi-Lane Federation**: `federated_retrieve` queries local shard databases, external SQL DBs, remote cloud nodes, and sibling SQLite vaults concurrently using thread pools.

### Fixed
- **Multi-Tenant Thread Isolation**: Fixed `ContextVar` loss in `federation.py` by propagating `copy_context().run` to worker threads, preventing tenant cross-talk.
- **FTS5 Multi-Keyword Title Boosting**: Corrected `_build_fts_query` in `local_vault.py` to evaluate and sum title hits across all query keywords.
- **Float32 Vector Deserialization in Cloud Sync**: Fixed Unicode decoding error in `nougen node push` by routing embeddings through `_embedding_for_json`.
- **Sub-Second Embed Timeout Truncation**: Fixed float-to-int truncation in `_embed_for_capture` and `embedding_backfill.py`.
- **SQLite Connection Leaks in `init_db()`**: Added `try/finally` protection around all table, trigger, and index creation logic.
- **Version Resolution Fallback**: `__init__.py` falls back gracefully to `pyproject.toml` when package is run directly from development checkout.
- **Skills Import Export**: Added missing `resolve_skills` and `format_instructions` helper wrappers in `skills.py`.
- **Google Gemini API Key Header Auth**: Migrated `GeminiClient.list_models` from query param auth to `x-goog-api-key` header auth.

## [1.3.0]
### Added
- **Private Vault** (`nougen_shards.private_vault`): encryption at rest for personal-scope
  content. AES-256-GCM per value under one 32-byte vault data key, the key itself DPAPI-wrapped
  through the Keymaker. Wire format `ngenc1:<b64(nonce||ct||tag)>`, with the format version bound
  as AEAD associated data so ciphertext cannot be replayed across future formats.
- **Sensitivity classification** (schema v2): `shards.sensitivity` (`normal` | `private` |
  `secret`) and `shards.enc`. `capture()` takes `sensitivity=`; `private`/`secret` bodies are
  encrypted immediately before INSERT, which is also what keeps the plaintext out of the
  `shards_fts` external-content index (its AFTER INSERT trigger reads `new.content`). Private
  shards are therefore discoverable by title and tag, not by body text -- a deliberate tradeoff,
  recorded here so it is not mistaken for a bug.
- **File lane**: `private_vault encrypt-file` / `decrypt-file`. An original is removed only after
  its ciphertext is decrypted back in memory and byte-compared to the source.
- **Key custody**: generating a data key always writes a one-time `RECOVERY_KEY.txt` and fails
  closed if it cannot -- DPAPI is user-bound, so a key with no recovery path is a data-loss bug
  for irreplaceable records. `load_key` sweeps known vault directories before minting so a
  config change cannot silently create a second key and orphan existing ciphertext.
- Env knobs: `NOUGEN_PRIVATE_KEY` (base64, for CI and non-Windows lanes),
  `NOUGEN_PRIVATE_KEY_FILE`, `NOUGEN_KEY_SEARCH_PATH`, `NOUGEN_SCHEMA_DB_GLOBS`,
  `NOUGEN_SECRETS_VAULT_DIR`.
- `tests/conftest.py` gives every test its own empty secrets vault. The tests were never isolated
  from the real vault -- the old CWD-relative default was doing it by accident, and making
  resolution deterministic exposed five tests that then read live credentials.
- 32 tests across `tests/test_private_vault.py` and `tests/test_keymaker_vault_resolution.py`.

### Fixed
- **The Keymaker secrets vault resolved to more than one place.** `VAULT_DIR` was
  `Path(os.getenv("NOUGEN_VAULT_DIR", ".nougen_vault"))`: `.nougen_vault` is CWD-relative, so the
  store moved with the working directory, and `NOUGEN_VAULT_DIR` is the *memory* vault, so
  honouring it aimed the secrets DB at a directory of 40+ shard databases and made
  `init_vault()`'s `icacls` call time out at 30s. Measured on a live deployment: 44 secrets across
  four stores, with `get_secret()` returning `None` in a way that reads as "never ingested"
  rather than "wrong file". Resolution is now `NOUGEN_SECRETS_VAULT_DIR`, else
  `~/.nougen/secrets`, and never `NOUGEN_VAULT_DIR`. Walking up from CWD to find a nearby
  `.nougen_vault` was implemented and rejected -- same CWD-sensitivity in longer form.
  `keymaker.find_legacy_stores()` reports fragmentation instead of silently following it.
- **Migration coverage**: `schema._vault_dbs()` discovers shard-bearing DBs by shape (does it have
  a `shards` table?) across `nougen_shards_*.db` *and* brain_scan's per-domain `*_vault.db`
  files. The old filename-only glob left domain vaults a schema version behind -- invisible until
  a write carrying a newer column hit one and failed.
- **Heterogeneous-schema tolerance**: index creation skips indexes whose columns a given DB lacks
  (domain vaults have no `utility_score`) instead of aborting that DB's whole migration. Skips are
  collected in `schema.SKIPPED_INDEXES` and printed by the CLI, never silently swallowed.
- The TypeScript port carried the identical CWD-relative and memory-vault-collision defect and
  now mirrors the Python resolution.

### Changed
- `core.hydrate()` decrypts encrypted bodies at every row-to-dict boundary. A shard whose key is
  unavailable returns a placeholder body instead of raising, so one unreadable row cannot take
  down an entire recall.
- `schema.TARGET_SCHEMA_VERSION` 1 -> 2. The migration is a pure widening: existing rows default
  to `normal`/unencrypted and nothing already stored changes meaning.
- `tools/ingest_provider_keys.py` no longer advertises `NOUGEN_VAULT_DIR` for secrets.

#### Previously unreleased
- **Node**: Remote MCP endpoint (streamable HTTP) at `/mcp` on the Space node,
  so the Claude mobile/web app can attach the node as a custom connector and
  any MCP client can use the memory over the network. Exposes only the memory
  surface (`recall_memory`, `capture_experience`, `mark_utility`,
  `node_status`); code execution and brain scan remain stdio-local. Gated by
  `NGS_NODE_TOKEN` (header or `?token=` query param for connector
  compatibility), deny-by-default like the REST API.
- **Recall**: Fuzzy retrieval lane grounded in `docs/theory/n-gram-topologies.md`
  (§8.2): fastText-style character trigrams with boundary markers, gated by the
  Szymkiewicz–Simpson overlap coefficient. Bridges typos and morphological
  variants ("automaton" → "automation") that exact-token FTS, substring LIKE,
  and trigram-FTS all miss. Fires only when the exact lanes return nothing, and
  exact hits always outrank fuzzy hits via explicit lane tiering.

### Fixed
- **Packaging**: Declared the previously-missing `numpy` dependency in `pyproject.toml`.
  `numpy` is imported in `src/nougen_shards/core.py` but was never declared, so a clean
  `pip install .` produced an installable package that crashed on first import of `core`.
  CI had been masking this by installing `numpy` manually. (Reproducibility / correctness.)

### Changed
- **Dependencies**: Added conservative lower-bound version pins to all runtime
  dependencies (e.g. `pydantic>=2.0`, `sqlalchemy>=2.0`, `openai>=1.0`). The codebase
  targets these majors; the floors prevent `pip` from resolving API-incompatible older
  majors while still allowing minor/patch upgrades. No behavior change (264 tests pass).

### Removed
- **Dependencies**: Dropped the unused, deprecated `google-generativeai` package from
  `pyproject.toml`. It was never imported anywhere in the repository (Gemini access uses
  raw HTTP in `models_client.py`), so it was pure install-size and supply-chain overhead.

## [1.1.0] - 2026-06-15
### Added
- **Security**: DavOs Gatekeeper middleware to enforce Mutation Gates on destructive actions, schema modifications, and deployment changes.
- **Optimization**: Reversed Compaction Hooks implementing Pointer Compaction for message history virtualization.
- **Analytics**: Kronos Temporal Engine for dynamic utility decay, access velocity momentum, and bi-temporal profile tracking.
- **Handoff**: Automated cross-agent session handoff registry and indexing database.
- **Tauri HUD**: Standalone Python sidecar compilation and bundling pipeline.

### Fixed
- UI crash on Tauri Cortex HUD startup when database status is null or connecting.
- JSONL parsing crash when processing complex list/dict payloads in conversation logs.
- Missing `nougen brain` subparser registration in CLI argument parser.

## [1.0.0] - 2026-06-10
### Added
- **Core**: Advanced Memory Substrate with SQLite, FTS5, and weighted relevance reranking.
- **Federation**: Universal Connector Fabric for SQL and remote Cloud Nodes.
- **Models**: Unified clients for OpenAI, Anthropic, Gemini, HF, OpenRouter, and local providers.
- **Resilience**: OpenRouter production routing with fallback, caching, and response healing.
- **Hardening**: `nougen doctor` for system diagnostics.
- **Node**: Production-ready Hugging Face Space node with persistent storage and write-auth.
- **History**: Time-series analytics with windowed horizons and ASCII sparklines.
- **Windows**: Self-healing `nougen.bat` bootstrap launcher.

### Changed
- Refactored CLI into a unified binary surface.
- Hardened SQL connector against identifier injection.

### Fixed
- UTF-8 console rendering for Windows environments.
- 1GB hard constraint for SQLite shard databases.

---
*Powered by Who Visions LLC.*
