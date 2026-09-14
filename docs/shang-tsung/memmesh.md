# Shang Tsung: ThinkfleetAI/memmesh → NouGen

Fleet batch 2026-09-14T03:26:00+00:00: 4 lanes (nemotron-3-super, nemotron-3-nano:30b, gpt-oss:120b, gemma4:31b), one parallel wave via `coach.ask`. README-only input (`analysis/shang-tsung/donors/`); raw lane output in `analysis/shang-tsung/batch_20260913.json`.

- **License:** Apache-2.0. Permissive, so code may be ported with attribution.
- **Stars / language:** 441 / Rust; last push 2026-08-25T16:50:04Z
- **What it is (lane 1):** NouGen should adopt MemMesh's local-first heuristic memory capture, bi‑temporal storage, hybrid semantic‑keyword search, token‑budgeted recall, consolidation, and supersede handling to enrich its autonomous memory system.

## Consensus moves (≥2/4 lanes)

| Move | Lanes | Top-3 | NouGen status | Landing | Effort |
|---|---|---|---|---|---|
| **bi_temporal_memory**: Stores memories with two timestamps — event time and learning time — enabling distinction between when something happened and when it was recorded. | 3/4 | 3 | new | memory/core | M |
| **consolidation**: Detects near‑duplicate memories and collapses them into a single survivor without data loss, optionally dry‑run. | 3/4 | 1 | partial | memory/consolidate_skill | M |
| **substantive_capture**: Heuristically filters raw agent output to retain only substantive facts, preferences, and decisions for storage. | 2/4 | 1 | partial | memory/observe_skill | S |

## Disagreements (<2 lanes; for Dave to adjudicate)

- `heuristic-observe` (1/4, new): Automatically filters raw conversational text and extracts substantive facts without any LLM calls, feeding them into the memory store.
- `semantic_keyword_search` (1/4, partial): Performs hybrid search using local embeddings combined with keyword matching, filtered by scope and recency.
- `soft-delete-audit` (1/4, new): Implements soft‑delete with an append‑only audit log, allowing reversible forgetting and full provenance tracking.
- `spreading-activation-prefetch` (1/4, new): Anticipatory retrieval that fetches related nodes in the memory graph before they are explicitly queried.
- `graph-reasoning-layer` (1/4, partial): Adds multi‑hop knowledge‑graph reasoning, anticipatory retrieval, and context‑building over the autobiographical graph.
- `local-embedding-download` (1/4, partial): Downloads a small, self‑contained embedding model on first use and uses it for hybrid semantic‑keyword search (RRF fusion).
- `local‑remote‑sync` (1/4, new): Bi‑temporal synchronization between local SQLite shards and optional remote Postgres/MCP server, preserving provenance and conflict resolution.
- `non-destructive-supersede` (1/4, partial): Versioning system where corrections create a new record that points to the old one for provenance rather than overwriting.
- `supersede_handling` (1/4, covered): Records corrections as superseding entries while preserving the original for provenance, supporting canon_pressure.
- `token_budgeted_recall` (1/4, new): Limits recall packets to a token budget, prioritizing high‑utility memories and discarding low‑value matches.
