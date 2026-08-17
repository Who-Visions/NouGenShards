# Continuous Sync Design - blade/whoart replica lane

## 1. Write-Ownership Rule

*   **Canonical Write Authority:** Blade is the sole authority for writes to the 9-database SQLite grid.
*   **Whoart Write Policy:** Whoart is read-only for the canonical data. All writes must originate from Blade.
*   **Sync Mechanism:** Whoart's `/sync/push` endpoint is strictly for receiving updates *from* Blade (replication). Whoart's `/sync/pull` is for requesting updates *from* Blade.
*   **GM-DECISION:** Implement a strict write-forward mechanism where Blade validates and commits all changes before broadcasting to Whoart.

## 2. Scheduled Bidirectional Sync

*   **Schedule:** Bidirectional sync runs every 60 seconds, initiated by a dedicated scheduler service on both nodes.
*   **Process:**
    1.  **Pull Phase:** Whoart initiates `/sync/pull` to check for missing/newer data from Blade.
    2.  **Push Phase:** Blade initiates `/sync/push` to broadcast committed changes to Whoart.
    3.  **Acknowledgement:** Both nodes acknowledge receipt of the latest successful sync timestamp.
*   **Data Format:** Sync payloads utilize a delta-based change log (e.g., SQLite WAL entries or JSON diffs) rather than full grid dumps.

## 3. Drift Detection

*   **Metric 1 (Row Count):** Periodic (every 5 minutes) comparison of total row counts per database shard (9 databases).
    *   *Threshold:* $\Delta > 0$ rows triggers immediate alert.
*   **Metric 2 (Content Hash):** Every 10 minutes, calculate a cryptographic hash (SHA-256) of the serialized content of a statistically significant sample of rows (e.g., 1% of total rows per shard).
    *   *Threshold:* Hash mismatch triggers a full shard content verification request.
*   **GM-DECISION:** Drift detection must be asynchronous and non-blocking to avoid impacting sync throughput.

## 4. Conflict Policy

*   **Policy:** Last Write Wins (LWW) based on a synchronized, monotonically increasing logical clock (Lamport or Vector clock).
*   **Same-Shard Edits:** If a write originates from Blade, it is the canonical version. If Whoart attempts a write (via a hypothetical future endpoint), it is rejected immediately.
*   **Sync Conflict:** If a sync conflict occurs (e.g., clock skew leading to out-of-order application), the update with the higher logical clock value prevails.

## 5. Failure Modes

*   **Machine Down:** If Whoart is down, Blade continues to replicate to a persistent queue. Upon recovery, Whoart performs a full state reconciliation against the last known successful sync timestamp.
*   **Sync Backlog:** If the sync queue exceeds 1 hour, the system triggers a throttling mechanism on the `/sync/push` endpoint to prioritize critical replication traffic over bulk updates.
*   **Clock Skew:** NTP synchronization is mandatory. If skew exceeds 500ms, the LWW policy is temporarily relaxed to prioritize the higher logical clock value, followed by an automated re-sync.

## 6. Rollout Gates

*   **Gate 1 (Internal Stability):** 72 hours of continuous operation with zero critical drift alerts and zero sync backlog events.
*   **Gate 2 (Tunnel Readiness):** Successful execution of a full, unthrottled bidirectional sync cycle (pull/push) with 100% content hash verification success for 48 hours.
*   **Gate 3 (Production):** Cloudflare Tunnel ingress established and validated via synthetic traffic testing, confirming low latency and consistent data serving across both endpoints.
*   **GM-DECISION:** Tunnel join is authorized only upon Gate 3 completion.
