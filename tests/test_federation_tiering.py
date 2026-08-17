"""Tiered federation, per-store timeout, and health-aggregate caching.

Countermoves from wargames/legacy-federation.md Move 5 (fork fired 2026-08-17
after /search measured 52-74s): the sweep's wall-clock is the slowest single
store, and one unindexed 1 GB store cost 46s per query. New behavior under
test:

  - hot/cold tiering: pinned / small / FTS-indexed stores swept inline, large
    unindexed stores only behind NOUGEN_FEDERATE_TIER2
  - per-store wall-clock budget (NOUGEN_LOCAL_VAULT_TIMEOUT_S) enforced via
    SQLite's progress handler; a timed-out store is reported errored, never
    silently skipped
  - /health and coverage aggregates cached for NOUGEN_HEALTH_CACHE_S
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.connectors import local_vault  # noqa: E402


def _store(tmp_path, name, rows=5, row_bytes=0, fts=False):
    """A registered-vault-shaped sqlite file with `rows` rows."""
    db = tmp_path / f"{name}.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE shards (title TEXT, content TEXT)")
    filler = "x" * row_bytes
    conn.executemany(
        "INSERT INTO shards VALUES (?, ?)",
        [(f"note {i}", f"body mentions valerion {i} {filler}") for i in range(rows)])
    if fts:
        conn.execute("CREATE VIRTUAL TABLE shards_ngsfts USING fts5("
                     "title, content, content='shards', content_rowid='rowid')")
        conn.execute("INSERT INTO shards_ngsfts(shards_ngsfts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    return db


def _conf(db, vid=1):
    return {"id": vid, "path": str(db), "table_name": "shards",
            "title_col": "title", "content_col": "content"}


@pytest.fixture(autouse=True)
def _allow_tmp_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_LOCAL_VAULT_ROOTS", str(tmp_path))
    monkeypatch.delenv("NOUGEN_FEDERATE_TIER2", raising=False)
    monkeypatch.delenv("NOUGEN_FEDERATE_HOT", raising=False)
    monkeypatch.delenv("NOUGEN_FEDERATE_HOT_MAX_MB", raising=False)
    monkeypatch.delenv("NOUGEN_LOCAL_VAULT_TIMEOUT_S", raising=False)
    local_vault._FTS_PROBE_CACHE.clear()


class TestTierPartition:
    def test_small_store_is_hot(self, tmp_path):
        hot, cold = local_vault._partition_tiers([_conf(_store(tmp_path, "tiny"))])
        assert len(hot) == 1 and not cold

    def test_large_unindexed_store_is_cold(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOUGEN_FEDERATE_HOT_MAX_MB", "0.001")  # 1 KB ceiling
        db = _store(tmp_path, "bigscan", rows=50, row_bytes=200)
        hot, cold = local_vault._partition_tiers([_conf(db)])
        assert not hot and len(cold) == 1

    def test_pinned_store_is_hot_regardless_of_size(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOUGEN_FEDERATE_HOT_MAX_MB", "0.001")
        monkeypatch.setenv("NOUGEN_FEDERATE_HOT", "bigpinned")
        db = _store(tmp_path, "bigpinned", rows=50, row_bytes=200)
        hot, cold = local_vault._partition_tiers([_conf(db)])
        assert len(hot) == 1 and not cold

    def test_fts_indexed_store_is_hot_regardless_of_size(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOUGEN_FEDERATE_HOT_MAX_MB", "0.001")
        db = _store(tmp_path, "bigindexed", rows=50, row_bytes=200, fts=True)
        hot, cold = local_vault._partition_tiers([_conf(db)])
        assert len(hot) == 1 and not cold


class TestTier2Gate:
    def test_cold_store_deferred_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOUGEN_FETERATE_TIER2", "off")  # noise: wrong name ignored
        monkeypatch.setenv("NOUGEN_FEDERATE_HOT_MAX_MB", "0.001")
        db = _store(tmp_path, "coldstore", rows=50, row_bytes=200)
        report: dict = {}
        rows = local_vault.query_local_vaults("valerion", [_conf(db)], limit=3,
                                              sweep_report=report)
        assert rows == []
        assert report["tier2"] is False
        assert report["tier2_deferred"] == ["coldstore"]
        assert report["stores_swept"] == 0

    def test_tier2_on_sweeps_cold_store(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOUGEN_FEDERATE_TIER2", "on")
        monkeypatch.setenv("NOUGEN_FEDERATE_HOT_MAX_MB", "0.001")
        db = _store(tmp_path, "coldstore", rows=50, row_bytes=200)
        report: dict = {}
        rows = local_vault.query_local_vaults("valerion", [_conf(db)], limit=3,
                                              sweep_report=report)
        assert rows, "tier2=on must sweep the cold store"
        assert report["tier2"] is True
        assert report["tier2_deferred"] == []


class TestPerStoreTimeout:
    def test_timed_out_store_reported_errored_not_silent(self, tmp_path, monkeypatch):
        # A budget that is already exhausted when the scan starts: the progress
        # handler fires within the first few thousand VM ops and aborts.
        monkeypatch.setenv("NOUGEN_LOCAL_VAULT_TIMEOUT_S", "0.000001")
        slow = _store(tmp_path, "slowstore", rows=8000, row_bytes=80)
        report: dict = {}
        rows = local_vault.query_local_vaults("valerion", [_conf(slow)], limit=3,
                                              sweep_report=report)
        assert rows == []
        assert [e["store"] for e in report["errored"]] == ["slowstore"]
        assert "timeout" in report["errored"][0]["error"]

    def test_timeout_does_not_take_out_healthy_sibling(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOUGEN_LOCAL_VAULT_TIMEOUT_S", "0.000001")
        slow = _store(tmp_path, "slowstore", rows=8000, row_bytes=80)
        # The sibling is FTS-indexed: its lookup finishes inside even a
        # micro-budget's first opcode window.
        fast = _store(tmp_path, "faststore", rows=5, fts=True)
        report: dict = {}
        rows = local_vault.query_local_vaults(
            "valerion", [_conf(slow, 1), _conf(fast, 2)], limit=3,
            sweep_report=report)
        stems = {r["_db_index"] for r in rows}
        assert "vault_faststore" in stems
        assert [e["store"] for e in report["errored"]] == ["slowstore"]

    def test_zero_budget_disables_enforcement(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOUGEN_LOCAL_VAULT_TIMEOUT_S", "0")
        db = _store(tmp_path, "unbudgeted", rows=200)
        report: dict = {}
        rows = local_vault.query_local_vaults("valerion", [_conf(db)], limit=3,
                                              sweep_report=report)
        assert rows and report["errored"] == []


@pytest.fixture()
def app_module():
    pytest.importorskip("gradio")
    import app
    app._AGG_CACHE.clear()
    yield app
    app._AGG_CACHE.clear()


class TestHealthAggregateCache:
    def test_second_call_within_ttl_uses_cache(self, app_module, monkeypatch):
        monkeypatch.setenv("NOUGEN_HEALTH_CACHE_S", "60")
        calls = {"n": 0}

        def counting():
            calls["n"] += 1
            return {"v": calls["n"]}

        assert app_module._cached("k", counting) == {"v": 1}
        assert app_module._cached("k", counting) == {"v": 1}
        assert calls["n"] == 1

    def test_ttl_zero_disables_cache(self, app_module, monkeypatch):
        monkeypatch.setenv("NOUGEN_HEALTH_CACHE_S", "0")
        calls = {"n": 0}

        def counting():
            calls["n"] += 1
            return calls["n"]

        app_module._cached("k", counting)
        app_module._cached("k", counting)
        assert calls["n"] == 2

    def test_health_reads_coverage_through_cache(self, app_module, monkeypatch):
        monkeypatch.setenv("NOUGEN_HEALTH_CACHE_S", "60")
        calls = {"n": 0}
        real = app_module._substrate_coverage

        def counting():
            calls["n"] += 1
            return real()

        monkeypatch.setattr(app_module, "_substrate_coverage", counting)
        app_module.health()
        app_module.health()
        assert calls["n"] == 1


class TestSearchSweepHonesty:
    def test_errored_store_surfaces_in_response_trailer(self, app_module, monkeypatch):
        def fake_retrieve(query, limit=3, sweep_report=None, **kw):
            if sweep_report is not None:
                sweep_report.update({
                    "errored": [{"store": "slowstore", "error": "timeout after 2.0s"}],
                    "stores_swept": 4, "tier2": False, "tier2_deferred": ["big1"]})
            return []

        monkeypatch.setattr(app_module, "federated_retrieve", fake_retrieve)
        payload = app_module.search(app_module.SearchRequest(query="q", limit=3),
                                    _token="t")
        assert len(payload) == 1
        meta = payload[0]
        assert meta["event_type"] == "FEDERATION_STATUS"
        body = json.loads(meta["content"])
        assert body["errored"][0]["store"] == "slowstore"
        assert body["tier2_deferred"] == ["big1"]

    def test_clean_sweep_leaves_response_unchanged(self, app_module, monkeypatch):
        monkeypatch.setattr(app_module, "federated_retrieve",
                            lambda query, limit=3, sweep_report=None, **kw: [])
        payload = app_module.search(app_module.SearchRequest(query="q", limit=3),
                                    _token="t")
        assert payload == []
