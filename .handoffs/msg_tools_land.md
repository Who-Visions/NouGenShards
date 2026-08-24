## 🔴 Active Incidents
- None. All of Rhea-Noir's tools verified landing on Kimi K3.

## 🟡 Ongoing Investigations
- None new. Carried: Space->blade sync still one-way; vault has no backups.

## 📋 Recent Changes
- **All 5 Rhea tools land** (health/recall/griot/tracker/relay), all brain=kimi:moonshotai/Kimi-K3, verified direct AND through the connector's ask_rhea.
- **Worker-subrequest trap fixed**: a CF Worker subrequest to a hostname in its OWN zone bypasses that zone's Worker routes and hits the origin. ask_rhea's call to shards.nougenai.com/agent was landing on blade (no /agent) => bare FastAPI 404. Now addresses the Space via RHEA_ORIGIN. **Rule: never let one Worker reach a sibling Worker through their shared public hostname.**
- **Kimi was 402, not rate-limited**: HUGGINGFACE_KEY_NOUGENAI_AT_GMAIL_COM depleted its monthly included credits. Probed 11 vaulted HF identities -> 9 still have credit. Added NGS_INFERENCE_TOKENS rotation pool (Space secret) + last-good-index memory in rhea_noir.py (commit 66abf26). Falls back to :free only after all 9 fail.
- **Prompt echo bug fixed**: system prompt's `{"answer": "<your reply>"}` was emitted verbatim by the weak model (relay probe returned zero tools). Replaced with a concrete example + "never narrate your process".
- ask_rhea timeout 90s -> 240s (multi-tool questions were aborting).
- Space at 198,001 shards vs blade 202,979 — overnight backfill ~97% done.

## ⚠️ Known Issues & Workarounds
- Per-HF-account inference credit is small and monthly; expect individual keys to 402 and the pool to carry it. thesexyslumberparty key lacks inference scope (403).
- Space app.py/rhea_noir.py run AHEAD of the GitHub public repo — still needs a PR.
- Deploy fleet-mcp from SOURCE (Who-Visions/nougen-fleet-mcp), never from the CF-fetched bundle; use keep_bindings so live vars survive.

## 📅 Upcoming Events
- Backfill completes shortly (~5k shards remaining).
- Open: reverse sync Space->blade, phoebus role decision, Outpost stale cloudflared, public-repo PR.
