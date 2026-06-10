# 🪩 NouGenShards: Shard History Implementation Plan (Coach Apollo)

## OBJECTIVE
Implement a time-series analytics substrate for the Shard Layer. Track the creation, access, and utility evolution of machine memory over multiple horizons (24h to 1 Year).

## ARCHITECTURE (2-YEAR HORIZON)
- **Substrate**: Dedicated `history.db` to prevent bloat in the memory-core shards.
- **Event Stream**: Every `capture`, `retrieve`, and `mark_shard` action triggers an asynchronous event log.
- **Aggregation**: Federated polling across the 9-DB cluster to reconstruct historical state snapshots.
- **Bayesian Drift**: Track the 'Utility Prior' over time to identify decaying knowledge patterns.

## TASK REGISTRY (DELEGATED TO FLEET)

### PHASE 1: EVENT LOGGING [1-200]
1.  Create `src/nougen_shards/history.py`.
2.  Define `shard_events` schema: `(shard_id, event_type, old_score, new_score, timestamp, metadata)`.
3.  Update `core.capture` to emit `CREATED` event.
4.  Update `core.retrieve` to emit `ACCESSED` event.
5.  Update `core.mark_shard` to emit `UTILITY_CHANGE` event.
... [Tasks 6-200: Hardening, indexing, and WAL optimization for history logs] ...

### PHASE 2: WINDOWED AGGREGATION [201-500]
201. Implement `get_growth_rate(window)` logic.
202. Implement `get_utility_trend(shard_id, window)` logic.
203. Create `HistoryEngine` class in `history.py`.
... [Tasks 204-500: Complex SQL for rolling averages and windowed counts across 9 DBs] ...

### PHASE 3: BAYESIAN DRIFT & RERANKING [501-800]
501. Implement `Module 19: Stabilize Reasoning` check for score volatility.
502. Add `decay_score(shard_id)` to penalize stale information.
... [Tasks 503-800: Integrating time-weighting into the retrieval likelihood synthesis] ...

### PHASE 4: EXECUTIVE CLI & VISUALS [801-1000]
801. Add `nougen stats` command.
802. Add `--period` flag (24h, week, month, quarter, year, custom).
803. Add `nougen trends` for utility visualization.
... [Tasks 804-1000: ASCII sparklines and data export for Next.js 16 site] ...

## EXECUTION MANTRA
Deep Grep. Leverage. Copy. Combine. Transform. Refactor. Remix.

---
Coach Apollo: "Play initiated. Stadium locked. Fleet advancing."
