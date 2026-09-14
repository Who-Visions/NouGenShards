# Shang Tsung: EverMind-AI/EverOS → NouGen

Fleet batch 2026-09-14T03:26:00+00:00: 4 lanes (nemotron-3-super, nemotron-3-super, gpt-oss:120b, gemma4:31b), one parallel wave via `coach.ask`. README-only input (`analysis/shang-tsung/donors/`); raw lane output in `analysis/shang-tsung/batch_20260913.json`.

- **License:** Apache-2.0. Permissive, so code may be ported with attribution.
- **Stars / language:** 12935 / Python; last push 2026-09-09T02:59:13Z
- **What it is (lane 1):** Extracted mechanisms from EverOS that could enhance NouGen's memory architecture with portable, file‑first and reflective capabilities.

## Consensus moves (≥2/4 lanes)

| Move | Lanes | Top-3 | NouGen status | Landing | Effort |
|---|---|---|---|---|---|
| **cascade-watcher**: File system watcher that detects edits to Markdown and propagates changes to indexes and downstream services. | 3/4 | 3 | new | Integration service – sync daemon linking file changes to SQLite/LanceDB updates. | M |
| **reflection**: Offline memory evolution that merges episode clusters and refines profiles/skills between sessions. | 3/4 | 1 | partial | Background job – periodic consolidation process updating summaries and skill extracts. | M |
| **orthogonal-retrieval**: Retrieval API that can filter by user_id, agent_id, app_id, project_id, session_id independently. | 3/4 | 0 | partial | Query layer – add multi‑dimensional ID filters to search endpoints. | M |
| **knowledge-wiki**: Editable, source‑backed Markdown knowledge pages with taxonomy, CRUD, and topic search. | 2/4 | 2 | new | Knowledge module – wiki service backed by the same Markdown source. | L |
| **markdown-source**: Store memories as canonical Markdown files that serve as the source of truth, editable and Git‑versioned. | 2/4 | 2 | new | Storage layer – treat Markdown as primary persistence alongside shards. | L |
| **multimodal-ingest-parser**: Add optional parsers for images, PDFs, audio, and office documents that extract text and metadata before ingestion. | 2/4 | 0 | new | ingestion pipeline | M |
| **user-agent-tracks**: Separate first‑class surfaces for user episodes/profiles and agent cases/skills, enabling orthogonal querying. | 2/4 | 0 | partial | Memory schema – distinct tables/collections for user‑centric and agent‑centric data. | M |

## Disagreements (<2 lanes; for Dave to adjudicate)

- `markdown-persistent-memory` (1/4, new): Persist every memory chunk as a canonical Markdown file that acts as the single source of truth, enabling human readability and Git‑style diffing.
- `local-stack` (1/4, partial): Unified three‑part local stack: Markdown + SQLite + LanceDB (or equivalent vector DB) without external dependencies.
- `versioned-markdown-diff` (1/4, new): Track changes to Markdown memory files with lightweight diffs and expose a history API for roll‑backs.
