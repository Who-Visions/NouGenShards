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
                  Response: {"delivered": true, "node": ..., "file": ...}
                  plus an OPTIONAL "elevated" object. Senders MUST tolerate its
                  absence: a missing "elevated" means "not evaluated", never
                  "denied". It is an internal enrichment on nodes that run the
                  judgment gate, not part of the cross-node contract.
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

# Opt-in auth: unset means open, exactly as before (an unupgraded sender keeps
# working). Set means every POST /msg must present it, since a message that
# passes auth may be eligible for elevated delivery (see the drain hooks),
# not just an inbox write. The receiver only ever sees this via env — never
# read from a plist, never logged, never echoed back in a response.
AUTH_TOKEN = os.environ.get("NOUGEN_AGY_MSG_TOKEN", "").strip()

# AUTH_LATCH says "a token WAS deployed on this node", which is a different
# fact from "a token resolved just now". Without the distinction, a vault miss
# is indistinguishable from a fresh un-provisioned node, and the fail-open rule
# below silently downgrades a hardened receiver to accept-all.
#
# That is not hypothetical. Observed 2026-09-03 on a live LAN-reachable node:
# one key stopped resolving, the launch wrapper exported an empty string, and a
# routine reload flipped the receiver from auth=required to auth=open for ~37
# minutes. Unauthenticated POSTs were accepted. Nothing announced it, because
# from the code's point of view a node with no token has simply never been set
# up. Fail-open belongs in a rollout, never in a gate that was already closed.
#
# Fail-SAFE parsing: any value other than an explicit off-word latches, so a
# typo closes the door rather than opening it.
_AUTH_LATCH_RAW = os.environ.get("NOUGEN_AGY_MSG_AUTH", "").strip()
AUTH_LATCH = _AUTH_LATCH_RAW.lower() not in ("", "0", "off", "false", "optional")

# Elevated delivery: writes directly into a live Claude Code session's
# messaging socket, framed identically to a real cross-session message. Only
# reachable for senders that already passed AUTH_TOKEN above (network gate),
# and only after Kaedra approves the content (judgment gate) — see
# _agy_live_delivery.py, shared with relay_watch_node.py so both transports
# feed the same audited decision instead of two copies that could drift.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _agy_live_delivery import gate_and_deliver, registry_parity_ok  # noqa: E402


def _auth_mode() -> str:
    """The startup line's auth field, which must be able to say LATCHED-NO-TOKEN.

    A node whose config claims protection it does not have is worse than one
    that knows it is open, because the wrong belief stops anyone looking. That
    happened on this fleet: a latch was set in a service definition while the
    running code had no reference to it, and the node was reported as fail-closed
    for an hour while it was fail-open. Printing the latch AS READ BY THIS CODE
    makes a config-only change unable to masquerade as protection: if the value
    does not appear here, this build is not reading it.
    """
    if AUTH_TOKEN:
        return "required(latch={})".format("on" if AUTH_LATCH else "off")
    if AUTH_LATCH:
        return "LATCHED-NO-TOKEN:refusing-all"
    return "open(unlatched)"


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


try:  # discovery, not configuration: absent adapters mean waking is impossible here
    from wake import enabled as _wake_enabled, status as _wake_status, wake as _wake_dispatch
except Exception:  # pylint: disable=broad-except
    _wake_enabled = lambda: False               # noqa: E731
    _wake_status = lambda: {"available": [], "unavailable": {"wake": "package not importable"}}
    _wake_dispatch = None


def _maybe_wake(msg: dict, verdict: dict) -> dict:
    """Wake an idle agent, but only for a message the gates already approved.

    Three refusals, each reported rather than silent:
    * no adapter imports here -> "unavailable", so a node that cannot be woken
      says so instead of appearing to accept and doing nothing;
    * the gate did not approve -> "not approved", so waking can never be a way
      around a judgment that delivery had to satisfy;
    * no explicit target -> "no target", so waking is opt-in per message even
      after approval, and an ordinary status ping never starts an agent.
    """
    if not _wake_enabled() or _wake_dispatch is None:
        return {"attempted": False, "wake": "unavailable", **_wake_status()}
    approved = bool(verdict.get("kaedra_approved")) or \
        verdict.get("origin") == "user_verified"
    if not approved:
        return {"attempted": False, "wake": "not approved",
                "reason_code": verdict.get("reason_code")}
    target = str(msg.get("wake_target") or "").strip()
    if not target:
        return {"attempted": False, "wake": "no target"}
    return _wake_dispatch(target, str(msg.get("text", "")), msg)


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
        if AUTH_LATCH and not AUTH_TOKEN:
            # Latched but nothing resolved: refuse rather than serve openly.
            # A node that was provisioned and lost its secret is a fault to
            # report, not a fresh node to welcome.
            self._send({"error": "unauthorized", "reason":
                        "auth latched required but no token resolved"}, 401)
            return
        if AUTH_TOKEN and self.headers.get("X-NGS-Token", "") != AUTH_TOKEN:
            self._send({"error": "unauthorized"}, 401)
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
        path = record(msg)  # inbox write always happens — covers a session that's asleep

        elevated = {"attempted": False}
        if AUTH_TOKEN:  # opting into auth is opting into the elevated pathway
            elevated = gate_and_deliver(
                str(msg.get("text", "")), str(msg.get("sender", "unknown")),
                message_id=msg.get("message_id"),  # honored if the sender provides one
                origin=str(msg.get("origin", "peer")),
                origin_proof=msg.get("origin_proof"))
            # Waking STARTS an agent where delivery only reaches one that is
            # already live, so it runs strictly after the same gates and only
            # on their approval. Never reachable for an unapproved message,
            # and never switched on by anything in the message itself: see
            # tools/wake for why availability is discovered, not configured.
            elevated["wake"] = _maybe_wake(msg, elevated)

        self._send({"delivered": True, "method": "http", "node": NODE, "file": path.name,
                    "elevated": elevated})


def resolve_port() -> "tuple":
    """Listen port and where it came from, so startup can log its provenance."""
    raw = os.environ.get("NOUGEN_AGY_MSG_PORT", "").strip()
    if raw.isdigit() and 0 < int(raw) < 65536:
        return int(raw), "env"
    return DEFAULT_PORT, "fallback"


def main() -> int:
    port, source = resolve_port()
    bind = os.environ.get("NOUGEN_AGY_MSG_BIND", "").strip() or DEFAULT_BIND
    print("[nougenmsg_node] node={} bind={}:{} inbox={} port_source={} auth={} kaedra_gate={}".format(
        NODE, bind, port, INBOX, source,
        _auth_mode(),
        "configured" if os.environ.get("KAEDRA_GATEWAY_TOKEN", "").strip() else "unset"),
        flush=True)
    ok, detail = registry_parity_ok()
    print("[nougenmsg_node] registry_parity={} ({})".format("ok" if ok else "MISMATCH", detail), flush=True)
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
