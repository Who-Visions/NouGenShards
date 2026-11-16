"""Recall memory guard (NOUGEN_RECALL_MEMORY_GUARD): hard cap with a fast refusal, bounded
work per retrieve, serialised matrix builds, and memory figures in the health payload."""
import contextvars
import sys
import threading
import time
from pathlib import Path

import numpy
import pytest

from nougen_shards import core

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_extra_search_is_refused_quickly():
    adm = core.SearchAdmission(max_active=2, max_waiting=0, wait_s=5.0, stall_s=60)
    adm.enter()
    adm.enter()
    start = time.monotonic()
    with pytest.raises(core.SearchBusy) as excinfo:
        adm.enter()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5
    assert excinfo.value.retry_after == 5.0
    assert adm.stats()["refused"] == 1


def test_waiter_gets_the_slot_when_one_frees():
    adm = core.SearchAdmission(max_active=1, max_waiting=1, wait_s=2.0, stall_s=60)
    adm.enter()
    event = threading.Event()
    errors = []

    def waiter():
        try:
            adm.enter()
            adm.leave()
            event.set()
        except Exception as e:
            errors.append(e)

    t = threading.Thread(target=waiter)
    t.start()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if adm.stats()["waiting"] == 1:
            break
        time.sleep(0.01)
    else:
        pytest.fail("waiter did not enter waiting state")
    adm.leave()
    t.join(timeout=1.0)
    assert event.is_set()
    assert not errors
    stats = adm.stats()
    assert stats["active"] == 0
    assert stats["waiting"] == 0
    assert stats["completed"] == 2
    assert stats["refused"] == 0


def test_waiter_times_out_and_is_refused():
    adm = core.SearchAdmission(max_active=1, max_waiting=1, wait_s=0.1, stall_s=60)
    adm.enter()
    start = time.monotonic()
    with pytest.raises(core.SearchBusy):
        adm.enter()
    elapsed = time.monotonic() - start
    assert 0.05 <= elapsed <= 1.0
    assert adm.stats()["waiting"] == 0


def test_leave_without_enter_is_harmless():
    adm = core.SearchAdmission(max_active=1, max_waiting=0, wait_s=0, stall_s=60)
    adm.leave()
    stats = adm.stats()
    assert stats["active"] == 0
    assert stats["completed"] == 0


def test_stalled_flag(monkeypatch):
    adm = core.SearchAdmission(max_active=1, max_waiting=0, wait_s=0, stall_s=1)
    adm.enter()
    real_monotonic = time.monotonic
    monkeypatch.setattr(core.time, "monotonic", lambda: real_monotonic() + 5)
    stats = adm.stats()
    assert stats["stalled"] is True
    assert stats["oldest_active_age_s"] > 1
    adm.leave()
    stats = adm.stats()
    assert stats["stalled"] is False


def test_admitted_search_is_reentrant_and_releases(monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", "1")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_INFLIGHT", "1")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_WAITING", "0")
    core.reset_search_admission()
    try:
        errors = []

        def nested():
            try:
                with core.admitted_search():
                    pass
            except Exception as e:
                errors.append(e)

        with core.admitted_search():
            assert core.search_admission().stats()["active"] == 1
            with core.admitted_search():
                assert core.search_admission().stats()["active"] == 1
            ctx = contextvars.copy_context()
            t = threading.Thread(target=ctx.run, args=(nested,))
            t.start()
            t.join(timeout=1.0)
            assert not errors
        stats = core.search_admission().stats()
        assert stats["active"] == 0
        assert stats["completed"] == 1

        # Thread without copied context should get SearchBusy
        errors.clear()

        def no_context():
            try:
                with core.admitted_search():
                    pass
            except Exception as e:
                errors.append(e)

        with core.admitted_search():
            t = threading.Thread(target=no_context)
            t.start()
            t.join(timeout=1.0)
            assert errors
            assert isinstance(errors[0], core.SearchBusy)
    finally:
        core.reset_search_admission()


@pytest.mark.parametrize("guard", ["0", "1"])
def test_tenant_context_is_unchanged_by_admission(tmp_path, monkeypatch, guard):
    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", guard)
    core.reset_search_admission()
    tokens = core.bind_active_vault(tmp_path, "tenant-a", "lane-a")
    try:
        vault_before = core.active_vault_dir()
        tenant_before = core.active_tenant_id()
        lane_before = core.active_lane()
        with core.admitted_search():
            assert core.active_vault_dir() == vault_before
            assert core.active_tenant_id() == tenant_before
            assert core.active_lane() == lane_before
        assert core.active_vault_dir() == vault_before
        assert core.active_tenant_id() == tenant_before
        assert core.active_lane() == lane_before
    finally:
        core.reset_active_vault(tokens)
        core.reset_search_admission()


def test_bound_search_limit(monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_MAX_LIMIT", "40")
    core.reset_search_admission()
    try:
        assert core.bound_search_limit(10**9) == 40
        assert core.bound_search_limit(0) == 1
        assert core.bound_search_limit(-5) == 1
        assert core.bound_search_limit("7") == 7
        assert core.bound_search_limit(None) == 3
        assert core.bound_search_limit("x") == 3
    finally:
        core.reset_search_admission()

    monkeypatch.setenv("NOUGEN_RECALL_MAX_LIMIT", "junk")
    core.reset_search_admission()
    try:
        assert core.bound_search_limit(10**9) == 250
    finally:
        core.reset_search_admission()


def test_retrieve_caps_the_work_it_asks_for(monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", "1")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_LIMIT", "40")
    core.reset_search_admission()
    try:
        token = core.FAST_LOCAL.set(True)
        try:
            recorded = {}

            def fake_keyword_retrieve(query, limit, *args, **kwargs):
                recorded["limit"] = limit
                return []

            monkeypatch.setattr(core, "_keyword_retrieve", fake_keyword_retrieve)
            core.retrieve("q", limit=10**9)
            assert recorded["limit"] == 40
        finally:
            core.FAST_LOCAL.reset(token)
    finally:
        core.reset_search_admission()


def test_retrieve_is_unbounded_with_the_guard_off(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_MEMORY_GUARD", raising=False)
    monkeypatch.setenv("NOUGEN_RECALL_MAX_LIMIT", "40")
    token = core.FAST_LOCAL.set(True)
    try:
        recorded = {}

        def fake_keyword_retrieve(query, limit, *args, **kwargs):
            recorded["limit"] = limit
            return []

        monkeypatch.setattr(core, "_keyword_retrieve", fake_keyword_retrieve)
        core.retrieve("q", limit=5000)
        assert recorded["limit"] == 5000
    finally:
        core.FAST_LOCAL.reset(token)


def test_admitted_search_is_a_no_op_with_the_guard_off(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_MEMORY_GUARD", raising=False)
    core.reset_search_admission()
    try:
        with core.admitted_search():
            assert core.search_admission().stats()["active"] == 0
    finally:
        core.reset_search_admission()


def test_recall_memory_guard_enabled(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_MEMORY_GUARD", raising=False)
    assert core.recall_memory_guard_enabled() is False
    for val in ("0", "", "off"):
        monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", val)
        assert core.recall_memory_guard_enabled() is False
    for val in ("1", " TRUE ", "on"):
        monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", val)
        assert core.recall_memory_guard_enabled() is True


def test_ro_cache_kb(monkeypatch):
    monkeypatch.delenv("NOUGEN_RECALL_MEMORY_GUARD", raising=False)
    monkeypatch.setenv("NOUGEN_RO_CACHE_KB", "8000")
    assert core.ro_cache_kb() == 64000

    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", "1")
    monkeypatch.setenv("NOUGEN_RO_CACHE_KB", "8000")
    assert core.ro_cache_kb() == 8000

    monkeypatch.setenv("NOUGEN_RO_CACHE_KB", "junk")
    assert core.ro_cache_kb() == 64000

    monkeypatch.setenv("NOUGEN_RO_CACHE_KB", "5")
    assert core.ro_cache_kb() == 64000

    monkeypatch.setenv("NOUGEN_RO_CACHE_KB", "99999999")
    assert core.ro_cache_kb() == 1000000


def test_process_rss_bytes():
    rss = core.process_rss_bytes()
    assert isinstance(rss, int)
    assert rss > 1_000_000


def test_recall_memory_stats_keys(monkeypatch):
    core.reset_search_admission()
    try:
        stats = core.recall_memory_stats()
        expected_keys = {
            "guard", "rss_bytes", "ro_pool_connections", "ro_cache_kb",
            "vector_matrix_bytes", "vector_matrices", "vector_builds_started", "search"
        }
        assert set(stats.keys()) == expected_keys
        assert isinstance(stats["rss_bytes"], int)
        assert "stalled" in stats["search"]
    finally:
        core.reset_search_admission()


def test_recall_memory_stats_vector_matrix_bytes(monkeypatch):
    core.reset_search_admission()
    try:
        fake_cache = {
            1: {"matrix": numpy.zeros((4, 8), dtype=numpy.float32)},
            2: {"matrix": None},
            3: "not a dict",
        }
        monkeypatch.setattr(core, "_VECTOR_CACHE", fake_cache)
        stats = core.recall_memory_stats()
        assert stats["vector_matrix_bytes"] == 128
        assert stats["vector_matrices"] == 3
    finally:
        core.reset_search_admission()


def _client(monkeypatch, seen):
    pytest.importorskip("fastapi")
    pytest.importorskip("gradio")
    import app as node
    from fastapi.testclient import TestClient
    from nougen_shards import core
    monkeypatch.setattr(node, "NODE_TOKEN", "tok")

    def fake_fed(query, limit=3, sweep_report=None, **kw):
        seen.append(core.FAST_LOCAL.get())
        return []
    monkeypatch.setattr(node, "federated_retrieve", fake_fed)
    return node, TestClient(node.app, raise_server_exceptions=False)


def test_guard_off_never_refuses(monkeypatch):
    seen = []
    node, c = _client(monkeypatch, seen)
    monkeypatch.delenv("NOUGEN_RECALL_MEMORY_GUARD", raising=False)
    monkeypatch.setenv("NOUGEN_RECALL_MAX_INFLIGHT", "1")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_WAITING", "0")
    core.reset_search_admission()
    gate = core.search_admission()
    gate.enter()
    try:
        r = c.post("/search", json={"query": "x", "limit": 3}, headers={"X-NGS-Token": "tok"})
        assert r.status_code == 200
        assert seen == [False]
    finally:
        gate.leave()
        core.reset_search_admission()


def test_guard_on_refuses_the_extra_search_fast(monkeypatch):
    seen = []
    node, c = _client(monkeypatch, seen)
    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", "1")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_INFLIGHT", "1")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_WAITING", "0")
    monkeypatch.setenv("NOUGEN_RECALL_WAIT_S", "3")
    core.reset_search_admission()
    gate = core.search_admission()
    gate.enter()
    try:
        start = time.monotonic()
        r = c.post("/search", json={"query": "x", "limit": 3}, headers={"X-NGS-Token": "tok"})
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
        assert r.status_code == 503
        assert r.headers.get("Retry-After") == "3"
        assert r.headers.get("X-NouGen-Busy") == "hard"
        assert r.json()["error"] == "search_busy"
        assert seen == []
    finally:
        gate.leave()
        core.reset_search_admission()


def test_guard_on_admits_and_releases(monkeypatch):
    seen = []
    node, c = _client(monkeypatch, seen)
    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", "1")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_INFLIGHT", "2")
    monkeypatch.setenv("NOUGEN_RECALL_MAX_WAITING", "0")
    core.reset_search_admission()
    try:
        for _ in range(3):
            r = c.post("/search", json={"query": "x", "limit": 3}, headers={"X-NGS-Token": "tok"})
            assert r.status_code == 200
        stats = core.search_admission().stats()
        assert stats["active"] == 0
        assert stats["completed"] == 3
    finally:
        core.reset_search_admission()


def test_health_local_reports_recall_memory(monkeypatch):
    seen = []
    node, c = _client(monkeypatch, seen)
    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", "1")
    core.reset_search_admission()
    try:
        r = c.get("/v1/health/local")
        assert r.status_code == 200
        data = r.json()
        assert "recall_memory" in data
        rm = data["recall_memory"]
        assert "rss_bytes" in rm
        assert "search" in rm
    finally:
        core.reset_search_admission()


def _vector_entry_fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_VECTOR_CACHE", {})
    monkeypatch.setattr(core, "_db_write_signature", lambda i: ("sig", i))
    monkeypatch.setattr(core, "get_db_path", lambda i: tmp_path / f"db{i}.db")
    monkeypatch.setattr(core, "_vector_cache_wait_s", lambda: 0.05)


def test_matrix_build_waits_its_turn_with_the_guard_on(monkeypatch, tmp_path):
    """A second grid DB does not start building while another build holds the gate: it
    answers keyword-only (None) inside the wait budget and leaves its own DB lock free."""
    _vector_entry_fixture(monkeypatch, tmp_path)
    monkeypatch.setenv("NOUGEN_RECALL_MEMORY_GUARD", "1")
    started = core._VECTOR_BUILDS_STARTED
    assert core._VECTOR_BUILD_GATE.acquire(timeout=1)
    try:
        t0 = time.monotonic()
        assert core._vector_cache_entry(7, conn=None) is None
        assert time.monotonic() - t0 < 1.0
    finally:
        core._VECTOR_BUILD_GATE.release()
    assert core._VECTOR_BUILDS_STARTED == started
    assert not core._vector_cache_lock(7).locked()
    assert not core._VECTOR_BUILD_GATE.locked()


def test_matrix_build_ignores_the_gate_with_the_guard_off(monkeypatch, tmp_path):
    _vector_entry_fixture(monkeypatch, tmp_path)
    monkeypatch.delenv("NOUGEN_RECALL_MEMORY_GUARD", raising=False)
    monkeypatch.setattr(core, "_load_vector_sidecar", lambda i, path, conn=None: 1 / 0)
    started = core._VECTOR_BUILDS_STARTED
    assert core._VECTOR_BUILD_GATE.acquire(timeout=1)
    try:
        with pytest.raises(ZeroDivisionError):  # it went past the gate and began the build
            core._vector_cache_entry(7, conn=None)
    finally:
        core._VECTOR_BUILD_GATE.release()
    assert core._VECTOR_BUILDS_STARTED == started + 1
    assert not core._vector_cache_lock(7).locked()
