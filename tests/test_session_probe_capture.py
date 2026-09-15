"""capture_session_shard verifies by row id and never reads a CaptureResult as a bool.

A CaptureResult is a dict, so any non-empty one is truthy: before this, a
failed or duplicate write counted as success. Verifying by recall also loaded
the whole grid's vector caches and OOMed on a low-RAM node. These tests fake
core so no real vault is touched.
"""
from nougen_shards import core, session_probe


def _fake(monkeypatch, result, row):
    monkeypatch.setattr(core, "capture", lambda *a, **k: core.CaptureResult(**result))
    monkeypatch.setattr(core, "get_shard_by_id", lambda sid, db: row)

    def no_recall(*a, **k):
        raise AssertionError("recall must not run when an id came back")

    monkeypatch.setattr(core, "retrieve", no_recall)


def test_fresh_write_verified_by_row_id(monkeypatch):
    _fake(monkeypatch, {"captured": True, "reason": "written", "shard_id": 7, "db_index": 3},
          {"id": 7, "title": "Bye probe X"})
    ok, msg = session_probe.capture_session_shard("Bye probe X", "body", ["t"])
    assert ok and msg.startswith("7@db3") and "row id" in msg


def test_durable_duplicate_counts_when_its_row_exists(monkeypatch):
    _fake(monkeypatch, {"captured": False, "reason": "duplicate", "durable": True,
                        "existing_shard_id": 9, "existing_db_index": 2},
          {"id": 9, "title": "an older title for the same content"})
    ok, msg = session_probe.capture_session_shard("Bye probe Y", "body", ["t"])
    assert ok and msg.startswith("9@db2")


def test_failed_write_is_not_success_even_though_the_dict_is_truthy(monkeypatch):
    _fake(monkeypatch, {"captured": False, "reason": "error", "error": "every grid DB is quarantined"}, None)
    ok, msg = session_probe.capture_session_shard("Bye probe Z", "body", ["t"])
    assert not ok and "did not write" in msg


def test_fresh_write_with_wrong_title_fails(monkeypatch):
    _fake(monkeypatch, {"captured": True, "reason": "written", "shard_id": 5, "db_index": 1},
          {"id": 5, "title": "something else"})
    ok, msg = session_probe.capture_session_shard("Bye probe W", "body", ["t"])
    assert not ok and "title differs" in msg
