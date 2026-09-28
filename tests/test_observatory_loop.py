"""
Unit tests for observatory_loop module.
"""
from nougen_shards.observatory_loop import ObservatoryEngine

def test_observatory_engine_cycle():
    engine = ObservatoryEngine()
    samples = ["make build run ship", "recurse and learn shard and relay"]
    facts = ["Rule 1: Never fake acks", "Substrate must stay clean"]

    res = engine.run_full_cycle(samples, facts)
    assert res["cycle_index"] == 1
    assert res["recurse_learn"]["shannon_entropy"] > 0
    assert res["build_harden"]["assertions_passed"] is True
    assert len(res["dream_evolve"]["synthesized_invariants"]) == 2

def test_phases_individually():
    engine = ObservatoryEngine()
    r1 = engine.recurse_and_learn(["test sentence"])
    assert r1["phase"] == "recurse_learn"

    r2 = engine.shard_and_relay("test_topic", {"data": 123})
    assert r2["phase"] == "shard_relay"

    r3 = engine.build_and_harden("martha", "marhta")
    assert r3["phase"] == "build_harden"
    assert r3["damerau_dist"] == 1

    r4 = engine.dream_and_evolve(["Rule: zero cost priority"])
    assert r4["phase"] == "dream_evolve"
    assert engine.state.cycle_index == 1
