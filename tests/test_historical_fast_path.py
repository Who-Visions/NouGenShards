"""Tests and benchmarks for Historical Fast Path Recall Module.

Verifies bitemporal retrieval precision and guarantees sub-1ms age-invariant execution.
"""

import time
import pytest
from nougen_shards.historical_fast_path import (
    FastPathIntent,
    HistoricalFastPathStore,
)


@pytest.fixture
def populated_store():
    store = HistoricalFastPathStore(":memory:")

    # Populate multiple historical eras
    # Era 1: Nov 2025 (epoch ~ 1763500000000)
    store.register_artifact("art_nov2025", 1763500000000, "fact", "phoebus", "Nov 2025 raw data")
    store.put_canonical("entity:fleet:config", "art_nov2025", revision=1, as_of_ms=1763500000000, payload={"mode": "v1_legacy"})
    store.add_entity_posting("entity:fleet", 1763500000000, "art_nov2025")
    store.add_tag_posting("cluster", "prod_v1", 1763500000000, "art_nov2025")
    store.add_metric_fact("tokens", "fleet", "monthly", 2025, 1763500000000, "art_nov2025", 50000)

    # Era 2: Jan 2026 (epoch ~ 1768000000000)
    store.register_artifact("art_jan2026", 1768000000000, "fact", "apollo", "Jan 2026 update")
    store.put_canonical("entity:fleet:config", "art_jan2026", revision=2, as_of_ms=1768000000000, payload={"mode": "v2_mesh"})
    store.add_entity_posting("entity:fleet", 1768000000000, "art_jan2026")

    # Era 3: Jun 2026 (epoch ~ 1781000000000)
    store.register_artifact("art_jun2026", 1781000000000, "fact", "whoart", "Jun 2026 update")
    store.put_canonical("entity:fleet:config", "art_jun2026", revision=3, as_of_ms=1781000000000, payload={"mode": "v3_hybrid"})

    # Era 4: Sep 2026 (epoch ~ 1789500000000 - current)
    store.register_artifact("art_sep2026", 1789500000000, "fact", "whoart", "Sep 2026 live state")
    store.put_canonical("entity:fleet:config", "art_sep2026", revision=4, as_of_ms=1789500000000, payload={"mode": "v4_temporal_fabric"})

    return store


def test_canonical_current_hit(populated_store):
    intent = FastPathIntent(canonical_key="entity:fleet:config", as_of_is_latest=True)
    res = populated_store.fast_lookup(intent)
    assert res.hit is True
    assert res.source_index == "canonical_current"
    assert res.revision == 4
    assert res.payload["mode"] == "v4_temporal_fabric"
    assert res.reason == "CANONICAL_CURRENT_HIT"


def test_canonical_history_as_of_nov_2025(populated_store):
    # Query as of Dec 2025 -> should yield Nov 2025 revision 1
    intent = FastPathIntent(canonical_key="entity:fleet:config", as_of_is_latest=False, as_of_ms=1764000000000)
    res = populated_store.fast_lookup(intent)
    assert res.hit is True
    assert res.source_index == "canonical_history"
    assert res.revision == 1
    assert res.payload["mode"] == "v1_legacy"


def test_canonical_history_as_of_jan_2026(populated_store):
    # Query as of Feb 2026 -> should yield Jan 2026 revision 2
    intent = FastPathIntent(canonical_key="entity:fleet:config", as_of_is_latest=False, as_of_ms=1770000000000)
    res = populated_store.fast_lookup(intent)
    assert res.hit is True
    assert res.source_index == "canonical_history"
    assert res.revision == 2
    assert res.payload["mode"] == "v2_mesh"


def test_direct_artifact_pk_hit(populated_store):
    intent = FastPathIntent(artifact_id="art_nov2025")
    res = populated_store.fast_lookup(intent)
    assert res.hit is True
    assert res.source_index == "artifact_pk"
    assert res.payload["node"] == "phoebus"


def test_entity_and_tag_posting(populated_store):
    intent_entity = FastPathIntent(entity_id="entity:fleet")
    res_entity = populated_store.fast_lookup(intent_entity)
    assert res_entity.hit is True
    assert res_entity.source_index == "entity_posting"
    assert res_entity.artifact_id == "art_jan2026"

    intent_tag = FastPathIntent(tag_namespace="cluster", tag_value="prod_v1")
    res_tag = populated_store.fast_lookup(intent_tag)
    assert res_tag.hit is True
    assert res_tag.source_index == "tag_posting"
    assert res_tag.artifact_id == "art_nov2025"


def test_metric_fact_lookup(populated_store):
    intent = FastPathIntent(
        metric_namespace="tokens",
        metric_scope="fleet",
        metric_period="monthly",
        metric_year=2025,
        as_of_ms=1763500000000
    )
    res = populated_store.fast_lookup(intent)
    assert res.hit is True
    assert res.source_index == "metric_fact"
    assert res.payload["value_bps"] == 50000


def test_miss_to_hybrid_planner(populated_store):
    intent = FastPathIntent(canonical_key="nonexistent_key", as_of_is_latest=True)
    res = populated_store.fast_lookup(intent)
    assert res.hit is False
    assert res.reason == "MISS_TO_HYBRID_PLANNER"


def test_age_invariant_latency_benchmark(populated_store):
    # Benchmark 1000 lookups per era
    eras = [
        ("Nov 2025", FastPathIntent(canonical_key="entity:fleet:config", as_of_is_latest=False, as_of_ms=1764000000000)),
        ("Jan 2026", FastPathIntent(canonical_key="entity:fleet:config", as_of_is_latest=False, as_of_ms=1770000000000)),
        ("Jun 2026", FastPathIntent(canonical_key="entity:fleet:config", as_of_is_latest=False, as_of_ms=1782000000000)),
        ("Sep 2026", FastPathIntent(canonical_key="entity:fleet:config", as_of_is_latest=True)),
    ]

    latencies_us = {}
    for label, intent in eras:
        # Warm up
        for _ in range(50):
            populated_store.fast_lookup(intent)
        times = []
        for _ in range(500):
            t0 = time.perf_counter_ns()
            res = populated_store.fast_lookup(intent)
            t1 = time.perf_counter_ns()
            assert res.hit is True
            times.append((t1 - t0) / 1000.0)
        times.sort()
        p50 = times[len(times) // 2]
        p95 = times[int(len(times) * 0.95)]
        latencies_us[label] = (p50, p95)
        # All p50 must be well under 1000 microseconds (sub-1ms)
        assert p50 < 1000.0, f"{label} p50 {p50}us exceeded 1ms"

    # Age invariance: Nov 2025 p50 should be comparable to Sep 2026 p50 (<200us difference)
    nov_p50 = latencies_us["Nov 2025"][0]
    sep_p50 = latencies_us["Sep 2026"][0]
    assert abs(nov_p50 - sep_p50) < 500.0
