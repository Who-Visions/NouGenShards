"""Substrate coverage: a partial mount must not read as an empty result."""
import ast
import sqlite3

import pytest

import nougen_shards.core as core


def _load_coverage():
    """Pull _substrate_coverage out of app.py without importing it.

    app.py imports gradio at module scope, which is not a test dependency.
    """
    src = open("app.py", encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "_substrate_coverage")
    ns = {"core": core}
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
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
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
