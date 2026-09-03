#!/usr/bin/env python3
"""Portable NouGenMsg node receiver: put any machine on the fleet message bus.

The fleet's live message transport pairs a fast local IPC channel with an HTTP
ingest for cross-machine sends.  The IPC half is platform specific (Windows
named pipes), which leaves macOS and Linux nodes unable to receive at all.
This module is the portable half: HTTP only, standard library only, so a node
joins the bus without forking platform-specific code.

Wire contract (identical to the HTTP side of the Windows listener, so an
existing ``send --node <name>`` reaches this process unchanged)::

    POST /msg     {"text": ..., "sender": ..., "priority": ...}  -> queue + inbox file
    GET  /status  {"status": "online", "node": ..., "pending_messages": N}
    GET  /health  {"ok": true}
    GET  /pop     drain and return the pending queue

Every message is written to the inbox directory as one JSON file, which is what
agent hooks drain into a session's context, and mirrored to a "last message"
state file for probes.

Configuration resolves from the environment first, then a documented fallback:

===========================  ===========================================
``NOUGEN_AGY_MSG_PORT``      listen port (default 8766)
``NOUGEN_AGY_MSG_BIND``      bind address (default 127.0.0.1; set
                             0.0.0.0 to accept cross-machine sends)
``NOUGEN_AGY_INBOX``         inbox directory (default ~/.nougen/agy_inbox)
``NOUGEN_MSG_STATE``         last-message file (default
                             ~/.nougen/state/agy_last_msg.json)
``NOUGEN_NODE_NAME``         node identity (default: short hostname)
===========================  ===========================================

Run it under whatever keeps a process alive on the platform: a launchd agent
with ``KeepAlive`` on macOS, a systemd user unit on Linux, or a scheduled task
on Windows.  A listener started from inside an agent turn dies with that turn,
so it needs a supervisor to be a real transport.
"""
from __future__ import annotations

import json
import os
import queue
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PENDING: "queue.Queue" = queue.Queue()

DEFAULT_PORT = 8766
DEFAULT_BIND = "127.0.0.1"  # opt into a LAN bind with NOUGEN_AGY_MSG_BIND
PREVIEW_CHARS = 400
SENDER_LABEL_CHARS = 64


def _env_path(key: str, *default_parts: str) -> Path:
    """Path from ``key`` if set, else ``~`` joined with ``default_parts``."""
    raw = os.environ.get(key, "").strip()
    return Path(raw) if raw else Path.home().joinpath(*default_parts)


def node_name() -> str:
    """This node's fleet identity: env first, else the short hostname."""
    raw = os.environ.get("NOUGEN_NODE_NAME", "").strip()
    if raw:
        return raw.lower()
    return (socket.gethostname() or "unknown").split(".")[0].lower()


INBOX = _env_path("NOUGEN_AGY_INBOX", ".nougen", "agy_inbox")
STATE = _env_path("NOUGEN_MSG_STATE", ".nougen", "state", "agy_last_msg.json")
NODE = node_name()


def safe_sender(raw: object) -> str:
    """A filename-safe sender label built from an allowlist, never a blocklist.

    The sender arrives over the network and is used to name a file, so this
    keeps only characters known to be inert in a path segment and drops
    everything else, rather than trying to enumerate the dangerous ones.
    An empty or fully-stripped value falls back to ``unknown``.
    """
    kept = [c for c in str(raw or "") if c.isalnum() or c in "._-"]
    label = "".join(kept).strip("._-")[:SENDER_LABEL_CHARS]
    return label or "unknown"


def inbox_path(filename: str) -> Path:
    """Resolve ``filename`` inside the inbox, refusing anything that escapes it.

    ``safe_sender`` already strips the characters that make an escape possible.
    This is the second, independent barrier: reduce the name to its last
    component, resolve it against the inbox, and refuse anything that does not
    land under the inbox root, so a future edit to the sanitizer cannot quietly
    reintroduce a traversal.
    """
    root = os.path.realpath(str(INBOX))
    candidate = os.path.realpath(os.path.join(root, os.path.basename(filename)))
    if not candidate.startswith(root + os.sep):
        raise ValueError("refusing to write outside the inbox: {!r}".format(filename))
    return Path(candidate)


def record(msg: dict) -> Path:
    """Persist one message to the inbox and the last-message state file."""
    INBOX.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    filename = "msg_{}_{}.json".format(int(time.time() * 1000), safe_sender(msg.get("sender")))
    path = inbox_path(filename)
    path.write_text(json.dumps(msg, indent=2), encoding="utf-8")
    STATE.write_text(json.dumps(msg, indent=2), encoding="utf-8")
    PENDING.put(msg)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print("\n[LIVE INCOMING MSG] ({}) from [{}]:\n   {}\n".format(
        stamp, msg.get("sender"), str(msg.get("text", ""))[:PREVIEW_CHARS]), flush=True)
    return path


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print("[http] {} {}".format(self.address_string(), fmt % args), flush=True)

    def _send(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self) -> str:
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    def do_GET(self) -> None:
        route = self._route()
        if route in ("/status", "/health", "/"):
            self._send({"status": "online", "service": "agy-msg", "node": NODE,
                        "timestamp": time.time(), "pending_messages": PENDING.qsize(),
                        "ok": True, "transport": "http"})
        elif route == "/pop":
            drained = []
            while not PENDING.empty():
                drained.append(PENDING.get_nowait())
            self._send({"messages": drained, "count": len(drained)})
        else:
            self._send({"error": "not found", "path": route}, 404)

    def do_POST(self) -> None:
        if self._route() != "/msg":
            self._send({"error": "not found", "path": self._route()}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            msg = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError) as exc:
            self._send({"error": "bad payload: {}".format(exc)}, 400)
            return
        if not isinstance(msg, dict) or not str(msg.get("text", "")).strip():
            self._send({"error": "message requires a non-empty 'text'"}, 400)
            return
        msg.setdefault("type", "live_message")
        msg.setdefault("sender", "unknown")
        msg.setdefault("priority", "normal")
        msg.setdefault("timestamp", time.time())
        msg["target"] = msg.get("target") or NODE
        path = record(msg)
        self._send({"delivered": True, "method": "http", "node": NODE, "file": path.name})


def resolve_port() -> "tuple":
    """Listen port and where it came from, so startup can log its provenance."""
    raw = os.environ.get("NOUGEN_AGY_MSG_PORT", "").strip()
    if raw.isdigit() and 0 < int(raw) < 65536:
        return int(raw), "env"
    return DEFAULT_PORT, "fallback"


def main() -> int:
    port, source = resolve_port()
    bind = os.environ.get("NOUGEN_AGY_MSG_BIND", "").strip() or DEFAULT_BIND
    print("[nougenmsg_node] node={} bind={}:{} inbox={} port_source={}".format(
        NODE, bind, port, INBOX, source), flush=True)
    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[nougenmsg_node] stopping", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
