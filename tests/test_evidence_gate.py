"""PR-C evidence sufficiency gate (owner leg 20260923T034306Z).

Synthetic policies only: no product lore, no product-lore coupling.
"""
import pytest

from nougen_shards.evidence_gate import (Authority, EvidenceReceipt, EvolveGate, Metrics,
                                          PolicyCandidate, PromotionRefused, Status,
                                          evaluate, from_replay)


def receipts(n: int, delta: float = 0.2):
    return tuple(EvidenceReceipt(f"trial{i}", "latency improved", delta) for i in range(n))


def candidate(**kw):
    base = dict(policy_id="retrieval.depth", version="2", hypothesis="deeper recall helps",
                receipts=receipts(30), rollback_to="1")
    base.update(kw)
    return PolicyCandidate(**base)


# --- the rule this gate exists for ------------------------------------------------
def test_single_anecdote_never_promotes():
    v = evaluate(candidate(receipts=receipts(1, 5.0)))   # huge effect, one observation
    assert v.status is Status.OBSERVE and not v.eligible
    assert "not a trend" in v.reason


def test_a_handful_shadows_but_does_not_adopt():
    v = evaluate(candidate(receipts=receipts(8)))
    assert v.status is Status.SHADOW and "do not adopt" in v.reason


def test_enough_evidence_with_a_positive_effect_is_eligible():
    v = evaluate(candidate())
    assert v.eligible and v.sample_count == 30 and v.effect > 0


def test_volume_without_a_positive_effect_is_not_eligible():
    v = evaluate(candidate(receipts=receipts(50, -0.3)))
    assert v.status is Status.SHADOW and "does not argue for the change" in v.reason


# --- regressions block, regardless of volume ---------------------------------------
def test_regression_blocks_promotion():
    v = evaluate(candidate(metrics=(Metrics("accuracy", 0.9, 0.8),)))
    assert v.status is Status.BLOCKED and "accuracy" in v.reason


def test_regression_blocks_even_with_overwhelming_evidence():
    v = evaluate(candidate(receipts=receipts(10_000, 9.9),
                           metrics=(Metrics("cost", 10, 12, higher_is_better=False),)))
    assert v.status is Status.BLOCKED  # volume never buys an exemption


def test_direction_of_a_metric_is_respected():
    assert evaluate(candidate(metrics=(Metrics("cost", 10, 8, higher_is_better=False),))).status is not Status.BLOCKED


# --- hard invariants demand elevated authority ------------------------------------
def test_touching_an_invariant_escalates_required_authority_to_owner():
    v = evaluate(candidate(invariants_touched=("canon_ceiling",),
                           required_authority=Authority.AUTOMATIC))
    assert v.eligible and v.required_authority is Authority.OWNER


def test_lane_authority_cannot_promote_an_invariant_touching_change():
    gate, c = EvolveGate(), candidate(invariants_touched=("canon_ceiling",))
    with pytest.raises(PromotionRefused, match="requires owner authority"):
        gate.promote(c, granted_by=Authority.LANE)
    receipt = gate.promote(c, granted_by=Authority.OWNER)
    assert receipt["status"] == "PROMOTED"


def test_a_policy_cannot_authorise_its_own_exception():
    # automatic authority is silently insufficient once an invariant is touched
    v = evaluate(candidate(invariants_touched=("safety_gate",),
                           required_authority=Authority.AUTOMATIC))
    assert v.promotable_by is Authority.OWNER


# --- determinism -------------------------------------------------------------------
def test_status_is_deterministic_from_the_same_evidence_bundle():
    a, b = evaluate(candidate()), evaluate(candidate())
    assert (a.status, a.bundle_id, a.effect) == (b.status, b.bundle_id, b.effect)


def test_different_evidence_yields_a_different_bundle_id():
    assert evaluate(candidate()).bundle_id != evaluate(candidate(receipts=receipts(29))).bundle_id


# --- promotion + rollback ----------------------------------------------------------
def test_promotion_refused_when_gate_is_not_eligible():
    gate = EvolveGate()
    with pytest.raises(PromotionRefused, match="OBSERVE"):
        gate.promote(candidate(receipts=receipts(1)), granted_by=Authority.OWNER)


def test_rollback_receipt_restores_the_prior_version():
    gate, c = EvolveGate(), candidate()
    gate.promote(c, granted_by=Authority.LANE)
    assert gate.current_version("retrieval.depth") == "2"
    r = gate.rollback("retrieval.depth", reason="latency regressed in production")
    assert r["restored_version"] == "1" and r["status"] == "ROLLED_BACK"
    assert gate.current_version("retrieval.depth") == "1"


def test_rollback_refused_when_never_promoted():
    with pytest.raises(PromotionRefused, match="never promoted"):
        EvolveGate().rollback("retrieval.depth", reason="whim")


def test_rollback_refused_when_promotion_had_no_target():
    gate = EvolveGate()
    gate.promote(candidate(rollback_to=None), granted_by=Authority.LANE)
    with pytest.raises(PromotionRefused, match="no rollback target"):
        gate.rollback("retrieval.depth", reason="regret")


def test_ledger_is_append_only_and_auditable():
    gate, c = EvolveGate(), candidate()
    gate.check(c); gate.promote(c, granted_by=Authority.LANE)
    gate.rollback("retrieval.depth", reason="regressed")
    actions = [e["action"] for e in gate.history("retrieval.depth")]
    assert actions == ["check", "promote", "rollback"]


# --- replay adapter ----------------------------------------------------------------
def test_from_replay_builds_a_candidate_without_product_coupling():
    trials = [{"name": f"t{i}", "effect": 0.1, "trials": 4} for i in range(6)]
    c = from_replay("context.budget", "3", "smaller budget is enough", trials, rollback_to="2")
    v = evaluate(c)
    assert c.sample_count == 24 and v.eligible


def test_no_autonomous_self_modification_in_this_module():
    # the gate decides and records; applying is the caller's separate act
    gate = EvolveGate()
    receipt = gate.promote(candidate(), granted_by=Authority.LANE)
    assert "applied" not in receipt and set(receipt) >= {"policy", "version", "granted_by"}
