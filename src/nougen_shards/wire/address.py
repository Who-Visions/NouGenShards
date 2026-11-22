"""One address scheme for every NouGen agent, whatever its provider.

    lane[/session][@node]

``lane`` names a kind of receiver (``codex``, ``claude-code``, ``muse``,
``ollama:gemma4:e2b``). ``session`` pins one running session of that lane, the
way Claude Code's cross-session messages pin one session. ``node`` pins the
machine; without it the hub resolves the lane on whichever node hosts it.

Lanes are provider kinds, not fleet members: node and session names come from
the address itself, never from a list in this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_LANE = r"[a-z][a-z0-9_-]{0,31}"
_MODEL = r"(?::[A-Za-z0-9._-]{1,64}){0,3}"
_SESSION = r"[A-Za-z0-9._-]{1,64}"
_NODE = r"[a-z0-9][a-z0-9_-]{0,31}"
_ADDR = re.compile(
    rf"^@?(?P<app>app:)?(?P<lane>{_LANE})(?P<model>{_MODEL})"
    rf"(?:/(?P<session>{_SESSION}))?(?:@(?P<node>{_NODE}))?$"
)

# Which provider family a lane belongs to. Used for receipts and the rendered
# turn header only; routing never depends on it.
LANE_PROVIDERS = {
    "claude": "anthropic", "claude-code": "anthropic", "claude-app": "anthropic",
    "codex": "openai", "openrouter": "openrouter",
    "antigravity": "google", "gemini": "google",
    "muse": "meta", "meta-app": "meta",
    "ollama": "local",
    "tester": "guest",
}


@dataclass(frozen=True)
class Address:
    lane: str
    model: str = ""
    session: Optional[str] = None
    node: Optional[str] = None
    app: bool = False  # app:<lane>, a desktop app agent behind a bridge

    @classmethod
    def parse(cls, raw: str) -> "Address":
        m = _ADDR.match(str(raw or "").strip())
        if not m:
            raise ValueError(f"not a NouGen address: {raw!r} (want lane[/session][@node])")
        return cls(m["lane"], (m["model"] or "").lstrip(":"), m["session"], m["node"], bool(m["app"]))

    @property
    def provider(self) -> str:
        return LANE_PROVIDERS.get(self.lane, "unknown")

    def __str__(self) -> str:
        out = ("app:" if self.app else "") + self.lane + (":" + self.model if self.model else "")
        if self.session:
            out += "/" + self.session
        if self.node:
            out += "@" + self.node
        return out

    def matches(self, lane: str, session: Optional[str] = None, node: Optional[str] = None,
                model: str = "", app: bool = False) -> bool:
        """True when a receiver (lane, session, node, model, app) should see a message sent here.

        Every part this address pins must be matched by the receiver: a pinned
        session, node, model or app prefix is never satisfied by a receiver that
        leaves it out, so an unqualified reader can't consume another machine's,
        session's or model's messages.
        """
        if self.lane != lane:
            return False
        if self.app and not app:
            return False
        if self.model and self.model != (model or ""):
            return False
        if self.session and self.session != session:
            return False  # a pinned message reaches that one session, never the whole lane
        if self.node and self.node != node:
            return False
        return True

    def receives_from(self, dest: "Address") -> bool:
        """True when this address, as a receiver, should see a message sent to ``dest``."""
        return dest.matches(self.lane, self.session, self.node, self.model, self.app)
