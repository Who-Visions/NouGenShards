"""Regression tests for the write-response truth defects (blade, 2026-09-07).

Four connector captures that returned ``captured: false / duplicate`` had in
fact been written -- 24540@db1, 26155@db9, 27509@db4, 30203@db7. Believing the
writes lost, the caller re-wrote content by hand, so 27507@db4 duplicates
24540@db1. These tests assert the API RESPONSE against durable state, which is
the check that was missing: every previous test asserted the response alone.
"""
import json
import socket
from unittest import mock

import pytest

from nougen_shards import snapshot_mode


def _forward(answer, *, timeout_first=False, env=None):
    """Run forward_capture against a canned /sync/push answer."""
    calls = {"n": 0}

    class _Resp:
        def __init__(self, payload): self._p = json.dumps(payload).encode()
        def read(self): return self._p
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _urlopen(req, timeout=None):
        calls["n"] += 1
        if timeout_first and calls["n"] == 1:
            raise socket.timeout("timed out")
        return _Resp(answer)

    environ = {"NOUGEN_CAPTURE_FORWARD_URL": "http://writer.example"}
    environ.update(env or {})
    with mock.patch.dict("os.environ", environ, clear=False), \
         mock.patch.object(snapshot_mode.urllib.request, "urlopen", _urlopen):
        out = snapshot_mode.forward_capture({"title": "t", "content": "c"})
    return out, calls["n"]


def test_fresh_write_reports_success():
    out, _ = _forward({"count": 1, "skipped": 0,
                       "results": [{"reason": "written", "durable": True,
                                    "shard_id": 42, "db_index": 3}]})
    assert out["captured"] is True
    assert out.get("shard_id") == 42 and out.get("db_index") == 3


def test_timeout_then_dedup_is_reported_as_WRITTEN_not_duplicate():
    """THE defect: our own first attempt committed, the retry deduped against
    it, and the dedup hit was reported as the outcome -- a false negative."""
    answer = {"count": 0, "skipped": 1, "skipped_duplicate": 1,
              "skipped_malformed": 0,
              "results": [{"reason": "duplicate", "durable": True,
                           "shard_id": 24540, "db_index": 1}]}
    out, n = _forward(answer, timeout_first=True)
    assert n == 2, "must retry after a timeout rather than declare failure"
    assert out["captured"] is True, (
        "a write that committed before the timeout must NOT be reported as a "
        "duplicate -- that is what caused the hand-written duplicate pair")
    assert out["reason"] == "written"
    assert out.get("shard_id") == 24540


def test_genuine_preexisting_duplicate_still_reports_duplicate():
    """No timeout: nothing we sent was written this call, so duplicate is true."""
    answer = {"count": 0, "skipped": 1, "skipped_duplicate": 1,
              "skipped_malformed": 0,
              "results": [{"reason": "duplicate", "durable": True,
                           "shard_id": 7, "db_index": 2}]}
    out, n = _forward(answer)
    assert n == 1
    assert out["captured"] is False and out["reason"] == "duplicate"
    assert out.get("durable") is True and out.get("shard_id") == 7


def test_malformed_rejection_is_an_error_never_a_duplicate():
    answer = {"count": 0, "skipped": 1, "skipped_duplicate": 0,
              "skipped_malformed": 1,
              "results": [{"reason": "malformed", "durable": False}]}
    out, _ = _forward(answer)
    assert out["captured"] is False
    assert out["reason"] == "error", (
        "a REJECTED row was never written anywhere; calling it a duplicate "
        "tells the caller its write was a redundant no-op")


def test_capture_duplicate_names_the_row_and_asserts_durability(tmp_path, monkeypatch):
    """core.capture's dedup answer must identify the row it deduped against,
    checked against the database rather than against the return value alone."""
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    import importlib
    from nougen_shards import core as _core
    importlib.reload(_core)

    body = "durability-truth probe 2026-09-07 unique-xyz"
    first = _core.capture("KNOWLEDGE", "probe", body)
    assert first["captured"] is True and first.get("shard_id")

    second = _core.capture("KNOWLEDGE", "probe", body)
    assert second["captured"] is False and second["reason"] == "duplicate"
    assert second.get("durable") is True, "a dedup hit means the content IS on disk"
    assert second.get("shard_id") is None, "this call wrote nothing"
    assert second.get("existing_db_index") == first["db_index"]
    assert second.get("existing_shard_id") == first["shard_id"], (
        "must name the SAME row, so a caller can verify durability instead of "
        "inferring failure from a bare counter")

    # The response must agree with the database, not merely with itself.
    import sqlite3
    p = _core.get_db_path(second["existing_db_index"])
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    row = conn.execute("SELECT COUNT(*) FROM shards WHERE id=?",
                       (second["existing_shard_id"],)).fetchone()
    conn.close()
    assert row[0] == 1
