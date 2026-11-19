"""
Comprehensive UDCT Test Suite for NouGenMorph Breakthrough NLP (`nougen_shards.nlp`).
"""

import json
import random
import pytest

from nougen_shards.nlp import (
    BreakthroughEngine,
    DecisionDestroyer,
    TimelineEngine,
    UnconsciousLoop,
    ValuesMatrix,
    WFOEngine,
)


def test_wfo_engine_well_formed_goal_passes():
    engine = WFOEngine(pass_threshold=0.8)
    res = engine.evaluate(
        "I will ship 100% verified NLP modules on WhoArt by 5pm today so that fleet autonomy and revenue compound."
    )
    assert res.passed is True
    assert res.score >= 0.8
    assert res.criteria["positive_terms"].passed is True
    assert res.criteria["sensory_specific"].passed is True
    assert res.criteria["context_defined"].passed is True
    assert res.criteria["meta_outcome"].passed is True
    assert res.criteria["ecology_safe"].passed is True
    assert res.criteria["self_initiated"].passed is True


def test_wfo_engine_negated_or_destructive_goal_fails():
    engine = WFOEngine(pass_threshold=0.8)
    neg_res = engine.evaluate("Do not fail or avoid writing tests")
    assert neg_res.passed is False
    assert neg_res.criteria["positive_terms"].passed is False
    assert len(neg_res.remediations) >= 1

    eco_res = engine.evaluate("I will wipe prod and force push on Apollo today so that revenue grows by 10%")
    assert eco_res.passed is False
    assert eco_res.criteria["ecology_safe"].passed is False


def test_wfo_engine_empty_and_boundary_inputs():
    engine = WFOEngine(pass_threshold=0.8)
    empty_res = engine.evaluate("")
    assert empty_res.passed is False
    assert empty_res.score == 0.0
    assert empty_res.passed_count == 0
    assert len(empty_res.remediations) == 10

    with pytest.raises(ValueError):
        WFOEngine(pass_threshold=1.5)
    with pytest.raises(TypeError):
        engine.evaluate(12345)  # type: ignore[arg-type]


def test_values_matrix_polarity_drivers_and_hierarchy():
    vm = ValuesMatrix()
    assert vm.classify_polarity("Achieve mastery and freedom") == "TOWARDS"
    assert vm.classify_polarity("Avoid failure and stress") == "AWAY_FROM"

    assert vm.map_driver("Total autonomy and adventure")[1] == "Frank"
    assert vm.map_driver("Deterministic hardening and stability")[1] == "Sally"
    assert vm.map_driver("Team mesh collaboration and family")[1] == "Bob"
    assert vm.map_driver("Mastery, revenue, and ROI excellence")[1] == "Cecil"
    assert vm.map_driver("Originality, unique style, and art")[1] == "Dwayne"

    hierarchy = vm.build_hierarchy(
        ["Security", "Freedom", "Mastery", "Avoid Failure"],
        pairwise_wins={"Freedom": 10, "Mastery": 8, "Security": 5, "Avoid Failure": 1},
    )
    assert [v.name for v in hierarchy] == ["Freedom", "Mastery", "Security", "Avoid Failure"]
    assert hierarchy[0].rank == 1
    assert hierarchy[0].persona == "Frank"
    assert hierarchy[3].polarity == "AWAY_FROM"

    reframed = vm.reframe_away_from(hierarchy[3])
    assert reframed.polarity == "TOWARDS"

    conflict = vm.resolve_conflict(hierarchy[0], hierarchy[2])
    assert conflict.primary.name == "Freedom"
    assert conflict.secondary.name == "Security"
    assert conflict.conflict_type == "AUTONOMY_VS_CERTAINTY"
    assert conflict.aligned is True


def test_decision_destroyer_locus_and_collapse():
    dd = DecisionDestroyer()
    assert dd.classify_locus("I can't finish because of them") == "EFFECT"
    assert dd.classify_locus("I engineer and verify the architecture") == "CAUSE"

    res = dd.destroy_limiting_decision(
        "I can't scale this pipeline because the legacy database is too slow",
        initial_submodalities={"brightness": 0.9, "size": 1.0, "distance_meters": 1.0, "volume": 0.9},
    )
    assert res.initial_locus == "EFFECT"
    assert res.final_locus == "CAUSE"
    assert "Externalized attribution" in res.root_gestalt
    assert res.collapsed_limiting_submodalities.brightness < 0.1
    assert res.collapsed_limiting_submodalities.volume == 0.0
    assert res.collapsed_limiting_submodalities.distance_meters >= 20.0
    assert res.installed_empowering_submodalities["brightness"] == 1.0


def test_timeline_engine_modes_and_future_pacing():
    te = TimelineEngine()
    assert te.classify_temporal_mode("I am immersed right now in the moment of flow") == "IN_TIME"
    assert te.classify_temporal_mode("Looking at the sequential schedule roadmap and milestones") == "THROUGH_TIME"

    plan = te.future_pace("Ship NouGenMorph Breakthrough NLP", horizon_days=14, milestones_count=5)
    assert plan.horizon_days == 14
    assert len(plan.milestones) == 5
    assert plan.milestones[0].step == 1
    assert plan.milestones[-1].day_offset == 14
    assert "Through-Time overview" in plan.look_back_integration


def test_unconscious_loop_directives_audit():
    ul = UnconsciousLoop()
    healthy_audit = ul.audit_telemetry(
        {"shards_online": True, "free_disk_gb": 5.0, "free_ram_gb": 8.0, "skills_loaded": True, "negative_commands": 0, "local_first": True, "context_logged": True}
    )
    assert healthy_audit.all_healthy is True
    assert healthy_audit.health_score == 1.0
    assert healthy_audit.autonomic_actions == []

    degraded_audit = ul.audit_telemetry(
        {"shards_online": False, "free_disk_gb": 0.5, "free_ram_gb": 1.0, "negative_commands": 3}
    )
    assert degraded_audit.all_healthy is False
    assert degraded_audit.health_score < 1.0
    assert len(degraded_audit.autonomic_actions) == 3


def test_breakthrough_facade_and_determinism():
    engine = BreakthroughEngine()
    r1 = engine.run_breakthrough(
        goal="I will build and verify the NLP engine on WhoArt today so that fleet autonomy scales by 10x",
        values=["Freedom", "Competency", "Security"],
        limiting_belief="I'm stuck on edge cases",
        horizon_days=7,
    )
    r2 = engine.run_breakthrough(
        goal="I will build and verify the NLP engine on WhoArt today so that fleet autonomy scales by 10x",
        values=["Freedom", "Competency", "Security"],
        limiting_belief="I'm stuck on edge cases",
        horizon_days=7,
    )
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    assert r1["wfo"]["passed"] is True
    assert r1["decision_destroyer"]["final_locus"] == "CAUSE"
    assert len(r1["strategic_vision"]["milestones"]) == 5


def test_10000_iteration_monte_carlo_invariants():
    """Validate all 5 engines across 10,000 deterministic randomized scenarios."""
    engine = BreakthroughEngine()
    rng = random.Random(20261017)

    positive_verbs = ["I will build", "We will deploy", "I engineer", "We deliver", "I verify", "We ship"]
    negative_verbs = ["Do not fail", "Never crash", "Stop losing", "Avoid bugs", "I can't do", "Don't break"]
    contexts = ["on WhoArt today", "in production by 5pm", "on Apollo node", "on Hyperion branch", "within 24h"]
    metrics = ["with 100 green tests", "at 15ms latency", "for $10k ROI", "verified in 9-DB logs", "seeing 0 errors"]
    purposes = ["so that freedom scales", "in order to compound revenue", "because competency matters", "to unlock autonomy"]
    hazards = ["wipe prod", "drop table", "force push", "bypass gate"]
    driver_samples = [
        "Freedom and adventure",
        "Security and deterministic plans",
        "Belonging and fleet team mesh",
        "Competency, mastery, and ROI",
        "Self-Expression, uniqueness, and art",
        "Avoid stress and failure",
        "Prevent chaos and loss",
    ]
    effect_excuses = [
        "I can't scale this because the database is slow",
        "It is impossible to finish because of them",
        "We are stuck on legacy code",
        "They made me miss the deadline",
        "I engineer deterministic solutions",
    ]

    for i in range(10000):
        mode = i % 5
        if mode == 0:
            g = f"{rng.choice(positive_verbs)} {rng.choice(metrics)} {rng.choice(contexts)} {rng.choice(purposes)}"
            wfo_res = engine.wfo.evaluate(g)
            assert wfo_res.passed is True
            assert wfo_res.score >= 0.8
        elif mode == 1:
            if i % 2 == 0:
                g = f"{rng.choice(negative_verbs)} {rng.choice(contexts)}"
                wfo_res = engine.wfo.evaluate(g)
                assert wfo_res.passed is False
            else:
                g = f"I will {rng.choice(hazards)} {rng.choice(contexts)} {rng.choice(purposes)}"
                wfo_res = engine.wfo.evaluate(g)
                assert wfo_res.passed is False
        elif mode == 2:
            sample = rng.sample(driver_samples, k=rng.randint(2, 5))
            h = engine.values.build_hierarchy(sample)
            assert len(h) == len(sample)
            assert engine.values.reframe_away_from(h[-1]).polarity == "TOWARDS"
            assert engine.values.resolve_conflict(h[0], h[1]).aligned is True
        elif mode == 3:
            dd_res = engine.destroyer.destroy_limiting_decision(rng.choice(effect_excuses))
            assert dd_res.final_locus == "CAUSE"
            assert dd_res.collapsed_limiting_submodalities.volume == 0.0
        else:
            days = rng.randint(1, 30)
            m_count = rng.randint(1, 10)
            plan = engine.timeline.future_pace(f"Milestone Goal #{i}", horizon_days=days, milestones_count=m_count)
            assert len(plan.milestones) == m_count
            assert plan.milestones[-1].day_offset == days

