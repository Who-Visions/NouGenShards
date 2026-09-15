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
