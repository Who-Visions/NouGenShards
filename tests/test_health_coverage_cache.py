"""/v1/health/local must not recount nine shard tables per probe nor block the
event loop: coverage is TTL-cached and computed off-loop (whoart 2026-10-26
saw 19.7s health against a 25s peer grace while warm-up had the grid busy)."""
import app as node_app


import threading
import time


def _fresh_cache(monkeypatch):
    monkeypatch.setattr(node_app, "_COVERAGE_CACHE", {"at": 0.0, "value": None, "refreshing": False})


def _settle():
    t0 = time.monotonic()
    while node_app._COVERAGE_CACHE.get("refreshing") and time.monotonic() - t0 < 3:
        time.sleep(0.01)


def test_coverage_is_cached_within_ttl_and_served_stale_after(monkeypatch):
    calls = []
    monkeypatch.setattr(node_app, "_substrate_coverage", lambda: calls.append(1) or {"n": len(calls)})
    _fresh_cache(monkeypatch)
    monkeypatch.setenv("NOUGEN_HEALTH_COVERAGE_TTL_S", "10")
    assert node_app.cached_substrate_coverage(now=100.0) == {"n": 1, "stale": False}
    assert node_app.cached_substrate_coverage(now=105.0) == {"n": 1, "stale": False}
    # Past the TTL: last value at once, tagged stale, refresh in the background.
    assert node_app.cached_substrate_coverage(now=110.5) == {"n": 1, "stale": True}
    _settle()
    assert node_app.cached_substrate_coverage(now=111.0) == {"n": 2, "stale": False}
    assert len(calls) == 2


def test_slow_count_never_blocks_a_probe_once_warm(monkeypatch):
    release = threading.Event()
    calls = []

    def slow():
        calls.append(1)
        if len(calls) > 1:
            release.wait(5)
        return {"n": len(calls)}

    monkeypatch.setattr(node_app, "_substrate_coverage", slow)
    _fresh_cache(monkeypatch)
    monkeypatch.setenv("NOUGEN_HEALTH_COVERAGE_TTL_S", "1")
    node_app.cached_substrate_coverage(now=0.0)
    t0 = time.monotonic()
    out = node_app.cached_substrate_coverage(now=5.0)
    assert time.monotonic() - t0 < 0.5 and out == {"n": 1, "stale": True}
    # Only one refresh is in flight however many probes arrive.
    node_app.cached_substrate_coverage(now=6.0)
    assert len(calls) == 2
    release.set()
    _settle()


def test_cold_node_answers_with_placeholder_within_wait_budget(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(node_app, "_substrate_coverage", lambda: release.wait(5) or {"n": 1})
    _fresh_cache(monkeypatch)
    t0 = time.monotonic()
    out = node_app.cached_substrate_coverage(now=0.0, wait_s=0.2)
    assert time.monotonic() - t0 < 1.5
    assert out["pending"] is True and out["stale"] is True and out["databases_expected"] == node_app.core.MAX_DB_COUNT
    release.set()
    _settle()


def test_local_health_uses_cached_coverage(monkeypatch):
    import asyncio
    monkeypatch.setattr(node_app, "cached_substrate_coverage",
                        lambda now=None: {"databases_mounted": 9, "databases_expected": 9, "shards": 5, "span": {}})
    out = asyncio.run(node_app.local_health())
    assert out["healthy"] is True and out["shard_count"] == 5 and "warm" in out
