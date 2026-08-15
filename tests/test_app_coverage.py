"""Substrate coverage: a partial mount must not read as an empty result."""
import ast
import logging
import os
import sqlite3

import pytest

import nougen_shards.core as core
import nougen_shards.keymaker as keymaker


def _load_coverage():
    """Pull the coverage helpers out of app.py without importing it.

    app.py imports gradio at module scope, which is not a test dependency.
    _substrate_coverage calls _registered_upstreams, so both are loaded into
    one namespace and resolve against each other.
    """
    src = open("app.py", encoding="utf-8").read()
    tree = ast.parse(src)
    ns = {"core": core, "os": os, "logging": logging}
    for name in ("_registered_upstreams", "_substrate_coverage"):
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        mod = ast.Module(body=[fn], type_ignores=[])
        exec(compile(ast.fix_missing_locations(mod), "app.py", "exec"), ns)
    return ns["_substrate_coverage"]


def _make_db(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE shards (id INTEGER)")
    con.executemany("INSERT INTO shards VALUES (?)", [(n,) for n in range(rows)])
    con.commit()
    con.close()


@pytest.fixture
def coverage(tmp_path, monkeypatch):
    """A grid with no read-through upstream, so coverage reflects local mounts."""
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(keymaker, "DB_PATH", tmp_path / "agent_secrets.db")
    return _load_coverage(), tmp_path


def test_full_grid_is_complete_and_trustworthy(coverage):
    cover, vault = coverage
    for i in range(1, core.MAX_DB_COUNT + 1):
        _make_db(vault / f"nougen_shards_{i}.db", 10)
    c = cover()
    assert c["complete"] is True
    assert c["recall_trustworthy"] is True
    assert c["databases_mounted"] == core.MAX_DB_COUNT
    assert c["shards"] == 10 * core.MAX_DB_COUNT
    assert c["databases_missing"] == []
    assert c["databases_errored"] == []


def test_missing_databases_are_named_not_silently_skipped(coverage):
    cover, vault = coverage
    for i in (1, 2, 3):
        _make_db(vault / f"nougen_shards_{i}.db", 100 * i)
    c = cover()
    assert c["complete"] is False
    assert c["recall_trustworthy"] is False
    assert c["databases_mounted"] == 3
    assert c["databases_missing"] == [4, 5, 6, 7, 8, 9]
    assert c["shards"] == 600


def test_corrupt_database_reports_a_reason(coverage):
    cover, vault = coverage
    _make_db(vault / "nougen_shards_1.db", 5)
    (vault / "nougen_shards_2.db").write_bytes(b"this is not a database")
    c = cover()
    assert c["complete"] is False
    errored = c["databases_errored"]
    assert [e["index"] for e in errored] == [2]
    # The reason matters: a locked database and a corrupt one need different responses.
    assert errored[0]["error"]
    assert c["shards"] == 5


def test_every_index_is_accounted_for_exactly_once(coverage):
    """The invariant that makes the report trustworthy."""
    cover, vault = coverage
    for i in (1, 2, 3):
        _make_db(vault / f"nougen_shards_{i}.db", 1)
    (vault / "nougen_shards_4.db").write_bytes(b"not a database")
    c = cover()
    seen = c["databases_mounted"] + len(c["databases_missing"]) + len(c["databases_errored"])
    assert seen == c["databases_expected"]


def test_empty_vault_is_incomplete_rather_than_zero(coverage):
    """Zero shards from an unmounted grid is not the same as zero matches."""
    cover, _ = coverage
    c = cover()
    assert c["shards"] == 0
    assert c["complete"] is False
    assert c["recall_trustworthy"] is False
    assert c["databases_missing"] == list(range(1, core.MAX_DB_COUNT + 1))


def test_read_through_is_false_without_an_upstream(coverage):
    cover, vault = coverage
    for i in range(1, core.MAX_DB_COUNT + 1):
        _make_db(vault / f"nougen_shards_{i}.db", 1)
    c = cover()
    assert c["read_through"] is False
    assert c["upstreams"] == []


def test_an_upstream_makes_a_thin_local_grid_expected_not_a_fault(coverage):
    """With read-through, local shards are a cache, so 'incomplete' is normal."""
    cover, vault = coverage
    _make_db(vault / "nougen_shards_1.db", 3)
    keymaker.register_cloud_node("https://blade.example", "blade")
    c = cover()
    assert c["complete"] is False          # locally it really is partial
    assert c["read_through"] is True
    assert c["recall_trustworthy"] is True  # the corpus lives upstream
    assert [u["name"] for u in c["upstreams"]] == ["blade"]
