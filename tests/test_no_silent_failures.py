"""Two shapes of the same defect: code that reports success or emptiness
where it should report a fault.

1. `capture()` answered with a bare bool. A caller that got a falsy answer
   could not tell "duplicate, nothing to do" from "the write failed", and a
   caller that got a truthy one could not name the row. Observed live
   2026-08-30: a capture came back as an empty object and had in fact
   SUCCEEDED, so lanes stopped trusting the return in either direction.

2. `NOUGEN_VECTOR_CACHE=0` reads like a memory knob but there is no uncached
   scan path any more (the per-row scan was a measured 10.7GB / 27s grid read
   and was deliberately removed). Turning it off therefore turns SEMANTIC
   RECALL off, and a user who set it to save ~800MB RSS silently got
   keyword-only recall that looked like "no semantic matches".
"""
# pylint: disable=duplicate-code, protected-access
import json
import logging
import sqlite3
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Temporary vault so the real grid is never touched."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        shards.init_db(1)
        yield temp_path


# --- 1. capture() must be branchable -----------------------------------------

def test_capture_success_names_the_shard_it_wrote():
    result = shards.capture("KNOWLEDGE", "branchable write",
                            "a unique body for the branchable write probe",
                            tags=["silent-failure"])
    assert result.captured is True
    assert result["captured"] is True
    assert result["reason"] == "written"
    assert isinstance(result["shard_id"], int) and result["shard_id"] > 0
    assert isinstance(result["db_index"], int)
    assert "error" not in result, "a successful write must not carry an error"


def test_capture_duplicate_is_falsy_and_says_why():
    body = "a unique body for the duplicate probe"
    first = shards.capture("KNOWLEDGE", "dupe probe", body)
    assert first.captured is True

    second = shards.capture("KNOWLEDGE", "dupe probe", body)
    assert second.captured is False
    assert second["reason"] == "duplicate"
    assert "duplicate" in second["error"]
    assert second.get("shard_id") is None, \
        "nothing was written, so no id may be claimed"


def test_capture_result_is_backward_compatible_and_serializable():
    """Old callers only ever asked `if capture(...)`. That must still work,
    and the richer answer must survive JSON/MCP serialization unchanged."""
    written = shards.capture("KNOWLEDGE", "compat probe",
                             "a unique body for the compat probe")
    duplicate = shards.capture("KNOWLEDGE", "compat probe",
                               "a unique body for the compat probe")

    assert bool(written) is True and bool(duplicate) is False
    assert (written and True) is True
    assert not duplicate

    payload = json.loads(json.dumps(dict(written)))
    assert payload["captured"] is True
    assert payload["shard_id"] == written["shard_id"]


def test_capture_does_not_swallow_a_real_write_fault(monkeypatch):
    """A genuine DB fault must RAISE, not degrade into `captured: False`.

    Reporting a broken vault as a quiet falsy answer is the very failure mode
    this module exists to stop.
    """
    def boom(_index):
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(shards, "get_connection", boom)
    with pytest.raises(sqlite3.OperationalError):
        shards.capture("KNOWLEDGE", "fault probe",
                       "a unique body for the write-fault probe")


def test_mcp_capture_tool_reports_the_outcome():
    """The stdio MCP surface must forward the distinction, not flatten it."""
    from nougen_shards import mcp as mcp_module

    body = "a unique body for the mcp surface probe"
    first = mcp_module.capture_experience("KNOWLEDGE", "mcp probe", body)
    assert "captured successfully" in first
    assert "id " in first

    second = mcp_module.capture_experience("KNOWLEDGE", "mcp probe", body)
    assert "NOT captured" in second
    assert "duplicate" in second


# --- 2. NOUGEN_VECTOR_CACHE=0 must be loud ------------------------------------

@pytest.fixture
def vector_lane_unwarned(monkeypatch):
    """Reset the process-level warn-once latch around each test."""
    monkeypatch.setattr(shards, "_VECTOR_LANE_OFF_WARNED", False, raising=False)
    yield
    monkeypatch.setattr(shards, "_VECTOR_LANE_OFF_WARNED", False, raising=False)


def _lane_off_warnings(caplog):
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and "NOUGEN_VECTOR_CACHE" in r.getMessage()]


def test_vector_lane_off_warns_exactly_once_per_process(monkeypatch, caplog,
                                                        vector_lane_unwarned):
    monkeypatch.setenv("NOUGEN_VECTOR_CACHE", "0")
    caplog.set_level(logging.WARNING, logger="nougen_shards.core")

    query = [0.1, 0.2, 0.3]
    for _ in range(5):
        assert shards._vector_retrieve(query, limit=5) == [], \
            "with no uncached scan path the lane can only return nothing"

    warnings = _lane_off_warnings(caplog)
    assert len(warnings) == 1, (
        "the operator must be told once that semantic recall is OFF -- once "
        f"per process, not per query or per DB; got {len(warnings)}")
    assert "OFF" in warnings[0].getMessage()


def test_vector_lane_on_does_not_warn(monkeypatch, caplog, vector_lane_unwarned):
    """The warning is about the switch, not about an empty vault."""
    monkeypatch.setenv("NOUGEN_VECTOR_CACHE", "1")
    caplog.set_level(logging.WARNING, logger="nougen_shards.core")

    shards._vector_retrieve([0.1, 0.2, 0.3], limit=5)

    assert _lane_off_warnings(caplog) == []
