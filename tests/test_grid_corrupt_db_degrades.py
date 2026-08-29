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
