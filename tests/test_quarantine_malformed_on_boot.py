"""Boot-time quarantine must heal ONLY malformed grid DBs, never healthy ones.

Surgical replacement for the volume-wipe doctrine (2026-09-01 Space-sqlite P1):
six of nine DBs went malformed and the wipe would have destroyed the three
healthy indices - including six hours of freshly repopulated rows - with them.
"""
from pathlib import Path

import pytest

from nougen_shards import core


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    # NEVER via env: core.GLOBAL_DIR is baked at import, so setting
    # NOUGEN_VAULT_DIR here silently resolves to the LIVE vault. That exact
    # mistake destroyed live grid DB2 (29,537 shards) on 2026-09-01 and it
    # was recovered only because a bucket snapshot existed. Bind through the
    # context API and hard-refuse to run anywhere but tmp_path.
    tokens = core.bind_active_vault(tmp_path, "owner")
    assert core.active_vault_dir() == tmp_path, (
        "vault fixture is NOT bound to tmp_path - refusing to touch any DB")
    assert str(core.get_db_path(1)).startswith(str(tmp_path))
    monkeypatch.delenv("NOUGEN_QUARANTINE_MALFORMED_ON_BOOT", raising=False)
    core._INITIALIZED_DBS.clear()
    yield tmp_path
    core._INITIALIZED_DBS.clear()
    core.reset_active_vault(tokens)


def _make_healthy(index):
    core.init_db(index)
    conn = core.get_connection(index)
    try:
        conn.execute(
            "INSERT INTO shards (timestamp, event_type, title, content, file_hash) "
            "VALUES ('2026-09-01T00:00:00Z', 'KNOWLEDGE', 't', 'c', ?)",
            (f"hash-{index}",))
        conn.commit()
    finally:
        conn.close()


def test_malformed_db_is_renamed_and_recreated(vault):
    _make_healthy(1)
    bad = core.get_db_path(2)
    bad.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)  # valid header, garbage body
    core._INITIALIZED_DBS.clear()

    result = core.quarantine_malformed_dbs()

    assert [q["index"] for q in result] == [2]
    moved = list(vault.glob("nougen_shards_2.db.malformed-*"))
    assert len(moved) == 1, "corrupt file must be renamed aside, not deleted"
    conn = core.get_connection(2)
    try:
        assert conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0] == 0
    finally:
        conn.close()


def test_healthy_db_is_untouched_bytes_for_bytes(vault):
    _make_healthy(1)
    before = core.get_db_path(1).read_bytes()

    result = core.quarantine_malformed_dbs()

    assert result == []
    assert core.get_db_path(1).read_bytes() == before
    assert not list(vault.glob("*.malformed-*"))
    conn = core.get_connection(1)
    try:
        assert conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0] == 1
    finally:
        conn.close()


def test_env_kill_switch_disables_quarantine(vault, monkeypatch):
    bad = core.get_db_path(3)
    bad.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)
    monkeypatch.setenv("NOUGEN_QUARANTINE_MALFORMED_ON_BOOT", "0")

    assert core.quarantine_malformed_dbs() == []
    assert bad.exists(), "kill switch must leave the file alone"


def test_no_orphan_sidecars_can_poison_the_recreated_db(vault):
    # sqlite's own open-time recovery may consume invalid -wal/-shm sidecars
    # before the rename runs; either way, none may remain beside the fresh DB.
    bad = core.get_db_path(4)
    bad.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)
    Path(str(bad) + "-wal").write_bytes(b"wal")
    Path(str(bad) + "-shm").write_bytes(b"shm")

    result = core.quarantine_malformed_dbs()

    assert [q["index"] for q in result] == [4]
    assert not Path(str(bad) + "-wal").exists()
    assert not Path(str(bad) + "-shm").exists()
    conn = core.get_connection(4)
    try:
        assert conn.execute("SELECT COUNT(*) FROM shards").fetchone()[0] == 0
    finally:
        conn.close()


def test_missing_files_are_not_created(vault):
    assert core.quarantine_malformed_dbs() == []
    assert not core.get_db_path(5).exists()
