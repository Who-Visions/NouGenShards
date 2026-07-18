# War-Game: NouGenQ Twitch Clip Lane
Executor: Claude Cli (Fable) inline — small precision surface. Date: 2026-07-14.
GM order: "I'll be streaming from Twitch so we can backend pull the clips."

## Mission
Backend lane that pulls Dave's Twitch clips/stream state into NouGenQ and files clip metadata as evidence-ready JSON.

## Moves
1. lib/twitch.ts — client-credentials app token (cached, refresh on 401), Helix helpers: user lookup, live-stream status, clips list (paginated, time-windowed).
   - Worked: typed results. Fail: 401 → refresh once then report degraded; no creds → `configured:false`, never throw.
2. Routes: GET /api/twitch/status (live check), GET /api/twitch/clips (window+pagination), POST /api/twitch/clips/sync (pull → write JSON under evidence dir).
   - Worked: keyless run returns degraded JSON. Fail: build/type errors → fix inline.
3. Env: TWITCH_CLIENT_ID/SECRET, NOUGENQ_TWITCH_BROADCASTER, optional NOUGENQ_TWITCH_USER_TOKEN (clips:edit, needed only for clip CREATION later — Dave supplies via OAuth himself; we never handle his password).
4. Verify: build green + curl /api/twitch/status → honest `configured:false` degraded state.

## Forks
- Reading clips needs only app token → route A (ship now). Creating clips needs user OAuth clips:edit → route B (deferred; env-injected token slot ready).
- Clip MP4 download: thumbnail-URL rewrite trick is unofficial/fragile → store canonical clip URL + metadata now; downloader deferred to ledger.

## Abort
- Helix API shape changed vs docs → stop, fetch official docs, re-plan.

## Done =
Build green, status route degrades gracefully keyless, clips sync writes evidence JSON, shard + handoff.
