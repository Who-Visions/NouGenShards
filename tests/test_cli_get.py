"""`nougen get` — resolve a shard by content hash.

Exists because both prior citation conventions failed under test:
`<id>@db<n>` is a node-local address that resolves to unrelated content
elsewhere, and "cite by phrase" is a ranked query — on 2026-09-08 a phrase
citation returned the very shard it was meant to supersede, ranked above it.
"""

import argparse
import sqlite3
from pathlib import Path

import pytest

from nougen_shards import cli


def _vault(tmp_path: Path, rows) -> Path:
    """Build a minimal grid: one DB per row-group, mirroring the real layout."""
    for index, group in rows.items():
        db = tmp_path / f"nougen_shards_{index}.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, "
                     "event_type TEXT, title TEXT, content TEXT, tags TEXT, "
                     "file_hash TEXT UNIQUE NOT NULL)")
        for sid, fhash, title, content in group:
            conn.execute("INSERT INTO shards VALUES (?,?,?,?,?,?,?)",
                         (sid, "2026-09-08T00:00:00Z", "KNOWLEDGE", title, content,
                          "[]", fhash))
        conn.commit()
        conn.close()
    return tmp_path


def _patch(monkeypatch, root: Path, count: int = 9):
    from nougen_shards import core
    monkeypatch.setattr(core, "MAX_DB_COUNT", count)
    monkeypatch.setattr(core, "get_db_path",
                        lambda i: root / f"nougen_shards_{i}.db")


def test_resolves_a_unique_prefix(tmp_path, monkeypatch, capsys):
    root = _vault(tmp_path, {6: [(12159, "43ebb7fe0454cd57e0f1f61e4b2bbdd0",
                                  "AN ALIEN MIND", "the essay body")]})
    _patch(monkeypatch, root)
    cli.cmd_get(argparse.Namespace(hash="43ebb7fe", full=False))
    out = capsys.readouterr().out
    assert "43ebb7fe0454cd57e0f1f61e4b2bbdd0" in out
    assert "12159@db6" in out
    assert "the essay body" in out


def test_locator_is_labelled_as_not_the_address(tmp_path, monkeypatch, capsys):
    """The output must not teach the habit this command exists to replace."""
    root = _vault(tmp_path, {6: [(1, "aaaaaaaa1111", "t", "c")]})
    _patch(monkeypatch, root)
    cli.cmd_get(argparse.Namespace(hash="aaaaaaaa", full=False))
    assert "NOT the address" in capsys.readouterr().out


def test_ambiguity_is_refused_not_silently_resolved(tmp_path, monkeypatch, capsys):
    """A citation that quietly picks one of several is worse than one that fails.

    Silently returning the first match would reproduce exactly the defect that
    motivated this command: a confident answer pointing at the wrong document.
    """
    root = _vault(tmp_path, {
        1: [(10, "beef00001111", "first", "a")],
        2: [(20, "beef00002222", "second", "b")],
    })
    _patch(monkeypatch, root)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_get(argparse.Namespace(hash="beef0000", full=False))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "AMBIGUOUS" in out and "quote more characters" in out
    assert "first" in out and "second" in out


def test_absence_is_reported_as_bytes_absent_here(tmp_path, monkeypatch, capsys):
    """A hash is content-derived, so a miss is a statement about THIS node."""
    root = _vault(tmp_path, {1: [(1, "cafe11112222", "t", "c")]})
    _patch(monkeypatch, root)
    with pytest.raises(SystemExit):
        cli.cmd_get(argparse.Namespace(hash="deadbeef", full=False))
    out = capsys.readouterr().out
    assert "not on this node" in out
    assert "not that the shard does not exist" in out


def test_short_prefixes_are_rejected(tmp_path, monkeypatch, capsys):
    root = _vault(tmp_path, {1: [(1, "abcd11112222", "t", "c")]})
    _patch(monkeypatch, root)
    with pytest.raises(SystemExit):
        cli.cmd_get(argparse.Namespace(hash="abc", full=False))
    assert "at least 6" in capsys.readouterr().out


def test_one_unreadable_db_does_not_hide_hits_in_the_others(tmp_path, monkeypatch, capsys):
    """A single corrupt vault must not turn a hit into a silent miss.

    The grid quarantines malformed DBs; a lookup that gave up on the first
    unreadable file would report 'not here' for content that is here.
    """
    root = _vault(tmp_path, {3: [(30, "feed11112222", "found", "body")]})
    (root / "nougen_shards_1.db").write_text("this is not a database")
    _patch(monkeypatch, root)
    cli.cmd_get(argparse.Namespace(hash="feed1111", full=False))
    assert "found" in capsys.readouterr().out


def test_full_flag_prints_the_whole_body(tmp_path, monkeypatch, capsys):
    body = "x" * 5000
    root = _vault(tmp_path, {1: [(1, "1234abcd5678", "t", body)]})
    _patch(monkeypatch, root)
    cli.cmd_get(argparse.Namespace(hash="1234abcd", full=True))
    out = capsys.readouterr().out
    assert "more characters" not in out
    assert out.count("x") == 5000
