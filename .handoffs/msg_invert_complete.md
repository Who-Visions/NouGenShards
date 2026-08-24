## 🔴 Active Incidents
- None. Two resolved this session: (1) ghost tunnel connector 502ing ~1/3 of public traffic (tunnel secret rotated, ghost locked out — GM still to kill the stale cloudflared on the Outpost box); (2) post-flip Worker 502s on /search (8s timeout + consumed-body bugs, Worker v2 deployed).

## 🟡 Ongoing Investigations
- None. Domain-invert is COMPLETE and kill-tested.

## 📋 Recent Changes
- **DOMAIN-INVERT EXECUTED END TO END (GM order)**: route `shards.nougenai.com/*` -> nougen-shard-failover attached (id 6d829881983b45e9a7fd918085c3f7d9). Space-primary, blade-fallback. OAuth routes to nougen-fleet-mcp untouched.
- Worker v2: timeouts env-overridable (default 35s, was 8s hardcoded), POST body buffered once for the fallback leg.
- **Kill test PASSED**: both :4444 PIDs killed -> public domain answered 200 from Space in ~2.5s (health AND search). Node restarted via 'NouGen NGS Node' task; read-through restored (5/6 cloud_blade rows via the public domain).
- Rollback pre-staged: ~/.nougen/worker_routes_rollback_20260817.json (all 10 pre-flip routes); revert = delete the one new route.
- Earlier this session: Space/blade token unified, Space secrets vault moved to /data, BIC exception for blade.nougenai.com, NGS_CLOUD_SEARCH_TIMEOUT=30, tunnel secret rotated (NOUGEN_TUNNEL_RUN_TOKEN fp 0bf7e0e456d8).

## ⚠️ Known Issues & Workarounds
- Outpost/ccr box still error-loops a cloudflared with the dead tunnel token — harmless, but kill it.
- mcp.nougenai.com rides the ngs-phoebus tunnel — NOT flipped, still phoebus-mortal. Same invert pattern applies if wanted.
- Space keymaker NGS_NODE_TOKEN row is plaintext on /data (no keyring in container). Parity-correct fix drafted, not applied: cloud.py falls back to its own env NGS_NODE_TOKEN for upstream auth.
- schtasks /run breaks under git-bash path mangling — use `powershell Start-ScheduledTask`.

## 📅 Upcoming Events
- Optional follow-ups: invert mcp.nougenai.com the same way; cloud.py env-fallback patch to the public repo; kill Outpost's stale cloudflared.
