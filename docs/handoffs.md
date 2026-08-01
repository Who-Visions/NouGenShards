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

# Which computers are in this fleet, and what has each one been doing
nougen handoff machines

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

## Machines

A handoff answers "who left this note". Once more than one computer is in play
it also has to answer "from which box" — the branch, the uncommitted files and
the paths in a note only exist on the machine that wrote it.

Every record therefore carries a `machine` block, and every state change carries
the machine that made it. Nothing needs to be configured: the host is detected.
Set `NOUGEN_MACHINE` to give a box a stable human name instead of whatever
hostname it advertises.

```bash
export NOUGEN_MACHINE=who-mac-mini    # optional, but makes records readable
nougen handoff machines               # the fleet roster, derived from records
```

`nougen handoff read` marks a note written elsewhere as `⇢ REMOTE` so its git
state is never mistaken for the local tree, and `list` gains a Machine column.

The host is folded into `handoff_id` and the filename, so two computers working
the same branch in the same second cannot produce colliding records when the
`.handoffs` directory is synced between them.

| Field | Meaning |
|---|---|
| `machine.host` | Human name (`NOUGEN_MACHINE`, else the short hostname). |
| `machine.machine_id` | Stable 12-char id — hostname + OS + arch, hashed. |
| `machine.os` / `arch` / `platform` | What the note was written on. |
| `machine.user` / `repo_root` | Local account and checkout. Omitted when `NOUGEN_MACHINE_PRIVATE=1`. |
| `acknowledged_on` / `completed_on` / `blocked_on` | The box that claimed, finished, or blocked the work. |

## Sync

Records do not move between computers on their own. `nougen handoff sync` makes
the handoff directory its own small git repository — separate from the project
repo, which deliberately keeps handoffs out of source history — and exchanges
records with a remote.

```bash
nougen handoff sync-init --remote git@github.com:you/handoffs.git
nougen handoff sync            # commit local records, pull remote ones, push
```

Set `NOUGEN_HANDOFF_REMOTE` and every machine picks the remote up automatically.
`--no-push` receives only, `--no-pull` publishes only.

Arrival is the half that matters: a record that lands here has never fired its
`created` triggers on this machine, so sync replays them for newly-arrived
*remote* records — once, tracked by handoff id, not on every sync. That is what
lets one box react to work another finished while it was asleep.

What does **not** travel: `handoffs.db` (derived — rebuilt on arrival) and
`triggers.json`. The trigger registry is executable configuration; a rule
arriving from another machine would run commands here. `--share-triggers` opts
into distributing it, and `on_machine` scoping exists so one shared registry can
cover the whole fleet.

Each handoff is its own file, so simultaneous work on two boxes normally merges
cleanly. A genuine collision — the same record edited on both — aborts the merge
and says so rather than guessing; nothing is lost, and the directory is a normal
git repo you can resolve by hand.

## Triggers

A handoff is a message; a trigger is what makes it actionable across computers.
When the Mac writes "branch pushed, needs a Windows build", the Windows box can
react without a human relaying it.

Rules live in `.handoffs/triggers.json` and match against the record plus the
event that just happened. **Nothing runs unless you register a rule** — an empty
registry is a no-op — and `NOUGEN_TRIGGERS=off` is a hard kill switch per
machine. `NOUGEN_TRIGGERS=dry` records what would have fired without running it.

```bash
# When any *other* machine opens a handoff, pull the branch it names
nougen handoff trigger-add --trigger-id sync-remote \
  --on created --origin remote \
  --run 'git fetch origin "$NOUGEN_HANDOFF_BRANCH"'

# Only the Mac runs the release build, even though the registry is shared
nougen handoff trigger-add --trigger-id mac-build \
  --on completed --on-machine who-mac-mini --background \
  --run './scripts/build.sh'

nougen handoff triggers                      # what is registered here
nougen handoff trigger-test --event created  # dry run against the latest record
nougen handoff trigger-runs                  # audit log of what actually fired
nougen handoff trigger-disable --trigger-id mac-build
```

Events: `created`, `acknowledged`, `started`, `checkpoint`, `blocked`,
`completed`.

Matching is deliberately blunt — equality and substring, no expression language.
A rule that fires the wrong build on the wrong machine is worse than a rule too
dumb to express what you wanted.

| Filter | Effect |
|---|---|
| `--origin local\|remote\|any` | Whether the handoff came from this box or another one. |
| `--on-machine <host>` | Only run the rule on that machine — lets one registry be synced everywhere. |
| `--agent`, `--match-host`, `--match-branch`, `--match-goal` | Narrow by who/where/what. |
| `--background`, `--timeout` | Detach, or bound a foreground command (default 60s). |

The command runs through the shell with the handoff in its environment:
`NOUGEN_HANDOFF_EVENT`, `_ID`, `_PATH`, `_MD_PATH`, `_AGENT`, `_STATUS`,
`_GOAL`, `_BRANCH`, `_ORIGIN`, `_HOST`, `_MACHINE_ID`, plus `NOUGEN_LOCAL_HOST`
and `NOUGEN_LOCAL_MACHINE_ID` for the box executing it.

Every fire is recorded in `handoff_trigger_runs` with exit code and output tail.
A failing or hanging trigger never blocks the handoff write — the note is the
durable artifact, the automation is best-effort.

### JSON schema

```jsonc
{
  "handoff_id": "20260611_212647_who-mac-mini_main",
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
  "machine": {                 // which computer wrote this
    "host": "who-mac-mini",
    "machine_id": "cf5a69b32748",
    "platform": "darwin",
    "os": "Darwin 24.6.0",
    "arch": "x86_64",
    "user": "kushboygroup",    // omitted when NOUGEN_MACHINE_PRIVATE=1
    "repo_root": "/…/nougenshards"
  },
  "status": "open",            // "open" until acknowledged
  "acknowledged_by": null,     // agent that ran `ack`
  "acknowledged_at": null,     // ISO timestamp of the ack
  "acknowledged_on": null,     // machine that ran `ack`
  "orchestration": {
    "run_id": "2026-06-11T230401_codex",
    "started_by": "codex",
    "started_at": "2026-06-11T23:04:01",
    "checkpoints": [
      {
        "timestamp": "2026-06-11T23:04:01",
        "agent": "codex",
        "state": "started",
        "message": "Claiming this run",
        "host": "who-pc",              // where the checkpoint happened
        "machine_id": "9f21ab77c004"
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
| `NOUGEN_MACHINE` | Stable human name for this computer. Defaults to the short hostname. |
| `NOUGEN_MACHINE_ID` | Override the derived machine id (rarely needed; useful for tests and cloned images). |
| `NOUGEN_MACHINE_PRIVATE` | `1` omits the local account name and checkout path from records. |
| `NOUGEN_TRIGGERS` | `off` disables trigger execution on this machine; `dry` records matches without running them. |
| `NOUGEN_HANDOFF_REMOTE` | Git remote the handoff directory syncs with. |

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
- The base model is pull, not push: the incoming agent has to run
  `nougen handoff read`. Triggers close that gap only as far as you configure
  them — they fire on the machine where the state change happens, so a rule that
  needs to wake another box has to do the reaching out itself (push, webhook,
  sync script) in the command you give it.
- Sync is manual: `nougen handoff sync` runs when something runs it. Put it in a
  shell hook, a cron entry, or a trigger if you want it continuous — there is no
  daemon watching the remote.
- Trigger commands run through the shell with the operator's own privileges.
  The registry is a local file — treat it as executable configuration, not data.
