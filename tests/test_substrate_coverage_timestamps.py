"""substrate_coverage must survive a non-ISO timestamp, and say so.

Found 2026-09-04 on the phoebus grid: 15 legacy shards stored Unix epoch
floats ("1765164383.78") in `timestamp`, written by a direct-write path that
predates capture()'s ISO normalisation. Two failures came out of one bad row:

  * loud   — the empty-month walk did `map(int, months[0].split("-"))` and
             raised ValueError, 500-ing the endpoint;
  * quiet  — "1765..." sorts BEFORE "2026-..." lexicographically, so one epoch
             row became `span.earliest` and the node reported a substrate
             reaching back to the year 1765.

The crash was the mercy. Had the walk been tolerant from the start, the wrong
span would have been served indefinitely with no symptom at all.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as node  # noqa: E402
from nougen_shards import core  # noqa: E402


@pytest.fixture()
def grid(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    core._INITIALIZED_DBS.clear()
    core.init_db(1)
    conn = sqlite3.connect(core.get_db_path(1))
    for ts in ("2026-01-05T00:00:00Z", "2026-03-05T00:00:00Z",
               "1765164383.7884684"):            # the epoch row
        conn.execute("INSERT INTO shards (event_type, title, content, timestamp, "
                     "file_hash) VALUES ('t','t','t',?,?)", (ts, f"h{ts}"))
    conn.commit()
    conn.close()
    monkeypatch.setenv("NOUGEN_COVERAGE_FEDERATED", "0")
    yield
    core._INITIALIZED_DBS.clear()


def test_epoch_timestamp_does_not_crash_the_endpoint(grid):
    out = node.substrate_coverage()
    assert out["total_shards"] == 3


def test_epoch_row_never_becomes_the_span(grid):
    """The quiet half. A year-1765 earliest is not a substrate, it is a bug."""
    out = node.substrate_coverage()
    assert out["span"]["earliest"] == "2026-01-05T00:00:00Z"
    assert out["span"]["latest"] == "2026-03-05T00:00:00Z"


def test_the_unusable_row_is_reported_not_dropped(grid):
    """It is real content no era-bounded query can reach. Counted in
    total_shards, absent from months — a caller must be able to see why."""
    out = node.substrate_coverage()
    assert out["malformed_timestamps"] == 1
    assert sum(out["months"].values()) == 2
    assert out["empty_months"] == ["2026-02"]


def test_clean_grid_reports_zero(grid, tmp_path, monkeypatch):
    conn = sqlite3.connect(core.get_db_path(1))
    conn.execute("DELETE FROM shards WHERE timestamp NOT LIKE '2%'")
    conn.commit()
    conn.close()
    assert node.substrate_coverage()["malformed_timestamps"] == 0
