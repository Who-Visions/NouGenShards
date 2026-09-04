"""File-descriptor headroom for a long-lived node process.

Why this exists (measured on phoebus, 2026-09-04): launchd hands every child a
SOFT open-files limit of 256 while the HARD limit is unlimited. One federated
recall opens nine grid DBs (each .db plus -wal plus -shm) on two lanes, the
history DB, and every registered vault. A single query fits; six concurrent
gateway fan-outs do not. The node's numeric descriptor count went from 14 at
rest to exactly 256 under a six-way burst, at which point every further
``open()`` failed:

  * ``Failed to log history event: unable to open database file`` - 1,698
    times in one day's log;
  * grid connections that failed to open dropped their vector-cache entry, so
    the next query rebuilt the embedding matrix from scratch - the node paid
    cold-path cost on every request (6-8s flat) while a fresh process on the
    same box answered in 0.7s warm;
  * the local lane therefore missed the 20s recall deadline on every query
    under load, and the fleet's ``shards_search`` reported ``complete:false``
    for six hours while ``/health`` stayed 200 the whole time.

The process may raise its own soft limit up to the hard limit without any
privilege, so the fix belongs in code that every node runs, not in one
machine's plist. Env-first per Rule 0.2: ``NOUGEN_NOFILE_MIN`` (default 4096).
Never raises - a node that cannot adjust its limit must still start, loudly.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MIN_NOFILE = 4096
ENV_MIN_NOFILE = "NOUGEN_NOFILE_MIN"


def _requested_minimum() -> int:
    raw = os.environ.get(ENV_MIN_NOFILE, "").strip()
    if not raw:
        return DEFAULT_MIN_NOFILE
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; using %d", ENV_MIN_NOFILE, raw, DEFAULT_MIN_NOFILE)
        return DEFAULT_MIN_NOFILE
    return max(value, 0)


def open_fd_count() -> Optional[int]:
    """Number of descriptors this process holds right now, or None if unknown.

    ``/dev/fd`` is the process's own table on macOS and Linux. The listing
    itself briefly holds one descriptor, so the count is off by at most one -
    fine for a diagnostic line, never used for a decision.
    """
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:
        return None


def ensure_fd_headroom(minimum: Optional[int] = None) -> dict:
    """Raise the soft RLIMIT_NOFILE to at least ``minimum`` when the hard limit allows.

    Returns a dict describing what happened so the caller can log it:
    ``{"supported": bool, "before": int|None, "after": int|None,
    "hard": int|None, "raised": bool, "wanted": int}``.
    """
    wanted = _requested_minimum() if minimum is None else max(int(minimum), 0)
    report = {"supported": True, "before": None, "after": None, "hard": None,
              "raised": False, "wanted": wanted}
    try:
        import resource  # pylint: disable=import-outside-toplevel
    except ImportError:  # Windows: no rlimits, and no 256 default either
        report["supported"] = False
        return report

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (ValueError, OSError) as exc:
        logger.warning("could not read RLIMIT_NOFILE: %s: %s", type(exc).__name__, exc)
        report["supported"] = False
        return report

    report["before"] = soft
    report["after"] = soft
    report["hard"] = hard
    if wanted <= 0 or soft >= wanted:
        return report

    # RLIM_INFINITY is a huge sentinel on every platform; treat it as "no cap".
    unlimited = hard == resource.RLIM_INFINITY or hard < 0
    target = wanted if unlimited else min(wanted, hard)
    if target <= soft:
        logger.warning(
            "open-files soft limit is %d and the hard limit %d prevents raising it to %d; "
            "concurrent recalls WILL hit the descriptor ceiling - raise the hard limit "
            "(launchd HardResourceLimits / ulimit -Hn)", soft, hard, wanted)
        return report

    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError) as exc:
        logger.warning("could not raise RLIMIT_NOFILE from %d to %d: %s: %s",
                       soft, target, type(exc).__name__, exc)
        return report

    report["after"] = target
    report["raised"] = True
    # WARNING, not INFO: the node runs at WARNING, and a raise means the
    # platform default would have starved recall. That is worth one line.
    logger.warning("open-files soft limit raised %d -> %d (hard %s); a launchd default of 256 "
                   "starves concurrent recall - see fd_budget.py",
                   soft, target, "unlimited" if unlimited else hard)
    return report
