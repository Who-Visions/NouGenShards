"""Proactive surfacing: a subscription returns only NEW matching shards, once."""
import sqlite3
import sys

import pytest

from nougen_shards import cli, core
from nougen_shards import shard_subscriptions as ss


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)  # vault path binds at import
    return tmp_path


def _cap(title, tags=None):
    assert core.capture("KNOWLEDGE", title, f"body of {title}", tags=tags)


def test_only_shards_after_subscribe_surface(vault):
    state = vault / "subs.json"
    _cap("old kotlin note", tags=["kotlin"])
    ss.subscribe("k", tags=["#Kotlin"], path=state)
    _cap("new kotlin note", tags=["kotlin"])
    _cap("unrelated", tags=["cooking"])
    hits = ss.surface("k", path=state)["k"]
    assert [h["title"] for h in hits] == ["new kotlin note"]
    assert "@db" in hits[0]["ref"]


def test_surface_consumes_and_peek_does_not(vault):
    state = vault / "subs.json"
    ss.subscribe("rag", keywords=["second brain"], path=state)
    _cap("Building a Second Brain talk")
    assert len(ss.surface("rag", advance=False, path=state)["rag"]) == 1
    assert len(ss.surface("rag", path=state)["rag"]) == 1
    assert ss.surface("rag", path=state)["rag"] == []


def test_keyword_matches_tags_not_encrypted_content(vault):
    state = vault / "subs.json"
    ss.subscribe("x", keywords=["morph"], path=state)
    _cap("plain title", tags=["nougenmorph"])
    _cap("other title")  # 'morph' only in content: must not match
    assert [h["title"] for h in ss.surface("x", path=state)["x"]] == ["plain title"]


def test_comma_separated_tags_fallback(vault):
    state = vault / "subs.json"
    ss.subscribe("f", tags=["suppressed"], path=state)
    res = core.capture("KNOWLEDGE", "retracted note", "body", tags=["initial"])
    db = core.get_db_path(res["db_index"])
    with sqlite3.connect(db) as con:
        con.execute("UPDATE shards SET tags = 'forgotten,suppressed' WHERE id = ?", (res["shard_id"],))
    hits = ss.surface("f", path=state)["f"]
    assert [h["title"] for h in hits] == ["retracted note"]


def test_vault_scoped_default_state_path(tmp_path, monkeypatch):
    v1 = tmp_path / "vault_a"
    v2 = tmp_path / "vault_b"
    v1.mkdir()
    v2.mkdir()
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(v1))
    monkeypatch.setattr(core, "GLOBAL_DIR", v1)
    ss.subscribe("sub_a", tags=["alpha"])
    assert "sub_a" in ss.list_subscriptions()

    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(v2))
    monkeypatch.setattr(core, "GLOBAL_DIR", v2)
    assert ss.list_subscriptions() == {}


def test_cli_subscribe_exits_nonzero_on_errors(vault, monkeypatch):
    parser = cli.get_parser()

    with pytest.raises(SystemExit) as exc1:
        cli.cmd_subscribe(parser.parse_args(["subscribe", "add"]))
    assert exc1.value.code == 2

    with pytest.raises(SystemExit) as exc2:
        cli.cmd_subscribe(parser.parse_args(["subscribe", "add", "empty_sub"]))
    assert exc2.value.code == 2

    with pytest.raises(SystemExit) as exc3:
        cli.cmd_subscribe(parser.parse_args(["subscribe", "surface", "missing_sub"]))
    assert exc3.value.code == 2


def test_validation_and_lifecycle(vault):
    state = vault / "subs.json"
    with pytest.raises(ValueError):
        ss.subscribe("empty", path=state)
    ss.subscribe("a", tags=["t"], path=state)
    assert "a" in ss.list_subscriptions(path=state)
    with pytest.raises(KeyError):
        ss.surface("nope", path=state)
    assert ss.unsubscribe("a", path=state) is True
    assert ss.list_subscriptions(path=state) == {}
