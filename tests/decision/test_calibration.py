"""Known-answer tests: every expected number is computable by hand."""
import json

import pytest

from nougen_shards.decision import calibration as cal
from nougen_shards.decision.calibration import EvalRecord as R

L = ["act", "info"]


def rec(truth, pred, conf=0.9, **kw):  # conf=None means uncalibrated
    return R(truth=truth, predicted=pred, confidence=conf, **kw)


def test_confusion_and_per_class_scores_by_hand():
    rs = [rec("act", "act"), rec("act", "info"), rec("info", "info"), rec("info", "info"), rec("info", "act")]
    rep = cal.evaluate(rs, L)
    assert rep.confusion == {"act": {"act": 1, "info": 1, "ABSTAIN": 0},
                             "info": {"act": 1, "info": 2, "ABSTAIN": 0}}
    assert rep.accuracy == pytest.approx(3 / 5)
    assert rep.precision["act"] == pytest.approx(1 / 2) and rep.recall["act"] == pytest.approx(1 / 2)
    assert rep.recall["info"] == pytest.approx(2 / 3) and rep.precision["info"] == pytest.approx(2 / 3)
    assert rep.f1["act"] == pytest.approx(0.5)


def test_empty_input_is_none_never_a_perfect_score():
    rep = cal.evaluate([], L)
    assert rep.n == 0 and rep.accuracy is None and rep.brier_score is None
    assert rep.expected_calibration_error is None and rep.p95_latency_ms is None
    assert rep.cost_per_1000 is None and rep.stability_rate is None


def test_absent_class_gives_none_not_zero():
    rep = cal.evaluate([rec("act", "act")], L)
    assert rep.recall["info"] is None and rep.precision["info"] is None and rep.f1["info"] is None


def test_abstain_counts_as_miss_and_is_reported():
    rs = [rec("act", None, conf=0.0), rec("act", "act")]
    rep = cal.evaluate(rs, L)
    assert rep.abstain_rate == 0.5 and rep.confusion["act"]["ABSTAIN"] == 1
    assert rep.recall["act"] == pytest.approx(0.5)


def test_brier_known_value_and_none_without_probabilities():
    rs = [rec("act", "act", probabilities={"act": 0.8, "info": 0.2}),
          rec("info", "act", probabilities={"act": 0.6, "info": 0.4})]
    # row1: (0.8-1)^2+(0.2-0)^2 = 0.08 ; row2: (0.6-0)^2+(0.4-1)^2 = 0.72 ; mean 0.4
    assert cal.brier(rs, L) == pytest.approx(0.4)
    assert cal.brier([rec("act", "act")], L) is None


def test_ece_perfectly_calibrated_and_overconfident():
    calibrated = [rec("act", "act", conf=1.0)] * 4
    assert cal.expected_calibration_error(calibrated) == pytest.approx(0.0)
    over = [rec("act", "act", conf=0.95), rec("act", "info", conf=0.95)]
    assert cal.expected_calibration_error(over) == pytest.approx(abs(0.5 - 0.95))


def test_weighted_miss_cost_uses_the_matrix():
    cost = {("act", "info"): 10.0, ("info", "act"): 1.0}
    rs = [rec("act", "info"), rec("info", "act"), rec("act", "act")]
    assert cal.weighted_miss_cost(rs, cost) == pytest.approx(11.0)
    assert cal.weighted_miss_cost([rec("act", None)], cost, abstain_cost=3.0) == 3.0


def test_percentile_nearest_rank_and_cost_per_1000():
    rs = [rec("act", "act", latency_ms=float(i), cost_usd=0.001) for i in range(1, 11)]
    rep = cal.evaluate(rs, L)
    assert rep.p50_latency_ms == 5.0 and rep.p95_latency_ms == 10.0
    assert rep.cost_per_1000 == pytest.approx(1.0)


def test_stability_only_counts_records_that_were_rerun():
    rs = [rec("act", "act", repeat_predictions=("act", "act")),
          rec("act", "act", repeat_predictions=("act", "info")),
          rec("act", "act")]
    assert cal.evaluate(rs, L).stability_rate == pytest.approx(0.5)


def test_unknown_label_is_rejected_not_silently_counted():
    with pytest.raises(ValueError):
        cal.evaluate([rec("bogus", "act")], L)
    with pytest.raises(ValueError):
        cal.evaluate([rec("act", "bogus")], L)


def test_threshold_sweep_picks_by_cost():
    cost = {("act", "info"): 10.0}
    rs = [rec("act", "act", conf=0.95), rec("act", "info", conf=0.6), rec("act", "act", conf=0.9)]
    sweep = {row["threshold"]: row for row in cal.threshold_sweep(rs, cost, [0.5, 0.8], escalation_cost=1.0)}
    assert sweep[0.5]["total_cost"] == pytest.approx(10.0)   # accepts the wrong 0.6 answer
    assert sweep[0.8]["total_cost"] == pytest.approx(1.0)    # escalates it instead
    assert sweep[0.8]["accepted"] == 2 and sweep[0.8]["escalated"] == 1


def test_promotion_gate_lists_failures_and_never_auto_passes():
    good = cal.evaluate([rec("act", "act", conf=1.0)] * 300, L, cost={})
    base = cal.evaluate([rec("act", "act", conf=1.0)] * 300, L, cost={})
    fails = cal.promotion_gate(good, base)
    assert any("fallback" in f for f in fails) and any("replay" in f for f in fails)
    assert cal.promotion_gate(good, base, fallback_tested=True, replay_stable=True) == []
    tiny = cal.evaluate([rec("act", "act")], L, cost={})
    assert any("too few" in f for f in cal.promotion_gate(tiny, base, fallback_tested=True, replay_stable=True))


def test_promotion_gate_blocks_a_cost_regression():
    rs_bad = [rec("act", "info")] * 300
    rs_ok = [rec("act", "act")] * 300
    cost = {("act", "info"): 5.0}
    worse = cal.evaluate(rs_bad, L, cost=cost)
    base = cal.evaluate(rs_ok, L, cost=cost)
    assert any("regressed" in f for f in cal.promotion_gate(worse, base, fallback_tested=True, replay_stable=True))


def test_tool_reads_jsonl_and_reports(tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "eval_tool", Path(__file__).resolve().parents[2] / "tools" / "eval_decision_plane.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = tmp_path / "c.jsonl"
    p.write_text("\n".join(json.dumps({"truth": "act", "predicted": "act", "confidence": 1.0}) for _ in range(3)))
    assert mod.main([str(p), "--labels", "act,info"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["n"] == 3 and out["report"]["accuracy"] == 1.0


def test_uncalibrated_is_excluded_from_ece_and_reported_not_scored_as_low():
    rs = [rec("act", "act", conf=None), rec("act", "act", conf=None), rec("act", "act", conf=1.0)]
    rep = cal.evaluate(rs, L)
    assert rep.uncalibrated_rate == pytest.approx(2 / 3)
    assert rep.expected_calibration_error == pytest.approx(0.0)   # only the calibrated row counts
    assert cal.evaluate([rec("act", "act", conf=None)], L).expected_calibration_error is None


def test_sweep_skips_uncalibrated_instead_of_escalating_them():
    cost = {("act", "info"): 10.0}
    rs = [rec("act", "act", conf=None), rec("act", "act", conf=0.95)]
    row = cal.threshold_sweep(rs, cost, [0.9], escalation_cost=1.0)[0]
    assert row["skipped_uncalibrated"] == 1 and row["accepted"] == 1 and row["escalated"] == 0


def test_gate_fails_when_confidence_is_not_calibrated():
    rs = [rec("act", "act", conf=None)] * 300
    rep = cal.evaluate(rs, L, cost={})
    assert any("not measurable" in f for f in cal.promotion_gate(rep, rep, fallback_tested=True, replay_stable=True))


class _V:
    def __init__(self, key, value, confidence, probabilities=None):
        self.key, self.value, self.confidence, self.probabilities = key, value, confidence, probabilities or {}


class _Esc:
    def __init__(self, value):
        self.value = value


class _Rcpt:
    def __init__(self, values, esc="accept", latency_ms=5.0, cost=0.002):
        self.values, self.escalation = values, _Esc(esc)
        self.latency_ms, self.estimated_cost_usd = latency_ms, cost


def test_record_from_receipt_zero_confidence_without_probs_is_uncalibrated():
    r = cal.record_from_receipt(_Rcpt([_V("class", "act", 0.0)]), "act", "class")
    assert r.predicted == "act" and r.confidence is None and r.latency_ms == 5.0 and r.cost_usd == 0.002


def test_record_from_receipt_keeps_real_low_confidence_and_probs():
    r = cal.record_from_receipt(_Rcpt([_V("class", "act", 0.0, {"act": 0.5, "info": 0.5})]), "info", "class")
    assert r.confidence == 0.0 and r.probabilities == {"act": 0.5, "info": 0.5}


def test_record_from_receipt_abstain_and_missing_value_are_abstentions():
    assert cal.record_from_receipt(_Rcpt([_V("class", "act", 0.9)], esc="abstain"), "act", "class").predicted is None
    assert cal.record_from_receipt(_Rcpt([]), "act", "class").predicted is None
    assert cal.record_from_receipt(_Rcpt([_V("class", "act", 0.9)], esc="human"), "act", "class").escalated is True
