"""tools/recall_eval.py: the metric and query-building math must be exact,
because every future retrieval change is judged by it."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import recall_eval as ev  # noqa: E402


def test_score_query_ranks_first_relevant_hit():
    s = ev.score_query(["9@1", "4@2", "7@3"], ["7@3", "8@5"], k=10)
    assert s["rank"] == 3
    assert (s["recall@1"], s["recall@3"], s["recall@5"]) == (0.0, 1.0, 1.0)
    assert math.isclose(s["mrr"], 1 / 3)
    assert math.isclose(s["ndcg@10"], 1 / math.log2(4))


def test_score_query_miss_and_cutoff():
    assert ev.score_query([], ["1@1"], k=10)["mrr"] == 0.0
    s = ev.score_query(["a", "b", "c", "hit"], ["hit"], k=3)
    assert s["rank"] is None and "recall@5" not in s


def test_aggregate_means_and_ignores_rank():
    rows = [ev.score_query(["x"], ["x"], 10), ev.score_query(["y"], ["x"], 10)]
    agg = ev.aggregate(rows)
    assert agg["n"] == 2 and agg["recall@1"] == 0.5 and "rank" not in agg


def test_sweep_picks_highest_recall_under_fp_target():
    pos = [0.9, 0.8, 0.5, None]
    neg = [0.6, 0.3, 0.2, 0.1]
    best = ev.sweep(pos, neg, fp_target=0.25)["best"]
    # t must exceed 0.3 to keep fp <= 0.25; the lowest such cut is 0.5 -> recall 3/4.
    assert best["threshold"] == 0.5 and best["recall"] == 0.75 and best["fp_rate"] == 0.25


def test_sweep_reports_none_when_target_unreachable():
    assert ev.sweep([None], [1.0], fp_target=-1)["best"] is None


def test_body_query_excludes_title_and_stopwords_deterministically():
    content = ("Retention policy governs which ledger entries survive compaction because "
               "archival tiers reorder checkpoints while telemetry streams replay failover")
    q = ev.body_query("Ledger compaction notes", content)
    words = q.lower().split()
    assert len(words) == 5 and "ledger" not in words and "because" not in words
    assert q == ev.body_query("Ledger compaction notes", content)


def test_body_query_rejects_thin_bodies():
    assert ev.body_query("t", "short words only here") is None


def test_negative_queries_are_seeded():
    assert ev.negative_queries(5, 7) == ev.negative_queries(5, 7)
    assert ev.negative_queries(5, 7) != ev.negative_queries(5, 8)


def test_classify_query_failure_taxonomy():
    clean = ev.classify_query_failure(
        ["1@1", "2@1"], ["1@1"], [{"domain_key": "alpha"}],
        expected_domain="alpha", k=10, latency_ms=12.0, max_latency_ms=500.0,
    )
    assert clean == []

    missed = ev.classify_query_failure(
        ["2@1"], ["1@1"], [{"domain_key": "beta"}],
        expected_domain="alpha", k=10, latency_ms=650.0, max_latency_ms=500.0,
    )
    assert missed == [ev.ERROR_MISSED_SHARD, ev.ERROR_WRONG_DOMAIN, ev.ERROR_LATENCY_BREACH]

    stale = ev.classify_query_failure(
        ["2@1", "3@1", "4@1", "1@1"], ["1@1"], [{"domain_key": "alpha"}],
        expected_domain="alpha", k=10, stale_rank_cutoff=3,
    )
    assert stale == [ev.ERROR_STALE_RANK]


def test_evaluate_gate_governance_blocks_even_with_perfect_scores():
    report = {
        "overall": {"recall@5": 1.0, "mrr": 1.0},
        "latency_ms": {"p95": 40.0},
        "negatives_total": 5,
        "negatives_nonempty": 0,
        "domain_leaks": 1,
        "taxonomy_counts": {ev.ERROR_WRONG_DOMAIN: 1},
    }
    verdict = ev.evaluate_gate(report)
    assert verdict["governance_passed"] is False
    assert verdict["quality_passed"] is True
    assert verdict["passed"] is False
    assert any("tenant_isolation" in msg for msg in verdict["failures"])


def test_evaluate_gate_quality_floor_failure():
    report = {
        "overall": {"recall@5": 0.9, "mrr": 0.4},
        "latency_ms": {"p95": 40.0},
        "negatives_total": 5,
        "negatives_nonempty": 0,
        "domain_leaks": 0,
    }
    verdict = ev.evaluate_gate(report, min_mrr=0.70)
    assert verdict["governance_passed"] is True
    assert verdict["quality_passed"] is False
    assert verdict["passed"] is False
    assert any("mrr" in msg for msg in verdict["failures"])


def test_evaluate_gate_passes_when_all_thresholds_met():
    report = {
        "overall": {"recall@5": 0.95, "mrr": 0.88},
        "latency_ms": {"p95": 120.0},
        "negatives_total": 6,
        "negatives_nonempty": 0,
        "domain_leaks": 0,
        "taxonomy_counts": {},
    }
    verdict = ev.evaluate_gate(report)
    assert verdict["passed"] is True
    assert verdict["governance_passed"] is True
    assert verdict["quality_passed"] is True
    assert verdict["failures"] == []
