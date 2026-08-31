"""A malformed grid DB must not make hash-routed captures un-ingestable.

Regression for the 2026-08-30 Space incident: DB8's file was corrupt
("database disk image is malformed"), capture() raised for every shard whose
hash routed there, and /sync/push turned each raise into a 500 for its whole
batch - deterministically, batch after batch.
"""
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import core  # noqa: E402


@pytest.fixture()
def tmp_vault(monkeypatch):
    # Same convention as test_grid_corrupt_db_degrades: patch GLOBAL_DIR and
    # get_db_path directly so the real grid is never touched, and rmtree with
    # ignore_errors because Windows cleanup can trip over the file this test
    # deliberately corrupts.
    temp_dir = tempfile.mkdtemp()
    try:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(core, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(core, "get_db_path", mock_get_db_path)
        monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
        core._QUARANTINED_WRITE_DBS.clear()
        core._INITIALIZED_DBS.clear()
        yield temp_path
    finally:
        core._QUARANTINED_WRITE_DBS.clear()
        core._INITIALIZED_DBS.clear()
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_capture_routes_around_malformed_db(tmp_vault, monkeypatch):
    corrupt_idx = 3
    # A real corrupt file: right header prefix, garbage body.
    core.get_db_path(corrupt_idx).write_bytes(
        b"SQLite format 3\x00" + b"\xde\xad\xbe\xef" * 64)
    monkeypatch.setattr(core, "get_write_index", lambda fhash: corrupt_idx)

    ok = core.capture("KNOWLEDGE", "quarantine test", "unique body 1")
    # capture() now returns a CaptureResult, which is TRUTHY on a write but
    # is not the `True` singleton. Truthiness is the contract; identity is not.
    assert ok
    assert ok.reason == "written" and ok.shard_id is not None
    assert corrupt_idx in core._QUARANTINED_WRITE_DBS

    # The shard landed in a healthy DB, not the corrupt one.
    found = []
    for i in range(1, core.MAX_DB_COUNT + 1):
        if i == corrupt_idx or not core.get_db_path(i).exists():
            continue
        conn = core.get_connection(i)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM shards WHERE title = ?",
                ("quarantine test",)).fetchone()[0]
        finally:
            conn.close()
        if n:
            found.append(i)
    assert found, "shard was not written to any healthy DB"

    # Second capture skips the quarantined index without touching the file.
    ok2 = core.capture("KNOWLEDGE", "quarantine test 2", "unique body 2")
    # Same contract: truthy CaptureResult, not the `True` singleton.
    assert ok2 and ok2.reason == "written"


def test_capture_returns_false_when_all_dbs_quarantined(tmp_vault, monkeypatch):
    monkeypatch.setattr(core, "get_write_index", lambda fhash: 1)
    for i in range(1, core.MAX_DB_COUNT + 1):
        core._QUARANTINED_WRITE_DBS.add(i)
    # Route-around has nowhere to go; capture degrades to False, no raise.
    core._QUARANTINED_WRITE_DBS.discard(1)
    core.get_db_path(1).write_bytes(
        b"SQLite format 3\x00" + b"\xde\xad\xbe\xef" * 64)
    ok = core.capture("KNOWLEDGE", "no home", "unique body 3")
    # Falsy, and now able to say WHY it failed rather than just that it did.
    assert not ok
    assert ok.reason == "error" and "quarantined" in ok.error
