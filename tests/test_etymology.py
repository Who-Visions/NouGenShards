"""Unit tests for nougen_shards.etymology (Idiolect Intent Resolution Layer)."""
import pytest
from nougen_shards.etymology import (
    EtymologyEngine,
    IdiolectStore,
    MorphologicalAnalyzer,
    CulturalArchetypeRegistry,
    resolve,
)


@pytest.fixture
def mem_engine(tmp_path):
    db_file = tmp_path / "test_idiolect.db"
    store = IdiolectStore(db_path=str(db_file))
    return EtymologyEngine(store=store)


def test_morphological_decomposition():
    analyzer = MorphologicalAnalyzer()
    breakdown = analyzer.decompose("synchronize telemetry across machines")
    lemmas = [m.lemma for m in breakdown]
    assert "synchron" in lemmas
    assert "telemetry" in lemmas

    # Check root extraction
    chrono_root = analyzer.lookup_root("chrono")
    assert chrono_root is not None
    assert chrono_root.literal_meaning == "time"


def test_archetype_matching():
    registry = CulturalArchetypeRegistry()
    matches = registry.find_matching_archetypes("Harriet Tubman stealth recovery")
    assert any(m.name == "Harriet Tubman" for m in matches)
    tubman = next(m for m in matches if m.name == "Harriet Tubman")
    assert "liberation" in tubman.domain.lower()


def test_seed_fleet_idiolect(mem_engine):
    # Test GM continuation command
    res_and = mem_engine.resolve_intent("and", user_id="dav3")
    assert res_and.top_intent is not None
    assert res_and.top_intent.intent_id == "workflow.closed_loop_continue"
    assert res_and.top_intent.confidence >= 0.95

    # Test friction reduction
    res_lube = mem_engine.resolve_intent("lube out", user_id="dav3")
    assert res_lube.top_intent is not None
    assert res_lube.top_intent.intent_id == "system.remove_operational_friction"

    # Test autonomy maximization
    res_top = mem_engine.resolve_intent("using top .001%", user_id="dav3")
    assert res_top.top_intent is not None
    assert res_top.top_intent.intent_id == "system.maximize_autonomous_execution"


def test_online_learning_and_feedback(mem_engine):
    user_id = "test_operator"
    # Learn a novel custom metaphor
    mem_engine.store.learn_metaphor(
        user_id=user_id,
        phrase_pattern="warp speed ahead",
        intent_id="deploy.expedited_rollout",
        action_template={"priority": "max", "verify": True},
        confidence=0.9
    )

    res = mem_engine.resolve_intent("warp speed ahead", user_id=user_id)
    assert res.top_intent is not None
    assert res.top_intent.intent_id == "deploy.expedited_rollout"

    # Reinforce with positive outcome
    mem_engine.reinforce(
        user_id=user_id,
        phrase="warp speed ahead",
        intent_id="deploy.expedited_rollout",
        success=True
    )

    history = mem_engine.store.get_history_outcomes(user_id=user_id, phrase_match="warp speed ahead")
    assert len(history) == 1
    assert history[0]["outcome_success"] == 1


def test_module_singleton_resolve():
    res = resolve("proceed", user_id="dav3")
    assert res.top_intent is not None
    assert res.top_intent.intent_id == "workflow.closed_loop_continue"


def test_in_memory_store_persists_across_calls():
    store = IdiolectStore(db_path=":memory:")
    store.learn_term("user1", "orbit", "celestial_loop", "astronomy", confidence=0.9)
    terms = store.get_terms_for_user("user1")
    assert len(terms) == 1
    assert terms[0].term == "orbit"


def test_word_boundary_isolation(mem_engine):
    # 'and' is seeded, but substrings inside other words must not trigger it
    res_cmd = mem_engine.resolve_intent("show command history", user_id="dav3")
    assert res_cmd.top_intent is None or res_cmd.top_intent.intent_id != "workflow.closed_loop_continue"

    res_under = mem_engine.resolve_intent("understand the system architecture", user_id="dav3")
    assert res_under.top_intent is None or res_under.top_intent.intent_id != "workflow.closed_loop_continue"

    # Actual standalone 'and' must trigger
    res_and = mem_engine.resolve_intent("and", user_id="dav3")
    assert res_and.top_intent is not None
    assert res_and.top_intent.intent_id == "workflow.closed_loop_continue"


def test_tenant_isolation(tmp_path):
    store_a = IdiolectStore(db_path=str(tmp_path / "tenant_a.db"), tenant_id="tenant_a")
    store_b = IdiolectStore(db_path=str(tmp_path / "tenant_b.db"), tenant_id="tenant_b")

    store_a.learn_term("operator", "cipher", "secret_key")
    assert len(store_a.get_terms_for_user("operator")) == 1
    assert len(store_b.get_terms_for_user("operator")) == 0

