from datetime import datetime, timezone
import json

import pytest

from nougen_shards.retrieval_v2 import (
    ArtifactCandidate,
    CanonicalEntity,
    QueryCoverage,
    QueryFlags,
    QueryReceipt,
    QueryState,
    RecoveryAction,
    append_state_transition,
    compile_intent,
    derive_followups,
    index_tags,
    next_recovery_action,
    normalize_query,
    parse_tag,
    reciprocal_rank_fusion,
)


NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
ENTITIES = (
    CanonicalEntity("blade1tb", ("blade",)),
    CanonicalEntity("phoebus", ("phoebus",)),
    CanonicalEntity("whoart", ("who art",)),
)


@pytest.mark.parametrize("query", [
    "all machine tokens ytd",
    "fleet tokens this year",
    "Blade Phoebus WhoArt YTD",
    "today token chart for all machines ytd",
    "all-machine tokens this year",
])
def test_ytd_query_variants_compile_to_same_fleet_key(query):
    intent = compile_intent(query, now=NOW, timezone="America/New_York", entities=ENTITIES)
    assert intent.metric == "token_usage"
    assert intent.period == "YTD"
    assert intent.year == 2026
    assert intent.scope == "FLEET"
    assert intent.canonical_key == "token_usage:fleet:YTD:2026"


def test_query_normalization_is_nfkc_and_keeps_original():
    original = "  all\u3000machine tokens  ytd  "
    intent = compile_intent(original, now=NOW, entities=ENTITIES)
    assert normalize_query(original) == "all machine tokens ytd"
    assert intent.query_original == original
    assert intent.query_normalized == "all machine tokens ytd"


def test_period_uses_caller_timezone_for_year_boundary():
    near_boundary = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
    intent = compile_intent("fleet token usage ytd", now=near_boundary, timezone="America/Los_Angeles")
    assert intent.year == 2025
    assert intent.canonical_key == "token_usage:fleet:YTD:2025"


def test_naive_clock_and_bad_timezone_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        compile_intent("tokens ytd", now=datetime(2026, 1, 1))
    with pytest.raises(Exception):
        compile_intent("tokens ytd", now=NOW, timezone="not/a-zone")


def test_provenance_and_metric_rules_are_deterministic():
    intent = compile_intent("prove all machine token usage ytd", now=NOW, entities=ENTITIES)
    assert intent.intent == "PROVENANCE"
    assert intent.scope == "FLEET"


def test_three_machine_aliases_imply_fleet_token_usage():
    intent = compile_intent("Blade Phoebus WhoArt YTD", now=NOW, entities=ENTITIES)
    assert intent.scope == "FLEET"
    assert intent.metric == "token_usage"
    assert intent.required_entities == ("blade1tb", "phoebus", "whoart")
    assert intent.canonical_key == "token_usage:fleet:YTD:2026"


def test_rrf_merges_lanes_deduplicates_and_breaks_ties_by_id():
    lanes = {
        "dense": [ArtifactCandidate("b", "dense", 1), ArtifactCandidate("a", "dense", 1)],
        "exact": [ArtifactCandidate("c", "exact", 1), ArtifactCandidate("b", "exact", 2)],
    }
    result = reciprocal_rank_fusion(lanes, k=60)
    assert [item[0] for item in result] == ["b", "a", "c"]
    assert result[0][1] > result[1][1] == result[2][1]
    assert reciprocal_rank_fusion(lanes, k=60) == result


def test_followups_are_stable_deduplicated_and_bounded():
    result = derive_followups(
        missing_entities=["whoart", "phoebus", "phoebus"],
        missing_current_artifact=True,
        conflicting_ids=["z", "a", "a"],
        budget=3,
    )
    assert result == [
        "current evidence for phoebus",
        "current evidence for whoart",
        "latest current canonical artifact",
    ]
    assert derive_followups(missing_entities=["a"], budget=0) == []
    with pytest.raises(ValueError, match="budget"):
        derive_followups(budget=-1)


@pytest.mark.parametrize(("changes", "expected"), [
    (
        {"completeness": "PARTIAL", "flags": QueryFlags(missing_expected_nodes=True, retryable=True)},
        RecoveryAction.CONTINUE_FEDERATION,
    ),
    (
        {"conflict": "CONFLICTED", "flags": QueryFlags(traceable=True)},
        RecoveryAction.TRACE_PROVENANCE,
    ),
    (
        {"freshness": "STALE", "canonical_key": "tokens:fleet:YTD:2026"},
        RecoveryAction.REFRESH_CANONICAL,
    ),
    (
        {"retrieval": "NO_HIT", "coverage": QueryCoverage(False)},
        RecoveryAction.EXPAND_RETRIEVAL,
    ),
    (
        {"retrieval": "NO_HIT", "coverage": QueryCoverage(True), "completeness": "COMPLETE",
         "flags": QueryFlags(deeper_search_available=True)},
        RecoveryAction.DRIFT_RECURSE,
    ),
    ({"pagination": "LOOP_DETECTED"}, RecoveryAction.REPARTITION_QUERY),
    (
        {"availability": "TIMEOUT", "flags": QueryFlags(failover_available=True)},
        RecoveryAction.FAILOVER,
    ),
    (
        {"truth_quality": "ESTIMATED", "flags": QueryFlags(exact_source_available=True)},
        RecoveryAction.RECONCILE,
    ),
    ({"canonicality": "SUPERSEDED"}, RecoveryAction.FOLLOW_SUPERSESSION),
    ({}, RecoveryAction.STOP_WITH_EXPLICIT_STATE),
])
def test_recovery_action_is_deterministic_by_axis(changes, expected):
    assert next_recovery_action(QueryState(**changes)) is expected


def test_recovery_precedence_prefers_missing_federated_nodes():
    state = QueryState(
        completeness="PARTIAL",
        conflict="CONFLICTED",
        flags=QueryFlags(missing_expected_nodes=True, retryable=True, traceable=True),
    )
    assert next_recovery_action(state) is RecoveryAction.CONTINUE_FEDERATION


@pytest.mark.parametrize("changes", [
    {"completeness": "PARTIAL", "coverage": QueryCoverage(True)},
    {"completeness": "COMPLETE", "coverage": QueryCoverage(False)},
    {"truth_quality": "UNKNOWN", "flags": QueryFlags(exact=True)},
    {"freshness": "EXPIRED", "flags": QueryFlags(current=True)},
    {"coverage": QueryCoverage(True, ("blade",), ())},
    {"reason_codes": ("missing_nodes",)},
])
def test_contradictory_state_is_rejected(changes):
    with pytest.raises(ValueError):
        QueryState(**changes)


def test_receipt_exposes_full_state_and_recovery_action():
    state = QueryState(
        status="DEGRADED",
        completeness="PARTIAL",
        coverage=QueryCoverage(False, ("blade", "phoebus"), ("phoebus",)),
        flags=QueryFlags(missing_expected_nodes=True, retryable=True),
        reason_codes=("federation.missing_expected_nodes",),
    )
    receipt = QueryReceipt("PARTIAL", ("phoebus",), ("blade",), state=state)
    result = receipt.to_dict()
    assert result["state"]["completeness"] == "PARTIAL"
    assert result["state"]["coverage"]["missing_nodes"] == ["blade"]
    assert result["state"]["recovery"] == "CONTINUE_FEDERATION"
    assert result["state"]["reason_codes"] == ("federation.missing_expected_nodes",)


def test_namespaced_tag_parser_preserves_legacy_tags():
    assert parse_tag("machine:phoebus").namespace == "machine"
    assert parse_tag("machine:phoebus").value == "phoebus"
    assert parse_tag("legacy-tag").namespace is None
    assert index_tags(["machine:phoebus", "machine:blade", "legacy-tag", "machine:phoebus"]) == {
        "free": ("legacy-tag",),
        "machine": ("blade", "phoebus"),
    }


def test_state_transitions_append_as_jsonl(tmp_path):
    path = tmp_path / "history.jsonl"
    partial = QueryState(
        status="DEGRADED",
        completeness="PARTIAL",
        coverage=QueryCoverage(False, ("phoebus", "blade"), ("phoebus",)),
        flags=QueryFlags(missing_expected_nodes=True, retryable=True),
    )
    complete = QueryState(
        status="SUCCESS",
        completeness="COMPLETE",
        coverage=QueryCoverage(True, ("phoebus", "blade"), ("phoebus", "blade")),
    )
    append_state_transition(path, partial, recorded_at="2026-09-16T23:00:00Z")
    append_state_transition(
        path, complete, previous=partial, outcome="federation resumed", recorded_at="2026-09-16T23:00:01Z"
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert len(events) == 2
    assert events[0]["recovery"] == "CONTINUE_FEDERATION"
    assert events[1]["previous"]["completeness"] == "PARTIAL"
    assert events[1]["current"]["completeness"] == "COMPLETE"
