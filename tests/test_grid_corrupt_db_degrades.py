"""One corrupt grid DB must degrade the federated read, never zero it out.

Reproduces the 2026-08-29 false-empty: shards_coverage reported
databases_errored [{index: 5, "DatabaseError: database disk image is
malformed"}] while recall AND search both returned 0 rows against a six-figure
vault. shards_window -- which filters on timestamp and never touches the
per-DB fan-out -- kept returning rows the whole time, which is what proved the
data was there and the ranked path was the broken one.

Cause: the fan-out loops in core.py wrapped each DB in try/finally with no
except, and the inner guard around the FTS SQL caught only
sqlite3.OperationalError. A corrupt file raises sqlite3.DatabaseError -- the
PARENT class -- so it escaped the loop entirely and killed the whole read.
Eight healthy DBs sat unread while health reported up.
"""
# pylint: disable=duplicate-code, protected-access
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards

CORRUPT_INDEX = 2
HEALTHY_INDEX = 1
NEEDLE = "quaxolotl"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Temporary vault so the real grid is never touched."""
    # Not TemporaryDirectory(): its cleanup raises NotADirectoryError on Windows
    # over the file this test deliberately corrupts, and a teardown artifact
    # must never masquerade as a failure.
    temp_dir = tempfile.mkdtemp()
    try:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(shards, "get_db_path", mock_get_db_path)

        shards.init_db(HEALTHY_INDEX)
        yield temp_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _corrupt(path: Path) -> None:
    """Make a real SQLite file unreadable the way a torn write does: keep a
    valid header so the connection opens, then shred the pages behind it.
    Truncating instead would raise a different error and prove less."""
    shards.init_db(CORRUPT_INDEX)
    raw = bytearray(path.read_bytes())
    assert len(raw) > 4096, "need at least a header page plus content to corrupt"
    for offset in range(1024, len(raw)):
        raw[offset] = 0xFF
    path.write_bytes(bytes(raw))


def test_corrupt_db_does_not_zero_the_federated_read(setup_test_env):
    """A shard in a healthy DB stays findable when a sibling DB is corrupt."""
    shards.capture(
        "TEST", "Findable shard",
        f"This shard mentions {NEEDLE} and lives on a healthy grid database.",
    )

    baseline = shards.retrieve(NEEDLE, limit=5)
    assert baseline, "precondition failed: the shard is not findable even with no corruption"

    _corrupt(setup_test_env / f"test_shards_{CORRUPT_INDEX}.db")

    after = shards.retrieve(NEEDLE, limit=5)
    assert after, (
        "recall returned EMPTY because one grid DB is corrupt - the healthy DB "
        "still holds the shard. This is the false-empty defect: a partial answer "
        "is correct, an empty one is a lie."
    )
    assert any(NEEDLE in (r.get("content") or "") for r in after)


def test_fuzzy_second_pass_survives_a_db_that_fails_after_the_first(setup_test_env, monkeypatch):
    """The SECOND fan-out in _keyword_retrieve needs the same guard as the first.

    _keyword_retrieve sweeps every DB, notes the ones where both exact lanes
    missed, and re-scans just those in a fuzzy pass. That second loop opens its
    own connection, so a DB that was readable during the first pass and fails
    during the second -- a lock, a checkpoint, a file replaced underneath -- hits
    get_connection() outside any guard. It shipped unguarded on 2026-08-29
    because the first pass in the same function was fixed and this one was not.
    """
    shards.init_db(CORRUPT_INDEX)
    shards.capture("TEST", "Findable shard",
                   f"This shard mentions {NEEDLE} and lives on a healthy grid database.")

    real_get_connection = shards.get_connection
    calls = {"n": 0}

    def flaky(index):
        if index == CORRUPT_INDEX:
            calls["n"] += 1
            if calls["n"] > 1:  # healthy for the first pass, broken for the fuzzy one
                raise sqlite3.DatabaseError("database disk image is malformed")
        return real_get_connection(index)

    monkeypatch.setattr(shards, "get_connection", flaky)

    results = shards.retrieve(NEEDLE, limit=5)

    # Without this the test is vacuous: if the fuzzy pass never re-opened the
    # DB, the guard it is meant to exercise was never reached.
    assert calls["n"] > 1, "the fuzzy second pass never ran - this test proves nothing"
    assert results, (
        "the fuzzy second pass let a DatabaseError escape and killed the whole "
        "retrieve - the healthy DB still holds the shard"
    )
    assert any(NEEDLE in (r.get("content") or "") for r in results)


def test_permission_denied_db_does_not_zero_the_read(setup_test_env, monkeypatch):
    """An ACL-locked DB file must degrade the fan-out, not abort it.

    Path.exists() returns False only for ENOENT/ENOTDIR -- on EACCES/EPERM it
    RAISES. The existence probe used to sit OUTSIDE the try, so a permission
    error escaped the DatabaseError handler two lines before it could help and
    killed the whole federated read: the same failure the handler exists to
    stop, through a different door.

    (PowerShell's Test-Path has the mirror-image bug -- it RETURNS $false on
    UnauthorizedAccessException, so "not allowed to look" is indistinguishable
    from "not there". Raising is the better default; it just has to be caught.)
    """
    shards.init_db(CORRUPT_INDEX)
    shards.capture("TEST", "Findable shard",
                   f"This shard mentions {NEEDLE} and lives on a healthy grid database.")

    real_get_db_path = shards.get_db_path

    class Denied(type(real_get_db_path(HEALTHY_INDEX))):
        def exists(self):
            raise PermissionError(13, "Access is denied")

    def denied_for_second(index):
        p = real_get_db_path(index)
        return Denied(p) if index == CORRUPT_INDEX else p

    monkeypatch.setattr(shards, "get_db_path", denied_for_second)

    results = shards.retrieve(NEEDLE, limit=5)
    assert results, (
        "a permission-denied DB aborted the whole retrieve - the healthy DB "
        "still holds the shard"
    )
    assert any(NEEDLE in (r.get("content") or "") for r in results)
