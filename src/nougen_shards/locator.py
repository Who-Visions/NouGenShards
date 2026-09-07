"""Globally-unique shard locators: ``node:db#id``.

A shard's numeric ``id`` is a per-vault autoincrement. Every ``nougen_shards_<N>.db``
mints its own sequence, so the same integer names a different shard in each DB, and
different nodes reuse the whole range again. On blade 2026-09-07 this was measured:
30,083 of 30,322 distinct ids (99.2%) existed in two or more local DBs -- a bare id
is not merely ambiguous, it is ambiguous almost always.

That is not a cosmetic problem. It produced three separate false conclusions across
the fleet in one afternoon, each of which read "not found" from an instrument that
could never have found the row: a canary declared lost fleet-wide while it sat on
disk the whole time, and published doctrine pointers that resolve to unrelated
shards. In every case the id looked like an address and was not one.

A locator carries all three parts that make a shard addressable::

    blade:2#29825      node "blade", nougen_shards_2.db, row id 29825

`parse` also accepts the degraded forms that already exist in the wild -- a bare
int, ``2#29825``, and the legacy ``29825@db2`` seen in relay legs -- so old
references keep resolving. What it will not do is invent the missing parts: an
unqualified id parses with ``node=None, db_index=None`` and the caller is expected
to treat that as "must search and disambiguate", never as "DB 1".
"""

from __future__ import annotations

import os
import re
from typing import NamedTuple

# node:db#id, with node and db each optional. Anchored so a stray id embedded in
# prose is not silently accepted as a locator.
_LOCATOR_RE = re.compile(
    r"""^\s*
        (?:(?P<node>[A-Za-z0-9][A-Za-z0-9._-]*)\s*:\s*)?   # optional "node:"
        (?:(?:db)?(?P<db>\d+)\s*\#\s*)?                    # optional "db#" / "2#"
        (?P<id>\d+)
        \s*$""",
    re.VERBOSE,
)

# Legacy form used in relay legs and shard bodies before locators existed: 29825@db2
_LEGACY_RE = re.compile(r"^\s*(?P<id>\d+)\s*@\s*(?:db)?(?P<db>\d+)\s*$", re.IGNORECASE)


class ShardRef(NamedTuple):
    """A parsed shard reference. ``node``/``db_index`` are None when unqualified."""

    shard_id: int
    db_index: int | None = None
    node: str | None = None

    @property
    def is_qualified(self) -> bool:
        """True only when this reference names exactly one row on exactly one node."""
        return self.db_index is not None and self.node is not None

    def __str__(self) -> str:
        return format_locator(self.shard_id, self.db_index, self.node)


def current_node() -> str:
    """This node's locator name, resolved at call time.

    Order is env override -> machine label -> hostname, per the dynamic-state rule:
    the value is discovered, never baked in, so a locator minted on a renamed or
    re-imaged host still says where it came from.
    """
    for var in ("NOUGEN_NODE", "NOUGEN_MACHINE"):
        val = (os.environ.get(var) or "").strip()
        if val:
            return val
    try:
        from nougen_shards import machine

        label = (machine.host_label() or "").strip()
        if label:
            return label
    except Exception:
        pass
    try:
        import socket

        return socket.gethostname().split(".")[0] or "unknown"
    except Exception:
        return "unknown"


def format_locator(
    shard_id: int | str,
    db_index: int | str | None = None,
    node: str | None = None,
) -> str:
    """Render ``node:db#id``, degrading gracefully when parts are missing.

    ``node`` defaults to this node. A missing ``db_index`` is NOT guessed -- the
    result is a bare id, which is exactly as ambiguous as the input and should read
    that way to whoever sees it.
    """
    try:
        sid = int(shard_id)
    except (TypeError, ValueError):
        return str(shard_id)
    if db_index is None or str(db_index).strip() == "":
        return str(sid)
    try:
        db = int(db_index)
    except (TypeError, ValueError):
        return str(sid)
    node = (node or current_node()).strip() or "unknown"
    return f"{node}:{db}#{sid}"


def parse(ref: "int | str | ShardRef | None") -> ShardRef | None:
    """Parse any known shard reference form. Returns None if it is not one.

    Accepts ``blade:2#29825``, ``2#29825``, ``db2#29825``, the legacy ``29825@db2``,
    a bare ``29825``, and an int. Unqualified inputs come back with None parts rather
    than defaults, so a caller can tell "DB 1" from "nobody told me the DB".
    """
    if ref is None:
        return None
    if isinstance(ref, ShardRef):
        return ref
    if isinstance(ref, bool):  # bool is an int subclass; never a shard id
        return None
    if isinstance(ref, int):
        return ShardRef(shard_id=ref)

    text = str(ref).strip()
    if not text:
        return None

    m = _LEGACY_RE.match(text) or _LOCATOR_RE.match(text)
    if not m:
        return None
    groups = m.groupdict()
    db = groups.get("db")
    node = groups.get("node")
    return ShardRef(
        shard_id=int(groups["id"]),
        db_index=int(db) if db not in (None, "") else None,
        node=(node or None),
    )


def stamp(item: dict, node: str | None = None) -> dict:
    """Add a ``locator`` key to a retrieved shard dict, in place.

    ``core.retrieve`` tags rows with the private ``_db_index``; anything that hands a
    row to a caller should call this so the DB travels with the id instead of being
    dropped at the boundary -- the drop is what made ids look like addresses.
    """
    if not isinstance(item, dict):
        return item
    sid = item.get("id")
    if sid is None:
        return item
    db = item.get("_db_index", item.get("db_index"))
    item["locator"] = format_locator(sid, db, node)
    return item
