# Changelog

All notable changes to NouGenShards will be documented in this file.

## [Unreleased]
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
