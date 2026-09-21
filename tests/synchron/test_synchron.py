import json

from nougen_shards.synchron import Config, detect, score_pair, verify
from nougen_shards.synchron.model import BaseRates, Snapshot
from nougen_shards.synchron.score import bridge, classify

from .fixtures import (ANGKOR, ANGKOR_SEARCHED, BMFM_ANNIV, BMFM_BACKFILLED, MOTO, SOLAR,
                       AS_OF, snap)

CFG = Config()


def test_case_b_independent_angkor_convergence_scores_and_passes_gates():
    r = score_pair(SOLAR, ANGKOR, snap(SOLAR, ANGKOR), CFG)
    assert r["rejected"] is None
    assert r["features"]["independence"] >= 0.6 and r["features"]["calendar"] == 1.0
    assert r["classification"] != "ignore", r


def test_case_b_direct_search_lineage_is_rejected():
    r = score_pair(SOLAR, ANGKOR_SEARCHED, snap(SOLAR, ANGKOR_SEARCHED), CFG)
    assert r["rejected"] == "likely self-induced" and r["score"] == 0.0


def test_case_a_anniversary_convergence_detected():
    [rec] = detect(snap(MOTO, BMFM_ANNIV))
    assert "biker mice from mars anniversary" in rec["temporal_evidence"]["windows"]
    assert rec["classification"] != "ignore", rec


def test_case_a_backfilled_evidence_is_penalised():
    clean = score_pair(MOTO, BMFM_ANNIV, snap(MOTO, BMFM_ANNIV), CFG)["score"]
    back = score_pair(MOTO, BMFM_BACKFILLED, snap(MOTO, BMFM_BACKFILLED), CFG)
    pen = {p["check"]: p["penalty"] for p in back["penalties"]}
    assert pen["dates_chosen_after_the_fact"] > 0 and back["score"] < clean


def test_unknown_base_rates_score_as_common_and_the_gap_is_named():
    # review repro 1: empty BaseRates used to zero the score with no reason
    s = Snapshot(AS_OF, (SOLAR, ANGKOR), (), BaseRates())
    r = score_pair(SOLAR, ANGKOR, s, CFG)
    assert r["features"]["rarity"] == 0.0 and r["score"] > 0.0
    [rec] = detect(s)
    assert rec["evidence_gaps"] == ["base_rates_unknown"]
    assert rec["base_rate"]["known"] is False


def test_malformed_canonical_date_does_not_kill_detect():
    # review repro 2
    bad = ANGKOR.__class__(**{**ANGKOR.__dict__, "canonical_date": "sept 22nd"})
    [rec] = detect(snap(SOLAR, bad))
    assert "malformed_canonical_date:angkor-equinox" in rec["evidence_gaps"]


def test_year_boundary_window_matches_across_new_year():
    # review repro 3: Dec 28 - Jan 3 never matched
    from nougen_shards.synchron import Window
    from nougen_shards.synchron.score import calendar
    from .fixtures import ms
    nye = Window("new year", "2026-12-28", "2027-01-03", "anniversary")
    for day in ("2026-12-30", "2027-01-02"):
        e = MOTO.__class__(**{**MOTO.__dict__, "canonical_date": "1999-" + day[5:]})
        s = Snapshot(ms(day + "T12:00:00"), (MOTO, e), (nye,), BaseRates())
        assert calendar(e, MOTO, s) == (1.0, ["new year"]), day


def test_same_source_is_never_a_candidate():
    twin = SOLAR.__class__(**{**SOLAR.__dict__, "event_id": "solar-2"})
    assert detect(snap(SOLAR, twin), include_rejected=True) == []


def test_determinism_same_snapshot_same_bytes():
    s = snap(SOLAR, ANGKOR, ANGKOR_SEARCHED, MOTO, BMFM_ANNIV)
    a = json.dumps(detect(s, include_rejected=True), sort_keys=True)
    b = json.dumps(detect(s, include_rejected=True), sort_keys=True)
    assert a == b


def test_receipts_are_sealed_and_tamper_evident():
    key = b"test-key-not-a-secret"
    [rec] = detect(snap(SOLAR, ANGKOR), key=key)
    assert verify(rec, key) and verify(rec)
    forged = {**rec, "score": 0.99}
    assert not verify(forged) and not verify(forged, key)
    assert not verify(rec, b"wrong-key")


def test_receipt_records_determinism_inputs_and_disconfirming_checks():
    [rec] = detect(snap(SOLAR, ANGKOR))
    d = rec["determinism"]
    assert d["corpus_revision"] == "fixture-r1" and d["weights"]["independence"] == 0.20
    assert len(rec["disconfirming_checks"]) == 5 and rec["created_at_ms"] == AS_OF


def test_bridge_is_an_inverted_u_and_classification_bands():
    assert bridge(0.62, CFG) == 1.0 and bridge(0.99, CFG) == 0.0 and bridge(0.2, CFG) == 0.0
    assert [classify(x) for x in (0.5, 0.6, 0.75, 0.9)] == [
        "ignore", "weak_convergence", "notable_serendipity", "high_value_temporal_convergence"]
