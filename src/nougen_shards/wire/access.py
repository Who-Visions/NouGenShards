"""Who is calling the wire, what they may do, and how fast.

Four kinds of caller, resolved from the X-NGS-Token header:

- **relay**: NOUGEN_WIRE_RELAY_TOKEN, held only by the connector Worker. The
  connector authenticates its own callers and derives their lane, so the node
  trusts the lane it names: send, read, ack and status for any lane.
- **shared**: the node's /msg token (NOUGEN_AGY_MSG_TOKEN), held by every
  sender. Send and status only. Its ``from`` is asserted, never proven, and the
  accepted receipt says so. It can't read or ack any inbox.
- **lane**: a per-lane token from the callers file, for an agent that pulls
  its own inbox directly. Sends only as its lane, reads and acks only its lane.
- **guest**: a tester or user. Always sends as ``tester/<name>``, sees only its
  own traffic, reaches only the lanes its entry lists, never an actuator.

Lane and guest tokens live in one JSON file (NOUGEN_WIRE_GUESTS_FILE) as
SHA-256 hashes, never in clear::

    python -m nougen_shards.wire.access mint --name tester-1 --send-to codex,ollama --days 14
    python -m nougen_shards.wire.access mint --lane codex --name codex-node-a --days 0

Each prints the token once. Every failure answers with a reason and a fix.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional, Tuple

from . import guard
from .address import Address

GUEST_LANE = "tester"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
FLEET_RATE = {"send": 600, "read": 2400}
GUEST_RATE = {"send": 30, "read": 120}


@dataclass(frozen=True)
class Caller:
    name: str
    kind: str  # relay | shared | lane | guest
    send_to: FrozenSet[str] = field(default_factory=frozenset)
    rate: Tuple[Tuple[str, int], ...] = ()
    lane: str = ""

    @property
    def fleet(self) -> bool:
        return self.kind != "guest"

    @property
    def address(self) -> str:
        if self.kind == "guest":
            return f"{GUEST_LANE}/{self.name}"
        return self.lane

    def limit(self, kind: str) -> int:
        return dict(self.rate).get(kind) or (FLEET_RATE if self.fleet else GUEST_RATE)[kind]

    def owns(self, raw: str) -> bool:
        """True when this caller may read and ack as ``raw``."""
        if self.kind == "relay":
            return True
        if self.kind == "shared":
            return False
        try:
            a = Address.parse(raw)
        except ValueError:
            return False
        if a.app:
            return False
        if self.kind == "lane":
            return a.lane == self.lane
        return a.lane == GUEST_LANE and a.session == self.name

    def may_send_as(self, raw: str) -> bool:
        return self.kind in ("relay", "shared") or self.owns(raw)

    def sees(self, env: Dict[str, Any]) -> bool:
        return self.kind in ("relay", "shared") or self.owns(str(env.get("from"))) or self.owns(str(env.get("to")))

    def may_send_to(self, to: Address) -> Tuple[bool, str]:
        if self.fleet:
            return True, ""
        if to.app or to.lane in guard.actuator_lanes():
            return False, f"guests can't message the actuator lane {to.lane!r}"
        if to.lane not in self.send_to:
            allowed = ", ".join(sorted(self.send_to)) or "none"
            return False, f"this token may message: {allowed}"
        return True, ""

    @property
    def sender_proof(self) -> str:
        return {"relay": "sender set by the connector", "shared": "sender asserted (shared token)",
                "lane": f"sender proven (lane token {self.name})", "guest": f"sender proven (guest {self.name})"}[self.kind]


RELAY = Caller("connector", "relay")
SHARED = Caller("shared", "shared")
FLEET = RELAY  # an open dev node, or a direct Hub user, has full powers


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def guests_file() -> str:
    return os.environ.get("NOUGEN_WIRE_GUESTS_FILE") or os.path.expanduser("~/.nougen/wire-guests.json")


class GuestBook:
    """The guest token table, re-read when the file changes (no restart to add a tester)."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or guests_file()
        self._mtime: Optional[float] = None
        self._by_hash: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _load(self) -> None:
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            self._by_hash, self._mtime = {}, None
            return
        if mtime == self._mtime:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                rows = json.load(f).get("guests", [])
        except (OSError, ValueError, AttributeError):
            rows = []
        self._by_hash = {r["token_sha256"]: r for r in rows if isinstance(r, dict) and r.get("token_sha256")}
        self._mtime = mtime

    def lookup(self, token: str, now: float) -> Tuple[Optional[Caller], str]:
        with self._lock:
            self._load()
            row = self._by_hash.get(_hash(token))
        if row is None or not NAME_RE.match(str(row.get("name", ""))):
            return None, "unknown token"
        if row.get("expires") and float(row["expires"]) <= now:
            return None, "token expired"
        rate = tuple((k, int(v)) for k, v in (row.get("rate") or {}).items() if k in GUEST_RATE)
        if row.get("kind") == "lane":
            return Caller(row["name"], "lane", rate=rate, lane=str(row.get("lane") or "")), ""
        return Caller(row["name"], "guest", frozenset(str(x).lower() for x in row.get("send_to") or []), rate), ""


def relay_token() -> str:
    tok = os.environ.get("NOUGEN_WIRE_RELAY_TOKEN", "").strip()
    if tok:
        return tok
    try:
        from nougen_shards.keymaker import get_secret
        return str(get_secret("NOUGEN_WIRE_RELAY_TOKEN") or "").strip()
    except Exception:  # pylint: disable=broad-except
        return ""


def _same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def authenticate(token: str, fleet_token: str, book: Optional[GuestBook], now: Optional[float] = None,
                 relay: str = "") -> Tuple[Optional[Caller], str]:
    """(caller, reason). A node with no fleet token configured is an open dev node."""
    token = str(token or "")
    if _same(token, relay):
        return RELAY, ""
    if _same(token, fleet_token):
        return SHARED, ""
    found, why = (None, "unknown token")
    if token and book is not None:
        found, why = book.lookup(token, time.time() if now is None else now)
    if found is not None:
        return found, ""
    if token:
        return None, why  # a token was presented and didn't match: never fall through to open access
    if not fleet_token:
        return RELAY, ""  # open dev node: no fleet token configured and no token presented
    return None, "missing X-NGS-Token header"


class RateLimiter:
    """Token bucket per (caller, kind), refilled over a minute."""

    def __init__(self, clock=time.time) -> None:
        self.clock = clock
        self._buckets: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, caller: Caller, kind: str) -> Tuple[bool, float]:
        cap = float(caller.limit(kind))
        key = (caller.kind + ":" + caller.name, kind)
        now = self.clock()
        with self._lock:
            level, last = self._buckets.get(key, (cap, now))
            level = min(cap, level + (now - last) * cap / 60.0)
            if level < 1.0:
                self._buckets[key] = (level, now)
                return False, round((1.0 - level) * 60.0 / cap, 1)
            self._buckets[key] = (level - 1.0, now)
            return True, 0.0


# -- CLI ---------------------------------------------------------------------
def _read(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"guests": []}


def _write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def mint(name: str, send_to=(), days: float = 14, path: Optional[str] = None, lane: str = "") -> str:
    if not NAME_RE.match(name):
        raise ValueError("name: lowercase letters, digits, - or _, up to 32")
    lanes = sorted({s.strip().lower() for s in send_to if s.strip()})
    for one in lanes + ([lane] if lane else []):
        Address.parse(one)
    path = path or guests_file()
    data = _read(path)
    kind = "lane" if lane else "guest"
    clash = [g for g in data.get("guests", []) if g.get("name") == name and g.get("kind", "guest") != kind]
    if clash:
        raise ValueError(f"name {name!r} is already a {clash[0].get('kind', 'guest')} token; revoke it first or pick another name")
    data["guests"] = [g for g in data.get("guests", []) if g.get("name") != name]  # same name and kind: rotate
    token = "ngw_" + secrets.token_urlsafe(24)
    row = {"name": name, "token_sha256": _hash(token), "send_to": lanes,
           "expires": round(time.time() + days * 86400) if days else None, "created": round(time.time())}
    if lane:
        row.update(kind="lane", lane=Address.parse(lane).lane, send_to=[])
    data["guests"].append(row)
    _write(path, data)
    return token


def revoke(name: str, path: Optional[str] = None) -> bool:
    path = path or guests_file()
    data = _read(path)
    before = len(data.get("guests", []))
    data["guests"] = [g for g in data.get("guests", []) if g.get("name") != name]
    _write(path, data)
    return len(data["guests"]) < before


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="nougen_shards.wire.access", description="Manage wire guest tokens")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mint")
    m.add_argument("--name", required=True)
    m.add_argument("--send-to", default="tester")
    m.add_argument("--lane", default="", help="mint a lane token (reads and acks that lane) instead of a guest")
    m.add_argument("--days", type=float, default=14)
    m.add_argument("--file")
    r = sub.add_parser("revoke")
    r.add_argument("--name", required=True)
    r.add_argument("--file")
    ls = sub.add_parser("list")
    ls.add_argument("--file")
    a = p.parse_args(argv)
    if a.cmd == "mint":
        tok = mint(a.name, a.send_to.split(","), a.days, a.file, lane=a.lane)
        if a.lane:
            print(f"lane token {a.name}: sends as, reads and acks {a.lane}")
        else:
            print(f"guest {a.name}: sends as {GUEST_LANE}/{a.name}, may message {a.send_to}")
        print("token (shown once, hand it over privately):")
        print(tok)
    elif a.cmd == "revoke":
        print("revoked" if revoke(a.name, a.file) else "no such guest")
    else:
        for g in _read(a.file or guests_file()).get("guests", []):
            print(g["name"], g.get("kind", "guest"), g.get("lane") or ",".join(g.get("send_to") or []),
                  "expires", g.get("expires"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
