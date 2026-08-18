"""Shard publication must redact credentials and keep private rows local by default."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sqlite3

import numpy as np


SPEC = spec_from_file_location(
    "relay_push", Path(__file__).parents[1] / "tools" / "relay_push.py")
relay_push = module_from_spec(SPEC)
SPEC.loader.exec_module(relay_push)


def test_prepare_for_relay_redacts_and_drops_stale_embedding():
    secret = "sk-proj-" + "A" * 32
    rows = [{
        "title": f"credential {secret}",
        "content": f"token={secret}",
        "tags": f'["{secret}"]',
        "embedding": [0.1, 0.2],
        "file_hash": "old",
        "sensitivity": "normal",
    }]

    prepared, private_skipped, redacted = relay_push.prepare_for_relay(rows)

    assert private_skipped == 0
    assert redacted == 1
    assert secret not in repr(prepared)
    assert prepared[0]["embedding"] is None
    assert prepared[0]["file_hash"] is None


def test_prepare_for_relay_skips_private_by_default():
    rows = [{"title": "p", "content": "body", "sensitivity": "private"}]
    prepared, private_skipped, redacted = relay_push.prepare_for_relay(rows)
    assert prepared == []
    assert private_skipped == 1
    assert redacted == 0


def test_remote_known_filter_uses_post_redaction_content_hash():
    secret = "sk-proj-" + "A" * 32
    rows = [{
        "title": "legacy credential",
        "content": f"token={secret}",
        "file_hash": "legacy-pre-redaction-hash",
        "sensitivity": "normal",
    }]
    prepared, _, redacted = relay_push.prepare_for_relay(rows)
    safe_hash = relay_push.relay_content_hash(prepared[0]["content"])

    filtered, safe_known = relay_push.filter_remote_known(prepared, {safe_hash})

    assert redacted == 1
    assert filtered == []
    assert safe_known == 1


def test_relay_content_hash_matches_capture_recall_packet_rule():
    base = "durable body"
    packet = base + "\n=== NOUGENSHARDS RECALL PACKET\ntransient context"
    assert relay_push.relay_content_hash(packet) == relay_push.relay_content_hash(base)


def test_decode_embedding_accepts_float32_blob():
    blob = np.asarray([0.25, -0.5, 1.0], dtype=np.float32).tobytes()
    assert relay_push._decode_embedding(blob) == [0.25, -0.5, 1.0]


def test_missing_plan_reads_full_rows_only_for_absent_hashes(tmp_path):
    conn = sqlite3.connect(tmp_path / "nougen_shards_1.db")
    try:
        conn.execute("CREATE TABLE shards(id INTEGER PRIMARY KEY, title TEXT, content TEXT, "
                     "file_hash TEXT, embedding BLOB)")
        conn.executemany("INSERT INTO shards VALUES(?,?,?,?,?)", [
            (1, "known", "a", "h1", np.asarray([1.0], dtype=np.float32).tobytes()),
            (2, "missing", "b", "h2", np.asarray([2.0], dtype=np.float32).tobytes()),
        ])
        conn.commit()
    finally:
        conn.close()

    plan = relay_push.plan_missing_shards(tmp_path, {"h1"})
    rows = list(relay_push.iter_planned_shards(plan))

    assert [(path.name, ids) for path, ids in plan] == [("nougen_shards_1.db", [2])]
    assert [row["file_hash"] for row in rows] == ["h2"]
    assert rows[0]["embedding"] == [2.0]
