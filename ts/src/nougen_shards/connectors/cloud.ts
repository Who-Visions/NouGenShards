/** Cloud Connector for remote NouGenShards instances. (TS mimic of connectors/cloud.py) */
import type { Shard } from "../core.js";

/**
 * Queries remote NouGenShards nodes and maps results to standard format.
 */
export async function query_cloud_shards(
  query: string,
  cloud_configs: Record<string, any>[],
  limit: number = 3,
): Promise<Shard[]> {
  const results: Shard[] = [];

  for (const conf of cloud_configs) {
    const url = String(conf.url).replace(/\/+$/, "");
    const name = conf.name as string;

    try {
      // POST /search
      const payload = { query, limit };
      const res = await fetch(`${url}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(5000),
      });
      const remote_data = await res.json();
      if (Array.isArray(remote_data)) {
        for (const r of remote_data) {
          // Normalize to local shard shape
          results.push({
            id: `cloud_${conf.id}_${r.id}`,
            event_type: `CLOUD_${r.event_type ?? "SHARD"}`,
            title: r.title ?? "Untitled Cloud Shard",
            content: r.content ?? "",
            tags: r.tags ?? "[]",
            utility_score: r.utility_score ?? 1.0,
            access_count: r.access_count ?? 0,
            file_hash: r.file_hash ?? "",
            final_score: r.final_score ?? 0.45,
            _db_index: `cloud_${name}`,
          });
        }
      }
    } catch {
      // Silent fail to prevent blocking the federation loop
      // (Module 10: Graceful Degradation)
      continue;
    }
  }

  return results;
}

/** Pushes a list of shards to a remote cloud node. */
export async function push_to_cloud(shards: Shard[], cloud_url: string, token: string): Promise<Record<string, any>> {
  const url = cloud_url.replace(/\/+$/, "");
  const payload = { shards };
  try {
    const res = await fetch(`${url}/sync/push`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-NGS-Token": token },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10000),
    });
    return (await res.json()) as Record<string, any>;
  } catch (e) {
    return { status: "error", message: String(e) };
  }
}

/** Pulls all shards from a remote cloud node. */
export async function pull_from_cloud(cloud_url: string, token: string): Promise<Shard[]> {
  const url = cloud_url.replace(/\/+$/, "");
  try {
    const res = await fetch(`${url}/sync/pull`, {
      method: "GET",
      headers: { "X-NGS-Token": token },
      signal: AbortSignal.timeout(10000),
    });
    return (await res.json()) as Shard[];
  } catch {
    return [];
  }
}
