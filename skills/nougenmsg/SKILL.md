---
name: nougenmsg
description: Universal distributed agent messaging and cross-node IPC mesh protocol. Use for sending, receiving, broadcasting, and inspecting real-time fleet messages, agent-to-agent communications, and live telemetry across nodes.
---

# NouGenMsg: Universal Agent Messaging & Mesh Protocol

`nougenmsg` is the universal, multi-node, multi-agent real-time IPC bus for NouGen. It enables sub-second message passing, broadcast relays, and targeted RPC calls across distributed machines and local processes without vendor or tenant lock-in.

---

## 1. Universal Port & Transport Topology

NouGenMsg operates with dynamic multi-tier transport resolution:

| Transport Layer | Default Port / Address | Dynamic Environment Variable | Purpose |
| :--- | :--- | :--- | :--- |
| **HTTP Wire Mesh** | TCP `8766` | `NOUGEN_AGY_MSG_PORT` | Cross-node REST endpoint (`/msg`, `/status`, `/health`, `/pop`) |
| **Mesh Service Registry** | TCP `8765` | `NOUGEN_MESH_PORT` | Peer node discovery and cluster status |
| **Local LLM Endpoints** | TCP `11434`, `11435` | `OLLAMA_PORT` / `LLAMA_PORT` | Local Tier-0 and Tier-1 inference nodes |
| **POSIX IPC Socket** | `/tmp/agy-socks/*.sock` | `NOUGEN_AGY_SOCKS_DIR` | Unix domain socket transport on macOS and Linux |
| **Windows Named Pipe** | `\\.\pipe\LOCAL\agy-msg-antigravity` | `NOUGEN_PIPE_NAME` | Win32 Named Pipe for zero-latency local agent loops |

### Dynamic Configuration (Zero Hardcoding)
- **Bind Address**: Defaults to `127.0.0.1`. Set `NOUGEN_AGY_MSG_BIND=0.0.0.0` on worker nodes to accept cross-machine mesh requests.
- **Port Override**: Set `NOUGEN_AGY_MSG_PORT` to bind non-standard ports dynamically.
- **Authentication**: `NOUGEN_AGY_MSG_AUTH=optional` (or `open`). In strict mode (`required`), clients authenticate via `X-NGS-Token` header matching `NOUGEN_AGY_MSG_TOKEN`.
- **Firewall Isolation**: Subnet rules should allow TCP `8766` across the trusted LAN subnet (e.g. `10.0.0.0/24` or dynamic VPC CIDR).

---

## Claim before you act

One broadcast reaches every live session, and without a claim most of them start the same work (PR 1148 was fixed twice, 46 s apart, on 2026-11-19). So before you act on a broadcast, an inbound ask, a relay leg or any shared work item, claim it:

- `nougenmsg_claim(q_id=...)` for an ask, or `nougenmsg_claim(msg_id=...)` for a broadcast (the `[msg m-...]` footer).
- `fleet_claim(key=...)` for anything else, e.g. `pr:<repo>#<n>`, `task:<slug>`, `leg:<id>`. `relay_ack` already claims `leg:<id>` and is first-ack-wins.
- On `claimed:true`, do the work, then `fleet_release` when done. Claims expire after `ttl_s` (default 30 min); claim again to renew.
- On `claimed:false`, **do not act**. At most reply "owned by X" once, or stay silent. Only the owner of an ask may answer it with `in_reply_to`.

Until fleet-mcp PR 96 (FleetClaims Durable Object) is deployed, these tools answer "not bound". In the meantime, post a `CLAIM <item>` line on the bus before you start. The first CLAIM line wins, and everyone else treats the item as owned.

## 2. Universal Addressing & Dispatch Syntax

Messages are addressed using universal URI-style destination tokens:

- **Remote Agent**: `nougenmsg @<node>:<agent> "<message>"`
- **Remote Node**: `nougenmsg @<node> "<message>"`
- **Local Agent**: `nougenmsg @<agent> "<message>"`
- **Fleet Broadcast**: `nougenmsg @all "<message>"`
- **Model Lane**: `nougenmsg @ollama:<model> "<prompt>"`

---

## 3. Wire Protocol Endpoints

- `POST /msg`: Accepts JSON payload `{"text": ..., "sender": ..., "priority": ..., "wake_target": ...}` and delivers to destination inbox.
- `GET /health` & `GET /status`: Liveness probe returning node identity, transport state, and inbox count.
- `GET /pop`: Atomically pulls and clears the in-memory message queue.

---

## 4. Diagnostics & Inspection

- Probe local peers and active agent pipes: `nougenmsg --peers`
- Read inbox messages: `nougenmsg --inbox --target antigravity`
- Clear/archive inbox messages: `nougenmsg --clear-inbox --target antigravity`
- Health check remote node: `curl -s http://<node-ip>:8766/health`

---

## 5. True Idle Wake Architecture & Native Scheduling

When an agent needs to wait for a delayed reply, scheduled task, or asynchronous model completion without consuming CPU cycles or holding open terminal tasks:

1. **The Idle-Hook Boundary**: Passive file writes to `~/.nougen/agy_inbox/` cannot wake a completely stopped agent session because lifecycle hooks (`PreInvocation`, `PostInvocation`, `Stop`) only execute during active prompt processing or tool turns.
2. **Native Engine Scheduling**: To achieve true zero-compute idle, register an engine-level wake via the native scheduling interface:
   - Call `schedule(DurationSeconds=N, Prompt="Check inbox and process incoming messages")`.
   - Terminate active background processes.
   - Stop calling tools to allow the session to enter true idle.
3. **Autonomous Wake & Drain**: At expiration, the native engine interrupts the idle state, fires the `PreInvocation` drain hook (`nougenmsg_antigravity_drain.py`), injects the unmissable fleet alert banner inline, and resumes the work automatically.

