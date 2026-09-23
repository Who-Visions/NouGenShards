"""Composition tests for the Thinking Brain Harness.

Leg 20260923T035006Z asked for the *composed* path to be validated and said
plainly: "Do NOT mark the system green merely because unit tests pass
independently. Composition is the test."

At 12944ff the harness is five working islands with no production callers --
`evidence_gate` and `adaptive_budget` are imported by their own test modules
and nothing else. So there is no composed path to exercise end to end yet.

What this module does instead is pin the *seam* between the two stages that do
exist, so that whoever wires them has to wire them correctly:

    TaskSignature -> decide_budget -> BudgetReceipt   (PR-A, stage 2-3)
                                          |
                                          v
    PolicyCandidate -> EvidenceGate.check -> promote  (PR-C, stage 10-12)

The load-bearing assertion is the negative one: the budget's information-gain
number is a *proxy* that the source itself labels "NOT measured", and feeding a
proxy to the evidence gate would fit policy to a number nobody observed. That
is exactly the "unstable self-reinforcing loop without evidence gating" the leg
lists as a fail condition, so it is asserted here rather than left to review.
"""

import pytest

from nougen_shards.decision.domains.adaptive_budget import (
    LatencyClass,
    TaskFamily,
    TaskSignature,
    budget_receipt,
    decide_budget,
    mode,
)
from nougen_shards.evidence_gate import (
    Authority,
    EvidenceReceipt,
    EvolveGate,
    Metrics,
    PolicyCandidate,
    PromotionRefused,
    Status,
)

PROXY_SOURCE = "adaptive_budget.expected_information_gain_proxy"


def signature(**over):
    base = dict(
        task_family=TaskFamily.SYNTHESIS,
        uncertainty=0.7,
        recurrence=0.2,
        canon_safety_sensitivity=0.4,
        latency_class=LatencyClass.BACKGROUND,
        tool_topology=("shards_recall", "ask_rhea"),
    )
    base.update(over)
    return TaskSignature(**base)


def receipts_from_budget(sig, trials=1, source=PROXY_SOURCE):
    """The seam, written out: turn a budget decision into gate evidence."""
    d = decide_budget(sig)
    return EvidenceReceipt(
        source=source,
        observation=f"route={d.route_class.value} depth={d.retrieval_depth}",
        delta=d.expected_information_gain_proxy,
        trials=trials,
    )


# --------------------------------------------------------------- the seam

def test_budget_receipt_fields_satisfy_the_gate_s_evidence_contract():
    """Stage 3's output must be constructible into stage 10's input without
    inventing a field. If this breaks, the two halves have drifted apart."""
    r = receipts_from_budget(signature())
    assert r.receipt_id
    c = PolicyCandidate("harness.seam", "v1", "budget sizing beats fixed", receipts=(r,))
    assert c.sample_count == 1
    assert c.bundle_id


def test_the_same_evidence_reaches_the_same_verdict_through_the_seam():
    """bundle_id is identity of the evidence, not of the record -- the seam
    must not introduce a nondeterministic field."""
    sig = signature()
    a = PolicyCandidate("harness.seam", "v1", "h", receipts=(receipts_from_budget(sig, 30),))
    b = PolicyCandidate("harness.seam", "v1", "h", receipts=(receipts_from_budget(sig, 30),))
    assert a.bundle_id == b.bundle_id


# ------------------------------------------- the proxy must not become evidence

def test_proxy_gain_is_still_labelled_unmeasured_upstream():
    """If PR-F ever replaces the proxy with a measurement, this fails and the
    quarantine below should be revisited deliberately, not silently."""
    d = decide_budget(signature())
    assert any("NOT measured" in r for r in d.reasons), (
        "the information-gain proxy stopped announcing that it is unmeasured; "
        "check whether PR-F landed a real measurement before relaxing anything"
    )


def test_one_budget_observation_is_not_a_trend():
    """Stage 3 emits one decision per task. Composing naively gives n=1, and
    the gate must answer OBSERVE -- never ELIGIBLE."""
    c = PolicyCandidate("harness.seam", "v1", "h", receipts=(receipts_from_budget(signature()),))
    v = EvolveGate().check(c)
    assert v.status is Status.OBSERVE
    assert not v.eligible


def test_a_candidate_built_only_from_proxy_receipts_cannot_be_promoted():
    """The fail condition in the leg: 'component outputs form an unstable
    self-reinforcing loop without evidence gating'. A budget that scores its
    own expected gain, then uses that score as the evidence that the budget
    works, is precisely that loop. It must not reach PROMOTED on volume alone.
    """
    # Plenty of volume, healthy positive effect -- everything except a real
    # measurement. The only thing standing between this and promotion is the
    # authority gate, so an invariant is declared and only LANE is granted.
    r = receipts_from_budget(signature(), trials=200)
    c = PolicyCandidate(
        "harness.self_scored", "v1",
        "the budget's own gain proxy proves the budget works",
        receipts=(r,),
        metrics=(Metrics("answer_quality", baseline=0.50, candidate=0.55),),
        invariants_touched=("information_gain_must_be_measured",),
        rollback_to="v0",
    )
    gate = EvolveGate()
    with pytest.raises(PromotionRefused) as e:
        gate.promote(c, Authority.LANE)
    assert gate.current_version("harness.self_scored") is None
    assert e.value.verdict.required_authority is Authority.OWNER


# ------------------------------------------------- invariants through the seam

def test_regression_blocks_regardless_of_volume():
    r = receipts_from_budget(signature(), trials=500)
    c = PolicyCandidate(
        "harness.seam", "v2", "h",
        receipts=(r,),
        metrics=(Metrics("answer_quality", baseline=0.80, candidate=0.60),),
    )
    v = EvolveGate().check(c)
    assert v.status is Status.BLOCKED


def test_shadow_mode_receipts_cannot_gate_a_route(monkeypatch):
    """A shadow-mode budget receipt records the mode it ran under and never
    claims to have changed routing. Composition must preserve that."""
    monkeypatch.setenv("NOUGEN_ADAPTIVE_BUDGET", "shadow")
    assert mode() == "shadow"
    rec = budget_receipt(signature())
    assert rec.mode == "shadow"
    assert rec.would_mutate_routing is False


def test_unrecognised_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("NOUGEN_ADAPTIVE_BUDGET", "enforce-ish")
    assert mode() == "off"


def test_promotion_is_reproducible_and_reversible():
    """Stage 12: every version that goes live must be nameable and revertable."""
    r = EvidenceReceipt(source="replay.natural_workload", observation="measured", delta=0.12, trials=40)
    c = PolicyCandidate(
        "harness.measured", "v2", "measured gain beats fixed budget",
        receipts=(r,),
        metrics=(Metrics("answer_quality", baseline=0.70, candidate=0.78),),
        rollback_to="v1",
    )
    gate = EvolveGate()
    assert gate.check(c).status is Status.ELIGIBLE
    gate.promote(c, Authority.LANE)
    assert gate.current_version("harness.measured") == "v2"
    gate.rollback("harness.measured", reason="composition test")
    assert gate.current_version("harness.measured") == "v1"


def test_rollback_refuses_when_nothing_was_promoted():
    with pytest.raises(PromotionRefused):
        EvolveGate().rollback("harness.never", reason="x")


# ------------------------------------------------------- the honest boundary

def test_stages_absent_from_this_repo_are_not_silently_passed():
    """Stages 1, 4, 7, 8, 9 (Context Gate, FAST/REFLECTIVE + DIVERGE/CONVERGE
    routing, measured Information Gain Receipt, Natural Workload Replay,
    Predictive Memory) do not exist at 12944ff. This test exists so the suite
    cannot be read as covering them -- it fails the day one lands unwired, and
    the composition assertions above must then be extended to it."""
    expected_absent = {
        "nougen_shards.context_gate",
        "nougen_shards.decision.domains.reflective_routing",
        "nougen_shards.information_gain",
        "nougen_shards.workload_replay",
        "nougen_shards.predictive_memory",
    }
    present = set()
    for name in sorted(expected_absent):
        try:
            __import__(name)
        except ImportError:
            continue
        present.add(name)
    assert not present, (
        "a harness stage landed since 12944ff: " + ", ".join(sorted(present))
        + ". Extend the composition assertions above to cover it, then update "
        "this test -- do not simply delete the name from the list."
    )
