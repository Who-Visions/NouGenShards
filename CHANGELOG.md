# Changelog

All notable changes to NouGenShards will be documented in this file.

## [1.2.0] - 2026-08-07
### Added
- **Private Vault** (`nougen_shards.private_vault`): encryption at rest for personal-scope
  content. Envelope scheme — AES-256-GCM per value under a single 32-byte vault data key,
  the key itself DPAPI-wrapped through the Keymaker. Wire format `ngenc1:<b64(nonce||ct||tag)>`,
  with the format version bound as AEAD associated data so ciphertext cannot be replayed
  across future formats.
- **Sensitivity classification** (schema v2): `shards.sensitivity` (`normal` | `private` |
  `secret`) and `shards.enc`. `capture()` takes a `sensitivity=` argument; `private` and
  `secret` bodies are encrypted immediately before INSERT, which also keeps the plaintext
  out of the `shards_fts` external-content index. Private shards are therefore discoverable
  by title and tag, not by body text — a deliberate tradeoff, documented here so it is not
  mistaken for a bug.
- **File lane**: `private_vault encrypt-file` / `decrypt-file` CLI for documents. An original
  is deleted only after its ciphertext has been decrypted back in memory and byte-compared
  to the source; a failed verification keeps the original and raises.
- **Key custody**: generating a data key always writes a one-time `RECOVERY_KEY.txt` beside
  the vault, and fails closed if that file cannot be written — DPAPI is user-bound, so a key
  with no recovery path is a data-loss bug for irreplaceable records. `load_key` sweeps every
  known vault directory before minting a new key so a `NOUGEN_VAULT_DIR` change cannot
  silently create a second key and orphan existing ciphertext.
- Environment knobs: `NOUGEN_PRIVATE_KEY` (base64 key, for CI and non-Windows lanes),
  `NOUGEN_PRIVATE_KEY_FILE`, `NOUGEN_KEY_SEARCH_PATH`.
- `tests/test_private_vault.py` — 20 tests covering round-trip, tamper rejection, wrong-key
  rejection, ciphertext-on-disk, FTS absence, graceful degradation when the key is missing,
  verified file deletion, recovery-file guarantee, key-divergence prevention, and migration
  idempotency.

### Changed
- **Migration coverage**: `schema._vault_dbs()` now discovers shard-bearing DBs by shape
  (does it have a `shards` table?) across `nougen_shards_*.db` **and** brain_scan's per-domain
  `*_vault.db` files, overridable via `NOUGEN_SCHEMA_DB_GLOBS`. The old filename-only glob left
  domain vaults a schema version behind — invisible until a write carrying a newer column
  hits one and fails.
- **Heterogeneous-schema tolerance**: index creation skips indexes whose columns a given DB
  lacks (the domain vaults have no `utility_score`) instead of aborting that DB's whole
  migration. Skips are collected in `schema.SKIPPED_INDEXES` and printed by the CLI — never
  silently swallowed.
- `core.capture()` accepts `sensitivity`; existing calls are unaffected and keep writing
  plaintext `normal` shards.
- `core.hydrate()` decrypts encrypted bodies at every row-to-dict boundary. A shard whose key
  is unavailable returns a placeholder body instead of raising, so one unreadable row cannot
  take down an entire recall.
- `schema.TARGET_SCHEMA_VERSION` 1 → 2. Migration is a pure widening: existing rows default to
  `normal`/unencrypted and nothing already stored changes meaning. Applied to the live vault
  with per-DB `.bak` backups across every shard-bearing DB, with zero row drift.

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
