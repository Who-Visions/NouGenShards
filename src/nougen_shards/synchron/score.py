"""Feature scores (all 0..1), hard gates, anti-apophenia, classification."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from .model import BaseRates, Config, Event, Snapshot

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS


def clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _cosine(u, v) -> float:
    if not u or not v or len(u) != len(v):
        return 0.0
    dot = sum(x * y for x, y in zip(u, v))
    nu, nv = math.sqrt(sum(x * x for x in u)), math.sqrt(sum(y * y for y in v))
    return clamp(dot / (nu * nv)) if nu and nv else 0.0


def semantic(a: Event, b: Event) -> float:
    """Embedding cosine when both carry vectors, else concept/entity overlap."""
    if a.topic_vector and b.topic_vector:
        return _cosine(a.topic_vector, b.topic_vector)
    return _jaccard(a.terms(), b.terms())


def shared_query_fraction(a: Event, b: Event) -> float:
    qa = {t.lower() for t in a.explicit_user_intent}
    qb = {t.lower() for t in b.explicit_user_intent}
    later, earlier = (b, a) if b.observed_at_ms >= a.observed_at_ms else (a, b)
    q_later = qb if later is b else qa
    # Did the later discovery's own search already name the earlier event's concepts?
    if not q_later:
        return 0.0
    return len(q_later & earlier.terms()) / len(q_later)


def independence(a: Event, b: Event, cfg: Config) -> Tuple[float, List[str]]:
    why: List[str] = []
    if a.source_id == b.source_id:
        return 0.0, ["same source_id"]
    if b.event_id in a.query_lineage or a.event_id in b.query_lineage:
        return 0.0, ["direct query lineage"]
    shared = shared_query_fraction(a, b)
    if shared > cfg.direct_query_threshold:
        return 0.0, [f"later search named earlier concepts ({shared:.2f})"]
    separation = 0.5 + 0.25 * (a.source_type != b.source_type) + 0.25 * (a.actor != b.actor)
    why.append(f"separation={separation:.2f} shared_query={shared:.2f}")
    return clamp(separation * (1.0 - shared)), why


def temporal_decay(a: Event, b: Event, cfg: Config) -> float:
    gap_h = abs(a.observed_at_ms - b.observed_at_ms) / HOUR_MS
    return 0.5 ** (gap_h / cfg.half_life_hours)


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def _safe_d(iso: Optional[str]) -> Optional[date]:
    """A malformed date is missing evidence, not a crash (review repro 2)."""
    try:
        return _d(iso) if iso else None
    except (TypeError, ValueError):
        return None


def _md_in(md: Tuple[int, int], start: date, end: date) -> bool:
    """Month-day membership that wraps the year (Dec 28 - Jan 3; repro 3)."""
    s, e = (start.month, start.day), (end.month, end.day)
    return s <= md <= e if s <= e else (md >= s or md <= e)


def _as_of_date(snap: Snapshot) -> date:
    return datetime.fromtimestamp(snap.as_of_ms / 1000, tz=timezone.utc).date()


def window_hits(ev: Event, snap: Snapshot) -> List[str]:
    """Windows the snapshot date sits in AND that this event is about.
    An event 'is about' a window if its canonical_date shares the window's
    month-day span (anniversaries) or its concepts name the window."""
    today = _as_of_date(snap)
    hits = []
    for w in snap.windows:
        if not _d(w.start) <= today <= _d(w.end):
            continue
        about = w.name.lower() in ev.terms() or any(w.name.lower() in c.lower() for c in ev.concepts)
        cd = _safe_d(ev.canonical_date)
        if cd is not None:
            about = about or _md_in((cd.month, cd.day), _d(w.start), _d(w.end))
        if about:
            hits.append(w.name)
    return hits


def calendar(a: Event, b: Event, snap: Snapshot) -> Tuple[float, List[str]]:
    hits = sorted(set(window_hits(a, snap) + window_hits(b, snap)))
    return (1.0 if hits else 0.0), hits


def _max_link(a: Event, b: Event, rates: BaseRates) -> Tuple[float, Optional[str]]:
    """Highest P(B-concept | A-concept) over all concept pairs. The most
    common link is the one that explains the pair away -- use it."""
    best, key = None, None
    for x in sorted(a.terms()):
        for y in sorted(b.terms()):
            if x == y:
                continue
            n = rates.concept_counts.get(x)
            if not n:
                continue
            p = (rates.pair(x, y) + 1) / (n + 2)  # Laplace: never 0, never 1
            if best is None or p > best:
                best, key = p, f"{x}->{y}"
    return best, key  # None => no base-rate data for any link


def rarity(a: Event, b: Event, rates: BaseRates) -> Tuple[float, Dict]:
    p, link = _max_link(a, b, rates)
    if p is None:
        # Unknown is scored as common for RARITY (never rare by absence), but it
        # is not evidence of density either -- the receipt names the gap instead
        # of silently multiplying the score by zero (review repro 1).
        return 0.0, {"p_b_given_a": None, "link": None, "revision": rates.revision, "known": False}
    return clamp(-math.log10(p) / 6.0), {"p_b_given_a": round(p, 6), "link": link,
                                        "revision": rates.revision, "known": True}


def bridge(sem: float, cfg: Config) -> float:
    return clamp(1.0 - abs(sem - cfg.bridge_target) / cfg.bridge_width)


def usefulness(a: Event, b: Event) -> float:
    """Placeholder until the Tracker learning loop exists: an explicit user
    intent on either side means someone is actively working the topic."""
    return 1.0 if (a.explicit_user_intent or b.explicit_user_intent) else 0.3


def provenance(a: Event, b: Event) -> float:
    ok = [bool(e.provenance_hash) and e.created_at_ms <= e.observed_at_ms for e in (a, b)]
    return sum(ok) / 2.0


def features(a: Event, b: Event, snap: Snapshot, cfg: Config) -> Dict:
    sem = semantic(a, b)
    ind, ind_why = independence(a, b, cfg)
    cal, cal_hits = calendar(a, b, snap)
    rar, base = rarity(a, b, snap.base_rates)
    return {
        "semantic": sem, "independence": ind, "temporal": max(temporal_decay(a, b, cfg), cal),
        "rarity": rar, "distance": bridge(sem, cfg), "usefulness": usefulness(a, b),
        "provenance": provenance(a, b), "calendar": cal,
        "_evidence": {"independence": ind_why, "calendar": cal_hits, "base_rate": base},
    }


def penalties(a: Event, b: Event, f: Dict, snap: Snapshot, cfg: Config) -> List[Dict]:
    r = snap.base_rates
    terms = sorted(a.terms() | b.terms())
    seasonal = max((r.seasonal.get(t, 0.0) for t in terms), default=0.0) if f["calendar"] else 0.0
    backfilled = sum(e.observed_at_ms - e.created_at_ms > cfg.hindsight_days * DAY_MS for e in (a, b))
    popular = max((r.popularity.get(t, 0.0) for t in terms), default=0.0)
    return [
        {"check": "caused_by_first_query", "penalty": clamp(shared_query_fraction(a, b))},
        {"check": "common_this_time_of_year", "penalty": clamp(seasonal)},
        {"check": "densely_linked_in_corpus",
         "penalty": clamp(f["_evidence"]["base_rate"]["p_b_given_a"] or 0.0),
         "known": f["_evidence"]["base_rate"]["known"]},
        {"check": "dates_chosen_after_the_fact", "penalty": 0.5 * backfilled / 2},
        {"check": "would_appear_anyway_popular", "penalty": clamp(popular)},
    ]


def classify(score: float) -> str:
    if score >= 0.85:
        return "high_value_temporal_convergence"
    if score >= 0.70:
        return "notable_serendipity"
    if score >= 0.55:
        return "weak_convergence"
    return "ignore"


def score_pair(a: Event, b: Event, snap: Snapshot, cfg: Config) -> Dict:
    f = features(a, b, snap, cfg)
    raw = sum(f[k] * w for k, w in cfg.weights)
    rejected = None
    if f["independence"] < cfg.min_independence:
        rejected = "likely self-induced"
    elif f["provenance"] < cfg.min_provenance:
        rejected = "insufficient receipts"
    elif f["semantic"] < cfg.min_semantic:
        rejected = "noise"
    pens = penalties(a, b, f, snap, cfg)
    final = raw
    for p in pens:
        final *= 1.0 - p["penalty"]
    if rejected:
        final = 0.0
    return {"features": f, "raw": raw, "penalties": pens, "score": final,
            "rejected": rejected, "classification": "rejected" if rejected else classify(final)}
