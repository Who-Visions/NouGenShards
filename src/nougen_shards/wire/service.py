"""The wire's HTTP surface, kept out of the node's handler so it can be tested.

The node (tools/nougenmsg_node.py, msgs.nougenai.com) authenticates the
request with its X-NGS-Token first, then hands ``/wire/*`` here:

    POST /wire/send          {envelope} or {from, to, text, kind?, in_reply_to?, priority?, ttl_s?}
    GET  /wire/inbox?for=<address>&after=<seq>&limit=<n>
    POST /wire/ack           {id, by}
    GET  /wire/status/<id>
    GET  /wire/info

The owner's sign-off for an action to an actuator lane is never a body field:
only a request carrying the separate owner token (X-NGS-Owner, matched against
NOUGEN_WIRE_OWNER_TOKEN) may set ``allow_actions``. Without an owner token
configured, nobody can, and the guard refuses action words to actuators.
"""
from __future__ import annotations

import hmac
import os
import threading
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs

from . import adapters as A
from . import envelope as E
from . import receipts
from .hub import Hub
from .store import WireStore

VERSION = 2


def owner_token() -> str:
    tok = os.environ.get("NOUGEN_WIRE_OWNER_TOKEN", "").strip()
    if tok:
        return tok
    try:
        from nougen_shards.keymaker import get_secret
        return str(get_secret("NOUGEN_WIRE_OWNER_TOKEN") or "").strip()
    except Exception:  # pylint: disable=broad-except
        return ""


class WireService:
    def __init__(self, hub: Hub, owner: Optional[str] = None) -> None:
        self.hub = hub
        self._owner = owner_token() if owner is None else owner
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def from_env(cls, node: str, db_path: str) -> "WireService":
        hub = Hub(WireStore(db_path), node, receipts.receipt_key(), A.enabled())
        return cls(hub)

    # -- pump ----------------------------------------------------------------
    def start_pump(self, interval_s: float = 5.0) -> None:
        if self._thread and self._thread.is_alive():
            return

        def loop() -> None:
            while not self._stop.wait(interval_s):
                try:
                    self.hub.pump()
                except Exception as exc:  # pylint: disable=broad-except
                    print(f"[wire] pump error: {type(exc).__name__}: {exc}", flush=True)

        self._thread = threading.Thread(target=loop, name="wire-pump", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # -- requests ------------------------------------------------------------
    def is_owner(self, presented: str) -> bool:
        return bool(self._owner) and hmac.compare_digest(self._owner, str(presented or ""))

    def handle(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
               owner_header: str = "") -> Tuple[int, Dict[str, Any]]:
        route, _, query = path.partition("?")
        route = route.rstrip("/")
        q = {k: v[-1] for k, v in parse_qs(query).items()}
        body = body or {}
        try:
            if method == "POST" and route == "/wire/send":
                return self._send(body, self.is_owner(owner_header))
            if method == "GET" and route == "/wire/inbox":
                if not q.get("for"):
                    return 400, {"error": "inbox needs for=<address>"}
                return 200, self.hub.inbox(q["for"], int(q.get("after") or 0), int(q.get("limit") or 25))
            if method == "POST" and route == "/wire/ack":
                if not body.get("id") or not body.get("by"):
                    return 400, {"error": "ack needs id and by"}
                out = self.hub.ack(str(body["id"]), str(body["by"]))
                code = 404 if out.get("state") == "unknown" else 409 if out.get("error") else 200
                return code, out
            if method == "GET" and route.startswith("/wire/status/"):
                out = self.hub.status(route[len("/wire/status/"):])
                return (404 if out["state"] == "unknown" else 200), out
            if method == "GET" and route == "/wire/info":
                return 200, {"wire": VERSION, "node": self.hub.node,
                             "push_lanes": sorted(self.hub.adapters),
                             "signed_receipts": bool(self.hub.key),
                             "owner_sign_off": bool(self._owner)}
        except ValueError as exc:
            return 400, {"error": str(exc)}
        return 404, {"error": "not found", "path": route}

    def _send(self, body: Dict[str, Any], owner: bool) -> Tuple[int, Dict[str, Any]]:
        if body.get("v") == 2:
            env = E.validate(dict(body))
        else:
            for field in ("from", "to", "text"):
                if not str(body.get(field) or "").strip():
                    raise ValueError(f"send needs {field}")
            env = E.make(str(body["from"]), str(body["to"]), str(body["text"]),
                         kind=str(body.get("kind") or "msg"), in_reply_to=body.get("in_reply_to"),
                         priority=str(body.get("priority") or "normal"),
                         ttl_s=int(body.get("ttl_s") or E.DEFAULT_TTL_S), now=self.hub.clock())
        allow = bool(body.get("allow_actions")) and owner
        out = self.hub.send(env, allow_actions=allow)
        if body.get("allow_actions") and not owner:
            out["note"] = "allow_actions ignored: it needs the owner token"
        # A refusal is a 200 with state "refused" on purpose: older senders fall
        # through to another route on a 4xx, and a refused message must never
        # find a route around the guard.
        return 200, out
