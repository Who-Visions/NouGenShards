"""Griot sharder: gather with the grid's own semantics, then distil.

GM's brief (relay `20260908T073337Z`): expand a bare Ollama snippet into a real
NouGen sharder built on *actual grid behaviour* rather than generic
summarisation. **Griot gathers; the model distils and tells.**

This module is the ORCHESTRATION POLICY only. Every tool is injected, so the
policy is testable without a node, an MCP session, or a model — and so that a
caller wiring real tools cannot be silently broken by a signature this file
guessed at. The tools live on the node and are exposed over MCP; nothing here
imports them.

The five rules below are not style. Each one is a defect this fleet paid for.

1. **Coverage before absence.** A miss is not evidence of absence until
   coverage says the ground was actually searched. On 2026-08-29 a corrupt DB
   reported a false empty and it read as "no such shard". On 2026-09-08 I
   grepped a log for "elevation", found none, and told another node to stop
   investigating — the events were real and lived in a different store. If
   coverage is incomplete, the honest answer is UNKNOWN, never NONE.

2. **Two retrievals, not one.** Semantic recall and keyword search fail
   differently. Recall ranks and can bury an exact match under near-neighbours;
   search matches literally and misses paraphrase. A duplicate or a correction
   found by neither is the one that hurts.

3. **Corrections are append-only.** Amend and retract; never overwrite. Eleven
   claims were retracted on this fleet in one night, and every retraction is
   only useful if the original is still readable beside it. Overwriting turns a
   corrected record into one that was never wrong.

4. **Chronology is the event's, not the capture's.** A shard written at 3 AM
   about something that happened on Sunday belongs on Sunday. Ordering by
   capture time silently rewrites history in whatever order someone got round
   to recording it.

5. **Gather, then distil — never the reverse.** The model summarises what the
   grid returned. It does not supply facts the grid did not, and it is never
   asked to decide whether something exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

__all__ = ["Tools", "Gathered", "gather", "UNKNOWN", "NONE", "FOUND"]

#: Three-valued, because "we looked and found nothing" and "we could not look"
#: must never render the same. See rule 1.
FOUND = "FOUND"
NONE = "NONE"
UNKNOWN = "UNKNOWN"


@dataclass
class Tools:
    """Injected grid surface. Every field is a callable the caller supplies."""

    whoami: Callable[[], dict]
    recall: Callable[[str], list]
    search: Callable[[str], list]
    coverage: Callable[[], dict]
    griot: Optional[Callable[[str], dict]] = None
    window: Optional[Callable[[str, str], list]] = None


@dataclass
class Gathered:
    """What the grid returned, and how far it could actually see."""

    query: str
    node: dict = field(default_factory=dict)
    state: str = UNKNOWN
    hits: list = field(default_factory=list)
    archive: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def distillable(self) -> bool:
        """Only a FOUND or NONE result is safe to hand a model.

        UNKNOWN means the grid could not see; asking a model to summarise that
        invites it to fill the gap with plausible text, which is the one thing
        this whole pipeline exists to prevent.
        """
        return self.state in (FOUND, NONE)


def _event_key(hit: Any) -> str:
    """Sort key: the event's own time, falling back to capture time.

    Rule 4. `event_time` when the shard carries one, else `timestamp`. A shard
    with neither sorts last rather than first, so an undated record cannot
    quietly claim to be the earliest thing that happened.
    """
    if isinstance(hit, dict):
        for key in ("event_time", "occurred_at", "timestamp"):
            value = hit.get(key)
            if value:
                return str(value)
    return "￿"


def gather(tools: Tools, query: str, since: str = "", until: str = "") -> Gathered:
    """Collect grid context for ``query``. Distillation is the caller's job.

    Never raises for a missing optional tool or a failing one — a gather that
    dies takes the answer with it. Failures are recorded in ``notes`` and
    degrade the state, so the caller sees a partial answer marked partial
    rather than a confident wrong one.
    """
    out = Gathered(query=query)

    try:
        out.node = tools.whoami() or {}
    except Exception as exc:                              # noqa: BLE001
        out.notes.append(f"whoami failed: {type(exc).__name__}")

    # Rule 1: coverage first, so a later miss can be interpreted at all.
    complete = None
    try:
        out.coverage = tools.coverage() or {}
        complete = out.coverage.get("complete")
        dropped = out.coverage.get("dropped_lanes") or []
        if dropped:
            out.notes.append(f"coverage incomplete: dropped {sorted(map(str, dropped))}")
    except Exception as exc:                              # noqa: BLE001
        out.notes.append(f"coverage failed: {type(exc).__name__}")

    # Rule 2: both retrievals, deduped by content address where available.
    seen, hits = set(), []
    for name, call in (("recall", tools.recall), ("search", tools.search)):
        try:
            for hit in call(query) or []:
                key = (hit.get("file_hash") or hit.get("id")) if isinstance(hit, dict) else hit
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
        except Exception as exc:                          # noqa: BLE001
            out.notes.append(f"{name} failed: {type(exc).__name__}")
            complete = False

    if tools.window and (since or until):
        try:
            for hit in tools.window(since, until) or []:
                key = (hit.get("file_hash") or hit.get("id")) if isinstance(hit, dict) else hit
                if key not in seen:
                    seen.add(key)
                    hits.append(hit)
        except Exception as exc:                          # noqa: BLE001
            out.notes.append(f"window failed: {type(exc).__name__}")

    # Rule 4: order by the event, not by when someone wrote it down.
    out.hits = sorted(hits, key=_event_key)

    if tools.griot:
        try:
            out.archive = tools.griot(query) or {}
        except Exception as exc:                          # noqa: BLE001
            out.notes.append(f"griot failed: {type(exc).__name__}")

    # Rule 1 again, at the only point where it changes an answer.
    if out.hits:
        out.state = FOUND
    elif complete is True:
        out.state = NONE
    else:
        out.state = UNKNOWN
        out.notes.append(
            "no hits AND coverage did not confirm completeness -- this is "
            "UNKNOWN, not NONE. Do not report absence.")
    return out
