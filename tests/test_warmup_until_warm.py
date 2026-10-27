"""Warm-up must keep passing until no grid DB is dropped, and /v1/health/local
must say whether the lane is warm so a fan-out peer can size its grace."""
import time

import app as node_app
from nougen_shards import core


def _wait_status(final=("warm", "cold", "error"), timeout=5.0):
    t0 = time.monotonic()
    while node_app._WARMUP_STATE.get("status") not in final and time.monotonic() - t0 < timeout:
        time.sleep(0.02)
    return dict(node_app._WARMUP_STATE)


def test_warmup_loops_until_no_grid_db_is_dropped(monkeypatch):
    misses = iter([5, 2, 0])
    calls = []
    monkeypatch.setattr(core, "retrieve", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(core, "last_scan_miss_count", lambda: next(misses))
    monkeypatch.setattr(core, "get_db_path", lambda i: type("P", (), {"exists": staticmethod(lambda: True)})())
    monkeypatch.setenv("NOUGEN_WARMUP_PAUSE_S", "0")
    monkeypatch.delenv("NOUGEN_WARMUP", raising=False)
    monkeypatch.setattr(node_app, "_WARMUP_STATE", {"status": "pending", "passes": 0, "misses": None})
    node_app._start_recall_warmup()
    st = _wait_status()
    assert st["status"] == "warm" and st["passes"] == 3 and len(calls) == 3
    assert node_app.warmup_status()["warm"] is True


def test_warmup_gives_up_after_pass_budget_and_reports_cold(monkeypatch):
    monkeypatch.setattr(core, "retrieve", lambda *a, **k: None)
    monkeypatch.setattr(core, "last_scan_miss_count", lambda: 3)
    monkeypatch.setattr(core, "get_db_path", lambda i: type("P", (), {"exists": staticmethod(lambda: True)})())
    monkeypatch.setenv("NOUGEN_WARMUP_PAUSE_S", "0")
    monkeypatch.setenv("NOUGEN_WARMUP_MAX_PASSES", "2")
    monkeypatch.delenv("NOUGEN_WARMUP", raising=False)
    monkeypatch.setattr(node_app, "_WARMUP_STATE", {"status": "pending", "passes": 0, "misses": None})
    node_app._start_recall_warmup()
    st = _wait_status()
    assert st["status"] == "cold" and st["passes"] == 2 and st["misses"] == 3
    assert node_app.warmup_status()["warm"] is False


def test_warmup_disabled_counts_as_warm(monkeypatch):
    monkeypatch.setenv("NOUGEN_WARMUP", "0")
    monkeypatch.setattr(node_app, "_WARMUP_STATE", {"status": "pending", "passes": 0, "misses": None})
    assert node_app.warmup_status()["warm"] is True
