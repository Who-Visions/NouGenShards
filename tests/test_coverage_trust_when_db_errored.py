"""recall_trustworthy must be FALSE while a grid database is unreadable.

shards_coverage's own tool description tells callers to check it "before
concluding a recall miss means the memory does not exist". On 2026-08-29 it
answered `recall_trustworthy: true` with `databases_errored [{index: 5,
"DatabaseError: database disk image is malformed"}]` and both ranked read paths
returning zero rows -- so everyone who did the responsible thing and checked
coverage first was told to conclude data loss.

The flag was `complete or bool(upstreams)`. An errored database made `complete`
false, and a configured upstream flipped it back to true -- an upstream that was
answering 530 at the time, which this function never probes.
"""
# pylint: disable=duplicate-code, protected-access
import shutil
import tempfile
from pathlib import Path

import pytest

import app
import nougen_shards.core as shards

HEALTHY_INDEX = 1
CORRUPT_INDEX = 2


@pytest.fixture()
def grid(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    try:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        monkeypatch.setattr(shards, "MAX_DB_COUNT", 2)
        shards.init_db(HEALTHY_INDEX)
        shards.init_db(CORRUPT_INDEX)
        yield temp_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _shred(path: Path) -> None:
    """Torn write, not a truncation: keep a valid header so the file opens."""
    raw = bytearray(path.read_bytes())
    for offset in range(1024, len(raw)):
        raw[offset] = 0xFF
    path.write_bytes(bytes(raw))


def test_errored_db_makes_recall_untrustworthy_even_with_an_upstream(grid, monkeypatch):
    """An upstream must not launder a corrupt database into a trustworthy read."""
    monkeypatch.setattr(app, "_registered_upstreams",
                        lambda: [{"name": "blade", "url": "https://example.invalid"}])

    clean = app._substrate_coverage()
    assert clean["recall_trustworthy"] is True, "precondition: healthy grid is trustworthy"

    _shred(grid / f"test_shards_{CORRUPT_INDEX}.db")

    degraded = app._substrate_coverage()
    assert degraded["databases_errored"], "precondition: the shredded DB must report as errored"
    assert degraded["recall_trustworthy"] is False, (
        "coverage called recall trustworthy while a database was unreadable - "
        "this is the flag callers are told to check before concluding a memory "
        "does not exist, and an upstream does not make dark shards readable"
    )
    assert "unreadable" in degraded["recall_trustworthy_reason"]
