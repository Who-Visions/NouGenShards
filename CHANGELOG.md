# Changelog

All notable changes to NouGenShards will be documented in this file.

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
