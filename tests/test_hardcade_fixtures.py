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
