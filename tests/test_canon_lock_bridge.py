"""Canon pressure consults GM canon-lock shards in the grid.

Synthetic data only: an invented harbor town, no real canon. The control
(`test_contradicting_a_gm_lock_is_a_fact_conflict`) is the known-contradiction
case that used to score UNKNOWN 0.35.
"""
import sqlite3

import pytest

from nougen_shards import canon_lock_bridge as bridge
from nougen_shards import canon_pressure

LOCKS = [
    (101, "GM CANON LOCK 2030-01-02: Mira Quell; beacon keeper Tovan born Mar 4 2140; "
          "the harbor is not a Guild port",
     "Locked by the GM.\n1. Mira's surname is QUELL.\n2. Tovan is a lighthouse engineer, not a smuggler.\n"),
    (102, "CANON INVARIANT: the ferry never sails at night", ""),
    (103, "Notes about canon lock drift in old drafts", "not a lock: prefix is not at the start"),
    (104, "canon lock: the bell tower has three bells", ""),
]

MODEL = {"records": [], "temporal_self": [], "themes": [], "fixed_points": [], "conflict_groups": []}


def _grid(dirpath, name="nougen_shards_3.db", rows=LOCKS):
    conn = sqlite3.connect(dirpath / name)
    conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, title TEXT, content TEXT)")
    conn.executemany("INSERT INTO shards (id, title, content) VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()
    return dirpath


@pytest.fixture
def grid(tmp_path, monkeypatch):
    _grid(tmp_path)
    monkeypatch.setenv("NOUGEN_CANON_LOCK_DIR", str(tmp_path))
    monkeypatch.setenv("NOUGEN_SELF_ARCHIVE_PATH", str(tmp_path / "absent_archive.json"))
    monkeypatch.setenv("NOUGEN_CANON_DB", str(tmp_path / "canon.db"))
    monkeypatch.delenv("NOUGEN_CANON_LOCKS", raising=False)
    bridge._CACHE.clear()
    return tmp_path


def _press(text):
    return canon_pressure.pressure(text, register=False, model=MODEL)


def test_load_locks_matches_prefixes_only(grid):
    locks = {lk["shard"]: lk for lk in bridge.load_locks(force=True)}
    assert set(locks) == {"101@db3", "102@db3", "104@db3"}
    gm = locks["101@db3"]
    assert gm["authority"] == "gm_lock" and locks["102@db3"]["authority"] == "gm"
    assert gm["clauses"][0] == "Mira Quell"  # prefix and ISO date stripped
    assert "Tovan is a lighthouse engineer, not a smuggler." in gm["clauses"]


def test_load_locks_matches_tag_and_honours_digest_exclusion(tmp_path, monkeypatch):
    conn = sqlite3.connect(tmp_path / "nougen_shards_4.db")
    conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, title TEXT, content TEXT, tags TEXT)")
    conn.executemany("INSERT INTO shards (id, title, content, tags) VALUES (?,?,?,?)", [
        (201, "VeilVerse special title", "Clause A", '["canon-lock"]'),
        (202, "VeilVerse digest title", "Clause B", '["canon-lock", "canon-digest"]'),
        (203, "Untagged non-lock title", "Clause C", '["other-tag"]')
    ])
    conn.commit()
    conn.close()
    monkeypatch.setenv("NOUGEN_CANON_LOCK_DIR", str(tmp_path))
    bridge._CACHE.clear()
    locks = {lk["shard"]: lk for lk in bridge.load_locks(force=True)}
    assert "201@db4" in locks
    assert "202@db4" not in locks  # excluded by canon-digest tag
    assert "203@db4" not in locks


def test_contradicting_a_gm_lock_is_a_fact_conflict(grid):
    out = _press("Tovan was born in 2150.")
    assert out["verdict"] == "FACT_CONFLICT"
    assert "101@db3" in out["evidence_ids"]
    assert out["confidence"] > 0.35
    assert out["locks_consulted"] == 3
    hit = next(f for f in out["findings"] if f.get("source") == "grid_lock")
    assert hit["rule"] == "number_mismatch"


def test_claim_the_lock_negates_conflicts(grid):
    assert _press("The harbor is a Guild port")["verdict"] == "FACT_CONFLICT"
    assert _press("The ferry sails at night")["verdict"] == "FACT_CONFLICT"


def test_a_not_b_lock_only_blocks_the_excluded_side(grid):
    assert _press("Tovan is a smuggler")["verdict"] == "FACT_CONFLICT"
    assert _press("Tovan is a lighthouse engineer")["verdict"] != "FACT_CONFLICT"


def test_candidate_denying_a_lock_conflicts(grid):
    res = bridge.check("Mira's surname is not Quell", bridge.load_locks(force=True))
    assert [c["rule"] for c in res["conflicts"]] == ["candidate_denies_lock"]


def test_matching_the_lock_is_valid_on_prime(grid):
    out = _press("Beacon keeper Tovan was born Mar 4 2140")
    assert out["verdict"] == "BRANCH_VALID" and out["branch"] == "U0"
    assert "101@db3" in out["evidence_ids"]


def test_unrelated_claim_stays_unknown(grid):
    out = _press("A merchant sells lanterns in the square")
    assert out["verdict"] == "UNKNOWN" and out["confidence"] == 0.35


def test_declared_branch_is_not_held_to_prime_locks(grid):
    out = _press("What if Tovan was born in 2150")
    assert out["verdict"] == "BRANCH_VALID" and out["branch"] == "SIM"


def test_bridge_can_be_disabled(grid, monkeypatch):
    monkeypatch.setenv("NOUGEN_CANON_LOCKS", "0")
    out = _press("Tovan was born in 2150.")
    assert out["verdict"] == "UNKNOWN" and out["locks_consulted"] == 0


def test_limit_env_and_bad_db_are_honoured(grid, monkeypatch):
    (grid / "nougen_shards_9.db").write_bytes(b"not a sqlite file at all" * 64)
    assert len(bridge.load_locks(force=True)) == 3  # corrupt db skipped, not fatal
    monkeypatch.setenv("NOUGEN_CANON_LOCK_LIMIT", "1")
    assert len(bridge.load_locks(force=True)) == 1
    monkeypatch.setenv("NOUGEN_CANON_LOCK_LIMIT", "lots")  # bad value -> logged fallback
    assert len(bridge.load_locks(force=True)) == 3


def test_lock_read_failure_never_breaks_pressure(grid, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("grid offline")
    monkeypatch.setattr(bridge, "lock_findings", boom)
    assert _press("Tovan was born in 2150.")["verdict"] == "UNKNOWN"
