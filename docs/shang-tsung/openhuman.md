# Shang Tsung: tinyhumansai/openhuman → NouGen

Absorbed 11:15 PM EDT Sun 9/13/2026. **GPL-3.0, so clean-room**: README and gitbook docs only, no code read or copied. The project is a Rust/Tauri agent harness (39.8k★, early beta) with local-first memory, orchestration and workflows. It positions itself directly against Claude Code.

**Fleet vote 11:24 PM EDT 9/13** (6 distinct models on Ollama + OpenRouter, 6/6 parsed; `analysis/shang-tsung/vote_20260913.json`): #3 memory tree borda 27, **6/6**; #6 tool-output compaction 24, **6/6**; #5 auto-sync 15, 4/6; #13 triggers 8, 3/6; #9 checkpoints 6, 4/6. The memory tree is the same move as Tencent's L0→L3 distillation, see [tencentdb-agent-memory.md](tencentdb-agent-memory.md). #1 privacy mode and #2 the circuit breaker **shipped** in `tools/fleet.py` (tests: `tests/test_fleet_privacy_breaker.py`).

| # | openhuman move | NouGen today | Verdict |
|---|---|---|---|
| 1 | **Privacy mode**: one switch, enforced in core, that blocks every cloud model call | Rule 0.3 is policy only; nothing in code stops a cloud call | **SHIP NOW**: `NOUGEN_PRIVACY=1` makes fleet.py refuse every non-local route |
| 2 | **No-progress circuit breaker**: stop identical-call loops and return a root-cause summary | Listed in the coach's "habits that cost Dave"; not enforced | **SHIP NOW** in the fleet call path |
| 3 | Memory Tree: ≤3k-token chunks folded into per-source / per-topic / per-day summary trees in SQLite | Flat shards + dailies; no hierarchy | Backlog (biggest memory win; pair with recall_eval body-tier R@10 0.28) |
| 4 | Obsidian mirror: every chunk as an editable `.md` | Notion→local mirror exists (inbound only) | Backlog: shards → md export |
| 5 | 20-minute auto-fetch sync loop | notion_mirror is incremental but manual; Claude scheduled tasks don't run unattended | Backlog: Windows Task Scheduler + pythonw |
| 6 | TokenJuice: compact tool output before it reaches the model (claims up to 80% fewer tokens) | Recall snippets + token budget (recall side only) | Backlog: needs a real ingest caller first (no demos) |
| 7 | Replay journals with per-call token/cost | coach ledger (per call) + NouGenTracker dailies | Partial; replay missing |
| 8 | Classified tool failures shown as timeline cards | Relay legs, FAILURE shards | Partial |
| 9 | Durable checkpointing: sub-agents pause for input and resume | Archive scan checkpoints only | Backlog |
| 10 | Routing hints (`reasoning` / `fast` / `vision`) | fleet.py ranks route kinds; coach sends images to local | Backlog: hint argument on `Fleet.map` |
| 11 | Reflex agent triages inbound traffic, reasoning core delegates | Kaedra elevation gate (e2b) + gate_eval | Covered |
| 12 | Approval gates on side effects | Watchtower mutation gate + DavOs Gatekeeper sandbox | Covered (policy + sandbox) |
| 13 | Trigger workflows (schedule / webhook / channel event) | Scheduled-tasks MCP (fires only on app start) | Backlog, same fix as #5 |
| 14 | Long-term goals + per-thread goals + shared kanban | Destiny shards (long-term) + relay legs (per-thread) | Partial; kanban view missing |
| 15 | Agent-to-agent E2E encryption | NouGenMsg bus + relay, both plaintext | Backlog |
| 16 | Mascot that speaks, reacts and remembers you | Kaedra/Yuki personas on e2b; EchoVault "Echo" concept | Partial; fold into the Echo work |
| 17 | In-process Whisper STT | `transcribe_media` | Covered |
| 18 | Local Ollama + BYOK + subscription mixed | fleet.py, 48 routes | Covered |
| 19 | OS keyring for secrets | Keymaker: 4 disjoint stores | Backlog: unify behind keyring |
| 20 | Multi-level sub-agents (3 deep) | Forbidden on this box (coach rule, 9/13 burn) | **Rejected**: the fleet is the fan-out |
| 21 | x402 agent payments | n/a | **Rejected**: moves money |
| 22 | Live meeting join / speak | n/a | Rejected for now (scope) |
