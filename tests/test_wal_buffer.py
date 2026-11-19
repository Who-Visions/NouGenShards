
from nougen_shards.wal_buffer import WriteAheadBuffer, content_sha256, normalize


def _buf(tmp_path, mirror=True):
    return WriteAheadBuffer(str(tmp_path / "pending.db"),
                            mirror_path=str(tmp_path / "wal.jsonl") if mirror else None)


def test_normalize_is_nfc_lf_and_trimmed():
    assert normalize("  a\r\nb\r  ") == "a\nb"
    assert content_sha256("a\r\nb") == content_sha256("a\nb")


def test_capture_is_durable_and_idempotent(tmp_path):
    b = _buf(tmp_path)
    first = b.capture({"title": "t", "content": "hello"})
    second = b.capture({"title": "t2", "content": "hello\r\n"})
    assert first["stored"] and not first["duplicate"]
    assert second["duplicate"] is True
    assert first["content_sha256"] == second["content_sha256"]
    lines = (tmp_path / "wal.jsonl").read_text().splitlines()
    assert len(lines) == 1  # mirror written once, not per duplicate
    b.close()


def test_capture_survives_reopen(tmp_path):
    b = _buf(tmp_path)
    b.capture({"title": "t", "content": "durable"})
    b.close()
    b2 = _buf(tmp_path)
    assert len(b2.pending_for("blade")) == 1
    b2.close()


def test_empty_content_rejected(tmp_path):
    b = _buf(tmp_path)
    try:
        b.capture({"title": "t", "content": "   "})
    except ValueError:
        pass
    else:
        raise AssertionError("empty content must be rejected")
    b.close()


def test_pull_then_ack_drains_per_node(tmp_path):
    b = _buf(tmp_path)
    b.capture({"title": "a", "content": "one", "event_time": "2026-10-15T00:00:00Z"})
    b.capture({"title": "b", "content": "two"})
    assert len(b.pending_for("blade")) == 2
    got = b.pending_for("blade", limit=1)
    assert len(got) == 1 and got[0]["title"] == "a"  # oldest first
    b.ack("blade", [got[0]["content_sha256"]])
    assert [r["title"] for r in b.pending_for("blade")] == ["b"]
    # other nodes still see both
    assert len(b.pending_for("phoebus")) == 2
    b.close()


def test_event_time_is_preserved(tmp_path):
    b = _buf(tmp_path)
    b.capture({"title": "a", "content": "x", "event_time": "2026-10-15T01:02:03Z"})
    assert b.pending_for("blade")[0]["event_time"] == "2026-10-15T01:02:03Z"
    b.close()


def test_fanout_acks_only_successful_nodes(tmp_path):
    b = _buf(tmp_path)
    sent = []

    def ok(rec):
        sent.append(rec["content_sha256"])
        return True

    def down(rec):
        return False

    def boom(rec):
        raise OSError("node unreachable")

    flags = b.fanout({"title": "a", "content": "fan"},
                     {"blade": ok, "phoebus": down, "whoart": boom})
    assert flags == {"blade": True, "phoebus": False, "whoart": False}
    assert len(sent) == 1
    # blade acked; phoebus and whoart still owe the shard
    assert b.pending_for("blade") == []
    assert len(b.pending_for("phoebus")) == 1
    assert len(b.pending_for("whoart")) == 1
    b.close()


def test_blade_outage_then_catchup(tmp_path):
    """Acceptance: capture succeeds while blade is down; blade drains on recovery."""
    b = _buf(tmp_path)
    b.fanout({"title": "during-outage", "content": "held"}, {"blade": lambda r: False})
    assert len(b.pending_for("blade")) == 1
    # blade recovers and pulls
    backlog = b.pending_for("blade")
    b.ack("blade", [r["content_sha256"] for r in backlog])
    assert b.pending_for("blade") == []
    b.close()
