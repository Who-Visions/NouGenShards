"""Benchmark of NouGen information dynamics (leg 20261001T180631Z).

Ten scenarios. Each asserts what is OBSERVED, including where the current information_gain
layer is blind: those are labelled LIMITATION and are findings, not bugs hidden by the test.
Metrics stay separate; no scenario relies on a combined score.
"""
import pytest

from nougen_shards import info_dynamics as D
from nougen_shards.information_gain import MemoryState, classify, features, gate

H = {"healthy": 0.5, "degraded": 0.5}
LIKE_DEGRADED = {"healthy": 0.1, "degraded": 0.9}
LIKE_HEALTHY = {"healthy": 0.9, "degraded": 0.1}
UTIL = {"keep_routing": {"healthy": 1.0, "degraded": -4.0},
        "drain_node":   {"healthy": -1.0, "degraded": 2.0}}


def _sig(g):
    return getattr(g, "signal", g.novelty)


def test_every_metric_carries_calibration_version_and_provenance():
    m = MemoryState(); m.observe({"a", "b"})
    ms = [D.surprisal_bits(m, {"a", "z"}), D.belief_shift_kl(H, D.bayes_update(H, LIKE_DEGRADED)),
          D.decision_distortion(H, H, UTIL), D.should_stop(0.9, 0.8, 0.01, 0.1),
          D.error_energy({"duplicate_work": 2}), D.semantic_survival(3, 5, True),
          D.action_allowed(0.7, True), D.project([1, 2, 3], 2, float)[1],
          D.swap_invariants({"identity": "x", "events": [], "provenance": [], "durable": []},
                            {"identity": "x", "events": [], "provenance": [], "durable": []})]
    for x in ms:
        assert x.calibration_version == D.CALIBRATION_VERSION and "uncalibrated" in x.calibration_version
        assert x.provenance["kind"] == "computed" and x.provenance["metric"] == x.name


# 1. duplicate ---------------------------------------------------------------
def test_duplicate_events_decay_to_near_zero_surprisal():
    m, ev = MemoryState(), {"relay", "ack", "lag"}
    bits = [D.surprisal_bits(m, ev).value for _ in range(40) if m.observe(ev) or True]
    assert bits[-1] < 0.05 * bits[0]


# 2. negation / 3. contradiction (LIMITATION: ΔI is lexical) -----------------------
def test_contradiction_built_from_known_tokens_scores_as_duplicate_LIMITATION():
    m = MemoryState()
    for _ in range(30):                       # BOTH halves are common, so no token is rare
        m.observe(features("disk is down"))
        m.observe(features("service is up"))
    g = m.gain(features("service is down"))   # every unigram AND bigram already common
    assert classify(_sig(g)) == "duplicate" and not gate(_sig(g))
    assert _sig(g) < _sig(m.gain(features("quantum teapot"))) / 5   # vs a genuinely unseen event
    # ...yet the meaning flips the decision. Decision distortion sees what ΔI cannot:
    post = D.bayes_update(H, LIKE_DEGRADED)
    stale = D.bayes_update(H, LIKE_HEALTHY)
    assert D.decision_distortion(post, stale, UTIL).value > 0


def test_negation_with_a_new_token_is_visible_but_not_as_a_reversal():
    m = MemoryState()
    for _ in range(30):
        m.observe(features("service is up"))
    g = m.gain(features("service is not up"))
    assert _sig(g) > 0.15      # visible, because the token "not" is new
    assert g.novelty < 1.0     # but scored as a new token, not as a reversal of meaning


# 4. rare irrelevant event ----------------------------------------------------
def test_rare_irrelevant_event_is_high_surprisal_zero_decision_value():
    m = MemoryState()
    for _ in range(30):
        m.observe(features("service is up"))
    rare = D.surprisal_bits(m, features("a gull landed on the antenna"))
    flat = {"healthy": 0.5, "degraded": 0.5}
    assert rare.value > 20                                           # very surprising
    assert D.decision_distortion(H, flat, UTIL).value == 0           # changes no decision
    assert D.belief_shift_kl(H, flat).value == 0                     # moves no belief


# 5. stale evidence -----------------------------------------------------------
def test_stale_evidence_is_invisible_to_gain_but_raised_by_error_energy():
    m = MemoryState()
    m.observe(features("node blade healthy"))
    assert classify(_sig(m.gain(features("node blade healthy")))) != "novel"
    fresh = D.error_energy({"stale_beliefs": 0})
    stale = D.error_energy({"stale_beliefs": 4})
    assert D.drift(fresh, stale).value > 0


# 6. semantic thrashing ---------------------------------------------------------
def test_thrashing_keeps_belief_shift_high_while_consistent_evidence_decays():
    flip, steady = H, H
    flips, steadies = [], []
    for i in range(10):
        new = D.bayes_update(flip, LIKE_DEGRADED if i % 2 == 0 else LIKE_HEALTHY)
        flips.append(D.belief_shift_kl(flip, new).value); flip = new
        new = D.bayes_update(steady, LIKE_DEGRADED)
        steadies.append(D.belief_shift_kl(steady, new).value); steady = new
    assert min(flips) > 0.3                       # never settles
    assert steadies[-1] < 0.05 < steadies[0]      # converges


# 7. channel loss ---------------------------------------------------------------
def test_semantic_capacity_is_not_transport_capacity():
    assert D.semantic_survival(2, 5, transport_ok=True, intent_verified=True).value == "lost"
    assert D.semantic_survival(8, 5, transport_ok=True).value == "unverified"
    assert D.semantic_survival(8, 5, transport_ok=False, intent_verified=True).value == "unverified"
    assert D.semantic_survival(8, 5, transport_ok=True, intent_verified=True).value == "verified"


# 8. node outage ----------------------------------------------------------------
def test_node_outage_raises_error_energy_and_recovery_gives_negative_drift():
    ok = D.error_energy({"unacked_critical_relays": 0})
    out = D.error_energy({"unacked_critical_relays": 3, "stale_beliefs": 2, "duplicate_work": 1})
    back = D.error_energy({"unacked_critical_relays": 0, "stale_beliefs": 0})
    assert D.drift(ok, out).value > 0 and D.drift(out, back).value < 0
    with pytest.raises(ValueError):
        D.error_energy({"vibes": 1})


# 9. provider swap --------------------------------------------------------------
def test_provider_swap_invariants_pass_when_faithful_and_name_each_violation():
    base = {"identity": "phoebus", "events": [("a", 10), ("b", 20)],
            "provenance": ["relay:1", "relay:2"], "durable": ["x", "y"]}
    faithful = {**base, "events": base["events"] + [("c", 15)], "durable": ["x", "y", "z"],
                "provenance": ["relay:1", "relay:2", "relay:3"]}
    assert D.swap_invariants(base, faithful).value == []
    bad = {"identity": "other", "events": [("a", 10), ("c", 15), ("b", 20)],
           "provenance": ["relay:1"], "durable": ["x", "Y"]}
    got = " | ".join(D.swap_invariants(base, bad).value)
    for needle in ("identity", "chronology", "provenance", "durable"):
        assert needle in got


# 10. irreversible action --------------------------------------------------------
def test_irreversible_actions_need_a_higher_bar_than_reversible_ones():
    assert D.action_allowed(0.7, reversible=True).value is True
    assert D.action_allowed(0.7, reversible=False).value is False
    assert D.action_allowed(0.97, reversible=False).value is True


# requirements 2 and 3 -------------------------------------------------------------
def test_bounded_projection_never_rewrites_the_append_only_durable_store():
    durable = tuple(range(100))
    w, m = D.project(durable, 10, lambda x: -abs(x - 50))
    assert len(w) == 10 and w == sorted(w) and durable == tuple(range(100))
    assert m.value["kept"] == 10 and m.value["of"] == 100


def test_retrieval_stops_only_when_sufficient_and_not_worth_another_fetch():
    assert D.should_stop(0.9, 0.8, expected_gain=0.01, cost=0.1).value is True
    assert D.should_stop(0.9, 0.8, expected_gain=0.5, cost=0.1).value is False   # still worth it
    assert D.should_stop(0.5, 0.8, expected_gain=0.01, cost=0.1).value is False  # not sufficient


def test_decision_distortion_is_about_decisions_not_text():
    full = D.bayes_update(H, LIKE_DEGRADED)
    flipped = D.bayes_update(H, LIKE_HEALTHY)                # a projection that drops the evidence's meaning
    assert D.decision_distortion(full, full, UTIL).value == 0
    assert D.decision_distortion(full, flipped, UTIL).value > 0
