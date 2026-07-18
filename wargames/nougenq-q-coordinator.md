# War-Game: NouGenQ Q Coordinator v0 + live pill
Executor: Claude Cli (Fable) writes precision code; cue generation itself delegates to the ollama lane at runtime (context-mode compliant). Date: 2026-07-14.

## Mission
First thinking loop: POST /api/q {transcript} → local gemma (ollama /api/chat, JSON mode) → zod-validated SAY/DO/CAUTION cues → lanes UI. Plus: shell polls /api/twitch/status → LIVE pill goes real.

## Moves
1. lib/qcoordinator.ts — model resolution (env → live /api/tags probe → logged fallback), ollama chat call with format:json, strict zod parse of cues, ≤3 cues, evidence defaults to "inferred".
   - Worked: valid cues from a test transcript. Fail: model returns junk JSON → one repair retry (reparse), then 502 with raw snippet in error field.
2. POST /api/q route — degraded {cues:[]} + note when ollama offline (cloud/Workers), never crash.
3. UI: input bar (enter = send), cues push into store with ids; poll /api/twitch/status + /api/health on interval (NOUGENQ_POLL_MS env → NEXT_PUBLIC, fallback 30000); live pill driven by twitch.live.
   - Fail signal: cues render in wrong lane → zod enum catch; UI stuck "Thinking" → ensure finally-clause.
4. Verify: curl /api/q with real remediation-style transcript against live gemma; browser check lanes populate; next build green; redeploy staging; cloud /api/q returns degraded note (no ollama there yet — cloud specialist lane comes when ANTHROPIC key lands).

## Forks
- gemma4:31b-cloud slow (>30s) → drop to gemma4:12b local (env override NOUGENQ_LOCAL_TEXT_MODEL); timeout env NOUGENQ_Q_TIMEOUT_MS fallback 45000.
- JSON mode unsupported by picked model → strip code fences + best-effort parse before failing.

## Abort
- ollama chat API shape mismatch → probe /api/chat manually, adjust, no blind retries.

## Done =
Real cues from real local model rendered in the three lanes, live pill wired, staging redeployed, shard + handoff.
