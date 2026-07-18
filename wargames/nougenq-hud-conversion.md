# War-Game: Broadcast HUD → live NouGenQ shell
Executor: Claude Cli (Fable) inline — design conversion is precision/taste work (scorecard: taste 10 lane). Date: 2026-07-15.
GM pick: style 05, screen cc32847365a24fd2a64a9866c0e27895.

## Mission
Reskin src/app/page.tsx (+ globals.css tokens) to the Broadcast HUD design while preserving all live wiring: health poll, twitch LIVE pill, cue input → POST /api/q → lanes, urgent treatment, footer lanes status. Add REAL latency readout (last /api/q round-trip ms) where the mock shows one.

## Moves
1. Read design/stitch/5-broadcast-hud.html — extract palette, type (mono/display), lane rail treatment, scanline texture, spacing.
   - Fail: HTML unreadable/bloated → screenshot is ground truth, rebuild by eye.
2. Port tokens to globals.css (Tailwind 4 @theme) — stage-black bg, lane colors, mono stack. No new font CDNs (CSP/perf): system mono (Consolas/ui-monospace) approximates the HUD feel.
3. Rewrite page.tsx: header (NOUGENQ wordmark, ONE VOICE MANY MINDS, LIVE ON TWITCH pill driven by twitch status), input bar ("Awaiting audio transcript stream…", CUE ME), three lane columns with LANE_01-03 rails, cue cards (teleprompter-scale text in SAY), evidence tags, urgent red treatment, footer LOCAL/CLOUD/LATENCY.
   - Failure signal: hydration errors or lanes lose cues → check store wiring unchanged.
4. Wire twitch status poll (NEXT_PUBLIC_POLL_MS) → setLive; latency = measured /api/q ms in store.
5. Verify: pnpm build green; dev server; POST real transcript → cues render in HUD; browser console clean; screenshot-compare vibe vs PNG.
6. Deploy worker (staging URL + serves prod route when Dave approves domain). Commit, shard, handoff.

## Forks
- If Stitch HTML uses webfonts (Space Grotesk etc): self-host? No — swap to system mono + tight tracking; log the substitution in commit.
- If scanline texture kills readability at small sizes → keep it header/footer only.

## Abort
- None foreseeable; pure frontend.

## Done =
HUD shell live locally with real cues from gemma lane, build green, deployed, artifacts updated.
