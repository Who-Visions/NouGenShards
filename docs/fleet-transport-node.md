# Putting a node on the fleet transport

Two long-running processes make a machine a full participant in the fleet:
a **message receiver** so other nodes can reach it, and a **relay watch** so it
notices when work is handed to it. Both live in `tools/`, depend only on the
standard library, and read their configuration from the environment.

| Process | File | What it does |
| --- | --- | --- |
| Message receiver | `tools/nougenmsg_node.py` | Serves the message wire contract on a port so `send --node <name>` from another machine lands in this node's inbox. |
| Relay watch | `tools/relay_watch_node.py` | Pulls the relay clone on an interval and announces new legs into the same inbox. |

Both write to one inbox directory, so a session has a single place to look.

## Why the receiver is HTTP only

The full transport pairs a fast local IPC channel with an HTTP ingest for
cross-machine sends. The IPC half uses Windows named pipes, which cannot exist
on macOS or Linux. `nougenmsg_node.py` implements the portable half, and it
speaks the same wire contract, so an existing sender reaches it unchanged:

```
POST /msg     {"text": ..., "sender": ..., "priority": ...}
GET  /status  {"status": "online", "node": ..., "pending_messages": N}
GET  /health  {"ok": true}
GET  /pop     drain the pending queue
```

## A listener needs a supervisor

A process started from inside an agent turn dies when that turn ends. If a node
reports its transport as live but nothing is listening a minute later, this is
almost always why. Give each process to the platform's supervisor and let it
restart on failure.

Verify with the socket and the endpoint, never with a log line alone:

```bash
curl -s http://127.0.0.1:8766/status
```

### macOS (launchd)

Write a `KeepAlive` agent to `~/Library/LaunchAgents/`, substituting your own
interpreter and checkout paths:

```xml
<key>ProgramArguments</key>
<array>
  <string>/usr/bin/python3</string>
  <string>/PATH/TO/tools/nougenmsg_node.py</string>
</array>
<key>EnvironmentVariables</key>
<dict>
  <key>NOUGEN_NODE_NAME</key><string>YOUR-NODE-NAME</string>
</dict>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
```

Load it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/NAME.plist`
and confirm with `launchctl list`.

### Linux (systemd user unit)

```ini
[Service]
ExecStart=/usr/bin/python3 /PATH/TO/tools/relay_watch_node.py
Restart=always
Environment=NOUGEN_RELAY_WATCH_SECS=60

[Install]
WantedBy=default.target
```

### Windows (Task Scheduler)

Register a task that runs the script under `pythonw.exe` so no console window
takes focus, with no execution time limit and restart on failure. Redirect
output to a log file: under `pythonw` both streams are `None`, and an HTTP
server writes to standard error on every request.

## Configuration

Every environment-shaped value resolves from the environment first, then a
probe where one makes sense, then a documented fallback. Nothing is hardcoded
to one machine.

| Variable | Used by | Default |
| --- | --- | --- |
| `NOUGEN_NODE_NAME` | receiver | short hostname |
| `NOUGEN_AGY_MSG_PORT` | receiver | `8766` |
| `NOUGEN_AGY_MSG_BIND` | receiver | `127.0.0.1` (set `0.0.0.0` to accept sends from other machines) |
| `NOUGEN_AGY_INBOX` | both | `~/.nougen/agy_inbox` |
| `NOUGEN_MSG_STATE` | receiver | `~/.nougen/state/agy_last_msg.json` |
| `NOUGEN_RELAY_DIR` | watch | probe for a clone with a handoff directory |
| `NOUGEN_RELAY_WATCH_SECS` | watch | `60` |
| `NOUGEN_RELAY_CURSOR` | watch | `~/.nougen/state/relay_watch.json` |
| `NOUGEN_RELAY_WATCH_ONCE` | watch | unset (loop forever) |

Node addresses come from `NOUGEN_NODE_<NAME>_IP` when hostname resolution does
not work on your network. Prefer that over editing an address table: a checked-in
address is a claim about someone else's network, and it goes stale silently.

## Two failure modes worth recognising

**The watch pulls but nothing arrives.** On macOS, an HTTPS clone using the
keychain credential helper pulls fine from a GUI-session agent and fails from a
non-interactive SSH shell with `could not read Username`. The keychain is locked
outside the desktop session. That is not a broken remote or an expired token.

**The first run says nothing.** By design. The cursor adopts the current listing
so installing on a node with thousands of existing legs does not replay them.
Announcements begin with the next new leg.
