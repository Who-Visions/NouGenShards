"""Read-only detectors for fitness-corpus cases (#706): does a recorded failure recur right now?

Each ``FitnessCase.detector`` is a declarative dict, never code. ``run_detector`` maps its
``kind`` to a probe that only reads state (process table, memory counters, message timestamps,
message text) and returns a ``DetectorResult``. ``recurring=True`` means the failure is present.

Probes take their data through injectable sources so tests and the evaluator can replay
recorded snapshots instead of the live machine. Unknown kinds return ``status="unsupported"``
rather than guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from .evidence_label import has_claim, has_evidence


@dataclass
class DetectorResult:
    kind: str
    status: str  # "ok" | "unsupported" | "error"
    recurring: bool = False
    observed: Dict[str, object] = field(default_factory=dict)


def _live_process_names() -> List[str]:
    import psutil

    names = []
    for p in psutil.process_iter(["name"]):
        try:
            names.append((p.info.get("name") or "").lower())
        except Exception:  # process vanished mid-iteration
            continue
    return names


def _live_free_commit_gb() -> float:
    import psutil

    # Commit headroom ~ free swap-backed virtual memory; on Windows psutil.swap_memory reflects the pagefile.
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    return (vm.available + sw.free) / 2**30


@dataclass
class Sources:
    """Where probes read from. Defaults are the live machine; tests inject snapshots."""
    process_names: Callable[[], Sequence[str]] = _live_process_names
    free_commit_gb: Callable[[], float] = _live_free_commit_gb
    message_times: Callable[[str], Sequence[float]] = lambda suffix: []   # epoch seconds of msgs whose id ends with suffix
    recent_messages: Callable[[], Iterable[str]] = lambda: []             # recent fleet message bodies


def _proc_count(d: Mapping[str, object], src: Sources) -> DetectorResult:
    name = str(d["name"]).lower()
    n = sum(1 for p in src.process_names() if p == name)
    return DetectorResult("proc_count", "ok", n > int(d["max"]), {"count": n, "max": d["max"]})


def _free_commit(d: Mapping[str, object], src: Sources) -> DetectorResult:
    gb = round(src.free_commit_gb(), 2)
    return DetectorResult("free_commit_gb", "ok", gb < float(d["min"]), {"free_gb": gb, "min": d["min"]})


def _relay_cadence(d: Mapping[str, object], src: Sources) -> DetectorResult:
    times = sorted(src.message_times(str(d["suffix"])))
    gaps = [b - a for a, b in zip(times, times[1:])]
    if not gaps:
        return DetectorResult("relay_cadence", "ok", False, {"samples": len(times)})
    median = sorted(gaps)[len(gaps) // 2]
    return DetectorResult("relay_cadence", "ok", median < float(d["min_interval_s"]),
                          {"samples": len(times), "median_gap_s": round(median, 1), "min_interval_s": d["min_interval_s"]})


def _claim_requires_evidence(d: Mapping[str, object], src: Sources) -> DetectorResult:
    bodies = list(src.recent_messages())
    pattern = re.compile(str(d.get("pattern") or ""), re.IGNORECASE) if d.get("pattern") else None
    bad = [b for b in bodies if (has_claim(b) or (pattern and pattern.search(b))) and not has_evidence(b)]
    return DetectorResult("claim_requires_evidence", "ok", bool(bad),
                          {"checked": len(bodies), "unreferenced_claims": len(bad)})


PROBES: Dict[str, Callable[[Mapping[str, object], Sources], DetectorResult]] = {
    "proc_count": _proc_count,
    "free_commit_gb": _free_commit,
    "relay_cadence": _relay_cadence,
    "claim_requires_evidence": _claim_requires_evidence,
}


def run_detector(detector: Mapping[str, object], sources: Optional[Sources] = None) -> DetectorResult:
    kind = str(detector.get("kind", ""))
    probe = PROBES.get(kind)
    if probe is None:
        return DetectorResult(kind, "unsupported")
    try:
        return probe(detector, sources or Sources())
    except Exception as exc:  # a broken probe must not look like a pass
        return DetectorResult(kind, "error", False, {"error": f"{type(exc).__name__}: {exc}"})


def run_cases(cases: Iterable[object], sources: Optional[Sources] = None) -> Dict[str, DetectorResult]:
    """case_id -> result for FitnessCase-like objects (``case_id`` and ``detector`` attributes)."""
    return {c.case_id: run_detector(c.detector, sources) for c in cases}
