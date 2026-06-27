/** Federated Retrieval Engine. Merges local substrate, external DBs, and cloud nodes. (TS mimic of federation.py) */
import * as core from "./core.js";
import { query_external_dbs } from "./connectors/sql.js";
import { query_cloud_shards } from "./connectors/cloud.js";
import * as keymaker from "./keymaker.js";
import type { Shard } from "./core.js";

/**
 * Module 8: Combine Compatible Systems.
 * Polls local Shard substrate, external DBs, and remote cloud nodes.
 * (async in the TS port because cloud polling rides fetch)
 */
export async function federated_retrieve(
  query: string,
  limit: number = 3,
  query_embedding: number[] | null = null,
): Promise<Shard[]> {
  // 1. Get Local Shards (weighted relevance blend)
  const local_results = core.retrieve(query, limit, query_embedding);

  // 2. Get Configs from Keymaker
  const external_configs = keymaker.list_external_dbs();
  const cloud_configs = keymaker.list_cloud_nodes();

  // 3. Query External DBs if configured.
  // Remote sources must never abort federation: a throwing external/cloud
  // source is logged and skipped so local_results always survive.
  // (Module 10: Graceful Degradation)
  let external_results: Shard[] = [];
  if (external_configs.length) {
    try {
      external_results = query_external_dbs(query, external_configs, limit);
    } catch (exc) {
      console.warn(
        `[federation] external DBs skipped (federation continues): ${String(exc)}`,
      );
      external_results = [];
    }
  }

  // 4. Query Cloud Nodes if configured
  let cloud_results: Shard[] = [];
  if (cloud_configs.length) {
    try {
      cloud_results = await query_cloud_shards(query, cloud_configs, limit);
    } catch (exc) {
      console.warn(
        `[federation] cloud nodes skipped (federation continues): ${String(exc)}`,
      );
      cloud_results = [];
    }
  }

  // 5. Merge and re-rank via weighted relevance blend
  // (Module 21: Orchestrate Convergence)
  const combined = [...local_results, ...external_results, ...cloud_results];
  combined.sort((a, b) => (b.final_score ?? 0) - (a.final_score ?? 0));

  return combined.slice(0, limit);
}
