## 🔴 Active Incidents
- None.

## 🟡 Ongoing Investigations
- None. Space-brain topology COMPLETE per GM directive ("all paths upstream to nougen space").

## 📋 Recent Changes
- **ALL public hostnames now front the HF Space**: mcp.nougenai.com + ngs.nougenai.com mirrored to shards.nougenai.com's route layout (20 new Worker routes). MCP/OAuth paths -> nougen-fleet-mcp; data paths -> nougen-shard-failover v2 (Space-primary 35s, blade-fallback). Verified: all three /health 200 origin=space persistent=true; OAuth discovery 200 per-host issuer; claude-app fleet connector green.
- Phoebus removed from the public path (tunnel/DNS untouched, edge routes intercept). Its node stays as a private lane.
- Earlier this session: domain-invert flip + kill test PASSED; ghost-connector 502 incident resolved (tunnel secret rotated); Worker v2 (timeout + body bugs); Space read-through fixed (token unify, /data secrets vault, BIC exception, 30s cloud timeout).

## ⚠️ Known Issues & Workarounds
- Outpost/ccr box: kill its stale cloudflared (dead token, error-looping).
- Phoebus role decision (replica vs gateway) still pending GM — if replica, unify its token and add as second NGS_UPSTREAM on the Space.
- Clients that used phoebus's node token on mcp.nougenai.com now get the fleet-worker OAuth flow instead (richer surface, lane tokens).
- Space keymaker token row is plaintext on /data; cloud.py env-fallback patch drafted, not applied.

## 📅 Upcoming Events
- Optional: cloud.py env-fallback PR to public repo; phoebus replica decision; Outpost cloudflared cleanup.
