"""The hub: ingest, guard, store, push, ack, receipts.

One hub runs per node (the owner's msgs node fronts one). Every
route into the fleet (the connector, a CLI, another node, an app bridge)
hands envelopes to a hub, so every route gets the same guard, the same dedupe
and the same receipts.

Push adapters wake a receiver as a new turn. Each one is a callable
``adapter(env, turn_text) -> {"pushed": bool, "verified": bool, "detail": str}``
keyed by lane. ``verified`` means the receiver confirmed it (Antigravity's
socket ack, a bridge reply); a bare socket write is ``pushed`` only. A model
lane that answers in the same call returns ``reply``, and the hub routes it back
to the sender as an answer. A lane with no adapter is a pull lane: its receiver
reads the inbox and acks.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

from . import envelope as E
from . import guard, receipts
from .address import Address
from .store import WireStore

log = logging.getLogger(__name__)

Adapter = Callable[[Dict[str, Any], str], Dict[str, Any]]


class Hub:
    def __init__(self, store: WireStore, node: str, key: bytes = b"",
                 adapters: Optional[Dict[str, Adapter]] = None,
                 clock: Callable[[], float] = time.time, key_scheme: str = "node") -> None:
        self.store, self.node, self.key = store, node, key
        self.key_scheme = key_scheme if key else "unsigned"
        if not key:
            log.warning("wire hub on %s has no receipt key: every receipt is marked unsigned", node)
        self.adapters: Dict[str, Adapter] = dict(adapters or {})
        self.clock = clock

    def _receipt(self, env: Dict[str, Any], state: str, detail: str = "") -> Dict[str, Any]:
        r = receipts.sign(self.key, E.canonical(env), env["id"], self.node, state, detail, self.clock(),
                          scheme=self.key_scheme)
        self.store.add_receipt(r)
        return r

    # -- ingest ------------------------------------------------------------
    def send(self, env: Dict[str, Any], allow_actions: bool = False, push: bool = True) -> Dict[str, Any]:
        E.validate(env)
        now = self.clock()
        if float(env["expires"]) <= now:
            return {"id": env["id"], "state": "expired", "receipts": []}
        verdict = guard.check(env, allow_actions=allow_actions)
        if not verdict.ok:
            r = receipts.sign(self.key, E.canonical(env), env["id"], self.node, "refused", verdict.rule, now,
                              scheme=self.key_scheme)
            return {"id": env["id"], "state": "refused", "guard": verdict.as_dict(), "receipts": [r]}
        inserted, state = self.store.put(env, now)
        if not inserted:
            stored = self.store.get(env["id"])
            if stored and E.canonical(stored["env"]) != E.canonical(env):
                return {"id": env["id"], "state": state, "conflict": True,
                        "error": "this id was already used for a different message; send a new id"}
            return {"id": env["id"], "state": state, "duplicate": True, "receipts": self.store.receipts(env["id"])}
        self._receipt(env, "accepted", f"guard {verdict.rule}")
        if env["kind"] == "answer":
            self._close_ask(env)
        if push:
            state = self._push(env)
        return {"id": env["id"], "state": state, "duplicate": False, "guard": verdict.as_dict(),
                "receipts": self.store.receipts(env["id"])}

    def _close_ask(self, answer: Dict[str, Any]) -> None:
        ask = self.store.get(str(answer["in_reply_to"]))
        if ask and ask["state"] not in ("answered", "expired"):
            self.store.set_state(ask["env"]["id"], "answered", self.clock(), acked_by=answer["from"])
            self._receipt(ask["env"], "answered", f"by {answer['from']} in {answer['id']}")

    # -- push and retry ----------------------------------------------------
    def _push(self, env: Dict[str, Any]) -> str:
        to = Address.parse(env["to"])
        adapter = self.adapters.get(to.lane)
        if adapter is None:
            return "accepted"  # pull lane: waits in its inbox for the receiver to read and ack
        if to.session and not getattr(adapter, "pins_session", False):
            # A pinned message reaches only that session. This transport can only
            # wake the whole lane, so the message waits in that session's inbox.
            self.store.park(env["id"])
            return "accepted"
        try:
            res = adapter(env, E.render_turn(env)) or {}
        except Exception as exc:  # pylint: disable=broad-except
            res = {"pushed": False, "verified": False, "detail": f"{type(exc).__name__}: {exc}"}
        pushed, verified = bool(res.get("pushed")), bool(res.get("verified"))
        state = self.store.record_push(env["id"], pushed, verified, self.clock())
        if state in ("delivered", "pushed", "failed"):
            self._receipt(env, state, str(res.get("detail", ""))[:300])
        reply = str(res.get("reply") or "").strip()
        if reply and verified and not env.get("in_reply_to"):
            state = self._model_reply(env, reply)
        return state

    def _model_reply(self, env: Dict[str, Any], reply: str) -> str:
        """A model lane answered in the same call: route its reply back as an envelope.

        Only for a first message (no in_reply_to), so two model lanes can never
        answer each other forever.
        """
        kind = "answer" if env["kind"] == "ask" else "msg"
        back = E.make(env["to"], env["from"], reply[:E.MAX_TEXT], kind=kind, in_reply_to=env["id"],
                      now=self.clock())
        self.send(back)
        if kind == "msg":
            self.store.set_state(env["id"], "acked", self.clock(), acked_by=env["to"])
            self._receipt(env, "acked", f"model replied in {back['id']}")
            return "acked"
        return "answered"

    def pump(self) -> Dict[str, int]:
        """One retry pass: expire old envelopes, re-push what is due."""
        expired = self.store.expire(self.clock())
        for env_id in expired:
            row = self.store.get(env_id)
            if row:
                self._receipt(row["env"], "expired")
        pushed = 0
        for env in self.store.due(self.adapters.keys(), self.clock()):
            self._push(env)
            pushed += 1
        return {"expired": len(expired), "retried": pushed}

    # -- receiver side -----------------------------------------------------
    def inbox(self, receiver: str, after: int = 0, limit: int = 25) -> Dict[str, Any]:
        who = Address.parse(receiver)
        items = self.store.inbox(who.lane, who.session, who.node, after, limit)
        for it in items:
            it["turn"] = E.render_turn(it["env"])
        return {"receiver": str(who), "items": items, "next_after": items[-1]["seq"] if items else int(after)}

    def ack(self, env_id: str, receiver: str) -> Dict[str, Any]:
        row = self.store.get(env_id)
        if row is None:
            return {"id": env_id, "state": "unknown"}
        who = Address.parse(receiver)
        if not Address.parse(row["env"]["to"]).matches(who.lane, who.session, who.node):
            return {"id": env_id, "state": row["state"], "error": "not addressed to this receiver"}
        if row["state"] in ("acked", "answered"):
            return {"id": env_id, "state": row["state"], "duplicate": True}
        self.store.set_state(env_id, "acked", self.clock(), acked_by=str(who))
        r = self._receipt(row["env"], "acked", f"by {who}")
        return {"id": env_id, "state": "acked", "receipt": r}

    def status(self, env_id: str) -> Dict[str, Any]:
        row = self.store.get(env_id)
        if row is None:
            return {"id": env_id, "state": "unknown", "receipts": []}
        rs = self.store.receipts(env_id)
        canon = E.canonical(row["env"])
        for r in rs:
            r["verified"] = receipts.verify(self.key, canon, r)
        return {"id": env_id, "state": row["state"], "attempts": row["attempts"],
                "acked_by": row["acked_by"], "receipts": rs}
