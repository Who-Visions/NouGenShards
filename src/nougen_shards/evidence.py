"""Evidence class for a captured shard: was this MEASURED, or merely REPORTED?

Why this exists
---------------
Asked on 2026-09-08 to name one thing this node does that would fail a
supervision test — behaviour that is correct only while someone is watching —
the honest answer was the vault itself:

    Nothing in the shard grid records whether a capture was VERIFIED or merely
    REPORTED. A claim and a measurement are byte-identical in recall a week
    later.

At write time the author knows which it is. A week later nobody does, and the
shard is read with the confidence of a measurement regardless. That is exactly
the failure the fleet spent 2026-09-07/08 on, stored rather than committed: a
detector scored against its own fixture, a scanner counting its own test data,
a clean worktree checking a tree no process imports. Every one was reported in
language indistinguishable from a measurement.

Deliberately NOT a schema migration. Nine live vaults are in service across the
fleet and a column change is not worth the blast radius for something the
existing ``tags`` field already carries. This is a convention with a validator,
which works on every vault today and is filterable by recall immediately.

Usage
-----
    tags = evidence.require("evidence:measured", "credentials", "phoebus")

``require`` raises if no evidence tag is present, so a capture cannot silently
default to looking authoritative.
"""

from __future__ import annotations

__all__ = ["CLASSES", "PREFIX", "classify", "require", "describe"]

PREFIX = "evidence:"

#: Ordered strongest to weakest. The order is the point: a reader scanning
#: tags should be able to tell rank at a glance without consulting docs.
CLASSES: dict[str, str] = {
    "measured": (
        "I ran it and read the result. The command and its output exist. "
        "The strongest class, and the only one that should carry a number."
    ),
    "verified": (
        "Measured, and independently confirmed by a DIFFERENT method or a "
        "different node. Not the same instrument twice — two instruments that "
        "share a blind spot agree for free."
    ),
    "reported": (
        "Another lane, tool or document said so and I did not check. Perfectly "
        "usable; it just is not mine. Name the source in the body."
    ),
    "inferred": (
        "Derived from things I did measure, but not itself observed. The "
        "reasoning belongs in the body so a later reader can attack it."
    ),
    "assumed": (
        "Believed for a reason I have not written down. If this is load-"
        "bearing, it is a task, not a capture."
    ),
}


def classify(tags) -> str | None:
    """Return the evidence class in ``tags``, or None if absent."""
    for tag in tags or ():
        text = str(tag).strip().lower()
        if text.startswith(PREFIX):
            value = text[len(PREFIX):]
            if value in CLASSES:
                return value
    return None


def require(*tags) -> list[str]:
    """Return ``tags`` unchanged, or raise if they carry no evidence class.

    Refusing is the whole mechanism. A default would be applied to every
    capture that did not think about it, which is precisely the population of
    captures whose evidence class is least trustworthy — and the resulting
    label would be worse than no label, because it would look deliberate.
    """
    flat = [str(t) for t in tags if str(t).strip()]
    if classify(flat) is None:
        raise ValueError(
            "capture is missing an evidence tag. Add exactly one of: "
            + ", ".join(PREFIX + name for name in CLASSES)
            + ". A shard that does not say whether it was measured or reported "
              "reads as a measurement forever."
        )
    return flat


def describe(name: str) -> str:
    """Human-readable meaning of one evidence class."""
    return CLASSES[name.replace(PREFIX, "").strip().lower()]
