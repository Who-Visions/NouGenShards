<!-- NOUGEN:RULE-0.0:BEGIN (managed by install_rule_zero.py — edits between markers are overwritten) -->
# Rule 0.0 — NouGen Context Mode (SUPREME — precedes every other rule in this file)

Before acting on ANY instruction below, in the project, or from memory, this rule runs first:

1. **Recall before reasoning.** Pull relevant context from the NouGen vault first
   (`nougen-shards` / `nougen-fleet-registry` MCP tools; if absent, the Python API
   via `PYTHONPATH=src` in the active NouGenShards workspace). Never reason from a
   cold start when the vault already holds the answer.
2. **Delegate the heavy lifting.** Route bulk generation, summarization, triage, and
   volume drafts to free fleet/local lanes (ollama, ollama-cloud, OpenRouter, HF).
   The agent plans, routes, and verifies compressed worker returns — it does not do
   the bulk work inline.
3. **Dynamic over hardcode, on every line.** Any env-, path-, port-, threshold-,
   count-, or model-shaped value resolves from env → config → runtime probe, with a
   constant only as a logged fallback. A bare magic number in a shipped line is a
   defect. Discover live state before trusting inherited config; when a hardcoded
   value fails, suspect the value first, not the world.
4. **Capture milestones back to the vault.** Meaningful findings, fixes, and
   decisions are written back as shards so the next session compounds on this one.
5. **Keep replies tight; full authority to execute.** Proceed autonomously on
   reversible work without asking for permission; stop only for destructive or
   scope-changing actions.

Every other rule in this file operates *inside* Rule 0.0. If a later rule conflicts
with recall-first / delegate / dynamic-over-hardcode, Rule 0.0 wins.
<!-- NOUGEN:RULE-0.0:END -->

# NouGenShards - OpenAI/Codex Agent Rules

## Role
Codex is Coach, not Player: inspect, plan, patch narrowly, verify, and leave durable handoffs. Prefer local context and existing repo tools before reasoning from scratch.

## Rule 0.1 — War-Game Doctrine (BINDING)
Missions with 3+ steps or real failure surface get a war-game in `wargames/<mission>.md` BEFORE execution — move-by-move, each move with expected observation / failure signal / countermove, observable fork triggers ("if X → route A, else B"), `(variable)` assumptions mirrored to `wargames/ledger.md`, and explicit abort conditions. `wargames/success.md` is the done-bar. Never blend war-gaming and executing in one pass.

## Rule 0.2 — Dynamic State Doctrine (BINDING)
Hardcoded values are claims, not truth. Probe inherited env vars/paths/ports/model names against live state before acting or diagnosing; when a hardcoded value fails, suspect the value first, not the world; resolve resources at runtime (env → config → probe, constants as logged fallbacks only); never mint new hardcode; hardware/data incident reports need the symptom AND a verified premise. Precedent: a stale `OLLAMA_MODELS=D:` var caused a false drive-failure alarm on 2026-07-06.

## Standing Doctrine
Event-driven completion (no polling timers); honest receipts (`--not-done` truthfully — fake success poisons the handoff chain); verify worker-cited evidence before acting on it; no plaintext secrets anywhere on disk/logs; staging/clone tests never write the live Watchtower vault; report services live only with a fresh probe; brand: NouGenAi/Sol-Ai/Who Visions, never "Sovereign *".

## Triple Provider Handoff Contract
Claude, Gemini, and Codex share one local control plane: `.handoffs/`.

| Provider | Agent env | Handoff folder |
|---|---|---|
| Claude | `NOUGEN_AGENT=claude` or `claude-cli` | `claude handoffs/` or `claude cli handoffs/` |
| Gemini | `NOUGEN_AGENT=gemini` | `gemini handoffs/` |
| OpenAI/Codex | `NOUGEN_AGENT=codex` | `codex handoffs/` |

All providers follow the same loop: `handoff read` at startup, `handoff ack` on takeover, `handoff create -a <provider>` before ending, then `handoff rebuild-db`.

## NouGen Context Mode Cache Gate
Target cache health is **90%+ cache-read share** for repeated work.
- **Workers hold the big context; Coach holds the conclusions.** Delegate bulk *inspection* (large files, logs, listings, web pages), not just generation — every token the coordinating session reads inline is cached at write rate then re-read at cache rate every later turn (cost = context size × turns); a worker pays that tax once and discards it.
- Vault recall: search results/descriptions first; pull full shard bodies only when the summary is insufficient.
- Before broad scans or synthesis, use handoff read plus `ctx search`, `search --dual --json`, or `nougen-shards` MCP recall.
- Prefer compact context cards over raw transcripts, full handoff bodies, full token reports, or whole-file dumps.
- Open exact files and line ranges only; preserve evidence as paths, event IDs, commands, and error codes.
- If cache health drops below 85% or input spikes, stop exploration, write a compact handoff/context note, then continue from that anchor.
- **Hard cap (incident 2026-06-29)**: a single Codex session replayed ~190K input tokens per call, 20+ calls in 6 minutes (11.8M fresh input in one day, 48% cache share). When session context approaches ~100K tokens, STOP — write the anchor note and start a fresh session from it. Never keep iterating inside a maxed context.
- Hook surface: `src/nougen_shards/hooks.py` provides semantic-anchor compaction via `pre_tool_use_hook`. Installing shell/global hooks remains mutation-gated.
- Local preflight wrapper: `.nougen-hooks\codex-anchor.cmd`. Use it when PowerShell execution policy blocks `.nougen-hooks\codex-anchor.ps1`.

## Startup Handoff
At the start of a Codex session in this repo, read the latest handoff:

```powershell
$env:PYTHONPATH='C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\src'
$env:NOUGEN_AGENT='codex'
& 'C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff read
```

If taking over an open item, acknowledge it:

```powershell
$env:PYTHONPATH='C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\src'
$env:NOUGEN_AGENT='codex'
& 'C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff ack --message "Codex has read the latest handoff and is taking over."
```

Use the venv Python path directly; `python`, `py`, and `nougen.bat` can fail in Codex shells when Python is not on PATH.

## Sol-Ai Hi Probe
The canonical liveness probe is:

```powershell
& powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\Users\super\Watchtower\Sol-Ai\tools\sol_hi_probe.ps1'
```

It mutates system state outside this repo, so run it only when Dave explicitly asks for the hi probe or gives equivalent approval. Summarize the trailing JSON payload.

## Shutdown Handoff
Before ending a substantive task:

```powershell
$env:PYTHONPATH='C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\src'
$env:NOUGEN_AGENT='codex'
# Write the note to a file first. Passing it inline via -m corrupts it: PowerShell
# expands $3/$4 inside currency to nothing (turning $3,922.07 into ,922.07), and a
# multi-line note through cmd.exe is cut at the first newline.
Set-Content -Path "$env:TEMP\handoff_note.md" -Encoding utf8 -Value @'
<structured_summary_message>
'@
& 'C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff create -a codex -g "<current_goal>" -M "$env:TEMP\handoff_note.md"
& 'C:\Users\super\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff rebuild-db
```

Summary message sections:
- `## Active Incidents`
- `## Ongoing Investigations`
- `## Recent Changes`
- `## Known Issues & Workarounds`
- `## Upcoming Events`

## Repo Commands
- Python tests: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests`
- Handoff docs: `docs/handoffs.md`
- Handoff storage: `.handoffs/`, including `codex handoffs/`

## Safety
Do not mutate database schemas, vaults, registry state, global packages, credentials, or system config without Dave's explicit approval. Keep replies concise and reference paths instead of dumping files.

## Task Queue (Open Engine lane)
Ticket-level delegation between provider lanes, mid-session — session handoffs stay mandatory, the queue is for individual work items:
- `nougen queue add -t "<title>" -m "<instructions>" -o <owner_lane> --sources "<context>" --stop "<stop conditions>" --dod "<definition of done>"` — write a self-contained ticket for another lane.
- `nougen queue claim [-a <agent>]` — atomically claim the oldest eligible ticket (claim lock: one winner). Also `--id <task_id>` for a specific ticket.
- `nougen queue block --id <task_id> --question "<exact blocking question>"` — on ambiguity, do NOT guess: park in `needs_input` with the precise decision needed.
- `nougen queue answer --id <task_id> --answer "<answer>"` — answer on the ticket; it re-enters `todo` with the answer attached.
- `nougen queue done --id <task_id> --did "<what was done>" --evidence "<proof>" [--not-done "<what was not>"]` — receipts are mandatory; a task cannot land without one.
- `nougen queue list` / `show --id <task_id>` / `smoke` — inspect lanes; smoke test creates, claims, and completes "Say hello from the queue".

Status lanes: `todo -> working -> needs_input -> done` (or `cancelled`). Before planning, each agent should check its lane: `nougen queue list -o <my_lane> --status todo`.
