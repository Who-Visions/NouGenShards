# War-Game: NouGenQ → nougenai.com/nougenq (Cloudflare, vinext)
Executor: Claude Cli (Fable) inline. Date: 2026-07-14.
GM order: "hook it to nougenai.com/nougenq" (while Dave gets Twitch creds).

## Recon (verified live)
- nougenai.com = CF Worker `nougenshards-site` (NouGenSite, vinext 1.0.0-beta.0 + @vinext/cloudflare, wrangler assets dist/client).
- vinext README: basePath ✅ "applied everywhere". wrangler: authenticated.
- NouGenQ sync route uses node:fs — NOT available on Workers (no disk).

## Plan: separate worker `nougenq`, basePath /nougenq, zone route nougenai.com/nougenq*
Moves:
1. Add vinext/@vinext/cloudflare/wrangler to NouGenQ; scripts mirroring NouGenSite.
   - Fail: peer conflicts with next 16.2.10 → align versions with site's lockfile.
2. next.config: basePath env-resolved (NOUGENQ_BASE_PATH, logged fallback "/nougenq"); expose NEXT_PUBLIC_BASE_PATH; page fetch via basePath-aware helper.
   - Fail signal: page loads but /api 404s → fetch missing prefix.
3. Evidence writer: dynamic fs import + try/catch → on Workers returns filed:false + clips metadata (degraded, honest). R2 binding = later ledger item.
4. wrangler.jsonc: name nougenq, nodejs_compat, NO route (staging = workers.dev). Route pattern nougenai.com/nougenq* documented for prod flip.
5. `vinext build` → verify. Deploy STAGING via vinext-cloudflare deploy (workers.dev URL). Prod route flip = human-in-the-loop (Dave), per scorecard gate.
   - Fail: vinext beta chokes on app structure → compare against NouGenSite conventions, adjust; abort if fundamental incompat, fall back to reverse-proxy from NouGenSite worker.

## Forks
- If vinext build fails on zod/ws/sqlite-free deps → tree-shake unused server libs out of edge bundle (ws only used later; remove until needed).
- If workers.dev staging URL breaks basePath asset loading → test /nougenq/ paths, adjust assets config.

## Abort
- vinext fundamentally can't build this app → route B: NouGenSite adds proxy route /nougenq → separate node host. Report first.

## Done =
Staging worker live at workers.dev/nougenq with health degraded-but-up; prod flip documented as one command for Dave; shard + handoff.
