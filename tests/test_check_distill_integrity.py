"""Fault-injection tests for tools/check_distill_integrity.py.

Each check must fire on a planted fault and stay silent on a clean sidecar. A clean result from the
live sidecar only means something if these pass.
"""

import importlib.util
import pathlib
import sqlite3

import pytest

from nougen_shards import distill

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_distill_integrity", ROOT / "tools" / "check_distill_integrity.py")
cdi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdi)

SRC = {
    "1_10": {"title": "Pizza", "content": "Likes pizza"},
    "1_11": {"title": "Name", "content": "Name is Alex"},
}


def good_hash(key):
    s = SRC[key]
    return cdi.content_hash(s["title"], s["content"])


def build(tmp_path, *, stale=False, orphan=False, dangling=False, lag=False):
    conn = sqlite3.connect(str(tmp_path / "side.db"))
    conn.executescript(distill.SCHEMA_SQL)
    keys = ["1_10", "1_11"] + (["1_99"] if orphan else [])
    for k in keys:
        h = good_hash(k) if k in SRC else "abc"
        if stale and k == "1_10":
            h = "0" * 40
        conn.execute("INSERT INTO distilled VALUES (?,?,?,?,?,?,?,?)",
                     (k, 1, int(k.split("_")[1]), h, "e2b", 1, "done", "2026-10-11T00:00:00Z"))
        conn.execute("INSERT INTO atoms(shard_key, type, text) VALUES (?,?,?)", (k, "fact", "x"))
    conn.execute("INSERT INTO entities(id, norm, name, kind) VALUES (1, 'pizza', 'Pizza', 'thing')")
    conn.execute("INSERT INTO entities(id, norm, name, kind) VALUES (2, 'alex', 'Alex', 'person')")
    conn.execute("INSERT INTO mentions VALUES (1, '1_10')")
    conn.execute("INSERT INTO mentions VALUES (1, '1_11')" if not dangling else "INSERT INTO mentions VALUES (1, '1_404')")
    conn.execute("INSERT INTO mentions VALUES (2, '1_11')")
    conn.execute("INSERT INTO scenes VALUES (1, 'summary', ?, '2026-10-11T00:00:00Z')", (1 if lag else 2,))
    conn.commit()
    return conn


def fake_source(keys):
    return {k: SRC[k] for k in keys if k in SRC}


def kinds(report):
    return {f["check"] for f in report["findings"]}


def test_clean_sidecar_has_no_findings(tmp_path):
    conn = build(tmp_path)
    assert cdi.check(conn, fake_source)["findings"] == []


def test_stale_hash_is_caught(tmp_path):
    assert "stale" in kinds(cdi.check(build(tmp_path, stale=True), fake_source))


def test_orphan_source_is_caught(tmp_path):
    assert "orphan" in kinds(cdi.check(build(tmp_path, orphan=True), fake_source))


def test_dangling_mention_is_caught(tmp_path):
    assert "dangling" in kinds(cdi.check(build(tmp_path, dangling=True), fake_source))


def test_scene_lag_is_caught(tmp_path):
    assert "scene_lag" in kinds(cdi.check(build(tmp_path, lag=True), fake_source))


def test_check_is_read_only(tmp_path):
    conn = build(tmp_path, stale=True)
    before = conn.execute("SELECT COUNT(*) FROM distilled").fetchone()[0]
    cdi.check(conn, fake_source)
    assert conn.execute("SELECT COUNT(*) FROM distilled").fetchone()[0] == before
