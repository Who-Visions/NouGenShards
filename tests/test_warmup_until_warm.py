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


def test_warmup_preloads_embedding_model_before_grid_passes(monkeypatch):
    order = []
    monkeypatch.setattr(node_app, "_warm_query_embedding",
                        lambda t: order.append(("embed", t)) or {"ready": True, "model": "m", "seconds": 0.1, "error": None})
    monkeypatch.setattr(core, "retrieve", lambda *a, **k: order.append(("retrieve",)))
    monkeypatch.setattr(core, "last_scan_miss_count", lambda: 0)
    monkeypatch.setattr(core, "get_db_path", lambda i: type("P", (), {"exists": staticmethod(lambda: True)})())
    monkeypatch.setenv("NOUGEN_WARMUP_EMBED_TIMEOUT_S", "77")
    monkeypatch.delenv("NOUGEN_WARMUP", raising=False)
    monkeypatch.setattr(node_app, "_WARMUP_STATE", {"status": "pending", "passes": 0, "misses": None})
    node_app._start_recall_warmup()
    st = _wait_status()
    assert order[0] == ("embed", 77.0) and order[1] == ("retrieve",)
    assert st["embed"]["ready"] is True and st["status"] == "warm"


def test_warm_query_embedding_never_raises(monkeypatch):
    import nougen_shards.embedding_backfill as eb

    def boom(*a, **k):
        raise ConnectionError("ollama down")

    monkeypatch.setattr(eb, "embed", boom)
    out = node_app._warm_query_embedding(1.0)
    assert out["ready"] is False and "ollama down" in out["error"]


def test_warmup_loops_until_no_grid_db_is_dropped(monkeypatch):
    monkeypatch.setattr(node_app, "_warm_query_embedding", lambda t: {"ready": True})
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
    monkeypatch.setattr(node_app, "_warm_query_embedding", lambda t: {"ready": False})
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
