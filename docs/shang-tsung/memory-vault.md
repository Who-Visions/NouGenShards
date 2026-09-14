# Shang Tsung: MihaiBuilds/memory-vault → NouGen

Fleet batch 2026-09-14T03:26:00+00:00: 4 lanes (nemotron-3-super, nemotron-3-nano:30b, gpt-oss:120b, gemma4:31b), one parallel wave via `coach.ask`. README-only input (`analysis/shang-tsung/donors/`); raw lane output in `analysis/shang-tsung/batch_20260913.json`.

- **License:** MIT. Permissive, so code may be ported with attribution.
- **Stars / language:** 63 / Python; last push 2026-09-14T03:10:10Z
- **What it is (lane 1):** NouGen should absorb hybrid semantic‑keyword search, MCP‑driven memory I/O, knowledge‑graph extraction, and token‑budgeted recall mechanisms to enhance its distributed shard architecture.

## Consensus moves (≥2/4 lanes)

| Move | Lanes | Top-3 | NouGen status | Landing | Effort |
|---|---|---|---|---|---|
| **knowledge-graph**: automatically extracts entities and relationships to build a graph of memory connections | 3/4 | 3 | partial | canon_pressure layer | M |
| **memory-spaces**: isolates memories into separate namespaces for project/domain separation | 3/4 | 1 | covered | shard naming layer | S |
| **mcp-integration**: exposes recall, remember, forget, purge, move, status tools via Model Context Protocol for external LLM interaction | 2/4 | 1 | new | agent lane hand‑off layer | L |

## Disagreements (<2 lanes; for Dave to adjudicate)

- `central-pgvector-backend` (1/4, new): Replace the distributed SQLite‑shard layer with a single PostgreSQL database augmented by the pgvector extension, enabling native hybrid (vector + full‑text) queries in one place.
- `hybrid-search` (1/4, partial): combines vector similarity with full‑text keyword matching using RRF to retrieve memories
- `mcp-resource-templates` (1/4, new): Exposing system health and space statistics as URI-based MCP resources (memory://stats) rather than just tools.
- `soft-delete-purge` (1/4, new): Two-stage deletion process: marking memories as 'forgotten' (soft-delete) followed by a time-based permanent purge.
- `cli‑tooling` (1/4, new): Implement a lightweight command‑line interface (ingest, search, status) that forwards calls to the REST API or MCP server.
- `cpu-optimized-embedding` (1/4, covered): Standardizing on lightweight, CPU-native sentence-transformers (all-MiniLM-L6-v2) for low-latency local ingestion.
- `docker‑compose‑deployment` (1/4, new): Provide a one‑command Docker Compose file that spins up PostgreSQL, the Memory‑Vault service, and optional monitoring containers.
- `local-llm-chat` (1/4, new): provides UI to query memories via local LLM with source attribution for verification
- `rest-api-gateway` (1/4, new): Expose all memory operations (ingest, search, recall, forget, status) through a FastAPI‑based REST endpoint with authentication and rate‑limiting.
- `token-budgeted-recall` (1/4, new): limits recall packet size by token budget and scores memories with utility/decay before retrieval
- `unified-hybrid-schema` (1/4, covered): Co-locating vector embeddings, full-text search indexes, and relational metadata in a single table/database to eliminate sync lag.
