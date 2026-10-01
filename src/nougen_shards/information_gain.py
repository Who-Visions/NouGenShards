"""Deterministic information-gain layer: ΔI(event | memory_state).

Spec
----
An event E is a set of features (tokens, entities, edge keys — whatever the
caller extracts; extraction is NOT part of the core). Only *presence* in an
event matters, not multiplicity inside it.

Memory state M keeps T = number of past events and, per feature f, e_f = the
number of past events that contained f. The probability that the next event
contains f, with additive smoothing α (default 0.5, the Krichevsky–Trofimov
estimator), is

    p(f | M) = (e_f + α) / (T + 2α)

Surprisal of seeing f, in bits:      s(f | M) = -log2 p(f | M)

Information gained by an event (total bits):

    ΔI(E | M) = Σ_{f ∈ E} s(f | M)

A feature present in every past event has p → 1 and s → 0; a feature never seen
has p = α/(T + 2α) and the largest surprisal available at that T,

    s_max(T) = log2((T + 2α) / α)

Normalised novelty in [0, 1], independent of event size:

    novelty(E | M) = ΔI(E | M) / ( |E| · s_max(T) )

An event made only of unseen features scores exactly 1.0 (including the very
first event against empty memory, T = 0). ΔI is measured against M as it stood;
``gain`` never mutates it, ``observe`` scores then absorbs.

Properties (each is tested):
  * First event on empty memory: novelty == 1.0.
  * Repeating an identical event: ΔI is strictly decreasing and tends to 0
    (after t repeats each feature costs log2((t+2α)/(t+α)) bits).
  * An event with features outside M scores higher than a repeat; partial
    overlap lands between the two.
  * Deterministic, order independent, ``gain`` is non-mutating.
  * Provenance: only kind="observation" may update memory. An "inference" or
    "recommendation" is scored but can never be absorbed as fact.

Uses: novelty scoring and dedup (``classify``), relay urgency (``urgency``) and
action gating (``gate``) are thin monotone functions of novelty. Retrieval
ranking is sorting by ``gain``; causal/provenance edge weighting is
``novelty * confidence`` with confidence supplied by the caller. Thresholds are
explicit arguments, never hidden state.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable

ALPHA = 0.5
KINDS = ("observation", "inference", "recommendation")
_WORD = re.compile(r"[a-z0-9]+")


def features(text: str) -> FrozenSet[str]:
    """Deterministic default extractor: lowercase word unigrams + bigrams."""
    words = _WORD.findall(text.lower())
    return frozenset(words) | frozenset(f"{a} {b}" for a, b in zip(words, words[1:]))


def _as_set(event: Iterable[str] | Dict[str, int]) -> FrozenSet[str]:
    return frozenset(event.keys() if isinstance(event, dict) else event)


@dataclass(frozen=True)
class Gain:
    bits: float          # ΔI(E | M), total
    novelty: float       # normalised to [0, 1]
    size: int            # |E|, distinct features
    kind: str            # provenance of the event that was scored
    peak: float = 0.0    # most surprising single feature, normalised to [0, 1]

    @property
    def signal(self) -> float:
        """Decision value for dedup, urgency and gating: max(novelty, peak).

        ``novelty`` is a per-feature average, so it dilutes: one decisive new fact in a long
        event of familiar features scores near 0 (49 common + 1 new after 60 repeats:
        7.5 bits but novelty 0.022). ``peak`` keeps that fact visible. Pass ``signal``, not
        ``novelty``, to ``classify``, ``urgency`` and ``gate``.
        """
        return max(self.novelty, self.peak)


class MemoryState:
    """Per-feature event counts. Mutated only by ``observe`` of kind='observation'."""

    def __init__(self, alpha: float = ALPHA) -> None:
        if alpha <= 0:
            raise ValueError("alpha must be > 0")
        self.alpha = alpha
        self.events = 0
        self.seen: Counter = Counter()

    def p(self, feature: str) -> float:
        return (self.seen.get(feature, 0) + self.alpha) / (self.events + 2 * self.alpha)

    def s_max(self) -> float:
        return math.log2((self.events + 2 * self.alpha) / self.alpha)

    def gain(self, event: Iterable[str] | Dict[str, int], kind: str = "observation") -> Gain:
        """Score an event against memory. Never mutates."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        ev = _as_set(event)
        if not ev:
            return Gain(0.0, 0.0, 0, kind)
        surprisals = [-math.log2(self.p(f)) for f in sorted(ev)]
        bits = sum(surprisals)
        s_max = self.s_max()
        return Gain(bits, bits / (len(ev) * s_max), len(ev), kind, peak=max(surprisals) / s_max)

    def observe(self, event: Iterable[str] | Dict[str, int], kind: str = "observation") -> Gain:
        """Score then absorb. Inferences/recommendations are refused, not absorbed."""
        if kind != "observation":
            raise ValueError(
                f"only kind='observation' may update memory (got {kind!r}); "
                "an inference must not silently become fact"
            )
        ev = _as_set(event)
        g = self.gain(ev, kind)
        self.seen.update(ev)
        self.events += 1
        return g


def classify(novelty: float, duplicate_below: float = 0.15, novel_above: float = 0.6) -> str:
    """duplicate | incremental | novel — thresholds are explicit and ordered."""
    if not duplicate_below < novel_above:
        raise ValueError("duplicate_below must be < novel_above")
    return "duplicate" if novelty < duplicate_below else ("novel" if novelty >= novel_above else "incremental")


def urgency(novelty: float, severity: float = 1.0) -> float:
    """Relay urgency in [0, 1]: severity scaled by novelty (a repeat is quiet)."""
    return max(0.0, min(1.0, novelty * severity))


def gate(novelty: float, threshold: float = 0.6, confidence: float = 1.0) -> bool:
    """Action gate: act only on state-changing information held with confidence."""
    return novelty * confidence >= threshold
