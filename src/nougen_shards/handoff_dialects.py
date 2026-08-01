"""Read the fleet's three handoff dialects as one corpus.

Three tools in this fleet write coordination records, and each grew its own
shape because each answers a different question:

    NouGenQ  tools/git_handoff.py  -> a CLAIM   "I am working on these files,
                                                 for this long, hands off"
    NouGenRelay                    -> a LEG     "here is where I stopped and
                                                 what the next box should know"
    NouGenShards                   -> a HANDOFF "I am transferring this; ack it
                                                 so we both know you have it"

They are not three implementations of one idea, and collapsing them into one
record type would destroy information: a claim without `scope` and `ttl_hours`
cannot answer "is anyone touching this file", and a handoff without
`acknowledged_by` cannot answer "did the transfer land". So this module does
not merge them. It normalises the fields they genuinely share — who, where,
when, what, what state — and keeps each dialect's own fields under `extra`.

What that buys: one query across the whole fleet. Before this, `handoff list`
on phoebus could not see that blade1tb held an open claim on NouGenQ, because
that claim lives in a different repo in a different shape. Two boxes could work
the same files while both registries looked quiet.

The mapping is deliberately narrow. Anything that requires guessing what a
field MEANS — rather than what it is called — is left alone.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

#: What each dialect calls the moment the record was written.
_TIME_KEYS = ("timestamp", "created_utc", "when", "created_at")

#: What each dialect calls the record's identity. NouGenQ has none in the body
#: at all — its identity is the filename — so the reader falls back to the stem.
_ID_KEYS = ("handoff_id", "id", "record_id")

#: Status vocabularies. The left column is what a dialect writes; the right is
#: the shared word. `released` and `complete` are the same event seen from two
#: sides — the claim ends, the work is done — and merging them is the whole
#: point of having one vocabulary. `acknowledged` is deliberately NOT mapped to
#: `active`: an ack means someone accepted a transfer, which is a stronger
#: claim than merely working, and flattening the two would lose the read-back.
_STATUS = {
    "open": "open",
    "active": "held",
    "claimed": "held",
    "acknowledged": "accepted",
    # Found by running this over the real corpus rather than by reading code:
    # 5 records in the synced registry say `acked`, an older spelling that no
    # current writer emits. Unmapped, they fell through as their own status and
    # would have been invisible to any query for accepted transfers.
    "acked": "accepted",
    "in_progress": "held",
    "blocked": "blocked",
    "released": "done",
    "complete": "done",
    "completed": "done",
    "stale-complete": "done",
}

#: Which fields identify each dialect. Checked in order; first match wins.
_SIGNATURES = (
    ("claim", ("ttl_hours", "scope")),          # NouGenQ git_handoff
    ("handoff", ("handoff_id",)),               # NouGenShards registry
    ("handoff", ("acknowledged_by", "tasks")),
    ("leg", ("stack",)),                        # NouGenRelay
    ("leg", ("id", "remote")),
)


def detect_dialect(data: Dict[str, Any]) -> str:
    """Which tool wrote this record: 'claim', 'leg', 'handoff' or 'unknown'.

    By field signature rather than by directory, because records travel. A
    NouGenQ claim copied into the synced registry is still a claim, and calling
    it a handoff because of where it landed would make it answer the wrong
    question.
    """
    for dialect, required in _SIGNATURES:
        if all(key in data for key in required):
            return dialect
    return "unknown"


def _first(data: Dict[str, Any], keys) -> Optional[Any]:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _machine_name(data: Dict[str, Any]) -> str:
    """The box that wrote it, from either a bare string or a stamp dict.

    NouGenShards stamps a dict so it can carry machine_id and OS; the other two
    write a bare name. Both are the same answer at different resolutions.
    """
    machine = data.get("machine")
    if isinstance(machine, dict):
        return str(machine.get("host") or machine.get("hostname") or "unknown")
    if isinstance(machine, str) and machine:
        return machine
    return "unknown"


def normalise(data: Dict[str, Any], source: Optional[Path] = None) -> Dict[str, Any]:
    """One record shape across all three dialects.

    Everything a dialect knows that the others do not is preserved under
    `extra` rather than dropped — a converged view that silently discards
    `scope` would be worse than no converged view, because it would look
    complete while answering "who is touching this file" with silence.
    """
    dialect = detect_dialect(data)
    raw_status = str(data.get("status") or "open").lower()
    shared = {"machine", "agent", "goal", "status", "branch", "sha"}
    shared.update(_TIME_KEYS)
    shared.update(_ID_KEYS)

    return {
        "dialect": dialect,
        "id": str(_first(data, _ID_KEYS) or (source.stem if source else "unknown")),
        "when": str(_first(data, _TIME_KEYS) or ""),
        "machine": _machine_name(data),
        "agent": str(data.get("agent") or "unknown-agent"),
        "goal": str(data.get("goal") or ""),
        "branch": str((data.get("git") or {}).get("branch")
                      if isinstance(data.get("git"), dict) else data.get("branch") or ""),
        "status": _STATUS.get(raw_status, raw_status),
        "raw_status": raw_status,
        # A claim names files; nothing else does. Kept first-class because it is
        # the only field that answers "may I edit this right now".
        "scope": [s for s in str(data.get("scope") or "").split(",") if s] or None,
        "held_by": data.get("acknowledged_by"),
        "source": str(source) if source else None,
        "extra": {k: v for k, v in data.items() if k not in shared},
    }


def read_corpus(roots: List[Path]) -> List[Dict[str, Any]]:
    """Every coordination record under the given roots, normalised and sorted.

    Unreadable files are skipped rather than raising: a corpus spanning three
    repos written by three tools will contain a half-written file eventually,
    and one bad record must not take the fleet view down.
    """
    out: List[Dict[str, Any]] = []
    for root in roots:
        if not root or not Path(root).exists():
            continue
        for path in sorted(Path(root).rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            out.append(normalise(data, path))
    # Newest first, by the record's own clock — not the file's mtime, which
    # describes this clone rather than the fleet.
    return sorted(out, key=lambda r: r["when"], reverse=True)


def active_claims(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Claims still held, newest first — the "may I touch this file" query.

    This is the reason the corpus exists. A claim held on NouGenQ is invisible
    to NouGenShards' registry and vice versa, so before this two boxes could
    edit the same files with both registries looking quiet.
    """
    return [r for r in records if r["dialect"] == "claim" and r["status"] == "held"]


def conflicting_scopes(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pairs of held claims from different machines over a shared path."""
    held = active_claims(records)
    clashes = []
    for i in range(len(held)):
        for j in range(i + 1, len(held)):
            a, b = held[i], held[j]
            if a["machine"] == b["machine"]:
                continue
            overlap = sorted(set(a["scope"] or []) & set(b["scope"] or []))
            if overlap:
                clashes.append({"machines": sorted((a["machine"], b["machine"])),
                                "paths": overlap, "ids": [a["id"], b["id"]]})
    return clashes
