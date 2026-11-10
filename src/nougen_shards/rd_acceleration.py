"""R&D acceleration instrument, modelled on METR's 2026-11-05 AI R&D assessment.

The recursive loop: model N helps build model N+1, which helps build N+2.
This module measures whether the fleet's own capability trend is speeding up,
how confident that claim is, and whether evaluation keeps pace. It observes
the loop; it never drives it.

Inputs are generation records: a release date and a benchmark score on a
log-scale metric (e.g. task time horizon in minutes).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Generation:
    name: str
    released: date
    score: float  # must be > 0; trends are fit on log(score)
    eval_lag_days: float = 0.0  # time from release to a finished safety eval


def _years(d: date, origin: date) -> float:
    return (d - origin).days / 365.25


def _slope(points: list[tuple[float, float]]) -> float:
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    den = sum((x - mx) ** 2 for x, _ in points)
    if den == 0:
        raise ValueError("generations share one date; slope undefined")
    return sum((x - mx) * (y - my) for x, y in points) / den


@dataclass
class AccelerationReport:
    ratio: float
    ci_low: float
    ci_high: float
    pattern: str  # one_time | compounding | bottlenecked | insufficient
    reaction_window_shrinking: bool
    notes: list[str] = field(default_factory=list)


def assess(gens: list[Generation], breakpoint: date, *, boots: int = 2000,
           seed: int = 0) -> AccelerationReport:
    """Compare log-score slope after `breakpoint` to the slope before it.

    ratio 1.9 means ~two years of prior-rate progress per year. The CI is a
    bootstrap over generations; like METR's, it does not cover model-selection
    or methodology uncertainty, and it says nothing about *why* (the
    no-AI-assist counterfactual is not observable here).
    """
    if any(g.score <= 0 for g in gens):
        raise ValueError("scores must be positive")
    gens = sorted(gens, key=lambda g: g.released)
    origin = gens[0].released
    pts = [(_years(g.released, origin), math.log(g.score)) for g in gens]
    before = [p for g, p in zip(gens, pts) if g.released < breakpoint]
    after = [p for g, p in zip(gens, pts) if g.released >= breakpoint]
    notes = ["CI excludes model-selection and benchmark-choice uncertainty",
             "attribution to AI assistance is not measured"]
    if len(before) < 2 or len(after) < 2:
        return AccelerationReport(float("nan"), float("nan"), float("nan"),
                                  "insufficient", False,
                                  notes + ["need >=2 generations each side"])

    def ratio(b, a):
        sb = _slope(b)
        return _slope(a) / sb if sb > 0 else float("inf")

    r = ratio(before, after)
    rng = random.Random(seed)
    samples = []
    for _ in range(boots):
        b = [rng.choice(before) for _ in before]
        a = [rng.choice(after) for _ in after]
        try:
            samples.append(ratio(b, a))
        except ValueError:
            continue
    samples.sort()
    lo = samples[int(0.025 * len(samples))] if samples else float("nan")
    hi = samples[int(0.975 * len(samples)) - 1] if samples else float("nan")

    # Pattern: compare the last three inter-generation step rates.
    rates = [(y2 - y1) / (x2 - x1) for (x1, y1), (x2, y2) in zip(pts, pts[1:])
             if x2 > x1]
    tail = rates[-3:]
    if r < 1.1 or len(tail) < 3:
        pattern = "one_time" if r >= 1.1 else "bottlenecked"
    elif tail[0] < tail[1] < tail[2]:
        pattern = "compounding"
    elif tail[2] < tail[1] < tail[0]:
        pattern = "bottlenecked"
    else:
        pattern = "one_time"

    # Reaction window: eval lag as a share of the gap to the next release.
    shares = []
    for g, nxt in zip(gens, gens[1:]):
        gap = (nxt.released - g.released).days
        if gap > 0 and g.eval_lag_days:
            shares.append(g.eval_lag_days / gap)
    shrinking = len(shares) >= 2 and shares[-1] > shares[0]
    if shares and shares[-1] >= 1:
        notes.append("latest eval finished after the next generation shipped")
    return AccelerationReport(r, lo, hi, pattern, shrinking, notes)


def load_jsonl(path) -> list[Generation]:
    """One record per line: {"name","released":"YYYY-MM-DD","score",["eval_lag_days"]}."""
    import json
    out = []
    with open(path) as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                out.append(Generation(r["name"], date.fromisoformat(r["released"][:10]),
                                      float(r["score"]), float(r.get("eval_lag_days", 0))))
    return out


def from_evaluation_ledger(path) -> list[Generation]:
    """Fleet feed: each promoted candidate in the RSI evaluation ledger is a generation.

    The ledger is sealed (it stores only the promotion bit), so the score is the
    cumulative promotion count, a proxy for capability, not a benchmark score.
    Same-day promotions collapse to that day's last count.
    """
    import sqlite3
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT candidate_hash, created_at FROM receipts "
                          "WHERE decision = 1 ORDER BY created_at").fetchall()
    finally:
        db.close()
    by_day: dict[date, Generation] = {}
    for n, (cand, ts) in enumerate(rows, 1):
        d = date.fromisoformat(ts[:10])
        by_day[d] = Generation(cand[:12], d, float(n))
    return list(by_day.values())
