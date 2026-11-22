"""Push adapters: how the hub wakes each lane, mapped onto what already works.

Each adapter takes ``(envelope, turn_text)`` and returns
``{"pushed", "verified", "detail"[, "reply"]}``:

- ``pushed``: the message reached the receiver's transport.
- ``verified``: the receiver's transport confirmed it (Antigravity's pipe ack,
  a model's reply). A Claude Code socket write is pushed, never verified.
- ``reply``: a model lane answered in the same call.

Lanes with no adapter here (claude-app, meta-app, muse, the phone) are pull
lanes: the message waits in their durable inbox until they read and ack it.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Iterable, Optional

from .address import Address

Adapter = Callable[[Dict[str, Any], str], Dict[str, Any]]

# openrouter is opt-in: it calls a hosted model on every message.
DEFAULT_PUSH_LANES = ("claude-code", "antigravity", "codex", "ollama")


def _origin(env: Dict[str, Any]) -> Dict[str, Any]:
    return {"original_sender": env["from"], "wire_id": env["id"], "wire_kind": env["kind"]}


def build(pinger: Any = None) -> Dict[str, Adapter]:
    """Every known adapter, bound to ``pinger`` (AgentPinger by default)."""
    if pinger is None:
        from ..nougenmsg import AgentPinger as pinger  # noqa: N813 - the class is the pinger

    def claude_code(env: Dict[str, Any], turn: str) -> Dict[str, Any]:
        to = Address.parse(env["to"])
        res = pinger.ping_claude(turn, origin=_origin(env), target_session=to.session) or {}
        live = len(res.get("delivered") or [])
        dropped = bool(res.get("inbox_file") or res.get("file"))
        return {"pushed": bool(live or dropped), "verified": False,
                "detail": f"claude-code sockets {live}, inbox file {'yes' if dropped else 'no'}"}

    claude_code.pins_session = True  # type: ignore[attr-defined]

    def antigravity(env: Dict[str, Any], turn: str) -> Dict[str, Any]:
        res = pinger.ping_antigravity(turn, origin=_origin(env)) or {}
        acked = bool(res.get("pipe_delivered"))
        return {"pushed": acked or bool(res.get("files")), "verified": acked,
                "detail": "antigravity pipe ack" if acked else f"antigravity inbox {len(res.get('files') or [])}"}

    def codex(env: Dict[str, Any], turn: str) -> Dict[str, Any]:
        res = pinger.ping_codex(turn, origin=_origin(env)) or {}
        piped = bool(res.get("pipe_delivered"))
        return {"pushed": piped or bool(res.get("file")), "verified": piped,
                "detail": f"codex {res.get('status', 'unknown')}"}

    def _model(lane: str, call: Callable[..., Dict[str, Any]], **kw: Any) -> Dict[str, Any]:
        res = call(**kw) or {}
        reply = str(res.get("response") or "").strip()
        ok = res.get("status") == "delivered" and bool(reply)
        return {"pushed": ok, "verified": ok, "reply": reply if ok else "",
                "detail": f"{lane} {res.get('model') or ''} {'replied' if ok else res.get('error', 'no reply')}".strip()}

    def ollama(env: Dict[str, Any], turn: str) -> Dict[str, Any]:
        to = Address.parse(env["to"])
        return _model("ollama", pinger.ping_ollama, prompt=env["text"], node=to.node or "local",
                      model=to.model or None, origin=_origin(env))

    def openrouter(env: Dict[str, Any], turn: str) -> Dict[str, Any]:
        to = Address.parse(env["to"])
        return _model("openrouter", pinger.ping_openrouter, prompt=env["text"], model=to.model or None,
                      origin=_origin(env))

    return {"claude-code": claude_code, "claude": claude_code, "antigravity": antigravity,
            "codex": codex, "ollama": ollama, "openrouter": openrouter}


def push_lanes(raw: Optional[str] = None) -> Iterable[str]:
    raw = os.environ.get("NOUGEN_WIRE_PUSH_LANES") if raw is None else raw
    lanes = raw.split(",") if raw is not None else DEFAULT_PUSH_LANES
    return [lane.strip().lower() for lane in lanes if lane.strip()]


def enabled(pinger: Any = None, lanes: Optional[Iterable[str]] = None) -> Dict[str, Adapter]:
    """The adapters this node pushes with: NOUGEN_WIRE_PUSH_LANES, else the defaults."""
    every = build(pinger)
    wanted = list(push_lanes() if lanes is None else lanes)
    if "claude-code" in wanted and "claude" not in wanted:
        wanted.append("claude")
    return {lane: every[lane] for lane in wanted if lane in every}
