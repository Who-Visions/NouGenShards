"""leakwatch: LeakCanary's retained-object idea, rebuilt for a long-running Python server.

LeakCanary (square/leakcanary, Apache-2.0; idea only, no code) works in three steps:
watch objects that should die, call them *retained* when they survive a grace
period plus a GC, and once enough are retained compute each one's *leak trace*
(the shortest strong-reference path from a GC root) and group traces by a
*fingerprint* so many instances of one bug read as one leak.

A Python server has no Activity.onDestroy to say "this should be dead now", so
retention is inferred from behaviour instead:

1. Sample: every interval, gc.collect() then count live GC-tracked objects by
   type (and process RSS when psutil is available).
2. Retained: a type whose live count rose in EVERY consecutive sample across the
   window, by at least a minimum total. Steady-state caches plateau and drop out;
   per-request objects that never get freed keep climbing.
3. Leak trace: for the top retained types, take recent live instances and walk
   gc.get_referrers() upward (breadth first, bounded) until a module global or a
   class attribute holds the chain - the Python analogue of a GC root. Each hop is
   labelled with the attribute / key / index that holds the next object.
4. Fingerprint: sha1 of the hop labels without indices, so the same bug groups.
5. Optional tracemalloc (NOUGEN_LEAKWATCH_TRACEMALLOC_FRAMES>0): the top source
   lines whose allocated bytes grew since the last check, for leaks made of
   str/bytes that object counting cannot see (they are not GC-tracked).

Everything is env-driven and off unless NOUGEN_LEAKWATCH is truthy. Reports go to
a JSONL log and to the last-report slot the /debug/leakwatch route serves.

Cost, measured 2026-11-08 on the blade gateway (4 GB heap, embedding model loaded):
count-only sampling is the production mode (seconds per check; run it at the default
300 s interval). tracemalloc is NOT for a heap that size: each snapshot copies every
live allocation trace, a check ran for minutes and pushed free commit under the
proc_guard threshold. Use NOUGEN_LEAKWATCH_TRACEMALLOC_FRAMES only on a small repro.
"""
from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import sys
import threading
import time
import types
from collections import Counter, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _env_num(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        logger.warning("leakwatch: %s=%r is not a number, using %s", name, raw, default)
        return default


def enabled() -> bool:
    return os.environ.get("NOUGEN_LEAKWATCH", "").strip().lower() in ("1", "true", "yes", "on")


def _type_key(o: Any) -> str:
    t = type(o)
    mod = getattr(t, "__module__", "") or ""
    return f"{mod}.{t.__qualname__}" if mod not in ("builtins", "") else t.__qualname__


def _rss_bytes() -> Optional[int]:
    try:
        import psutil  # optional
        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


class LeakWatch:
    def __init__(
        self,
        interval_s: float = 300.0,
        window: int = 4,
        min_growth: int = 200,
        top: int = 3,
        trace_depth: int = 10,
        tracemalloc_frames: int = 0,
        log_path: Optional[Path] = None,
        trace_budget_calls: int = 40,
        trace_budget_s: float = 8.0,
        trace_width: int = 24,
        trace_referrers_per_object: int = 256,
    ) -> None:
        self.trace_referrers_per_object = int(trace_referrers_per_object)
        # gc.get_referrers() scans the WHOLE heap per call. On a gateway holding an
        # embedding model that is millions of objects, so an unbounded walk hung
        # the first live run. Every trace is capped in calls, seconds and width;
        # running out yields a partial "no root within budget" trace, never a hang.
        self.trace_budget_calls = int(trace_budget_calls)
        self.trace_budget_s = float(trace_budget_s)
        self.trace_width = int(trace_width)
        self.interval_s = interval_s
        self.window = max(2, int(window))
        self.min_growth = int(min_growth)
        self.top = int(top)
        self.trace_depth = int(trace_depth)
        self.tracemalloc_frames = int(tracemalloc_frames)
        self.log_path = log_path
        self.samples: Deque[Tuple[float, Counter, Optional[int]]] = deque(maxlen=self.window)
        self.last_report: Optional[Dict[str, Any]] = None
        self._tm_prev = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        if self.tracemalloc_frames > 0:
            import tracemalloc
            if not tracemalloc.is_tracing():
                tracemalloc.start(self.tracemalloc_frames)

    @classmethod
    def from_env(cls) -> "LeakWatch":
        home = Path(os.environ.get("NOUGEN_HOME_STATE") or (Path.home() / ".nougen"))
        return cls(
            interval_s=_env_num("NOUGEN_LEAKWATCH_INTERVAL_S", 300.0),
            window=int(_env_num("NOUGEN_LEAKWATCH_WINDOW", 4)),
            min_growth=int(_env_num("NOUGEN_LEAKWATCH_MIN_GROWTH", 200)),
            top=int(_env_num("NOUGEN_LEAKWATCH_TOP", 3)),
            trace_depth=int(_env_num("NOUGEN_LEAKWATCH_TRACE_DEPTH", 10)),
            tracemalloc_frames=int(_env_num("NOUGEN_LEAKWATCH_TRACEMALLOC_FRAMES", 0)),
            log_path=Path(os.environ.get("NOUGEN_LEAKWATCH_LOG") or (home / "logs" / "leakwatch.jsonl")),
            trace_budget_calls=int(_env_num("NOUGEN_LEAKWATCH_TRACE_CALLS", 40)),
            trace_budget_s=_env_num("NOUGEN_LEAKWATCH_TRACE_SECONDS", 8.0),
            trace_width=int(_env_num("NOUGEN_LEAKWATCH_TRACE_WIDTH", 24)),
            trace_referrers_per_object=int(_env_num("NOUGEN_LEAKWATCH_TRACE_REFERRERS", 256)),
        )

    # -- 1. sample ---------------------------------------------------------
    def sample(self) -> Counter:
        gc.collect()
        objs = gc.get_objects()
        try:
            counts = Counter(_type_key(o) for o in objs)
        finally:
            del objs  # never let the sampling list become a referrer in a trace
        self.samples.append((time.time(), counts, _rss_bytes()))
        return counts

    # -- 2. retained -------------------------------------------------------
    def retained(self) -> List[Dict[str, Any]]:
        if len(self.samples) < self.window:
            return []
        series = [c for _, c, _ in self.samples]
        out = []
        for key in series[-1]:
            vals = [c.get(key, 0) for c in series]
            if all(b > a for a, b in zip(vals, vals[1:])) and vals[-1] - vals[0] >= self.min_growth:
                out.append({"type": key, "first": vals[0], "last": vals[-1], "growth": vals[-1] - vals[0]})
        out.sort(key=lambda r: r["growth"], reverse=True)
        return out

    # -- 3. leak trace -----------------------------------------------------
    def leak_trace(self, type_key: str, max_instances: int = 3) -> Optional[Dict[str, Any]]:
        targets = [o for o in gc.get_objects() if _type_key(o) == type_key][-max_instances:]
        if not targets:
            return None
        frame = sys._getframe()
        # id(module.__dict__) -> (name, the dict itself): one lookup per referrer
        # instead of scanning every module. The dict is held, and matched by
        # identity, because some extension modules build a fresh __dict__ on each
        # access; its id is freed at once and reused by unrelated dicts, which an
        # id-only map then mislabels as a module global (caught by test, _openssl.lib).
        modules = {}
        for name, m in list(sys.modules.items()):
            d = getattr(m, "__dict__", None) if m is not None else None
            if isinstance(d, dict):
                modules[id(d)] = (name, d)
        ignore = {id(targets), id(frame)}
        for target in targets:
            chain = self._walk(target, modules, ignore, frame)
            if chain:
                labels = [hop["label"] for hop in chain]
                shape = "|".join(h["kind"] + ":" + (h["name"] if h["kind"] in ("module", "attr", "key", "class") else "") for h in chain)
                return {
                    "type": type_key,
                    "trace": labels,
                    "root": labels[0],
                    "fingerprint": hashlib.sha1(shape.encode()).hexdigest()[:12],
                }
        return {"type": type_key, "trace": [], "root": None, "fingerprint": None,
                "note": f"no root within budget (depth {self.trace_depth}, {self.trace_budget_calls} calls, {self.trace_budget_s}s)"}

    def _walk(self, target: Any, modules: Dict[int, Tuple[str, dict]], ignore: set, frame) -> Optional[List[Dict[str, str]]]:
        # BFS from the leaking object up through referrers; parent map rebuilds the path.
        start = id(target)
        parent: Dict[int, Tuple[int, Dict[str, str]]] = {}
        objs = {start: target}
        frontier = [target]
        seen = {start}
        calls = 0
        deadline = time.monotonic() + self.trace_budget_s
        for _depth in range(self.trace_depth):
            nxt = []
            for child in frontier:
                if calls >= self.trace_budget_calls or time.monotonic() > deadline:
                    return None
                calls += 1
                # The budget holds inside one referrer list too (Codex P2 on #986): a
                # hub object can have thousands of referrers, each labelled with a
                # dict/list scan. Cap the referrers examined per object and re-check
                # the deadline as we go.
                for n, ref in enumerate(gc.get_referrers(child)):
                    if n >= self.trace_referrers_per_object or time.monotonic() > deadline:
                        break
                    rid = id(ref)
                    if rid in seen or rid in ignore or isinstance(ref, types.FrameType) or ref is frontier or ref is nxt:
                        continue
                    seen.add(rid)
                    hop = self._label(ref, child, modules)
                    parent[rid] = (id(child), hop)
                    objs[rid] = ref
                    if hop["kind"] in ("module", "class"):
                        return self._path(rid, start, parent)
                    nxt.append(ref)
            if not nxt:
                return None
            # Prefer containers that look like holders (dicts, lists, objects with
            # __dict__) and bound the width; a leak chain is narrow near its root.
            frontier = nxt[: self.trace_width]
        return None

    @staticmethod
    def _path(rid: int, start: int, parent) -> List[Dict[str, str]]:
        path = []
        cur = rid
        while cur != start and cur in parent:
            child, hop = parent[cur]
            path.append(hop)
            cur = child
        return path  # root first

    @staticmethod
    def _label(ref: Any, child: Any, modules: Dict[int, Tuple[str, dict]]) -> Dict[str, str]:
        if isinstance(ref, dict):
            # A module's __dict__ is how globals hold things (O(1) lookup).
            entry = modules.get(id(ref))
            if entry is not None and entry[1] is ref:
                mname = entry[0]
                key = next((k for k, v in ref.items() if v is child), "?")
                return {"kind": "module", "name": f"{mname}.{key}", "label": f"module {mname} . {key}"}
            key = next((k for k, v in ref.items() if v is child), None)
            if key is not None:
                return {"kind": "key", "name": str(key)[:60], "label": f"dict[{str(key)[:60]!r}]"}
            return {"kind": "dict", "name": "", "label": "dict (value)"}
        if isinstance(ref, type):
            return {"kind": "class", "name": ref.__qualname__, "label": f"class {ref.__module__}.{ref.__qualname__}"}
        if isinstance(ref, (list, tuple, deque)):
            try:
                idx = next(i for i, v in enumerate(ref) if v is child)
            except StopIteration:
                idx = "?"
            return {"kind": type(ref).__name__, "name": "", "label": f"{type(ref).__name__}[{idx}]"}
        if isinstance(ref, (set, frozenset)):
            return {"kind": "set", "name": "", "label": "set member"}
        d = getattr(ref, "__dict__", None)
        if isinstance(d, dict):
            attr = next((k for k, v in d.items() if v is child), None)
            if attr:
                return {"kind": "attr", "name": f"{_type_key(ref)}.{attr}", "label": f"{_type_key(ref)}.{attr}"}
        return {"kind": "obj", "name": "", "label": _type_key(ref)}

    # -- 5. tracemalloc growth -------------------------------------------------
    def _tracemalloc_growth(self, limit: int = 8) -> List[Dict[str, Any]]:
        if self.tracemalloc_frames <= 0:
            return []
        import tracemalloc
        snap = tracemalloc.take_snapshot().filter_traces((
            tracemalloc.Filter(False, tracemalloc.__file__),
            tracemalloc.Filter(False, __file__),
        ))
        prev, self._tm_prev = self._tm_prev, snap
        if prev is None:
            return []
        out = []
        for st in snap.compare_to(prev, "lineno")[:limit]:
            if st.size_diff <= 0:
                continue
            fr = st.traceback[0]
            out.append({"where": f"{fr.filename}:{fr.lineno}", "grew_kb": round(st.size_diff / 1024, 1), "count_diff": st.count_diff})
        return out

    # -- check (sample + report) -------------------------------------------
    def check(self) -> Dict[str, Any]:
        with self._lock:
            self.sample()
            ret = self.retained()
            traces = [t for t in (self.leak_trace(r["type"]) for r in ret[: self.top]) if t]
            rss = [s[2] for s in self.samples]
            report = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "samples": len(self.samples),
                "window": self.window,
                "rss_mb": [round(r / 1048576, 1) if r else None for r in rss],
                "retained": ret[:20],
                "leaks": traces,
                "tracemalloc_top_growth": self._tracemalloc_growth(),
            }
            self.last_report = report
            if self.log_path:
                try:
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.log_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(report) + "\n")
                except OSError as e:
                    logger.warning("leakwatch: could not write %s: %s", self.log_path, e)
            if traces:
                logger.warning("leakwatch: %d retained type(s); top %s +%d via %s",
                               len(ret), ret[0]["type"], ret[0]["growth"], " -> ".join(traces[0]["trace"]) or "?")
            return report

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run():
            while not self._stop.wait(self.interval_s):
                try:
                    self.check()
                except Exception:
                    logger.exception("leakwatch: check failed")

        self.sample()  # baseline immediately
        self._thread = threading.Thread(target=_run, name="nougen-leakwatch", daemon=True)
        self._thread.start()
        logger.info("leakwatch: on (interval=%ss window=%s min_growth=%s tracemalloc=%s)",
                    self.interval_s, self.window, self.min_growth, self.tracemalloc_frames)

    def stop(self) -> None:
        self._stop.set()


_instance: Optional[LeakWatch] = None


def start_from_env() -> Optional[LeakWatch]:
    """Start the process-wide watcher when NOUGEN_LEAKWATCH is on; no-op otherwise."""
    global _instance
    if not enabled():
        return None
    if _instance is None:
        _instance = LeakWatch.from_env()
        _instance.start()
    return _instance


def instance() -> Optional[LeakWatch]:
    return _instance
