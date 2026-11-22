"""Who is calling the wire, what they may do, and how fast.

Two kinds of caller:

- **fleet**: holds the node's X-NGS-Token. Trusted to name its own sender
  (the connector derives it from the caller's key before it gets here).
- **guest**: a tester or user handed a scoped token. A guest always sends as
  ``tester/<name>``, reads only that inbox, acks only its own messages, sees the
  status of only its own traffic, may address only the lanes its entry lists
  (never an actuator), and can never carry the owner's sign-off.

Guest tokens live in a JSON file (NOUGEN_WIRE_GUESTS_FILE) as SHA-256 hashes,
never in clear. Mint one with::

    python -m nougen_shards.wire.access mint --name harley --send-to codex,ollama --days 14

which prints the token once. Every failure answers with a reason and a fix a
tester can read.
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
    fleet: bool
    send_to: FrozenSet[str] = field(default_factory=frozenset)
    rate: Tuple[Tuple[str, int], ...] = ()

    @property
    def address(self) -> str:
        return f"{GUEST_LANE}/{self.name}"

    def limit(self, kind: str) -> int:
        return dict(self.rate).get(kind) or (FLEET_RATE if self.fleet else GUEST_RATE)[kind]

    def owns(self, raw: str) -> bool:
        """True when ``raw`` is this guest's own address (any node)."""
        try:
            a = Address.parse(raw)
        except ValueError:
            return False
        return a.lane == GUEST_LANE and a.session == self.name and not a.app

    def may_send_to(self, to: Address) -> Tuple[bool, str]:
        if self.fleet:
            return True, ""
        if to.app or to.lane in guard.actuator_lanes():
            return False, f"guests can't message the actuator lane {to.lane!r}"
        if to.lane not in self.send_to:
            allowed = ", ".join(sorted(self.send_to)) or "none"
            return False, f"this token may message: {allowed}"
        return True, ""


FLEET = Caller("fleet", True)


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
        return Caller(row["name"], False, frozenset(str(x).lower() for x in row.get("send_to") or []), rate), ""


def authenticate(token: str, fleet_token: str, book: Optional[GuestBook], now: Optional[float] = None
                 ) -> Tuple[Optional[Caller], str]:
    """(caller, reason). A node with no fleet token configured is an open dev node."""
    token = str(token or "")
    if fleet_token and token and hmac.compare_digest(token.encode(), fleet_token.encode()):
        return FLEET, ""
    guest, why = (None, "unknown token")
    if token and book is not None:
        guest, why = book.lookup(token, time.time() if now is None else now)
    if guest is not None:
        return guest, ""
    if not fleet_token:
        return FLEET, ""  # open dev node: no fleet token configured, no latch
    return None, why if token else "missing X-NGS-Token header"


class RateLimiter:
    """Token bucket per (caller, kind), refilled over a minute."""

    def __init__(self, clock=time.time) -> None:
        self.clock = clock
        self._buckets: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, caller: Caller, kind: str) -> Tuple[bool, float]:
        cap = float(caller.limit(kind))
        key = (("fleet" if caller.fleet else "guest:" + caller.name), kind)
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


def mint(name: str, send_to, days: float = 14, path: Optional[str] = None) -> str:
    if not NAME_RE.match(name):
        raise ValueError("name: lowercase letters, digits, - or _, up to 32")
    lanes = sorted({s.strip().lower() for s in send_to if s.strip()})
    for lane in lanes:
        Address.parse(lane)
    path = path or guests_file()
    data = _read(path)
    data["guests"] = [g for g in data.get("guests", []) if g.get("name") != name]
    token = "ngw_" + secrets.token_urlsafe(24)
    data["guests"].append({"name": name, "token_sha256": _hash(token), "send_to": lanes,
                           "expires": round(time.time() + days * 86400) if days else None,
                           "created": round(time.time())})
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
    m.add_argument("--days", type=float, default=14)
    m.add_argument("--file")
    r = sub.add_parser("revoke")
    r.add_argument("--name", required=True)
    r.add_argument("--file")
    ls = sub.add_parser("list")
    ls.add_argument("--file")
    a = p.parse_args(argv)
    if a.cmd == "mint":
        tok = mint(a.name, a.send_to.split(","), a.days, a.file)
        print(f"guest {a.name}: sends as {GUEST_LANE}/{a.name}, may message {a.send_to}")
        print("token (shown once, hand it over privately):")
        print(tok)
    elif a.cmd == "revoke":
        print("revoked" if revoke(a.name, a.file) else "no such guest")
    else:
        for g in _read(a.file or guests_file()).get("guests", []):
            print(g["name"], ",".join(g.get("send_to") or []), "expires", g.get("expires"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
