"""SQLite busy timeout comes from NOUGEN_SQLITE_TIMEOUT_S, with a logged fallback."""
import logging
import sqlite3

import pytest

from nougen_shards import core, graph

ENV = "NOUGEN_SQLITE_TIMEOUT_S"


def _spy_connect(monkeypatch):
    seen = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        seen.append(kwargs.get("timeout"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    return seen


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert core.sqlite_timeout_s() == core.DEFAULT_SQLITE_TIMEOUT_S


def test_blank_is_default_without_warning(monkeypatch, caplog):
    monkeypatch.setenv(ENV, "  ")
    with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
        assert core.sqlite_timeout_s() == core.DEFAULT_SQLITE_TIMEOUT_S
    assert ENV not in caplog.text


def test_env_override(monkeypatch):
    monkeypatch.setenv(ENV, "2.5")
    assert core.sqlite_timeout_s() == 2.5


@pytest.mark.parametrize("val", ["abc", "nan", "inf", "0", "-3"])
def test_invalid_falls_back_with_warning(monkeypatch, caplog, val):
    monkeypatch.setenv(ENV, val)
    with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
        assert core.sqlite_timeout_s() == core.DEFAULT_SQLITE_TIMEOUT_S
    assert ENV in caplog.text


def test_graph_connection_uses_env_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "3.5")
    monkeypatch.setattr(graph, "get_graph_db_path", lambda: tmp_path / "graph.db")
    seen = _spy_connect(monkeypatch)
    graph.get_graph_connection().close()
    assert 3.5 in seen


def test_core_connection_uses_env_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "4.5")
    monkeypatch.setattr(core, "get_db_path", lambda index=1: tmp_path / f"s{index}.db")
    monkeypatch.setattr("nougen_shards.snapshot_mode.enabled", lambda: False)
    seen = _spy_connect(monkeypatch)
    core.get_connection(1).close()
    assert 4.5 in seen


def test_caller_default_is_used_when_env_unset(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert core.sqlite_timeout_s(default=30.0) == 30.0


def test_env_still_wins_over_caller_default(monkeypatch):
    monkeypatch.setenv(ENV, "7.5")
    assert core.sqlite_timeout_s(default=30.0) == 7.5


def test_invalid_env_falls_back_to_caller_default(monkeypatch, caplog):
    monkeypatch.setenv(ENV, "-1")
    with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
        assert core.sqlite_timeout_s(default=30.0) == 30.0
    assert ENV in caplog.text


@pytest.mark.parametrize("bad", [0, -5, float("nan"), float("inf")])
def test_invalid_caller_default_falls_back_to_module_default(monkeypatch, caplog, bad):
    monkeypatch.delenv(ENV, raising=False)
    with caplog.at_level(logging.WARNING, logger="nougen_shards.core"):
        assert core.sqlite_timeout_s(default=bad) == core.DEFAULT_SQLITE_TIMEOUT_S
    assert "sqlite_timeout_s(default=" in caplog.text


def _build_over_one_db(monkeypatch, tmp_path, env_value):
    """Run ann_index.build against a single real vault DB, recording every open."""
    from nougen_shards import ann_index

    db = tmp_path / "nougen_shards_1.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, embedding BLOB)")
    con.commit()
    con.close()

    if env_value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, env_value)
    monkeypatch.setattr(core, "MAX_DB_COUNT", 1)

    timeouts = []
    pragmas = []
    real_connect = sqlite3.connect

    class _Recorder:
        """sqlite3.Connection attributes are read-only, so delegate instead."""

        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *a, **k):
            if "busy_timeout" in str(sql):
                pragmas.append(str(sql))
            return self._conn.execute(sql, *a, **k)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def spy(*args, **kwargs):
        timeouts.append(kwargs.get("timeout"))
        return _Recorder(real_connect(*args, **kwargs))

    monkeypatch.setattr(sqlite3, "connect", spy)
    ann_index.build(vault=tmp_path)
    return timeouts, pragmas


def test_ann_build_uses_its_own_default_when_env_unset(monkeypatch, tmp_path):
    from nougen_shards import ann_index

    timeouts, pragmas = _build_over_one_db(monkeypatch, tmp_path, None)
    assert timeouts == [ann_index.BUILD_TIMEOUT_S]
    assert pragmas == [f"PRAGMA busy_timeout={int(ann_index.BUILD_TIMEOUT_S * 1000)}"]


def test_ann_build_honours_env_timeout(monkeypatch, tmp_path):
    """Control: before the fix the build always waited 30s, whatever the env said."""
    timeouts, pragmas = _build_over_one_db(monkeypatch, tmp_path, "2.5")
    assert timeouts == [2.5]
    assert pragmas == ["PRAGMA busy_timeout=2500"]
