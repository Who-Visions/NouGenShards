## 🔴 Active Incidents
- RESOLVED this session: ghost tunnel connector (bcb67da2, another LAN Windows box — likely Outpost/ccr — running blade's tunnel token with a dead origin) was 502ing ~25-33% of ALL public shards.nougenai.com requests. Fixed by rotating the tunnel secret (new run token fp 0bf7e0e456d8 in keymaker as NOUGEN_TUNNEL_RUN_TOKEN), relaunching local cloudflared, kicking stale connectors. Verified 8/8 public /search 200, single connector e279df52. **GM: kill the stale cloudflared on the Outpost box** — it error-loops with the dead token.

## 🟡 Ongoing Investigations
- Domain-invert M3 flip: the read-through gate is **PASSED** (Space /search returns 7/10 cloud_blade rows). The ONLY remaining step is attaching Worker route `shards.nougenai.com/* -> nougen-shard-failover` (Space-primary, blade-fallback; rollback = delete route). Awaiting GM go per war-game doctrine (wargames/domain-invert.md).

## 📋 Recent Changes
- Space secret NGS_NODE_TOKEN unified with blade's (fp 9c67af03a9da) — flip prerequisite.
- Space vars: NOUGEN_SECRETS_VAULT_DIR=/data/nougen_secrets (persistent keymaker DB; default ~/.nougen is ephemeral), NGS_CLOUD_SEARCH_TIMEOUT=30 (blade takes 9-11s over tunnel vs 5s default). NGS_NODE_TOKEN written into the Space's keymaker DB via /mcp/ vault_put (plaintext flag temp-set then removed; read path tolerates plaintext rows).
- Cloudflare: config ruleset cca2fa078c534139b8967505d24229e2 — Browser Integrity Check disabled ONLY for blade.nougenai.com (python-urllib got 403/1010; BFM was already off).
- Tunnel 1f830bb9 secret rotated; NOUGEN_TUNNEL_RUN_TOKEN updated in keymaker (fp 0bf7e0e456d8). tools/ngs_named_tunnel.py mints tokens dynamically so future restarts self-heal.
- Milestone shard captured: "M3 read-through gate PASSED + ghost-connector incident resolved".

## ⚠️ Known Issues & Workarounds
- Space /mcp redirects 307 to /mcp/ — POST clients must target the trailing-slash path (urllib won't re-POST on 307).
- The Space's keymaker row for NGS_NODE_TOKEN is plaintext on /data (no keyring in the container). Consider the cloud.py env-fallback patch (node uses its own env NGS_NODE_TOKEN for upstream auth) as the parity-correct public-app fix — drafted idea, not applied.
- Uncommitted repo changes on security/elevate-supply-chain remain untouched (other agents' work + internal ops files — do NOT push to public repo).

## 📅 Upcoming Events
- GM go/no-go on the M3 route attach (the final flip). Pre-staged rollback: delete the Worker route. Success test per wargames/success.md: kill blade's uvicorn, domain still answers from the Space.
