"""Regression tests for recall-packet body truncation (RECALL_SNIPPET_CHARS).

Graduation gate for the migration-pipeline war-game: a feature cannot move to
the public app without tests. Guards against megabyte CODE_SHARD bodies
(e.g. a raw encoder.json vocab) flooding a recall packet.
"""
from nougen_shards.core import RECALL_SNIPPET_CHARS, compile_recall_packet


def _shard(content, shard_id=1, db_index=2):
    return {
        "id": shard_id,
        "_db_index": db_index,
        "final_score": 0.5,
        "timestamp": None,
        "title": "test shard",
        "content": content,
    }


def test_oversized_body_is_truncated_with_evidence_handle():
    huge = "x" * (RECALL_SNIPPET_CHARS + 5000)
    packet = compile_recall_packet([_shard(huge, shard_id=42, db_index=3)])
    # Body capped: packet stays same order of magnitude as the snippet limit.
    assert len(packet) < RECALL_SNIPPET_CHARS + 500
    # Evidence-preserving marker points at the exact shard handle.
    assert "truncated" in packet
    assert "shard_get(shard_id=42, db_index=3)" in packet


def test_small_body_passes_through_untouched():
    packet = compile_recall_packet([_shard("hello vault")])
    assert "hello vault" in packet
    assert "truncated" not in packet


def test_none_content_does_not_crash():
    packet = compile_recall_packet([_shard(None)])
    assert "RECALL PACKET" in packet
