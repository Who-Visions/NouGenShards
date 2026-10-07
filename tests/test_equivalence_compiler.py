"""Acceptance tests for the bounded differential EquivalenceCompiler slice."""
import hashlib
import json

import pytest

from nougen_shards.equivalence_compiler import (
    Invariant,
    VERDICT_INDETERMINATE,
    VERDICT_REGRESSED,
    compare_implementations,
    write_certificate,
)


def test_matching_finite_workload_is_not_misreported_as_proven():
    def reference(row):
        return {"decision": row["x"] > 0}

    def candidate(row):
        return {"decision": row["x"] > 0}

    receipt = compare_implementations(
        reference, candidate, [{"x": 0}, {"x": 4}], [Invariant("decision")]
    )

    assert receipt["verdict"] == VERDICT_INDETERMINATE
    assert receipt["promotion_allowed"] is False
    assert receipt["equivalence_coverage"] == 1.0
    assert receipt["counterexample_count"] == 0


def test_mismatch_is_a_counterexample_and_blocks_promotion():
    receipt = compare_implementations(
        lambda row: {"decision": row["x"] >= 0},
        lambda row: {"decision": row["x"] > 0},
        [{"x": 0}, {"x": 1}],
        [Invariant("decision", critical=True)],
    )

    assert receipt["verdict"] == VERDICT_REGRESSED
    assert receipt["promotion_allowed"] is False
    assert receipt["counterexample_count"] == 1
    assert receipt["comparisons"][0]["mismatched_invariants"] == ["decision"]


def test_reference_input_mutation_cannot_hide_candidate_regression():
    def reference(row):
        row["nested"]["value"] = 999
        return {"output": 999}

    def candidate(row):
        return {"output": row["nested"]["value"]}

    original = {"nested": {"value": 1}}
    receipt = compare_implementations(reference, candidate, [original], [Invariant("output")])
    assert original == {"nested": {"value": 1}}
    assert receipt["verdict"] == VERDICT_REGRESSED
    assert receipt["counterexample_count"] == 1
    assert receipt["equivalence_coverage"] == 0.0


def test_missing_observation_fails_closed():
    receipt = compare_implementations(
        lambda row: {"decision": True},
        lambda row: {"other": True},
        [1],
        [Invariant("decision")],
    )
    assert receipt["verdict"] == VERDICT_REGRESSED
    assert receipt["comparisons"][0]["missing_invariants"] == ["decision"]


def test_matching_exception_types_do_not_count_as_verified_behavior():
    def raises(_):
        raise ValueError("private detail must not escape")

    receipt = compare_implementations(raises, raises, ["case"], [Invariant("decision")])
    assert receipt["verdict"] == VERDICT_INDETERMINATE
    assert receipt["equivalence_coverage"] == 0.0
    assert receipt["comparisons"][0]["reference_error_type"] == "ValueError"
    assert "private detail" not in json.dumps(receipt)


def test_receipt_is_deterministic_and_self_hashes():
    def reference(row):
        return {"decision": row["x"] % 2}

    first = compare_implementations(
        reference, reference, [{"x": 3}], [Invariant("decision")], environment={"runtime": "test"}
    )
    second = compare_implementations(
        reference, reference, [{"x": 3}], [Invariant("decision")], environment={"runtime": "test"}
    )
    assert first == second
    claimed = first.pop("certificate_sha256")
    actual = hashlib.sha256(
        json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()
    assert claimed == actual


@pytest.mark.parametrize(
    "cases,invariants",
    [([], [Invariant("decision")]), ([1], []), ([1], [Invariant("decision"), Invariant("decision")])],
)
def test_rejects_empty_or_ambiguous_evidence_spec(cases, invariants):
    with pytest.raises(ValueError):
        compare_implementations(lambda _: {}, lambda _: {}, cases, invariants)


def test_rejects_non_json_workload_before_execution():
    called = []
    with pytest.raises(ValueError):
        compare_implementations(
            lambda _: called.append(True) or {}, lambda _: {}, [object()], [Invariant("decision")]
        )
    assert called == []


def test_rejects_nonfinite_weights_before_execution():
    called = []
    with pytest.raises(ValueError, match="finite positive"):
        compare_implementations(
            lambda _: called.append(True) or {},
            lambda _: {},
            [1],
            [Invariant("decision", weight=float("nan"))],
        )
    assert called == []


def test_certificate_writer_is_atomic_and_never_replaces_existing_evidence(tmp_path):
    receipt = compare_implementations(
        lambda row: {"decision": row["x"]},
        lambda row: {"decision": row["x"]},
        [{"x": 1}],
        [Invariant("decision")],
    )
    target = write_certificate(tmp_path / "receipt.json", receipt)
    assert json.loads(target.read_text()) == receipt
    with pytest.raises(FileExistsError):
        write_certificate(target, receipt)
    tampered = dict(receipt, verdict="EQUIVALENT")
    with pytest.raises(ValueError, match="hash"):
        write_certificate(tmp_path / "tampered.json", tampered)
