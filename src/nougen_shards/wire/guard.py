"""The action guard, enforced at the hub so every route gets it.

Before v2 the only guard lived in the Phoebus app bridge, so a message that
fell back to an app's own node or its mailbox skipped it. Here the hub checks
every envelope on ingest, before any route is chosen.

This is a first filter on the text, not the safety boundary: it is a keyword
list, so a paraphrase ("pick up the car") or obfuscation passes. The boundary
is the actuator itself asking its owner. Policy is per receiving lane. An *actuator* lane (an app agent that can act in
the world: buy, book, call) refuses a message that asks for such an act unless
the send carries the owner's sign-off. Coding and model lanes are not
actuators, so "call the function" or "cancel the job" between them passes;
their verdict is still recorded on the receipt.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, Optional

from .address import Address

DEFAULT_ACTUATORS = ("muse", "meta-app")
ACTION_RE = re.compile(
    r"\b(buy|purchase|pay|order|checkout|cancel|book|reserve|call|phone|dial|"
    r"transfer|send\s+money|wire\s+money|subscribe|sign\s+up)\b",
    re.IGNORECASE,
)


def actuator_lanes() -> set:
    """The defaults plus any NOUGEN_WIRE_ACTUATOR_LANES. Additive only: an empty or
    mistyped override can never switch the guard off for muse or meta-app."""
    extra = os.environ.get("NOUGEN_WIRE_ACTUATOR_LANES") or ""
    return set(DEFAULT_ACTUATORS) | {lane.strip().lower() for lane in extra.split(",") if lane.strip()}


@dataclass(frozen=True)
class Verdict:
    ok: bool
    rule: str
    matched: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {"ok": self.ok, "rule": self.rule, "matched": self.matched}


def check(env: Dict[str, object], allow_actions: bool = False, actuators: Optional[set] = None) -> Verdict:
    to = Address.parse(str(env["to"]))
    acts = actuator_lanes() if actuators is None else actuators
    hit = ACTION_RE.search(str(env.get("text", "")))
    if to.lane not in acts and not to.app:
        return Verdict(True, "not-an-actuator", hit.group(0) if hit else "")
    if not hit:
        return Verdict(True, "clean")
    if allow_actions:
        return Verdict(True, "owner-sign-off", hit.group(0))
    return Verdict(False, "guarded: action words need the owner's sign-off", hit.group(0))
