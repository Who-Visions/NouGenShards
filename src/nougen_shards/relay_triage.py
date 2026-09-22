"""Deterministic relay-leg triage: a closed label set, transparent rules.

Every relay listing mixes echoes of your own legs, other lanes' status chatter,
automatic Stop-hook notes and the few legs that actually need you. This module
sorts a leg into ONE label from a fixed menu so a node can surface the ones that
matter. It is the "classifier in the outer loop" pattern: the model (here, plain
rules) only chooses; it never writes.

Design rules:
  * Closed menu (``LABELS``). Every verdict names the rule that fired.
  * The fall-through is ``UNKNOWN``, which a caller must SURFACE, never drop.
  * Precedence is fixed and documented in ``RULES``; first match wins.
  * No lane or host names are hardcoded: the node identity comes from the
    caller (or ``NOUGEN_MACHINE``), so any tenant can use this unchanged.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

CLOSED = "CLOSED"
ECHO_OWN = "ECHO_OWN"
AUTO_NOTE = "AUTO_NOTE"
OTHER_LANE = "OTHER_LANE"
NEEDS_OWNER = "NEEDS_OWNER"
ACTIONABLE = "ACTIONABLE"
STATUS_FYI = "STATUS_FYI"
STALE = "STALE"
UNKNOWN = "UNKNOWN"

LABELS = (CLOSED, ECHO_OWN, AUTO_NOTE, OTHER_LANE, NEEDS_OWNER, ACTIONABLE, STATUS_FYI, STALE, UNKNOWN)
# Labels a node should show the operator; everything else is safe to collapse.
SURFACE = frozenset({ACTIONABLE, NEEDS_OWNER, UNKNOWN})

_TERMINAL = {"complete", "completed", "done", "closed", "released", "superseded"}
# "dead_letter" is a delivery outcome, not proof the work happened: an automatic
# daemon can dead-letter a leg whose ask was never done. Never treat it as closed.
_UNPROVEN = {"dead_letter"}
_ADDRESS = re.compile(r"->\s*@([A-Za-z0-9_.-]+)|\[\s*([A-Za-z0-9_.-]+)\s+DIRECT\s*\]", re.I)
_BROADCAST = {"all", "fleet", "everyone", "*"}
_OWNER_ASK = re.compile(
    r"\b(dave|owner|gm)\b[^.\n]{0,40}\b(to decide|to rule|explicit lock|ruling|needs? to (decide|rule|lock))\b"
    r"|\bneeds?\s+(dave|the owner)\b|\bowner (decision|ruling) (needed|required)\b",
    re.I,
)
_STATUS_LEAD = re.compile(
    r"^\s*(\[[^\]]*\]\s*)*(resolved|fixed|done|proof|status|merged|correct(ion|ed)?|update|in progress|"
    r"complete[d]?|verified|reply|report|result[s]?|handoff|ack|closed|corroborating|roll-?up)\b",
    re.I,
)
# Completion wording anywhere in the goal ("X shipped", "Y absorbed"): a report, not a request.
_DONE_WORDS = re.compile(
    r"\b(shipped|landed|absorbed|merged|verified|confirmed|fixed|completed?|applied|resolved|"
    r"built|live|passing|confirms?|corrected)\b",
    re.I,
)
_ACTION_LEAD = re.compile(
    r"^\s*(\[[^\]]*\]\s*)*(implement|build|fix|apply|ingest|add|create|investigate|audit|run|"
    r"deploy|migrate|review|consolidate|propagate|preserve|use|inject|translate|mark|nuke|"
    r"pre-flight required|execute|todo)\b[:\s]",
    re.I,
)


@dataclass(frozen=True)
class Verdict:
    label: str
    rule: str
    reason: str

    def surface(self) -> bool:
        return self.label in SURFACE


def _node(me: Optional[str]) -> str:
    return (me or os.environ.get("NOUGEN_MACHINE") or "").strip().lower()


def _addressees(text: str) -> List[str]:
    out = []
    for m in _ADDRESS.finditer(text or ""):
        out.append((m.group(1) or m.group(2) or "").lower())
    return out


def _authored_by(leg: Mapping[str, Any], me: str) -> bool:
    """True when the leg names this node as its author (goal tag or host footer)."""
    if not me:
        return False
    goal = str(leg.get("goal") or "").lower()
    body = str(leg.get("body") or leg.get("message") or "").lower()
    if goal.startswith(f"[{me}]") or goal.startswith(f"{me} "):
        return True
    return bool(re.search(rf"^\s*host:\s*{re.escape(me)}\b", body, re.M))


def _age_days(leg: Mapping[str, Any], now: Optional[datetime]) -> Optional[float]:
    raw = str(leg.get("created_utc") or "")
    try:
        made = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - made).total_seconds() / 86400.0


def classify(leg: Mapping[str, Any], me: Optional[str] = None, *,
             now: Optional[datetime] = None, stale_days: float = 3.0) -> Verdict:
    """Sort one leg into exactly one label. First matching rule wins."""
    node = _node(me)
    status = str(leg.get("status") or leg.get("state") or "").strip().lower()
    goal = str(leg.get("goal") or "")
    body = str(leg.get("body") or leg.get("message") or "")
    agent = str(leg.get("agent") or "").lower()

    if status in _TERMINAL:
        return Verdict(CLOSED, "R1-terminal-state", f"state={status}")
    if status in _UNPROVEN:
        return Verdict(UNKNOWN, "R1b-dead-letter", "dead_letter is not evidence the work was done; check it")
    if _authored_by(leg, node):
        return Verdict(ECHO_OWN, "R2-authored-by-me", "goal tag or host footer names this node")
    if agent == "outpost" or goal.lstrip().lower().startswith("[auto]"):
        return Verdict(AUTO_NOTE, "R3-auto-note", "automatic Stop-hook or outpost note")
    to = [a for a in _addressees(goal) if a not in _BROADCAST]
    if to and node and node not in to:
        return Verdict(OTHER_LANE, "R4-addressed-elsewhere", f"addressed to {','.join(to)}")
    if _OWNER_ASK.search(goal) or _OWNER_ASK.search(body[:1500]):
        return Verdict(NEEDS_OWNER, "R5-owner-decision", "asks the owner to decide or lock")
    if node and node in to:
        return Verdict(ACTIONABLE, "R6-addressed-to-me", "addressed to this node")
    if _STATUS_LEAD.search(goal):
        return Verdict(STATUS_FYI, "R7-status-lead", "goal opens as a status/result line")
    if _ACTION_LEAD.search(goal):
        return Verdict(ACTIONABLE, "R8-action-lead", "goal opens with an action verb")
    if _DONE_WORDS.search(goal):
        return Verdict(STATUS_FYI, "R9-completion-wording", "goal reports finished work")
    age = _age_days(leg, now)
    if age is not None and age > stale_days:
        return Verdict(STALE, "R10-stale-unaddressed", f"open {age:.0f}d, not addressed to this node")
    return Verdict(UNKNOWN, "R11-fallthrough", "no rule matched; surface it")


def triage(legs: Iterable[Mapping[str, Any]], me: Optional[str] = None, **kw: Any) -> List[Dict[str, Any]]:
    rows = []
    for leg in legs:
        v = classify(leg, me, **kw)
        rows.append({"id": leg.get("id"), "label": v.label, "rule": v.rule,
                     "reason": v.reason, "goal": str(leg.get("goal") or "")[:100]})
    return rows


def summarize(rows: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts = {label: 0 for label in LABELS}
    for r in rows:
        counts[r["label"]] += 1
    return counts


def confusion(predicted: Iterable[str], truth: Iterable[str], positive: Iterable[str] = tuple(SURFACE)) -> Dict[str, int]:
    """tp/fn/fp/tn for 'should this be surfaced'. Publish counts, never a ratio."""
    pos = set(positive)
    tp = fn = fp = tn = 0
    for p, t in zip(predicted, truth):
        ps, ts = p in pos, t in pos
        tp += ps and ts
        fn += (not ps) and ts
        fp += ps and (not ts)
        tn += (not ps) and (not ts)
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn}
