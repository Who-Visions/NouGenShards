"""Stadium model: tickets, rosters, call budgets, and verified call-ups across shard vaults.

Each vault is a stadium. A shard's row id is its seat number, which only means something inside
that stadium. A shard's ticket is its ``file_hash``: the MD5 of its content, computed the same way
as at capture (``core.capture``). The same ticket in two stadiums is the same record; the same seat
number in two stadiums usually is not.

A call-up brings one shard onto the stage for a play:

1. The ticket must be on the roster for this objective (refused otherwise, budget untouched).
2. The play's call budget must have room (refused otherwise).
3. Every stadium is asked for the ticket, read-only. A stadium that cannot be opened is reported
   as unavailable, never guessed around.
4. The returned content is re-hashed. It counts as verified only if it hashes to the ticket.

Nothing here writes to a vault.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

RECALL_MARKER = "=== NOUGENSHARDS RECALL PACKET"
TICKET_RE = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_CALL_BUDGET = 5
MAX_ROSTER = 64


def ticket_of(content: str) -> str:
    """The ticket for a piece of content: identical to the capture-time ``file_hash``."""
    clean = content
    if RECALL_MARKER in content:
        clean = content.split(RECALL_MARKER)[0].strip()
    return hashlib.md5(clean.encode("utf-8", errors="ignore"), usedforsecurity=False).hexdigest()


def is_ticket(value: Any) -> bool:
    return isinstance(value, str) and bool(TICKET_RE.match(value))


@dataclass(frozen=True)
class Stadium:
    name: str
    path: Path


def default_stadiums() -> list[Stadium]:
    """This node's vaults, as stadiums db1..dbN."""
    from . import core  # pylint: disable=import-outside-toplevel

    return [Stadium(f"db{i}", core.get_db_path(i)) for i in range(1, core.MAX_DB_COUNT + 1)]


def _open_ro(path: Path) -> sqlite3.Connection:
    # as_uri() percent-encodes spaces, so paths like "The Observatory" open correctly.
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)


def health(stadium: Stadium) -> dict[str, Any]:
    """Whether a stadium can answer for its seats right now."""
    if not stadium.path.exists():
        return {"stadium": stadium.name, "status": "unavailable", "reason": "vault file missing"}
    try:
        con = _open_ro(stadium.path)
        try:
            con.execute("SELECT 1 FROM shards LIMIT 1").fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return {"stadium": stadium.name, "status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    return {"stadium": stadium.name, "status": "up"}


def ticket_lookup(ticket: str, stadiums: Iterable[Stadium]) -> dict[str, Any]:
    """Every seat holding this ticket, plus the stadiums that could not answer."""
    if not is_ticket(ticket):
        raise ValueError("stadium: a ticket is a 32-character lowercase hex file_hash")
    seats: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for st in stadiums:
        h = health(st)
        if h["status"] != "up":
            unavailable.append(h)
            continue
        con = _open_ro(st.path)
        try:
            for row in con.execute("SELECT id, title FROM shards WHERE file_hash = ?", (ticket,)):
                seats.append({"stadium": st.name, "seat": row[0], "title": row[1]})
        finally:
            con.close()
    return {"ticket": ticket, "seats": seats, "unavailable": unavailable}


class BudgetExceeded(Exception):
    pass


@dataclass
class CallBudget:
    limit: int = DEFAULT_CALL_BUDGET
    used: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.limit, int) or self.limit < 1:
            raise ValueError("stadium: call budget must be a positive integer")

    def spend(self) -> None:
        if self.used >= self.limit:
            raise BudgetExceeded(f"call budget of {self.limit} used up")
        self.used += 1


@dataclass(frozen=True)
class Roster:
    tickets: frozenset = field(default_factory=frozenset)

    @classmethod
    def of(cls, tickets: Iterable[str]) -> "Roster":
        items = list(tickets)
        if len(items) > MAX_ROSTER:
            raise ValueError(f"stadium: a roster holds at most {MAX_ROSTER} tickets")
        bad = [t for t in items if not is_ticket(t)]
        if bad:
            raise ValueError(f"stadium: not a ticket: {bad[0]!r}")
        return cls(frozenset(items))

    def allows(self, ticket: str) -> bool:
        return ticket in self.tickets


def callup(ticket: str, *, roster: Roster, budget: CallBudget, stadiums: Iterable[Stadium]) -> dict[str, Any]:
    """Bring one shard on stage. Returns a result with a status and evidence; never raises for a
    refusal, so a caller can record every outcome."""
    base = {"ticket": ticket, "budget_used": budget.used, "budget_limit": budget.limit}
    if not is_ticket(ticket):
        return {**base, "status": "refused", "reason": "not a ticket"}
    if not roster.allows(ticket):
        return {**base, "status": "refused", "reason": "ticket is not on the roster"}
    try:
        budget.spend()
    except BudgetExceeded as exc:
        return {**base, "status": "over_budget", "reason": str(exc)}
    base["budget_used"] = budget.used

    stadiums = list(stadiums)
    unavailable: list[dict[str, Any]] = []
    for st in stadiums:
        h = health(st)
        if h["status"] != "up":
            unavailable.append(h)
            continue
        con = _open_ro(st.path)
        try:
            row = con.execute(
                "SELECT id, title, content FROM shards WHERE file_hash = ? LIMIT 1", (ticket,)
            ).fetchone()
        finally:
            con.close()
        if row is None:
            continue
        seat, title, content = row
        content = content or ""
        actual = ticket_of(content)
        evidence = {"stadium": st.name, "seat": seat, "title": title, "content_ticket": actual}
        if actual != ticket:
            return {**base, "status": "hash_mismatch", "evidence": evidence,
                    "reason": "stored content does not hash to its ticket"}
        return {**base, "status": "verified", "evidence": {**evidence, "content": content}}

    if unavailable:
        return {**base, "status": "unavailable", "unavailable": unavailable,
                "reason": "not found in reachable stadiums; some stadiums could not answer"}
    return {**base, "status": "not_found", "reason": "no stadium holds this ticket"}


def cli_main(args) -> int:
    """``nougen stadium health | ticket <hash> | callup <hash> [--roster ...] [--budget N]``."""
    import json  # pylint: disable=import-outside-toplevel

    stadiums = default_stadiums()
    action = getattr(args, "stadium_action", None)
    if action == "health":
        out: Any = [health(s) for s in stadiums]
    elif action == "ticket":
        out = ticket_lookup(args.ticket, stadiums)
    elif action == "callup":
        roster = Roster.of(args.roster or [args.ticket])
        out = callup(args.ticket, roster=roster, budget=CallBudget(args.budget), stadiums=stadiums)
        if out.get("status") == "verified" and not args.full:
            out["evidence"]["content"] = out["evidence"]["content"][:280]
    else:
        print("usage: nougen stadium {health,ticket,callup}")
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0
