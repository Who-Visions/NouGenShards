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


def test_vault_journal_mode_defaults_to_wal(monkeypatch):
    monkeypatch.delenv("NOUGEN_VAULT_JOURNAL_MODE", raising=False)
    monkeypatch.delenv("SPACE_ID", raising=False)
    monkeypatch.delenv("HF_SPACE_ID", raising=False)
    assert core.get_vault_journal_mode() == "WAL"


def test_vault_journal_mode_env_override(monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_JOURNAL_MODE", "delete")
    assert core.get_vault_journal_mode() == "DELETE"
    monkeypatch.setenv("NOUGEN_VAULT_JOURNAL_MODE", "truncate")
    assert core.get_vault_journal_mode() == "TRUNCATE"


def test_vault_journal_mode_auto_detects_space(monkeypatch):
    monkeypatch.delenv("NOUGEN_VAULT_JOURNAL_MODE", raising=False)
    monkeypatch.setenv("SPACE_ID", "Who-Visions/NouGenShards")
    assert core.get_vault_journal_mode() == "DELETE"


def test_vault_connection_honors_delete_journal_mode(vault, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_JOURNAL_MODE", "DELETE")
    core.init_db(1)
    conn = core.get_connection(1)
    try:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        assert str(row[0]).upper() == "DELETE"
    finally:
        conn.close()


def test_clean_check_is_remembered_and_skipped_inside_window(vault, monkeypatch):
    """quick_check is O(file size): a node restarting several times an hour must not
    re-read the whole grid every boot (741s over 12 GB on 2026-11-12)."""
    _make_healthy(1)
    calls = []
    real_connect = core.sqlite3.connect

    def counting_connect(*a, **kw):
        calls.append(a[0] if a else kw.get("database"))
        return real_connect(*a, **kw)

    assert core.quarantine_malformed_dbs() == []
    monkeypatch.setattr(core.sqlite3, "connect", counting_connect)
    assert core.quarantine_malformed_dbs() == []
    assert not [c for c in calls if str(c) == str(core.get_db_path(1))], "re-checked a fresh clean DB"


def test_recheck_window_zero_checks_every_boot(vault, monkeypatch):
    _make_healthy(1)
    assert core.quarantine_malformed_dbs() == []
    monkeypatch.setenv("NOUGEN_QUARANTINE_RECHECK_HOURS", "0")
    bad = core.get_db_path(1)
    core._INITIALIZED_DBS.clear()
    bad.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)
    moved = core.quarantine_malformed_dbs()
    assert [q["index"] for q in moved] == [1]


def test_expired_clean_check_is_rechecked(vault, monkeypatch):
    import json
    _make_healthy(1)
    path = core.get_db_path(1)
    core._quarantine_state_path().write_text(json.dumps({str(path): 0}), encoding="utf-8")
    core._INITIALIZED_DBS.clear()
    path.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4096)
    assert [q["index"] for q in core.quarantine_malformed_dbs()] == [1]
