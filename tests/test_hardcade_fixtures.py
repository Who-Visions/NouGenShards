"""Tests for Hardcade Replay Fixtures and Evidence Verifier.

Tests that all six success-shaped failure fixtures trigger COMBO BREAKER at the expected hit index,
and that only genuine multi-node, multi-credential independent evidence can emit PERFECT or GODLIKE.
An implementation that emits PERFECT on any fixture is decorative and fails CI.
"""

import json
from pathlib import Path
import pytest

from nougen_shards.hardcade_verifier import (
    EvidenceTuple,
    evaluate_hardcade_evidence
)

FIXTURES_PATH = Path(__file__).parent / "hardcade_fixtures" / "fixtures.json"


@pytest.fixture
def replay_fixtures():
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_fixtures_file_exists_and_has_six_incidents(replay_fixtures):
    assert len(replay_fixtures) == 6
    expected_ids = {
        "fixture-1-shards-status-false-green",
        "fixture-2-silent-tool-removal-deploy",
        "fixture-3-captured-true-quarantine",
        "fixture-4-http-200-empty-body",
        "fixture-5-stale-wiki-deployed",
        "fixture-6-zero-tools-score"
    }
    actual_ids = {fix["id"] for fix in replay_fixtures}
    assert actual_ids == expected_ids


@pytest.mark.parametrize("fixture_index", range(6))
def test_each_fixture_triggers_combo_breaker_never_perfect(replay_fixtures, fixture_index):
    fix = replay_fixtures[fixture_index]
    claim = fix["claim"]
    subject = fix["subject"]
    observer = fix["observer"]
    
    tuples = [
        EvidenceTuple(
            claim=claim,
            probe=p["probe"],
            node=p["node"],
            observed=p["observed"],
            credential=p.get("credential"),
            observer=observer,
            subject=subject
        )
        for p in fix["probe_calls"]
    ]

    result = evaluate_hardcade_evidence(
        claim=claim,
        evidence_list=tuples,
        subject=subject,
        observer=observer
    )

    # Acceptance test rule: An implementation that emits PERFECT on any fixture is decorative and fails CI
    assert result.verdict != "PERFECT", f"Fixture {fix['id']} emitted PERFECT! Must emit COMBO BREAKER."
    assert result.verdict == fix["expected_verdict"], f"Fixture {fix['id']} verdict mismatch: {result.verdict}"
    assert result.announcer_call == "COMBO BREAKER"
    assert result.breaker_hit_index == fix["breaker_hit_index"]


def test_independent_evidence_reaches_perfect():
    """Two probes differing in premise, distinct credentials, and observed verified health."""
    claim = "endpoint health and capacity verified"
    tuples = [
        EvidenceTuple(
            claim=claim,
            probe="http_status_and_body",
            node="whoart",
            observed={"status_code": 200, "body_length": 1500, "alive": True},
            credential="key-alpha",
            observer="whoart",
            subject="blade"
        ),
        EvidenceTuple(
            claim=claim,
            probe="synthetic_transaction_check",
            node="phoebus",
            observed={"transaction_ok": True, "latency_ms": 42},
            credential="key-beta",
            observer="phoebus",
            subject="blade"
        )
    ]

    result = evaluate_hardcade_evidence(
        claim=claim,
        evidence_list=tuples,
        subject="blade",
        observer="phoebus"
    )

    assert result.verdict == "GODLIKE"
    assert result.announcer_call == "GODLIKE"
    assert result.effective_observations == 2


def test_shared_credential_collapses_to_single_observation():
    """Hop 4 rule: Observations sharing a credential are ONE observation."""
    claim = "api service healthy"
    tuples = [
        EvidenceTuple(
            claim=claim,
            probe="probe_1",
            node="whoart",
            observed={"status_code": 200, "body_length": 500},
            credential="SHARED_FLEET_TOKEN",
            observer="whoart",
            subject="api"
        ),
        EvidenceTuple(
            claim=claim,
            probe="probe_2",
            node="phoebus",
            observed={"status_code": 200, "body_length": 500},
            credential="SHARED_FLEET_TOKEN",
            observer="phoebus",
            subject="api"
        )
    ]

    result = evaluate_hardcade_evidence(
        claim=claim,
        evidence_list=tuples,
        subject="api",
        observer="phoebus"
    )

    assert result.verdict != "GODLIKE"
    assert result.verdict != "PERFECT"
    assert result.effective_observations == 1
    assert any("Observations share a single credential" in r for r in result.reasons)


def _tuple(node, credential, observer, claim="api healthy"):
    return EvidenceTuple(
        claim=claim,
        probe=f"probe-{node}",
        node=node,
        observed={"status_code": 200, "body_length": 9},
        credential=credential,
        observer=observer,
        subject="api",
    )


def test_self_reported_tuple_cannot_corroborate_a_verified_one():
    """Hop 4 rule 1: identity, not just credentials, bounds independence.

    Regression. Counting distinct CREDENTIALS alone let a self-reported tuple
    pair with one verified tuple and reach 2 effective observations, emitting
    PERFECT on evidence where only ONE party's identity was ever established.
    Credentials catch one actor wearing two hostnames; verified identity catches
    one hostname vouching for itself. Both bounds are required.
    """
    result = evaluate_hardcade_evidence(
        claim="api healthy",
        evidence_list=[
            _tuple("self-reported", "key-alpha", "whoart"),
            _tuple("phoebus", "key-beta", "phoebus"),
        ],
        subject="api",
        observer="phoebus",
    )

    assert result.effective_observations == 1, "a self-reported tuple must not corroborate"
    assert result.verdict not in ("PERFECT", "GODLIKE")
    assert any("self-reported" in r for r in result.reasons)


def test_two_verified_nodes_with_distinct_credentials_still_reach_godlike():
    """Negative control: the fix must not collapse genuinely independent evidence."""
    result = evaluate_hardcade_evidence(
        claim="api healthy",
        evidence_list=[
            _tuple("whoart", "key-alpha", "whoart"),
            _tuple("phoebus", "key-beta", "phoebus"),
        ],
        subject="api",
        observer="phoebus",
    )

    assert result.verdict == "GODLIKE"
    assert result.effective_observations == 2


def test_unstamped_hostnames_do_not_corroborate():
    """Identity verification is opt-IN, not opt-OUT.

    Regression, found by whoart/outpost-1d re-deriving PR #268 independently.
    The first fix caught the honest confessor (node="self-reported") and missed
    the ordinary case: two tuples carrying plain hostnames and NO observer were
    counted as two independent observers and reached GODLIKE, having been
    stamped by nobody. That is the realistic shape — it is what NouGenMsg
    produces when a lane self-stamps NouGenMsg-<node>. A hostname is a claim
    about identity, not evidence of it.
    """
    result = evaluate_hardcade_evidence(
        claim="api healthy",
        evidence_list=[
            EvidenceTuple(claim="api healthy", probe="p1", node="alpha",
                          observed={"status_code": 200, "body_length": 9},
                          credential="key-alpha", subject="api"),
            EvidenceTuple(claim="api healthy", probe="p2", node="beta",
                          observed={"status_code": 200, "body_length": 9},
                          credential="key-beta", subject="api"),
        ],
        subject="api",
        observer="phoebus",
    )

    assert result.effective_observations == 0
    assert result.verdict not in ("PERFECT", "GODLIKE")


def test_observer_equal_to_subject_cannot_vouch_for_itself():
    """A subject stamping its own tuples is self-attestation wearing a uniform."""
    result = evaluate_hardcade_evidence(
        claim="api healthy",
        evidence_list=[
            EvidenceTuple(claim="api healthy", probe="p1", node="alpha",
                          observed={"status_code": 200, "body_length": 9},
                          credential="key-alpha", observer="api", subject="api"),
            EvidenceTuple(claim="api healthy", probe="p2", node="beta",
                          observed={"status_code": 200, "body_length": 9},
                          credential="key-beta", observer="api", subject="api"),
        ],
        subject="api",
        observer="phoebus",
    )

    assert result.effective_observations == 0
    assert result.verdict not in ("PERFECT", "GODLIKE")


def test_same_observer_twice_is_one_observation():
    """Deliberate, not a bug: one observer running two probes is one vantage.

    Documented so nobody "fixes" it into counting two. Independence is about
    who observed, not how many probes they ran.
    """
    result = evaluate_hardcade_evidence(
        claim="api healthy",
        evidence_list=[
            EvidenceTuple(claim="api healthy", probe="p1", node="alpha",
                          observed={"status_code": 200, "body_length": 9},
                          credential="key-alpha", observer="whoart", subject="api"),
            EvidenceTuple(claim="api healthy", probe="p2", node="beta",
                          observed={"status_code": 200, "body_length": 9},
                          credential="key-beta", observer="whoart", subject="api"),
        ],
        subject="api",
        observer="whoart",
    )

    assert result.effective_observations == 1
    assert result.verdict not in ("PERFECT", "GODLIKE")
