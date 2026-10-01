"""Information-gain layer: repeats decay to ~0, state-changing info scores higher."""
import pytest

from nougen_shards.information_gain import MemoryState, classify, features, gate, urgency

EVENT = {"relay": 1, "ack": 1, "lag": 1}


def test_first_event_on_empty_memory_is_maximally_novel():
    g = MemoryState().gain(EVENT)
    assert g.novelty == pytest.approx(1.0)
    assert g.bits == pytest.approx(3.0) and g.size == 3  # 1 bit per unseen feature at T=0


def test_repeated_event_gain_strictly_decreases_toward_zero():
    m, bits = MemoryState(), []
    for _ in range(60):
        bits.append(m.observe(EVENT).bits)
    assert all(a > b for a, b in zip(bits, bits[1:])), "marginal gain must strictly fall"
    assert bits[-1] < 0.05 * bits[0], "repeated information approaches zero marginal gain"


def test_state_changing_event_beats_a_repeat():
    m = MemoryState()
    for _ in range(30):
        m.observe(EVENT)
    repeat = m.gain(EVENT)
    changing = m.gain({"gateway": 1, "502": 1, "restart": 1})
    assert changing.novelty > repeat.novelty
    assert changing.bits > repeat.bits
    assert classify(repeat.novelty) == "duplicate" and classify(changing.novelty) == "novel"


def test_partial_overlap_is_between_repeat_and_disjoint():
    m = MemoryState()
    for _ in range(30):
        m.observe(EVENT)
    repeat = m.gain(EVENT).novelty
    partial = m.gain({"relay": 1, "ack": 1, "newfault": 1}).novelty
    disjoint = m.gain({"x": 1, "y": 1, "z": 1}).novelty
    assert repeat < partial < disjoint


def test_gain_is_non_mutating_and_deterministic_and_order_independent():
    m = MemoryState()
    m.observe(EVENT)
    before = (dict(m.seen), m.events)
    a = m.gain(["lag", "relay", "ack", "relay"])
    b = m.gain(["relay", "ack", "relay", "lag"])
    assert a == b
    assert (dict(m.seen), m.events) == before


def test_inference_and_recommendation_are_scored_but_never_absorbed():
    m = MemoryState()
    m.observe(EVENT)
    snapshot = (dict(m.seen), m.events)
    for kind in ("inference", "recommendation"):
        assert m.gain({"hypothesis": 1}, kind=kind).kind == kind
        with pytest.raises(ValueError):
            m.observe({"hypothesis": 1}, kind=kind)
    assert (dict(m.seen), m.events) == snapshot


def test_relay_urgency_and_action_gate_are_monotone_in_novelty():
    m = MemoryState()
    for _ in range(30):
        m.observe(EVENT)
    quiet = m.gain(EVENT).novelty
    loud = m.gain({"gateway": 1, "502": 1}).novelty
    assert urgency(loud) > urgency(quiet)
    assert gate(loud) and not gate(quiet)
    assert not gate(loud, confidence=0.3)


def test_empty_event_has_zero_gain_and_bad_inputs_are_rejected():
    assert MemoryState().gain({}).bits == 0.0
    with pytest.raises(ValueError):
        MemoryState(alpha=0)
    with pytest.raises(ValueError):
        MemoryState().gain(EVENT, kind="rumour")
    with pytest.raises(ValueError):
        classify(0.5, duplicate_below=0.7, novel_above=0.6)


def test_default_extractor_feeds_the_same_primitives():
    m = MemoryState()
    first = m.observe(features("the relay watcher is blind on phoebus"))
    again = m.gain(features("the relay watcher is blind on phoebus"))
    other = m.gain(features("arxiv fulltext returns only a cache path"))
    assert first.novelty == pytest.approx(1.0)
    assert again.novelty < other.novelty
