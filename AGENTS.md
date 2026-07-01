# NouGenShards - OpenAI/Codex Agent Rules

## Role
Codex is Coach, not Player: inspect, plan, patch narrowly, verify, and leave durable handoffs. Prefer local context and existing repo tools before reasoning from scratch.

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
- Before broad scans or synthesis, use handoff read plus `ctx search`, `search --dual --json`, or `nougen-shards` MCP recall.
- Prefer compact context cards over raw transcripts, full handoff bodies, full token reports, or whole-file dumps.
- Open exact files and line ranges only; preserve evidence as paths, event IDs, commands, and error codes.
- If cache health drops below 85% or input spikes, stop exploration, write a compact handoff/context note, then continue from that anchor.
- Hook surface: `src/nougen_shards/hooks.py` provides semantic-anchor compaction via `pre_tool_use_hook`. Installing shell/global hooks remains mutation-gated.
- Local preflight wrapper: `.nougen-hooks\codex-anchor.cmd`. Use it when PowerShell execution policy blocks `.nougen-hooks\codex-anchor.ps1`.

## Startup Handoff
At the start of a Codex session in this repo, read the latest handoff:

```powershell
$env:PYTHONPATH='%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\src'
$env:NOUGEN_AGENT='codex'
& '%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff read
```

If taking over an open item, acknowledge it:

```powershell
$env:PYTHONPATH='%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\src'
$env:NOUGEN_AGENT='codex'
& '%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff ack --message "Codex has read the latest handoff and is taking over."
```

Use the venv Python path directly; `python`, `py`, and `nougen.bat` can fail in Codex shells when Python is not on PATH.

## Sol-Ai Hi Probe
The canonical liveness probe is:

```powershell
& powershell -NoProfile -ExecutionPolicy Bypass -File '%USERPROFILE%\Watchtower\Sol-Ai\tools\sol_hi_probe.ps1'
```

It mutates system state outside this repo, so run it only when Dav3 explicitly asks for the hi probe or gives equivalent approval. Summarize the trailing JSON payload.

## Shutdown Handoff
Before ending a substantive task:

```powershell
$env:PYTHONPATH='%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\src'
$env:NOUGEN_AGENT='codex'
& '%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff create -a codex -g "<current_goal>" -m "<structured_summary_message>"
& '%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe' -m nougen_shards.cli handoff rebuild-db
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
Do not mutate database schemas, vaults, registry state, global packages, credentials, or system config without Dav3's explicit approval. Keep replies concise and reference paths instead of dumping files.
