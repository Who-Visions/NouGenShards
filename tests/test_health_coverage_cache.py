"""/v1/health/local must not recount nine shard tables per probe nor block the
event loop: coverage is TTL-cached and computed off-loop (whoart 2026-10-26
saw 19.7s health against a 25s peer grace while warm-up had the grid busy)."""
import app as node_app


def test_coverage_is_cached_within_ttl_and_refreshed_after(monkeypatch):
    calls = []
    monkeypatch.setattr(node_app, "_substrate_coverage", lambda: calls.append(1) or {"n": len(calls)})
    monkeypatch.setattr(node_app, "_COVERAGE_CACHE", {"at": 0.0, "value": None})
    monkeypatch.setenv("NOUGEN_HEALTH_COVERAGE_TTL_S", "10")
    assert node_app.cached_substrate_coverage(now=100.0) == {"n": 1}
    assert node_app.cached_substrate_coverage(now=105.0) == {"n": 1}
    assert node_app.cached_substrate_coverage(now=110.5) == {"n": 2}
    assert len(calls) == 2


def test_coverage_ttl_zero_disables_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(node_app, "_substrate_coverage", lambda: calls.append(1) or {})
    monkeypatch.setattr(node_app, "_COVERAGE_CACHE", {"at": 0.0, "value": None})
    monkeypatch.setenv("NOUGEN_HEALTH_COVERAGE_TTL_S", "0")
    node_app.cached_substrate_coverage(now=1.0)
    node_app.cached_substrate_coverage(now=1.0)
    assert len(calls) == 2


def test_local_health_uses_cached_coverage(monkeypatch):
    import asyncio
    monkeypatch.setattr(node_app, "cached_substrate_coverage",
                        lambda now=None: {"databases_mounted": 9, "databases_expected": 9, "shards": 5, "span": {}})
    out = asyncio.run(node_app.local_health())
    assert out["healthy"] is True and out["shard_count"] == 5 and "warm" in out
