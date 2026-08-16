"""Legacy vault federation (decision 16729): RRF mixed-lane merge and
coverage honesty for federated stores.

New file on purpose — additive to the concurrent recall-fix diff, no shared
edits with existing test modules.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import core  # noqa: E402


def _row(score, db_index, rid, title="t"):
    return {"id": rid, "title": title, "content": "c", "file_hash": f"h{rid}",
            "utility_score": 1.0, "timestamp": None, "final_score": score,
            "_db_index": db_index}


class TestRRFMixedLaneTieBreak:
    def test_int_and_str_db_index_do_not_raise(self):
        """Grid rows carry int _db_index; local-vault rows carry
        'vault_<stem>' strings. Tied final scores across those lanes made the
        tie-break compare int<str and raised TypeError, killing the whole
        federated retrieve (observed live 2026-08-16, 2 of 41 stores)."""
        grid = [_row(0.9, 3, 101), _row(0.8, 4, 102)]
        vault = [_row(0.9, "vault_visions_ai_vault", "vault_a_16", ),
                 _row(0.8, "vault_nougen_shards_2", "vault_b_16")]
        merged = core.reciprocal_rank_fusion([grid, vault], k=60)
        assert len(merged) == 4  # nothing dropped, nothing raised

    def test_merge_is_deterministic(self):
        lanes = [[_row(0.5, 1, 7)], [_row(0.5, "vault_x", "vault_x_1")]]
        a = core.reciprocal_rank_fusion([list(l) for l in lanes], k=60)
        b = core.reciprocal_rank_fusion([list(l) for l in lanes], k=60)
        assert [r["id"] for r in a] == [r["id"] for r in b]


@pytest.fixture()
def app_module():
    pytest.importorskip("gradio")
    import app
    return app


class TestFederatedCoverage:
    def _fake_store(self, tmp_path, rows=3):
        db = tmp_path / "fake_vault.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE shards (title TEXT, content TEXT)")
        conn.executemany("INSERT INTO shards VALUES (?, ?)",
                         [(f"t{i}", f"c{i}") for i in range(rows)])
        conn.commit()
        conn.close()
        return db

    def test_gate_off_returns_none(self, app_module, monkeypatch):
        monkeypatch.setenv("NOUGEN_COVERAGE_FEDERATED", "0")
        assert app_module._federated_coverage() is None

    def test_reports_stores_and_row_totals(self, app_module, monkeypatch, tmp_path):
        monkeypatch.delenv("NOUGEN_COVERAGE_FEDERATED", raising=False)
        db = self._fake_store(tmp_path, rows=5)
        from nougen_shards import keymaker
        monkeypatch.setattr(keymaker, "list_local_vaults", lambda: [
            {"id": 1, "path": str(db), "table_name": "shards",
             "title_col": "title", "content_col": "content"}])
        cov = app_module._federated_coverage()
        assert cov["stores"] == 1
        assert cov["names"] == ["fake_vault"]
        assert cov["rows_total"] == 5
        assert cov["errored"] == []

    def test_bad_store_degrades_into_errored(self, app_module, monkeypatch, tmp_path):
        monkeypatch.delenv("NOUGEN_COVERAGE_FEDERATED", raising=False)
        good = self._fake_store(tmp_path)
        from nougen_shards import keymaker
        monkeypatch.setattr(keymaker, "list_local_vaults", lambda: [
            {"id": 1, "path": str(good), "table_name": "shards",
             "title_col": "title", "content_col": "content"},
            {"id": 2, "path": str(tmp_path / "missing.db"),
             "table_name": "shards", "title_col": "title",
             "content_col": "content"},
            {"id": 3, "path": str(good), "table_name": "shards; DROP",
             "title_col": "title", "content_col": "content"}])
        cov = app_module._federated_coverage()
        assert cov["stores"] == 1
        assert set(cov["errored"]) == {"missing", "fake_vault"}

    def test_section_is_additive_in_substrate_coverage(self, app_module, monkeypatch):
        """Consumers parse tolerantly but must still find every pre-existing
        field; federated_stores may only ADD."""
        monkeypatch.setenv("NOUGEN_COVERAGE_FEDERATED", "0")
        out = app_module.substrate_coverage()
        for field in ("total_shards", "span", "months", "empty_months",
                      "grid", "vault"):
            assert field in out
        assert out.get("federated_stores") is None
