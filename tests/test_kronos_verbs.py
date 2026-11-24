"""Direct tests for kronos_temporal_engine and verbs registry."""
import math
import os
import time

import pytest

from nougen_shards import kronos_temporal_engine as kte
from nougen_shards import verbs


@pytest.fixture
def shard_file(tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("x")
    return p


def test_shard_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        kte.TemporalNexusShard(str(tmp_path / "nope.txt"))


def test_shard_physical_substrate(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    assert set(s.physical_dimensions) == {"btime", "mtime", "ctime", "atime"}
    assert s.bitemporal_dimensions["valid_time_start"] == s.physical_dimensions["mtime"]
    assert s.bitemporal_dimensions["transaction_time"] == s.system_ingestion_time


def test_parse_anchors_full_strings_and_year(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    s.parse_payload_anchors("see arXiv:2401.01234 dated 2024-03-15")
    anchors = s.semantic_dimensions["extracted_anchors"]
    assert "arXiv:2401.01234" in anchors
    assert "2024-03-15" in anchors
    assert all(isinstance(a, str) for a in anchors)
    from datetime import datetime
    assert s.bitemporal_dimensions["valid_time_start"] == datetime(2024, 1, 1).timestamp()


def test_parse_no_year_keeps_mtime(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    before = s.bitemporal_dimensions["valid_time_start"]
    s.parse_payload_anchors("nothing dated here")
    assert s.semantic_dimensions["extracted_anchors"] == []
    assert s.bitemporal_dimensions["valid_time_start"] == before


def test_register_access_event(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    s.register_access_event()
    s.register_access_event()
    assert s.logical_clock == 2
    assert len(s.access_history) == 2


def test_utility_half_life(shard_file):
    s = kte.TemporalNexusShard(str(shard_file), base_utility=2.0)
    eng = kte.KronosEngine(half_life_days=1.0)
    s.physical_dimensions["mtime"] = time.time() - 86400
    assert eng.calculate_cognitive_utility(s) == pytest.approx(1.0, abs=1e-3)
    s.physical_dimensions["mtime"] = time.time()
    assert eng.calculate_cognitive_utility(s) == pytest.approx(2.0, abs=1e-3)


def test_momentum_empty_and_recent(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    eng = kte.KronosEngine()
    assert eng.calculate_temporal_momentum(s) == 0.0
    s.register_access_event()
    s.register_access_event()
    assert eng.calculate_temporal_momentum(s) == pytest.approx(2.0, abs=1e-2)


def test_alignment_identical_is_one(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    s.bitemporal_dimensions["valid_time_start"] = s.bitemporal_dimensions["transaction_time"]
    assert kte.KronosEngine().calculate_alignment_coefficient(s) == 1.0


def test_alignment_decreases_with_gap(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    eng = kte.KronosEngine()
    t = s.bitemporal_dimensions["transaction_time"]
    s.bitemporal_dimensions["valid_time_start"] = t - 1000
    near = eng.calculate_alignment_coefficient(s)
    s.bitemporal_dimensions["valid_time_start"] = t - 10**9
    far = eng.calculate_alignment_coefficient(s)
    assert 0 < far < near < 1
    assert near == pytest.approx(round(1 / (1 + math.log(1001)), 6), abs=1e-5)


def test_synthesize_profile(shard_file):
    s = kte.TemporalNexusShard(str(shard_file))
    s.register_access_event()
    prof = kte.KronosEngine().synthesize_temporal_profile(s)
    assert prof["file"] == os.path.basename(str(shard_file))
    assert prof["logical_sequence_id"] == 1
    assert set(prof["metrics"]) == {"cognitive_utility", "temporal_momentum", "bitemporal_alignment"}


def test_verbs_registry_consistent():
    assert len(verbs.VERBS) == 11
    assert len(verbs.PLANES) == 6
    for name, v in verbs.VERBS.items():
        assert v["plane"] in verbs.PLANES
        assert name in verbs.PLANES[v["plane"]]["verbs"]
        for nxt in v["next_verbs"]:
            assert nxt in verbs.VERBS
    listed = [n for p in verbs.PLANES.values() for n in p["verbs"]]
    assert sorted(listed) == sorted(verbs.VERBS)


def test_get_verb_info_normalizes():
    info = verbs.get_verb_info("  Relay ")
    assert info["verb"] == "relay"
    assert info["plane"] == "coordination"


def test_get_verb_info_unknown_and_none():
    assert "error" in verbs.get_verb_info("bogus")
    assert "error" in verbs.get_verb_info(None)


def test_get_all_verbs_shape():
    out = verbs.get_all_verbs()
    assert out["verbs"] is verbs.VERBS
    assert out["planes"] is verbs.PLANES
    assert out["non_collapse_rules"]
