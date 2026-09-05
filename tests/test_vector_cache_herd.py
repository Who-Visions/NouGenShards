"""A recall must never queue behind a matrix build past its own deadline.

phoebus 2026-09-04: one six-way burst 32s after boot, while the warm-up held
the single grid-wide vector-cache lock, left 327 threads parked on that lock
(each holding sqlite connections), draining at ~10 threads per 6 minutes while
every recall missed the 20s federation deadline. These tests pin the guard:
per-DB locks, a bounded wait, stale-matrix or keyword-only fallback, one
warning per DB.
"""
import logging
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import nougen_shards.core as core  # noqa: E402


@pytest.fixture
def clean_cache(monkeypatch):
    monkeypatch.setattr(core, "_VECTOR_CACHE", {})
    monkeypatch.setattr(core, "_VECTOR_DB_LOCKS", {})
    monkeypatch.setattr(core, "_VECTOR_WAIT_WARNED", set())
    monkeypatch.setenv("NOUGEN_VECTOR_CACHE_WAIT_S", "0.2")
    yield


def _hold(lock, released: threading.Event):
    lock.acquire()
    try:
        released.wait(5)
    finally:
        lock.release()


def test_per_db_locks_are_distinct(clean_cache):
    a, b = core._vector_cache_lock(1), core._vector_cache_lock(2)
    assert a is not b
    assert core._vector_cache_lock(1) is a  # stable per DB
    assert core._vector_cache_lock() is core._VECTOR_CACHE_LOCK  # compat, no arg


def test_held_lock_returns_stale_matrix_not_a_queue(clean_cache, caplog):
    path = str(core.get_db_path(1))
    stale = {"sig": ("stale",), "path": path, "dim": 4, "n_embedded": 0, "max_id": 0,
             "ids": [], "ts": [], "util": [], "dom": [], "etype": [], "matrix": None,
             "legacy": []}
    core._VECTOR_CACHE[1] = stale
    released = threading.Event()
    t = threading.Thread(target=_hold, args=(core._vector_cache_lock(1), released), daemon=True)
    t.start()
    try:
        import time
        started = time.monotonic()
        with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
            got = core._vector_cache_entry(1, conn=None)
        elapsed = time.monotonic() - started
    finally:
        released.set()
        t.join(5)
    assert got is stale  # answered from what it had
    assert elapsed < 2.0  # bounded by the wait budget, not the build
    assert any("held its lock past" in r.getMessage() and "stale matrix" in r.getMessage()
               for r in caplog.records)


def test_held_lock_with_no_entry_hands_db_to_keyword_lane(clean_cache, caplog):
    released = threading.Event()
    t = threading.Thread(target=_hold, args=(core._vector_cache_lock(2), released), daemon=True)
    t.start()
    try:
        with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
            got = core._vector_cache_entry(2, conn=None)
    finally:
        released.set()
        t.join(5)
    assert got is None
    assert any("keyword-only" in r.getMessage() for r in caplog.records)


def test_wait_warning_fires_once_per_db(clean_cache, caplog):
    released = threading.Event()
    t = threading.Thread(target=_hold, args=(core._vector_cache_lock(3), released), daemon=True)
    t.start()
    try:
        with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
            core._vector_cache_entry(3, conn=None)
            core._vector_cache_entry(3, conn=None)
    finally:
        released.set()
        t.join(5)
    assert sum("held its lock past" in r.getMessage() for r in caplog.records) == 1


def test_other_db_is_not_blocked_by_a_held_lock(clean_cache):
    """The whole point of per-DB locks: DB 5's build must not wait on DB 4's."""
    released = threading.Event()
    t = threading.Thread(target=_hold, args=(core._vector_cache_lock(4), released), daemon=True)
    t.start()
    try:
        assert core._vector_cache_lock(5).acquire(timeout=0.05)
        core._vector_cache_lock(5).release()
    finally:
        released.set()
        t.join(5)


def test_wait_budget_is_env_first(monkeypatch):
    monkeypatch.setenv("NOUGEN_VECTOR_CACHE_WAIT_S", "1.5")
    assert core._vector_cache_wait_s() == 1.5
    monkeypatch.setenv("NOUGEN_VECTOR_CACHE_WAIT_S", "soon")
    assert core._vector_cache_wait_s() == 5.0
    monkeypatch.delenv("NOUGEN_VECTOR_CACHE_WAIT_S")
    assert core._vector_cache_wait_s() == 5.0
