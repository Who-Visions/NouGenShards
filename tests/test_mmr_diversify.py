"""Stage-3 MMR diversification: near-duplicate shards must not crowd the top-k.

Capture-time dedup is hash-based, so re-captures of the same fix with slightly
different wording all survive and — pre-MMR — monopolized the recall packet.
"""
import numpy as np
import pytest

import nougen_shards.core as shards


def _item(title, score, vec=None):
    it = {"title": title, "content": title, "utility_score_tripartite": score}
    if vec is not None:
        arr = np.array(vec, dtype=np.float32)
        it["embedding"] = (arr / np.linalg.norm(arr)).tobytes()
    return it


def test_mmr_demotes_near_duplicates():
    # Three near-identical top items and one distinct lower-scored item: MMR
    # must pull the distinct item into a top-3 packet.
    items = [
        _item("dup A", 1.00, [1.0, 0.0, 0.01]),
        _item("dup B", 0.99, [1.0, 0.0, 0.02]),
        _item("dup C", 0.98, [1.0, 0.0, 0.03]),
        _item("distinct", 0.60, [0.0, 1.0, 0.0]),
    ]
    picked = shards.mmr_diversify(items, limit=3, lambda_=0.5)
    titles = [p["title"] for p in picked]
    assert titles[0] == "dup A", "top candidate must always survive"
    assert "distinct" in titles, "novel item should displace a near-duplicate"


def test_mmr_without_embeddings_preserves_relevance_order():
    items = [_item(f"t{i}", 1.0 - i * 0.1) for i in range(5)]
    picked = shards.mmr_diversify(items, limit=3, lambda_=0.5)
    assert [p["title"] for p in picked] == ["t0", "t1", "t2"]


def test_mmr_lambda_one_is_pure_relevance_passthrough():
    items = [
        _item("a", 1.0, [1.0, 0.0]),
        _item("a2", 0.9, [1.0, 0.001]),
        _item("b", 0.1, [0.0, 1.0]),
    ]
    picked = shards.mmr_diversify(items, limit=2, lambda_=1.0)
    assert [p["title"] for p in picked] == ["a", "a2"]


def test_mmr_handles_legacy_json_embeddings():
    items = [
        _item("bin", 1.0, [1.0, 0.0]),
        {"title": "legacy", "content": "legacy",
         "utility_score_tripartite": 0.9, "embedding": b"[0.5, 0.5]"},
        _item("other", 0.8, [0.0, 1.0]),
    ]
    picked = shards.mmr_diversify(items, limit=3, lambda_=0.5)
    assert len(picked) == 3  # no crash; legacy item competes on relevance alone


def test_mmr_limit_larger_than_pool():
    items = [_item("only", 1.0, [1.0, 0.0])]
    assert shards.mmr_diversify(items, limit=5, lambda_=0.5) == items
