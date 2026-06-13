/** NouGenShards: Persistent local memory for coding agents. (TS mimic of __init__.py) */
export { capture, retrieve, mark_shard, compile_recall_packet } from "./core.js";
export { federated_retrieve } from "./federation.js";
export { HistoryEngine, log_event, init_history_db } from "./history.js";
export { link_shards, related_shards } from "./graph.js";

export const __version__ = "1.0.0";
