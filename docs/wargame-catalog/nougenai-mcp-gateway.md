# War-game candidates — nougenai-mcp-gateway

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

9 candidates · P0 3 · P1 6 · P2 0 · P3 0 · defend 3 · elevate 6

| id | P | kind | title |
|---|---|---|---|
| WG-0013 | P0 | defend | Resolve the mcp.nougenai.com hostname claim between this repo and nougen-shard-gateway |
| WG-0029 | P0 | elevate | Land PR #3 switchboard tools without importing CC BY-NC-SA terms or provider secrets |
| WG-0044 | P0 | elevate | Decide revive-or-retire for nougenai-mcp-gateway now that Watchtower owns the public gateway |
| WG-0375 | P1 | defend | Fail closed on /mcp when NOUGEN_MCP_TOKEN is unset instead of silently opening writes |
| WG-0391 | P1 | elevate | Migrate GET /mcp + POST /messages to Streamable HTTP without stranding SSE clients |
| WG-0407 | P1 | elevate | Rotate the shared NOUGEN_MCP_TOKEN with timing-safe compare and zero client downtime |
| WG-0423 | P1 | elevate | Add per-lane tokens and a scope filter so a leaked token cannot read every build note |
| WG-0439 | P1 | defend | Free the gateway from hardcoded :8787 that WhoVisions Archive Supervisor already binds |
| WG-0455 | P1 | elevate | Expose the Express gateway via named tunnel without being shadowed by failover Worker routes |

---

### WG-0013 · P0 · defend · effort M

**Resolve the mcp.nougenai.com hostname claim between this repo and nougen-shard-gateway**

- Failure surface: README, /docs and /.well-known/nougen.json all advertise https://mcp.nougenai.com/mcp, but fleet handoffs show that hostname is served by the Cloudflare Worker nougen-shard-gateway fronting the Python Watchtower gateway (89,422 shards, openapi.json with 34 schemas). A client following this repo's docs gets shards tools, not brand tools, and nobody owns the discrepancy.
- First fork: if you observe https://mcp.nougenai.com/openapi.json returning 200 -> the hostname belongs to the shards stack: rewrite this repo's URLs to a new hostname or retire the claim; else -> reserve the hostname formally in the relay and gate this repo's tunnel on that record.
- Evidence: `src/index.ts`, `README.md`, `NouGenRelay/.handoffs/20260909T004319Z__whoart__claude-cli.md`
- Lens: public surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: README, /docs and /.well-known/nougen.json in src/index.ts all advertise https://mcp.nougenai.com/mcp. 0909 whoart handoff verifies live POST mcp.nougenai.com/mcp served by the nougen-fleet-mcp Worker and GET /openapi.json with 34 schemas. The '89,422 shards' figure is not in the cited evidence but immaterial.
- #550 families: 34

### WG-0029 · P0 · elevate · effort L

**Land PR #3 switchboard tools without importing CC BY-NC-SA terms or provider secrets**

- Failure surface: Draft PR #3 (codex/nougen-switchboard-recursion, 472 additions, 4 route tools, 7 skill modes) is a behavioral recursion of an Attribution-NonCommercial-ShareAlike upstream; merging code that reads provider quota or keys into a public gateway risks both the license boundary and the secret boundary.
- First fork: if you observe any literal copied structure or a raw provider key read in the PR diff -> reject and rewrite clean-room with opaque candidate metadata; else -> review against the eight-step architecture list and merge behind a feature flag.
- Evidence: `NouGenRelay/.handoffs/20260910T194142Z__chatgpt-app__g-whoentertains.md`, `src/mcp/tools.ts`, `package.json`
- Lens: licensing/agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff 20260910T194142Z documents draft PR #3 on codex/nougen-switchboard-recursion, 472 additions, 4 route tools, CC BY-NC-SA upstream and the secret-boundary rule; git ls-remote shows refs/pull/3/head and the branch on origin.
- #550 families: 76

### WG-0044 · P0 · elevate · effort M

**Decide revive-or-retire for nougenai-mcp-gateway now that Watchtower owns the public gateway**

- Failure surface: No src change since 2026-05-10; blade's local nougenai-mcp-gateway is described as a 'different, older project'; the Watchtower SSE gateway already has per-lane tokens and scope filters. Two half-alive gateways means two token stores to rotate and two docs sets that lie.
- First fork: if you observe Dave lock on a distinct purpose for this repo (brand/site context for site builders) -> revive under a new hostname with a scoped charter; else -> archive the repo, move brand constants into a shards resource, and delete the hostname claims.
- Evidence: `src/nougen/sites.ts`, `NouGenRelay/.handoffs/20260819T154716Z__claude-app__g-whoentertains.md`, `NouGenRelay/.handoffs/20260806T003101Z__blade1tb__claude-cli.md`
- Lens: stale-repo · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: git log: last src change 2026-05-10 (commit 3d30a3d). The 'different, older project' quote is in 20260819T154716Z, not the cited 0908 handoff (swapped). 0806 handoff documents Watchtower per-lane tokens and scope filter. Note 0910 handoff shows a draft PR #3 adding switchboard tools to this repo, so it is not fully dormant.

### WG-0375 · P1 · defend · effort S

**Fail closed on /mcp when NOUGEN_MCP_TOKEN is unset instead of silently opening writes**

- Failure surface: authMiddleware returns next() with no log when the env var is missing, so a scheduled-task launch without .env exposes nougen_save_build_note and every resource to anyone reaching the tunnel; nobody notices because /health stays 'healthy' and README marks auth [x] done.
- First fork: if you observe GET /mcp returning 200 with no Authorization header on the deployed host -> treat as live exposure: stop the process, rotate token, audit build_notes for foreign rows; else -> ship the fail-closed change plus a startup log line and a /health 'auth: configured' field.
- Evidence: `src/index.ts`, `README.md`, `NouGenRelay/.handoffs/20260805T234121Z__blade1tb__claude-cli.md`
- Lens: security/auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/index.ts authMiddleware: `if (!AUTH_TOKEN) return next();` with no log; README Roadmap marks bearer auth [x]; /health is a static 'healthy' object. 0805 handoff describes the separate Watchtower gateway's auth (context only).
- #550 families: 35

### WG-0391 · P1 · elevate · effort M

**Migrate GET /mcp + POST /messages to Streamable HTTP without stranding SSE clients**

- Failure surface: /docs and README tell clients transport 'http' but the server only speaks legacy SSE; a Streamable HTTP client POSTing to /mcp gets an Express 404. Migration must keep the SSE path alive for whichever fleet connector still uses it.
- First fork: if you observe any live consumer connecting via SSE (transports Map non-empty in logs) -> dual-mount both transports behind the same auth; else -> replace SSE outright and update /docs, README and .well-known in the same commit.
- Evidence: `src/index.ts`, `README.md`, `package-lock.json`
- Lens: public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: README and /docs advertise `"transport": "http"` while src/index.ts mounts only GET /mcp (SSEServerTransport) and POST /messages; no POST /mcp route exists so Express 5 returns 404. package-lock pins sdk 1.29.0 which ships StreamableHTTPServerTransport.
- #550 families: 21

### WG-0407 · P1 · elevate · effort M

**Rotate the shared NOUGEN_MCP_TOKEN with timing-safe compare and zero client downtime**

- Failure surface: One static token compared with !== and no overlap window; the fleet TODO to rotate gateway-stack tokens and delete .gateway_token.retired-20260805 is still open. A rotation without dual-accept breaks every connector config at once.
- First fork: if you observe more than one live consumer config (Antigravity, claude connector, smoke script) -> implement dual-token acceptance for a window, rotate, then retire; else -> rotate directly and update the single config.
- Evidence: `src/index.ts`, `scripts/smoke-memory.mjs`, `NouGenRelay/.handoffs/20260806T003101Z__blade1tb__claude-cli.md`
- Lens: secrets · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: src/index.ts compares with `token !== AUTH_TOKEN` (not timing-safe), single static token, no overlap window. 0806 handoff documents `.gateway_token.retired-20260805` but for the Watchtower gateway, and says legacy token already RETIRED; whether a fleet TODO to delete it is still open is not shown in cited evidence. smoke script hardcodes one token.

### WG-0423 · P1 · elevate · effort M

**Add per-lane tokens and a scope filter so a leaked token cannot read every build note**

- Failure surface: Unlike the Watchtower gateway (per-lane tokens fleet/claude-client, gateway_scopes.json), this server has one token for read and write; any lane can dump all build_notes with a single search. No X-NouGen-Lane header exists.
- First fork: if you observe notes from multiple lanes already in build_notes -> retrofit a lane column and filter before issuing new tokens; else -> issue read-only and write tokens first, then lane scoping.
- Evidence: `src/index.ts`, `src/mcp/db.ts`, `NouGenRelay/.handoffs/20260805T234121Z__blade1tb__claude-cli.md`
- Lens: privacy/auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: One NOUGEN_MCP_TOKEN gates both read tools and nougen_save_build_note; no lane header, no scope filter in src/index.ts or src/mcp/db.ts. 0805 handoff documents Watchtower's per-lane tokens and gateway_scopes.json; 0806 documents X-NouGen-Lane 403 behaviour.

### WG-0439 · P1 · defend · effort S

**Free the gateway from hardcoded :8787 that WhoVisions Archive Supervisor already binds**

- Failure surface: port is a const 8787 with no PORT env; the fleet's WhoVisions Archive app.py is supervised on localhost:8787 and a handoff probe found 8787 refused. Whichever process starts second dies with EADDRINUSE, and the loser is whichever one the watchdog restarts less often.
- First fork: if you observe EADDRINUSE or curl :8787/health returning the Archive HTML -> pick a fleet-registered port (NGS_PORT-style pin) and update tunnel ingress; else -> add PORT/NOUGEN_MCP_PORT env with 8787 default and document the port registry.
- Evidence: `src/index.ts`, `NouGenRelay/.handoffs/20260913T154523Z__whoart__antigravity.md`, `NouGenRelay/.handoffs/20260914T024316Z__whoart__antigravity.md`, `NouGenRelay/.handoffs/20260908T061017Z__claude-app__g-whoentertains.md`
- Lens: infra/runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: `const port = 8787` with no env override confirmed. Neither cited handoff (0819, 0814) mentions 8787 or the Archive; corrected to 0913/0914 whoart handoffs, which document 'WhoVisions Archive Supervisor' on localhost:8787 (on whoart, not blade), and 0908 which found 8787 refused. Collision only materialises if the gateway is deployed on whoart, so inference not observed.
- #550 families: 34

### WG-0455 · P1 · elevate · effort M

**Expose the Express gateway via named tunnel without being shadowed by failover Worker routes**

- Failure surface: Fleet scenario D: Worker routes bound to a hostname take precedence over its DNS CNAME, so a correctly tunneled origin never receives traffic. The nougen-fleet-mcp Worker also rewrites bearer to x-ngs-token, which would make this repo's authMiddleware 401 every request even if routed.
- First fork: if you observe the tunnel healthy locally but public /health returning the shards node's JSON -> a Worker route owns the host: remove or re-scope the route first; else -> bring up cloudflared with path-fenced ingress (/mcp,/messages,/health only) and verify a bearer round-trip end to end.
- Evidence: `src/index.ts`, `NouGenRelay/.handoffs/20260901T200524Z__claude-app__g-whoentertains.md`, `NouGenRelay/.handoffs/20260818T170510Z__phoebus__claude-cli.md`
- Lens: infra/deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: 0901 handoff scenario D directly documents Worker routes on mcp.nougenai.com shadowing a healthy tunnel. The claim that nougen-fleet-mcp rewrites bearer to x-ngs-token is not in the cited 0818 handoff; relay only shows the NGS node itself uses X-NGS-Token. authMiddleware in src/index.ts does require Bearer, so a rewrite would 401, but the rewrite itself is unverified.
- #550 families: 34
