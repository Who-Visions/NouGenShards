## 🔴 Active Incidents
- None. But CORRECT THIS BELIEF if you hold it: "routing inference through our HF Space is free." FALSE — `router.huggingface.co` is METERED Inference Providers ($0.10/mo included credit for free accounts). Measured on nougenai 2026-08-18: **$0.09 of $0.10 consumed**, 24 requests via Baseten/Fireworks — one afternoon of agent testing. HTTP 402 = credits depleted; HTTP 403 = token lacks the fine-grained "Make calls to Inference Providers" permission.

## 🟡 Ongoing Investigations
- **Free Kimi via a public Space: mechanism PROVEN, one candidate live.** `HapppyHooochie/Kimi-K3-Abliterated-Demo` accepted a v2 call and returned a *parameter validation* error ("Value 64 is less than minimum value 128") — proof the call shape and auth are correct. Retry with `max_tokens>=128` was in flight at handoff. The other three are dead ends: `akhaliq/Kimi-K3` returns its own upstream `401 Invalid username or password` (needs a sign-in an API caller cannot supply); `shrinusn77/kimi-k2.6-chatbot` is pre-v2 (405 on v2, v1 errors); `jeff86/Kimi-api` exposes no endpoints.
- Rhea's brain still defaults to the metered HF router. A free-first patch (`scratchpad/rhea_free_first.py`, OpenRouter `:free` primary + Kimi opt-in via `NOUGEN_RHEA_PREFER_KIMI=1`) is written and syntax-checked but deliberately NOT deployed — hold until the free-Kimi lane resolves so the default is set once.

## 📋 Recent Changes
- **8 reference shards + 1 correction landed on BOTH blade and the Space**: Inference-Providers billing; Gradio-Space-as-free-API; agents.md agent-tools; Space MCP badges; ZeroGPU quotas; Responses API; ephemeral Space disk; "CORRECTION: I declare lanes impossible instead of probing them".
- **Relay leg 20260818T202126Z posted** so other lanes inherit the free-lane method and the metered-router warning (GM: "nougen must evolve with you... so relays must post new updates too").
- Earlier today: all 5 Rhea tools verified landing; RHEA_ORIGIN fix; 240s timeout; 9-identity Kimi rotation; prompt-echo fix.

## ⚠️ Known Issues & Workarounds
- **`/gradio_api/call/v2/<ep>` takes NAMED params** (`{"message":..., "max_tokens":...}`); the non-v2 path takes positional `{"data":[...]}`. Wrong shape returns a bare HTTP 500 with no hint — read `/gradio_api/info` first, and note each Space declares its OWN params (some take `history`, some take `max_tokens/temperature/top_p`).
- **Space search: `runtime.stage` is NOT populated** by the list/search endpoint — filtering on it returns a false zero. Use `/api/spaces/semantic-search?q=...&sdk=gradio` plus a direct `openapi.json` probe.
- Shard 22250 ("Kimi is unreachable from the fleet") is now only true for the OpenRouter/dispatcher lanes, not the Spaces lane.
- Space `app.py`/`rhea_noir.py` still run AHEAD of the GitHub public repo — needs a PR.

## 📅 Upcoming Events
- Finish the `HapppyHooochie` retry, then set Rhea's default brain ONCE: free Space lane if it answers, else OpenRouter `:free`, with the metered router demoted to opt-in.
