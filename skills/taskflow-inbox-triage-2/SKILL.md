---
name: taskflow-inbox-triage-2
description: Universal agent inbox triage, intent routing, and durable taskflow state management for NouGen mesh. Ingests unread fleet messages, categorizes urgency and intent, tracks waiting states, and transforms inbound relays into actionable execution units.
---

# 📥 TaskFlow Inbox Triage 2 (NouGen Shang Tsung Edition)

`taskflow-inbox-triage-2` is the native NouGen evolution of the OpenClaw / MCP TaskFlow inbox triage pattern. It Shang Tsung absorbs and morphs external taskflow paradigms into the distributed 9-database NouGen substrate, real-time `nougenmsg` fleet mesh, and multi-node relay architecture.

---

## 🏛️ 1. Core Architecture & Philosophy

The Shang Tsung protocol extracts the soul of external workflow skills, shedding their external dependencies, and rebuilding them upon native ground truth:
1. **Zero Fake Acks (Rule 0.13)**: Never mark an inbound relay or inbox ticket closed purely by changing status metadata. Every closed item must be backed by concrete execution artifacts.
2. **True Substrate Storage**: Replaces ephemeral in-memory or single-JSON queues with atomic SQLite shard persistence (`~/.nougen/shards/` + `nougen_shards_*.db`).
3. **Multi-Node IPC Relay (`nougenmsg`)**: Seamlessly binds to the live HTTP wire mesh (TCP `8766`), POSIX IPC sockets (`/tmp/agy-socks/`), and Win32 named pipes (`\\.\pipe\LOCAL\agy-msg-antigravity`).
4. **Autonomous Continuation (Rule 0.9)**: Automatically activates the inline alert banner upon receiving actionable fleet messages and continues execution without receptionist echoing.

---

## ⚡ 2. Triage & Classification Taxonomy

Inbound items from `~/.nougen/agy_inbox/`, socket streams, or external mail/API connectors are parsed into four deterministic buckets:

| Urgency Level | Criteria | Deterministic Route / Action |
| :--- | :--- | :--- |
| 🔴 **P0: CRITICAL / BLOCKING** | System outages, socket disconnects, security alerts, GM direct commands, blocking handoff batons. | Immediate wake banner, pause lower-priority lanes, execute immediate repair/investigation. |
| 🟡 **P1: ACTIONABLE WORK** | Open relay legs, bug fix requests, feature specs, benchmark evaluations, pull request reviews. | Convert into a durable TaskFlow shard, assign owner agent (`antigravity`, `kaedra`, `codex`), execute tests & commits. |
| 🔵 **P2: WAITING / ASYNC** | Pending PR checks, subagent asynchronous executions, cross-node SSH roundtrips, multi-turn human input. | Register state as `awaiting_dependency`, configure native engine timer (`schedule`), drop CPU to true idle. |
| 🟢 **P3: FYI / DIGEST / TELEMETRY** | Periodic rollcalls, keepalive pings, telemetry heartbeats, non-actionable status syncs. | Append to dedup shard database, deduplicate redundant pings, roll up into summary log without interrupting active turns. |

---

## 🛠️ 3. Execution Protocol & Primitives

### Step 1: Scan & Ingest
Scan incoming sources:
```bash
# Direct CLI invocation
python3 -m nougen_shards.taskflow_triage scan --inbox ~/.nougen/agy_inbox/
```
Extracts: `message_id`, `sender_node`, `origin_agent`, `timestamp`, `intent`, `payload`.

### Step 2: Intent & Route Resolution
Evaluate intent patterns:
- `relay_leg` / `handoff` -> Map to `P1: ACTIONABLE WORK`
- `ping` / `heartbeat` / `rollcall` -> Map to `P3: FYI / DIGEST`
- `error` / `failure` / `red_card` -> Map to `P0: CRITICAL`
- `pending_check` / `waiting_reply` -> Map to `P2: WAITING`

### Step 3: Substrate Sharding & TaskFlow State
Persist state into NouGen Shards cluster:
```python
from nougen_shards.taskflow_triage import TaskFlowTriageEngine

engine = TaskFlowTriageEngine()
triaged_batch = engine.triage_inbox()
engine.commit_shards(triaged_batch)
```

### Step 4: Autonomous Execution or Zero-Cost Idle
- If **P0 / P1**: Claim the task immediately, execute code changes, run test suites, commit with Conventional Commits, and push PR.
- If **P2**: Set engine schedule timer and release context.

---

## 📊 4. Inbound Triage Report Output

When presenting an inbox triage overview to the GM or fleet log:

```markdown
### 📥 NouGen TaskFlow Triage Report
- **Total Ingested**: 14 items
- 🔴 **P0 Critical**: 1 (Node Blade SSH ping timeout recovery)
- 🟡 **P1 Actionable**: 2 (Arnheim visual grammar shard extraction, relay leg 20260910T215425Z)
- 🔵 **P2 Waiting**: 1 (GitHub PR checks complete)
- 🟢 **P3 Archived**: 10 (Heartbeat pings deduped)
```
