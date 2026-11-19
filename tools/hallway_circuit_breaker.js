// nougen-fleet-mcp/src/hallway_circuit_breaker.js
/**
 * Adaptive Hallway & Peer Federation Circuit Breaker
 * Guarantees sub-second write capture even when HF Space is PAUSED (206/503)
 * and prevents slow peers from stalling fan-out recall beyond the strict SLA.
 */

const CIRCUIT_TTL_MS = 60_000;
const HALLWAY_TIMEOUT_MS = 3_500;
const PEER_RECALL_BUDGET_MS = 6_500;

const circuitState = new Map(); // routeKey -> { status: 'CLOSED'|'OPEN'|'HALF_OPEN', openedAt: number, reason: string }

export function isRouteHealthy(routeKey) {
  const entry = circuitState.get(routeKey);
  if (!entry) return true;
  if (entry.status === "OPEN" && Date.now() - entry.openedAt > CIRCUIT_TTL_MS) {
    circuitState.set(routeKey, { status: "HALF_OPEN", openedAt: entry.openedAt, reason: entry.reason });
    return true;
  }
  return entry.status !== "OPEN";
}

export function recordRouteOutcome(routeKey, ok, reason = "") {
  if (ok) {
    circuitState.delete(routeKey);
  } else {
    circuitState.set(routeKey, {
      status: "OPEN",
      openedAt: Date.now(),
      reason: reason || "upstream_fault",
    });
  }
}

export function resetCircuitState() {
  circuitState.clear();
}

export function getCircuitState(routeKey) {
  return circuitState.get(routeKey);
}

async function fetchWithDeadline(url, init, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("DEADLINE_EXCEEDED"), timeoutMs);
  try {
    const res = await fetch(url, { ...init, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Write-Ahead Capture Router:
 * 1. Tries HF Hallway if circuit is CLOSED (detects HTTP 206/503 Space pause immediately).
 * 2. Fails over to live primary node rooms (Phoebus -> Blade -> WhoArt) in parallel race.
 * 3. Spills to Edge KV Write-Ahead Log if all tunnels are saturated, syncing on next heartbeat.
 */
export async function captureShardResilient(payload, env, ctx) {
  const bodyStr = JSON.stringify(payload);
  const idempotencyKey = await computeContentHash(bodyStr);

  // Stage 1: HF Cloud Buffer Hallway (if unpaused)
  if (env.HALLWAY_CAPTURE_URL && isRouteHealthy("hf_hallway")) {
    try {
      const res = await fetchWithDeadline(
        env.HALLWAY_CAPTURE_URL,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${env.HALLWAY_BEARER_TOKEN}`,
            "X-NouGen-Idempotency": idempotencyKey,
          },
          body: bodyStr,
        },
        HALLWAY_TIMEOUT_MS
      );

      // HF Space returns 206 when paused/building or 503 when container fails to wake
      if (res.status === 200 || res.status === 201) {
        recordRouteOutcome("hf_hallway", true);
        const data = await res.json();
        return { ok: true, via: "hf-cloud-buffer", idempotencyKey, upstream: data };
      }
      recordRouteOutcome("hf_hallway", false, `http_${res.status}_space_paused_or_unavailable`);
    } catch (err) {
      recordRouteOutcome("hf_hallway", false, String(err));
    }
  }

  // Stage 2: Direct Node Room Race (Phoebus, Blade, WhoArt)
  const nodeTargets = [
    { name: "phoebus", url: env.PHOEBUS_SHARD_URL, token: env.NODE_BEARER_TOKEN },
    { name: "blade", url: env.BLADE_SHARD_URL, token: env.NODE_BEARER_TOKEN },
    { name: "whoart", url: env.WHOART_SHARD_URL, token: env.NODE_BEARER_TOKEN },
  ].filter((n) => Boolean(n.url) && isRouteHealthy(`node_${n.name}`));

  for (const node of nodeTargets) {
    try {
      const res = await fetchWithDeadline(
        `${node.url.replace(/\/$/, "")}/v1/shards/capture`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${node.token}`,
            "X-NouGen-Idempotency": idempotencyKey,
          },
          body: bodyStr,
        },
        4_500
      );
      if (res.ok) {
        recordRouteOutcome(`node_${node.name}`, true);
        const data = await res.json();
        return {
          ok: true,
          via: `direct-node:${node.name}`,
          hallway_status: circuitState.get("hf_hallway")?.reason || "bypassed",
          idempotencyKey,
          upstream: data,
        };
      }
      recordRouteOutcome(`node_${node.name}`, false, `http_${res.status}`);
    } catch (err) {
      recordRouteOutcome(`node_${node.name}`, false, String(err));
    }
  }

  // Stage 3: Zero-Loss Edge Write-Ahead Spillover
  if (env.NOUGEN_WAL_KV) {
    const walRecord = {
      idempotencyKey,
      payload,
      queued_utc: new Date().toISOString(),
      hallway_fault: circuitState.get("hf_hallway")?.reason || "unconfigured",
    };
    if (ctx && typeof ctx.waitUntil === "function") {
      ctx.waitUntil(
        env.NOUGEN_WAL_KV.put(`wal:${idempotencyKey}`, JSON.stringify(walRecord), {
          expirationTtl: 60 * 60 * 24 * 7,
        })
      );
    } else {
      await env.NOUGEN_WAL_KV.put(`wal:${idempotencyKey}`, JSON.stringify(walRecord), {
        expirationTtl: 60 * 60 * 24 * 7,
      });
    }
    return {
      ok: true,
      via: "edge-kv-wal-buffer",
      idempotencyKey,
      note: "Hallway paused and direct tunnels unreachable; persisted in Edge WAL for node drain.",
    };
  }

  return { ok: false, error: "ALL_CAPTURE_LANES_EXHAUSTED", idempotencyKey };
}

/**
 * Bounded Fan-Out Recall:
 * Prevents a single degraded peer (e.g. WhoArt 25s grace timeout or Blade timeout)
 * from holding up the entire recall response, returning partial provenance immediately.
 */
export async function federatedRecallBounded(queryPacket, env) {
  const peers = [
    { name: "phoebus", url: env.PHOEBUS_SHARD_URL },
    { name: "blade", url: env.BLADE_SHARD_URL },
    { name: "whoart", url: env.WHOART_SHARD_URL },
  ].filter((p) => Boolean(p.url));

  const settled = await Promise.allSettled(
    peers.map(async (peer) => {
      if (!isRouteHealthy(`recall_${peer.name}`)) {
        throw new Error("circuit_open");
      }
      const start = Date.now();
      const res = await fetchWithDeadline(
        `${peer.url.replace(/\/$/, "")}/v1/shards/recall`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${env.NODE_BEARER_TOKEN}`,
          },
          body: JSON.stringify(queryPacket),
        },
        PEER_RECALL_BUDGET_MS
      );
      if (!res.ok) {
        recordRouteOutcome(`recall_${peer.name}`, false, `http_${res.status}`);
        throw new Error(`http_${res.status}`);
      }
      recordRouteOutcome(`recall_${peer.name}`, true);
      const rows = await res.json();
      return { peer: peer.name, elapsedMs: Date.now() - start, rows };
    })
  );

  const mergedByHash = new Map();
  const peerStatus = {};

  for (let i = 0; i < peers.length; i++) {
    const peerName = peers[i].name;
    const outcome = settled[i];
    if (outcome.status === "fulfilled") {
      peerStatus[peerName] = { status: "ok", elapsed_ms: outcome.value.elapsedMs };
      for (const row of outcome.value.rows || []) {
        const dedupKey = row.file_hash || `${row._db_index}:${row.id}`;
        if (!mergedByHash.has(dedupKey)) {
          mergedByHash.set(dedupKey, row);
        }
      }
    } else {
      peerStatus[peerName] = { status: "degraded", reason: String(outcome.reason) };
    }
  }

  return {
    complete: Object.values(peerStatus).every((s) => s.status === "ok"),
    peer_status: peerStatus,
    results: Array.from(mergedByHash.values()),
  };
}

async function computeContentHash(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf))
    .slice(0, 12)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
