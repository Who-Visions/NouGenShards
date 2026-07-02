# Changelog

All notable changes to NouGenShards will be documented in this file.

## [Unreleased]
### Added
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
