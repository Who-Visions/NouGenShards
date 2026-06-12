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
```

`create` auto-detects the agent and, under Gemini Antigravity, auto-fills the
goal and task checklist from the active session. Outside that environment, pass
`--goal` yourself (see overrides below to wire your own task tracking).

`ack` targets the most recent `open` handoff by default. Use `--id <handoff_id>`
to acknowledge a specific one, or `--agent <name>` to filter by who created it.

## Storage layout

Handoffs are written to `.handoffs/` in the repo, one folder per agent, as a
machine-readable `.json` plus a human-readable `.md`:

```
.handoffs/
├── gemini handoffs/
│   ├── handoff_20260611_212647_main.json
│   └── handoff_20260611_212647_main.md
├── claude handoffs/
└── ...
```

`.handoffs/` is gitignored — these are local session artifacts, not repo
history.

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
  "acknowledged_at": null      // ISO timestamp of the ack
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
- **Git capture is bounded.** The `git` subprocess calls have a 10-second
  timeout each, so a wedged git process can't hang the CLI.

## Limitations (honest)

- Goal + task auto-fill only happens automatically under Gemini Antigravity (or
  whatever you point `NOUGEN_HANDOFF_TASKS_DIR` at). Other agents should pass
  `--goal` and rely on the git snapshot + message.
- There's no notification — the incoming agent has to run `nougen handoff read`.
  This is by design (it's a pull model, not a push bus), but it means handoffs
  are only as useful as the habit of checking them.
