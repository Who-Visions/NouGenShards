"""The wire's HTTP surface, kept out of the node's handler so it can be tested.

The node (tools/nougenmsg_node.py) resolves the caller first (fleet token or a
scoped guest token, see access.py), then hands ``/wire/*`` here:

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

from . import access
from . import adapters as A
from . import envelope as E
from . import receipts
from .access import Caller
from .address import Address
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
    def __init__(self, hub: Hub, owner: Optional[str] = None,
                 guests: Optional[access.GuestBook] = None, relay: str = "") -> None:
        self.hub = hub
        self._relay = relay
        self._owner = owner_token() if owner is None else owner
        self.guests = guests
        self.limiter = access.RateLimiter(hub.clock)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def from_env(cls, node: str, db_path: str) -> "WireService":
        key, scheme = receipts.resolve_key()
        if scheme != "node":
            # Never run on the shared /msg token or unsigned: make this node its own key.
            key, scheme = receipts.node_key(os.path.join(os.path.dirname(os.path.abspath(db_path)), "wire-receipt.key")), "node"
        hub = Hub(WireStore(db_path), node, key, A.enabled(), key_scheme=scheme)
        return cls(hub, guests=access.GuestBook(), relay=access.relay_token())

    def authenticate(self, token: str, fleet_token: str) -> Tuple[Optional[Caller], str]:
        return access.authenticate(token, fleet_token, self.guests, self.hub.clock(), relay=self._relay)

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
        if not self._owner or not presented:
            return False
        return hmac.compare_digest(self._owner.encode("utf-8"), str(presented).encode("utf-8", "replace"))

    def handle(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
               owner_header: str = "", caller: Caller = access.FLEET) -> Tuple[int, Dict[str, Any]]:
        route, _, query = path.partition("?")
        route = route.rstrip("/")
        q = {k: v[-1] for k, v in parse_qs(query).items()}
        body = body or {}
        ok, wait = self.limiter.take(caller, "send" if method == "POST" else "read")
        if not ok:
            return 429, {"error": "rate limited", "retry_after_s": wait,
                         "fix": f"slow down: this token allows {caller.limit('send')} sends a minute"}
        try:
            if method == "POST" and route == "/wire/send":
                return self._send(body, caller.fleet and self.is_owner(owner_header), caller)
            if method == "GET" and route == "/wire/inbox":
                who = q.get("for") or caller.address
                if not who:
                    return 400, {"error": "inbox needs for=<address>", "fix": "add ?for=lane/session"}
                if not caller.owns(who):
                    return 403, _forbidden(caller, _read_scope(caller))
                return 200, self.hub.inbox(who, int(q.get("after") or 0), int(q.get("limit") or 25))
            if method == "POST" and route == "/wire/ack":
                by = str(body.get("by") or caller.address)
                if not body.get("id") or not by:
                    return 400, {"error": "ack needs id and by", "fix": "send {\"id\": \"w-...\", \"by\": \"lane/session\"}"}
                if not caller.owns(by):
                    return 403, _forbidden(caller, _read_scope(caller, "acks"))
                out = self.hub.ack(str(body["id"]), by)
                code = 404 if out.get("state") == "unknown" else 409 if out.get("error") else 200
                return code, out
            if method == "GET" and route.startswith("/wire/status/"):
                env_id = route[len("/wire/status/"):]
                if not self._sees(caller, env_id):
                    return 404, {"id": env_id, "state": "unknown", "receipts": []}
                out = self.hub.status(env_id)
                return (404 if out["state"] == "unknown" else 200), out
            if method == "GET" and route == "/wire/info":
                info = {"wire": VERSION, "node": self.hub.node,
                        "push_lanes": sorted(self.hub.adapters),
                        "signed_receipts": bool(self.hub.key), "receipt_scheme": self.hub.key_scheme,
                        "owner_sign_off": bool(self._owner)}
                info["caller"] = caller.kind
                if caller.kind == "guest":
                    info.update(you=caller.address, may_message=sorted(caller.send_to),
                                sends_per_minute=caller.limit("send"))
                elif caller.kind == "lane":
                    info["you"] = caller.address
                return 200, info
        except (ValueError, TypeError) as exc:
            return 400, {"error": str(exc),
                         "fix": "check the address, kind and in_reply_to fields; docs/nougenmsg-wire-tester.md"}
        return 404, {"error": "not found", "path": route,
                     "fix": "routes: POST /wire/send, GET /wire/inbox, POST /wire/ack, GET /wire/status/<id>, GET /wire/info"}

    def _sees(self, caller: Caller, env_id: str) -> bool:
        row = self.hub.store.get(env_id)
        return bool(row) and caller.sees(row["env"])

    def _send(self, body: Dict[str, Any], owner: bool, caller: Caller = access.FLEET) -> Tuple[int, Dict[str, Any]]:
        if body.get("v") == 2:
            env = E.validate(dict(body))
            if not caller.may_send_as(env["from"]):
                return 403, _forbidden(caller, f"this token sends only as {caller.address}")
        else:
            named = str(body.get("from") or "").strip()
            if caller.kind == "lane" and named and caller.owns(named):
                sender = named
            elif caller.kind in ("lane", "guest"):
                sender = caller.address
            else:
                sender = named
            for f, v in (("from", sender), ("to", body.get("to")), ("text", body.get("text"))):
                if not str(v or "").strip():
                    raise ValueError(f"send needs {f}")
            env = E.make(sender, str(body["to"]), str(body["text"]),
                         kind=str(body.get("kind") or "msg"), in_reply_to=body.get("in_reply_to"),
                         priority=str(body.get("priority") or "normal"),
                         ttl_s=int(body.get("ttl_s") or E.DEFAULT_TTL_S), now=self.hub.clock())
        allowed, why = caller.may_send_to(Address.parse(env["to"]))
        if not allowed:
            return 403, _forbidden(caller, why)
        allow = bool(body.get("allow_actions")) and owner
        out = self.hub.send(env, allow_actions=allow, proof=caller.sender_proof)
        if out.get("conflict"):
            return 409, out
        if body.get("allow_actions") and not owner:
            out["note"] = "allow_actions ignored: it needs the owner token"
        if body.get("v") != 2 and body.get("from") and str(body["from"]) != env["from"]:
            out["note"] = f"from set to {env['from']}: this token can't name another sender"
        # A refusal is a 200 with state "refused" on purpose: older senders fall
        # through to another route on a 4xx, and a refused message must never
        # find a route around the guard.
        return 200, out


def _read_scope(caller: Caller, verb: str = "reads") -> str:
    if caller.kind == "shared":
        return (f"the shared token can send but never {'read' if verb == 'reads' else 'ack'}: "
                "use the connector or a lane token")
    return f"this token {verb} only as {caller.address}"


def _forbidden(caller: Caller, why: str) -> Dict[str, Any]:
    return {"error": "forbidden", "reason": why, "you": caller.address,
            "fix": "ask the node owner to widen this token, or message a lane it allows"}
