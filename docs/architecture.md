# The Metameric Memory Engine: 21 Steps of Orchestration

NouGenShards (NGS) is not just a database wrapper; it is an implementation of a 21-step cognitive architecture. It treats the chaotic output of disparate AI tools as a single, continuous stream of machine experience.

We do not ask AI to remember. We reverse-engineer where it stores its state, abstract the invariants, and orchestrate convergence into a unified local memory substrate.

Here is the exact software architecture mapped to the 21-step operating loop:

## Theoretical Foundation: The Architecture of Adjacency
The Metameric Memory Engine is mathematically grounded in the [Architecture of Adjacency](theory/n-gram-topologies.md) and the [Clinical Handoff Convergence Theory](theory/clinical-handoffs.md). We leverage N-gram topologies and clinical safety protocols (SBAR/5 Ps) to transform raw symbolic streams into resilient, state-conserving agent boundaries.

---

## Phase 1: The Reconnaissance (Discovery & Parsing)
1. **Metamers**: The engine identifies disparate AI tool histories (`.claude`, `.cursor`, `.gemini`) that represent the same underlying phenomenon (machine experience).
2. **Activate Orchestration**: `nougen brain scan` initializes the environment discovery pipeline.
3. **Deep Grep Latent Structure**: `brain_scan.scanner` crawls the local filesystem, identifying high-confidence dotfolders and hidden state files.
4. **Surface Leverage**: `brain_scan.classifiers` scores the discovered files, isolating high-utility target files from raw noise.

## Phase 2: The Extraction (Ingestion & Normalization)
5. **Extract Invariants**: `brain_scan.parsers` decodes JSON, JSONL, and MD logs, stripping the proprietary wrappers to find the invariant truth (the actual prompt/response).
6. **Copy Successful Topology**: `brain_scan.importer` maps the extracted truth into a standardized `NormalizedRecord`.
7. **Transpose Patterns**: The system normalizes the data structures across all supported AI tools into a single memory schema.
8. **Combine Compatible Systems**: `federation.py` unifies the local SQLite shards, remote SQL clusters, and the Who Visions Cloud Gateway.

## Phase 3: The Substrate (Storage & Hardening)
9. **Synthesize Coherent Signal**: Raw traces are compiled into discrete, context-rich "Shards" of memory.
10. **Integrate Constraints**: `brain_scan.redaction` aggressively strips API keys (`sk-...`, `gl-pat-...`) and skips dangerous directories to enforce local security boundaries.
11. **Transform Architecture**: `core.py` manages a 9-node SQLite cluster (1GB limits) using Deterministic Hash-Based Routing for O(1) reads.
12. **Refactor Complexity**: `core.capture` calculates an MD5 hash of every shard, ensuring immediate O(1) deduplication across the entire 9-DB cluster.

## Phase 4: The Dream State (Evolution & Recall)
13. **Compress Noise**: `fts5` tokenization drops stopwords and uses trigrams to allow for high-speed, noisy text matching.
14. **Expand Solution Space**: `core.retrieve` uses Vector Embeddings and `cosine_similarity` to find semantically related shards even if keywords don't match.
15. **Remix Viable Patterns**: `core.compile_recall_packet` batches the best historical solutions into an injected payload for the LLM.
16. **Invert Assumptions**: We do not inject context into every prompt; we use `OpenRouter` caching arrays and sticky `session_id`s to keep history server-side.
17. **Reverse-Engineer Intent**: `core.mark_utility` (outcome-driven update of the usefulness prior) adjusts the `utility_score` of a shard based on whether the recalled memory actually worked in practice.
18. **Reconstruct Coherence**: `history.py` graphs the total memory growth across all platforms into a single, unified timeline.
19. **Stabilize Reasoning**: `decay_utility_scores` runs a slow, background 0.95x multiplier to prune stale memories over time, ensuring only high-signal knowledge survives.

## Phase 5: The Loop
20. **Iterate Recursively**: The `FastMCP` server (`mcp.py`) exposes these primitives, allowing external coding agents to trigger their own memories, rank their own utility, and promote their own contexts autonomously.
21. **Orchestrate Convergence into NGS**: The final outcome. Chaotic multi-tool development is centralized into a singular, owned, indestructible local memory engine.
