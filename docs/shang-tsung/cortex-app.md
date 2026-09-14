# Shang Tsung: trace-cortex/cortex-app → NouGen

Fleet batch 2026-09-14T03:26:00+00:00: 4 lanes (nemotron-3-super, nemotron-3-nano:30b, gpt-oss:120b, gemma4:31b), one parallel wave via `coach.ask`. README-only input (`analysis/shang-tsung/donors/`); raw lane output in `analysis/shang-tsung/batch_20260913.json`.

- **License:** MIT. Permissive, so code may be ported with attribution.
- **Stars / language:** 898 / Python; last push 2026-08-26T05:00:11Z
- **What it is (lane 1):** Integrate Cortex's memory and reasoning mechanisms into NouGen to enable richer, cited, and self‑calibrating AI interactions.

## Consensus moves (≥2/4 lanes)

| Move | Lanes | Top-3 | NouGen status | Landing | Effort |
|---|---|---|---|---|---|
| **sleep-consolidation**: Runs a bounded sleep‑time pass that resolves contradictions and pre‑warms verified hot‑context packs. | 3/4 | 2 | partial | sleep-pass | S |
| **layered-persona-map**: Builds typed layers (voice, preferences, decisions, facts, episodic, entities, topics) into a whole‑person map. | 3/4 | 1 | partial | persona-layer | L |
| **contextual-memory-protocol**: Assembles minimal cited context using a token‑aware knapsack and delta channel to avoid re‑sending known tokens. | 2/4 | 2 | partial | context-assembly-engine | M |
| **trust-aware-knowledge-graph**: Walks a provenance‑tracked graph with bounded multi‑hop recall and personalized PageRank to surface connected facts. | 2/4 | 2 | new | knowledge-graph | M |
| **sha256-addressed-packs**: Stores memory packs as content‑addressable SHA‑256 blobs, making them immutable, replayable, and dedupable across lanes. | 2/4 | 0 | new | archive storage layer (extends self_archive) | S |

## Disagreements (<2 lanes; for Dave to adjudicate)

- `personalized-pagerank-recall` (1/4, new): Graph-based retrieval that surfaces nodes based on connectivity/centrality rather than just lexical or vector proximity.
- `session-delta-channel` (1/4, new): Stateful tracking of context already sent to an agent to avoid re-sending redundant tokens in subsequent turns.
- `canon-pressure` (1/4, partial): Handles contradictions by superseding older entries with deterministic safety rules.
- `destiny-shards` (1/4, new): Stores prospective‑memory triggers as shards that fire when conditions match, enabling future‑memory recall.
- `optional-e2e-encrypted-sync` (1/4, new): End‑to‑end encrypted multi‑device sync protocol that can be toggled on, keeping all data local by default.
- `revocable-per-tool-permissions` (1/4, new): Scoped, revocable permissions per AI tool with automatic redaction of disallowed fields before context is sent.
- `trust-aware-provenance` (1/4, partial): Scoped, revocable per-tool permissions with redaction and strict citation requirements for every retrieved fact.
