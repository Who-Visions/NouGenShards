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
import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional

from .address import Address

DEFAULT_ACTUATORS = ("muse", "meta-app")
ACTION_RE = re.compile(
    r"\b(buy|buying|bought|purchas\w*|pay|paying|paid|payments?|order\w*|check[\s-]*out\w*|"
    r"cancel\w*|book|booking|booked|reserv\w*|rsvp|call|calling|phone|dial\w*|"
    r"transfer\w*|(?:send|wire)\s+(?:\$|money|cash|funds)|venmo|zelle|cash\s*app|paypal|"
    r"subscrib\w*|sign[\s-]*up|add\s+to\s+(?:cart|bag)|donat\w*|sell\w*|renew\w*|refund\w*)\b",
    re.IGNORECASE,
)
_INVISIBLE = re.compile("[\u00ad\u034f\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "|": "i"})
_SPACED = re.compile(r"\b(?:[A-Za-z][\s.\-_*·]){2,}[A-Za-z]\b")


def _views(text: str):
    """The text as written, plus normalized views that undo the usual dodges:
    lookalike letters (NFKC), invisible characters, l33t digits, and spaced
    or dotted letters ("b.u.y", "b u y")."""
    base = _INVISIBLE.sub("", unicodedata.normalize("NFKC", text))
    yield base
    joined = _SPACED.sub(lambda m: re.sub(r"[\s.\-_*·]", "", m.group(0)), base)
    yield joined
    yield joined.translate(_LEET)


def find_action(text: str):
    for view in _views(text):
        hit = ACTION_RE.search(view)
        if hit:
            return hit
    return None


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
    hit = find_action(str(env.get("text", "")))
    if to.lane not in acts and not to.app:
        return Verdict(True, "not-an-actuator", hit.group(0) if hit else "")
    if not hit:
        return Verdict(True, "clean")
    if allow_actions:
        return Verdict(True, "owner-sign-off", hit.group(0))
    return Verdict(False, "guarded: action words need the owner's sign-off", hit.group(0))
