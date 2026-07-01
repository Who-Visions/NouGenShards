# Cross-Agent Handoffs

NouGenShards lets one coding agent leave a structured note for the next one. If
you bounce between Claude, Gemini, Codex, and local models on the same project,
a handoff captures *where you left off* — the goal, the git state, the open
tasks, and a free-text note — so the next agent doesn't start cold or redo work.

## What this is (and isn't)

This is **durable, asynchronous, cross-process** handoff. Agent A finishes a
session and writes a note to disk; Agent B reads it later in a completely
separate process — maybe a different machine, definitely a different model.

It is **not** the in-process delegation pattern you see in frameworks like
OpenAI Swarm, AutoGen, or LangGraph, where agents inside one running program
pass control to each other via tool calls over a message bus. Those solve
real-time orchestration. This solves *continuity across sessions*. Don't confuse
the two — they look similar and share the word "handoff," but the machinery and
the problem are different.

## The protocol

A handoff has three steps. The third is the one most systems skip, and the one
that actually makes it reliable:

1. **create** — the outgoing agent records the current state.
2. **read** — the incoming agent reviews the latest handoff.
3. **ack** — the incoming agent *acknowledges* it, stamping who picked it up and
   when. Until a handoff is acknowledged it stays `open`.

The acknowledgement is the "read-back" / forcing function: it makes the transfer
of responsibility unambiguous, so you can always tell whether a handoff was
actually picked up or just left hanging.

## Provider lanes

Claude, Gemini, and OpenAI/Codex are first-class provider lanes over the same
handoff protocol. The lane is just the `NOUGEN_AGENT` value plus its storage
folder:

| Provider | `NOUGEN_AGENT` | Folder |
|---|---|---|
| Claude | `claude` or `claude-cli` | `claude handoffs/` or `claude cli handoffs/` |
| Gemini | `gemini` | `gemini handoffs/` |
| OpenAI/Codex | `codex` | `codex handoffs/` |

Each provider should read at startup, ack when it takes responsibility, create a
handoff before ending substantive work, and rebuild the SQLite index. On Windows
Codex sessions where `python` is not on PATH, use `.venv\Scripts\python.exe`
with `PYTHONPATH=src`.

## Context/cache discipline

Provider handoffs are also cache anchors. The target cache-read share for
repeated work is 90%+. Before broad scans or synthesis, agents should read the
latest handoff, search compact context (`ctx search`, `search --dual --json`, or
MCP recall), and open only exact files/ranges needed. If cache health drops below
85% or input spikes, stop broad exploration and write a compact handoff/context
note before continuing. `src/nougen_shards/hooks.py` exposes a semantic-anchor
compaction hook for runtimes that can load provider hooks; installing shell or
global hooks is mutation-gated.
On Windows hosts that block PowerShell scripts, use the repo-local
`.nougen-hooks\codex-anchor.cmd` wrapper or run
`.venv\Scripts\python.exe -m nougen_shards.cli hook codex-anchor` with
`PYTHONPATH=src`.

## Orchestration boundary

The same file also acts as a lightweight orchestration boundary. It does not
spawn agents or run a scheduler. Instead, it records the state transitions that a
separate orchestrator, human operator, or next agent can trust:

1. **start** - claim the latest open handoff, acknowledge it, and create an
   `orchestration` run with a checkpoint stream.
2. **checkpoint** - append durable progress with a state of `in_progress`,
   `blocked`, or `complete`.
3. **complete** - close the run with a final checkpoint.

These actions make the handoff record usable as a local control plane: the live
runner can stay simple, while the state history survives process exits, model
switches, and desktop restarts.

## Usage

```bash
# Outgoing agent leaves a note
nougen handoff create --goal "Wire the Tauri sidecar" \
                      --message "Frontend done; Rust command stubbed, see lib.rs:72"

# Incoming agent reviews the latest open handoff
nougen handoff read

# ...and claims it
nougen handoff ack --message "Picking this up, starting on the sidecar"

# See the full history and which handoffs are still open
nougen handoff list

# Optional: use the handoff as an orchestration state boundary
nougen handoff start --message "Claiming this run"
nougen handoff checkpoint --message "Routes restored; testing now"
nougen handoff checkpoint --state blocked --message "Need Keymaker for deploy token"
nougen handoff complete --message "Verified and ready"

# Rebuild the local SQLite index from JSON records
nougen handoff rebuild-db

# Search the NouGenContext mirror for handoff state events
nougen ctx search "handoff"
nougen ctx get 12
```

`create` auto-detects the agent and, under Gemini Antigravity, auto-fills the
goal and task checklist from the active session. Outside that environment, pass
`--goal` yourself (see overrides below to wire your own task tracking).

`ack` targets the most recent `open` handoff by default. Use `--id <handoff_id>`
to acknowledge a specific one, or `--agent <name>` to filter by who created it.

## Storage layout

Handoffs are written to `.handoffs/` in the repo, one folder per agent, as a
machine-readable `.json` plus a human-readable `.md`. They are also mirrored
into `.handoffs/handoffs.db` for indexed local orchestration queries:

```
.handoffs/
├── gemini handoffs/
│   ├── handoff_20260611_212647_main.json
│   └── handoff_20260611_212647_main.md
├── claude handoffs/
├── handoffs.db
└── ...
```

`.handoffs/` is gitignored — these are local session artifacts, not repo
history.

### SQLite index

The JSON record is still the portable source artifact. The SQLite database is a
local index for fast orchestration state queries and checkpoint history:

- `handoff_records` stores one row per handoff with current status, agent, goal,
  branch, acknowledgement fields, completion fields, and the full JSON payload.
- `handoff_checkpoints` stores the ordered orchestration checkpoint stream.

Every `create`, `ack`, `start`, `checkpoint`, and `complete` command syncs the
record into SQLite. If the DB is missing or stale, run `nougen handoff rebuild-db`
to rebuild it from the JSON files.

### NouGenContext mirror

The same state transitions also write compact events to NouGenContext
`ctx_events`. This makes handoff activity searchable by context mode without
dumping full handoff JSON into the session database.

Mirrored event types:

- `HANDOFF_CREATED`
- `HANDOFF_ACKNOWLEDGED`
- `HANDOFF_ORCHESTRATION_STARTED`
- `HANDOFF_ORCHESTRATION_CHECKPOINT`
- `HANDOFF_ORCHESTRATION_BLOCKED`
- `HANDOFF_ORCHESTRATION_COMPLETED`
- `HANDOFF_DB_REBUILT`

Use `nougen ctx search <query>` to find compact event cards, then
`nougen ctx get <event_id>` to inspect the exact event and metadata. The JSON
handoff remains the portable source artifact, SQLite remains the local handoff
index, and NouGenContext is the searchable session-memory mirror.

### JSON schema

```jsonc
{
  "handoff_id": "20260611_212647_main",
  "timestamp": "2026-06-11T21:26:47",
  "goal": "Wire the Tauri sidecar",
  "message": "Frontend done; Rust command stubbed",
  "git": {
    "branch": "main",
    "changes": ["M src-tauri/src/lib.rs"],
    "commits": ["8cd1d77 fix: harden launcher"]
  },
  "tasks": { "completed": [], "in_progress": [], "pending": [] },
  "session_id": "79e7f783-...",
  "agent": "gemini",
  "status": "open",            // "open" until acknowledged
  "acknowledged_by": null,     // agent that ran `ack`
  "acknowledged_at": null,     // ISO timestamp of the ack
  "orchestration": {
    "run_id": "2026-06-11T230401_codex",
    "started_by": "codex",
    "started_at": "2026-06-11T23:04:01",
    "checkpoints": [
      {
        "timestamp": "2026-06-11T23:04:01",
        "agent": "codex",
        "state": "started",
        "message": "Claiming this run"
      }
    ]
  }
}
```

## Environment overrides

The system is portable — nothing is hardcoded to one machine or one agent:

| Variable | Effect |
|---|---|
| `NOUGEN_AGENT` | Forces the agent name for detection (e.g. `claude`, `codex`). Wins over auto-detection. |
| `NOUGEN_HANDOFF_DIR` | Where handoffs are stored. Defaults to `<repo>/.handoffs`. |
| `NOUGEN_HANDOFF_TASKS_DIR` | Directory holding `task.md` / `implementation_plan.md` for goal + checklist auto-fill. Defaults to the Gemini Antigravity brain layout; point it anywhere to use your own task tracking. |

## Reliability notes

- **Atomic writes.** Every JSON record is written to a temp file and atomically
  renamed into place, so an interrupted or concurrent write can never leave a
  truncated handoff that breaks `list` / `read`.
- **Queryable index.** State changes mirror into `.handoffs/handoffs.db`, while
  the JSON files remain readable even if the DB is deleted and rebuilt.
- **Git capture is bounded.** The `git` subprocess calls have a 10-second
  timeout each, so a wedged git process can't hang the CLI.

## Limitations (honest)

- Goal + task auto-fill only happens automatically under Gemini Antigravity (or
  whatever you point `NOUGEN_HANDOFF_TASKS_DIR` at). Other agents should pass
  `--goal` and rely on the git snapshot + message.
- There's no notification — the incoming agent has to run `nougen handoff read`.
  This is by design (it's a pull model, not a push bus), but it means handoffs
  are only as useful as the habit of checking them.
