"""PR-A: AdaptiveInformationBudget, shadow mode. Sanitized/synthetic fixtures only."""
import pytest

from nougen_shards.decision.domains.adaptive_budget import (
    LatencyClass, ModelStrengthClass, RouteClass, TaskFamily, TaskSignature,
    benchmark_vs_fixed, budget_receipt, decide_budget, fixed_budget_baseline, mode,
)

BOUNDED_LOOKUP = TaskSignature(TaskFamily.LOOKUP, uncertainty=0.1, recurrence=0.9,
                               canon_safety_sensitivity=0.1, latency_class=LatencyClass.INTERACTIVE)
HIGH_STAKES_AMBIGUOUS = TaskSignature(TaskFamily.CANON_JUDGMENT, uncertainty=0.9, recurrence=0.1,
                                      canon_safety_sensitivity=0.9, latency_class=LatencyClass.DEFERRED)


def test_bounded_input_is_validated():
    with pytest.raises(ValueError):
        TaskSignature(TaskFamily.LOOKUP, uncertainty=1.5, recurrence=0.0,
                      canon_safety_sensitivity=0.0, latency_class=LatencyClass.BACKGROUND)


def test_deterministic_same_signature_same_decision():
    a = decide_budget(BOUNDED_LOOKUP)
    b = decide_budget(BOUNDED_LOOKUP)
    assert a == b


def test_low_uncertainty_low_stakes_bounded_family_stays_on_rules():
    d = decide_budget(BOUNDED_LOOKUP)
    assert d.route_class is RouteClass.RULES and d.model_strength_class is ModelStrengthClass.NONE
    assert d.retrieval_depth == 0


def test_high_uncertainty_and_stakes_escalate_to_ensemble_and_deep_retrieval():
    d = decide_budget(HIGH_STAKES_AMBIGUOUS)
    assert d.route_class is RouteClass.ENSEMBLE
    assert d.model_strength_class is ModelStrengthClass.STRONG
    assert d.retrieval_depth == 3


def test_recurrence_saves_one_retrieval_pass_but_never_below_zero():
    routine_risky = TaskSignature(TaskFamily.SYNTHESIS, uncertainty=0.5, recurrence=0.9,
                                  canon_safety_sensitivity=0.1, latency_class=LatencyClass.BACKGROUND)
    novel_risky = TaskSignature(TaskFamily.SYNTHESIS, uncertainty=0.5, recurrence=0.0,
                                canon_safety_sensitivity=0.1, latency_class=LatencyClass.BACKGROUND)
    assert decide_budget(routine_risky).retrieval_depth < decide_budget(novel_risky).retrieval_depth
    bounded_routine = TaskSignature(TaskFamily.LOOKUP, uncertainty=0.0, recurrence=1.0,
                                    canon_safety_sensitivity=0.0, latency_class=LatencyClass.BACKGROUND)
    assert decide_budget(bounded_routine).retrieval_depth == 0  # never negative


def test_prior_failure_rate_can_only_escalate_never_deescalate():
    calm = TaskSignature(TaskFamily.LOOKUP, uncertainty=0.1, recurrence=0.5,
                         canon_safety_sensitivity=0.1, latency_class=LatencyClass.BACKGROUND,
                         prior_failure_rate=0.0)
    failing = TaskSignature(TaskFamily.LOOKUP, uncertainty=0.1, recurrence=0.5,
                            canon_safety_sensitivity=0.1, latency_class=LatencyClass.BACKGROUND,
                            prior_failure_rate=0.5)
    assert decide_budget(calm).route_class is RouteClass.RULES
    escalated = decide_budget(failing)
    assert escalated.route_class is RouteClass.DEEP_MODEL
    assert any("prior failure rate" in r for r in escalated.reasons)


def test_latency_class_shapes_tool_budget():
    topology = ("shards_search", "get_shard", "relay_read")
    interactive = TaskSignature(TaskFamily.TRIAGE, uncertainty=0.2, recurrence=0.5,
                                canon_safety_sensitivity=0.1, latency_class=LatencyClass.INTERACTIVE,
                                tool_topology=topology)
    deferred = TaskSignature(TaskFamily.TRIAGE, uncertainty=0.2, recurrence=0.5,
                             canon_safety_sensitivity=0.1, latency_class=LatencyClass.DEFERRED,
                             tool_topology=topology)
    assert decide_budget(interactive).tool_budget < decide_budget(deferred).tool_budget


def test_reasons_are_never_empty_and_every_decision_is_explained():
    for sig in (BOUNDED_LOOKUP, HIGH_STAKES_AMBIGUOUS):
        d = decide_budget(sig)
        assert len(d.reasons) >= 1


def test_information_gain_proxy_is_bounded_and_labeled_as_a_proxy():
    for sig in (BOUNDED_LOOKUP, HIGH_STAKES_AMBIGUOUS):
        d = decide_budget(sig)
        assert 0.0 <= d.expected_information_gain_proxy <= 1.0
        assert any("NOT measured" in r for r in d.reasons)


# --- property tests: bounds hold across a fuzzed, bounded input space -----------
def _fuzzed_signatures():
    import random
    rng = random.Random(1234)  # fixed seed: this property sweep is itself deterministic
    for _ in range(200):
        yield TaskSignature(
            task_family=rng.choice(list(TaskFamily)),
            uncertainty=rng.random(), recurrence=rng.random(),
            canon_safety_sensitivity=rng.random(),
            latency_class=rng.choice(list(LatencyClass)),
            tool_topology=tuple(f"tool_{i}" for i in range(rng.randint(0, 5))),
            prior_failure_rate=rng.random(),
        )


def test_property_decision_fields_always_in_bounds():
    for sig in _fuzzed_signatures():
        d = decide_budget(sig)
        assert 0 <= d.retrieval_depth <= 3
        assert d.context_budget > 0
        assert d.tool_budget >= 1
        assert 0.0 <= d.expected_information_gain_proxy <= 1.0
        assert d.reasons


def test_property_deterministic_across_repeated_calls():
    for sig in list(_fuzzed_signatures())[:20]:
        assert decide_budget(sig) == decide_budget(sig)


# --- receipt / adapter: shadow mode never mutates routing ------------------------
def test_receipt_marks_shadow_mode_and_never_mutates_routing():
    r = budget_receipt(BOUNDED_LOOKUP)
    assert r.would_mutate_routing is False
    assert r.mode == mode()  # defaults to "off" with no env set


def test_mode_fails_closed_on_garbage_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_ADAPTIVE_BUDGET", "yolo")
    assert mode() == "off"
    monkeypatch.setenv("NOUGEN_ADAPTIVE_BUDGET", "shadow")
    assert mode() == "shadow"


# --- benchmark vs fixed baseline --------------------------------------------------
def test_benchmark_shows_savings_on_bounded_tasks_and_spend_on_risky_ones():
    rows = benchmark_vs_fixed([BOUNDED_LOOKUP, HIGH_STAKES_AMBIGUOUS])
    bounded_row = next(r for r in rows if r.task_family == "lookup")
    risky_row = next(r for r in rows if r.task_family == "canon_judgment")
    assert bounded_row.context_saved > 0          # adaptive spends less on a bounded task
    assert risky_row.context_saved <= 0            # adaptive spends at least as much on a risky one


def test_fixed_baseline_is_identical_regardless_of_signature():
    a = fixed_budget_baseline(BOUNDED_LOOKUP)
    b = fixed_budget_baseline(HIGH_STAKES_AMBIGUOUS)
    assert (a.retrieval_depth, a.context_budget, a.route_class, a.tool_budget) == \
        (b.retrieval_depth, b.context_budget, b.route_class, b.tool_budget)
