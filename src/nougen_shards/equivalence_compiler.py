"""Bounded differential evidence for comparing two callable implementations.

This module deliberately does not claim a formal refinement proof. A matching
finite corpus can find regressions, but cannot establish universal equivalence.
Inputs must be inert JSON values and implementations should run in isolated,
side-effect-free sandboxes; this runner itself does not sandbox Python code.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any


VERDICT_REGRESSED = "REGRESSED"
VERDICT_INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class Invariant:
    """A named observable that both implementations must return."""

    name: str
    weight: float = 1.0
    critical: bool = True


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence must contain finite JSON-compatible values") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def compare_implementations(
    reference: Callable[[Any], Mapping[str, Any]],
    candidate: Callable[[Any], Mapping[str, Any]],
    cases: Sequence[Any],
    invariants: Sequence[Invariant],
    *,
    environment: Mapping[str, Any] | None = None,
    max_cases: int = 10_000,
) -> dict[str, Any]:
    """Compare declared observations over a frozen finite JSON workload.

    Mismatches fail closed as REGRESSED. Agreement is INDETERMINATE because
    finite differential execution alone is not an independent proof.
    Raw inputs, outputs, and exception messages are omitted from the receipt;
    only their hashes and exception types are retained.
    """
    if not callable(reference) or not callable(candidate):
        raise TypeError("reference and candidate must be callable")
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise TypeError("cases must be a finite sequence of JSON values")
    if not cases:
        raise ValueError("at least one frozen workload case is required")
    if len(cases) > max_cases:
        raise ValueError(f"workload exceeds max_cases={max_cases}")
    if not invariants or any(not isinstance(item, Invariant) for item in invariants):
        raise ValueError("at least one declared Invariant is required")
    names = [item.name for item in invariants]
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("invariant names must be non-empty strings")
    if len(set(names)) != len(names):
        raise ValueError("invariant names must be unique")
    if isinstance(max_cases, bool) or not isinstance(max_cases, int) or max_cases <= 0:
        raise ValueError("max_cases must be a positive integer")
    if any(
        isinstance(item.weight, bool)
        or not isinstance(item.weight, (int, float))
        or not math.isfinite(item.weight)
        or item.weight <= 0
        for item in invariants
    ):
        raise ValueError("invariant weights must be finite positive numbers")

    frozen_cases = [_canonical_json(case) for case in cases]
    environment_manifest = dict(environment or {})
    # Validate provenance inputs before executing either implementation.
    _canonical_json(environment_manifest)
    manifest = {
        "schema_version": 1,
        "reference_callable": getattr(reference, "__qualname__", type(reference).__name__),
        "candidate_callable": getattr(candidate, "__qualname__", type(candidate).__name__),
        "reference_code_hash": _callable_hash(reference),
        "candidate_code_hash": _callable_hash(candidate),
        "workload_sha256": _sha256(frozen_cases),
        "case_count": len(frozen_cases),
        "invariants": [asdict(item) for item in invariants],
        "environment_sha256": _sha256(environment_manifest),
    }

    comparisons: list[dict[str, Any]] = []
    verified_weight = 0.0
    total_weight = sum(item.weight for item in invariants) * len(cases)
    regressed = False

    for case_json in frozen_cases:
        case = json.loads(case_json)
        reference_result = _run_one(reference, case)
        # Each implementation gets an independent copy of the frozen input.
        # Otherwise a reference mutation can contaminate candidate execution
        # and hide a real behavioral difference.
        candidate_result = _run_one(candidate, json.loads(case_json))
        mismatches: list[str] = []
        missing: list[str] = []
        if reference_result["error_type"] or candidate_result["error_type"]:
            if reference_result != candidate_result:
                mismatches.extend(names)
        else:
            for invariant in invariants:
                name = invariant.name
                left = reference_result["value"]
                right = candidate_result["value"]
                if name not in left or name not in right:
                    missing.append(name)
                elif _canonical_json(left[name]) == _canonical_json(right[name]):
                    verified_weight += invariant.weight
                else:
                    mismatches.append(name)

        if mismatches:
            regressed = True
        comparisons.append(
            {
                "case_sha256": _sha256(json.loads(case_json)),
                "reference_output_sha256": reference_result["output_sha256"],
                "candidate_output_sha256": candidate_result["output_sha256"],
                "reference_error_type": reference_result["error_type"],
                "candidate_error_type": candidate_result["error_type"],
                "mismatched_invariants": sorted(set(mismatches)),
                "missing_invariants": sorted(set(missing)),
            }
        )

    coverage = verified_weight / total_weight if total_weight else 0.0
    if any(row["missing_invariants"] for row in comparisons):
        regressed = True
    body: dict[str, Any] = {
        "schema_version": 1,
        "evidence_kind": "finite_differential_execution",
        "manifest": manifest,
        "comparisons": comparisons,
        "equivalence_coverage": coverage,
        "counterexample_count": sum(bool(row["mismatched_invariants"]) for row in comparisons),
        "verdict": VERDICT_REGRESSED if regressed else VERDICT_INDETERMINATE,
        "promotion_allowed": False,
        "limitations": [
            "Finite differential agreement does not establish universal equivalence.",
            "The runner does not isolate callables or prove independence of the implementations.",
            "No symbolic, formal, shadow-traffic, or resource-gain evidence is included.",
        ],
    }
    body["certificate_sha256"] = _sha256(body)
    return body


def write_certificate(path: str | os.PathLike[str], certificate: Mapping[str, Any]) -> Path:
    """Atomically create a certificate file without replacing prior evidence."""
    target = Path(path)
    if not isinstance(certificate, Mapping):
        raise TypeError("certificate must be a mapping")
    body = dict(certificate)
    claimed_hash = body.pop("certificate_sha256", None)
    if not isinstance(claimed_hash, str) or claimed_hash != _sha256(body):
        raise ValueError("certificate hash is missing or invalid")
    body["certificate_sha256"] = claimed_hash
    encoded = (_canonical_json(body) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link publishes the complete, flushed file atomically and
        # fails if a receipt already occupies the destination.
        os.link(temporary, target)
        return target
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _run_one(function: Callable[[Any], Mapping[str, Any]], case: Any) -> dict[str, Any]:
    try:
        value = function(case)
        if not isinstance(value, Mapping):
            raise TypeError("implementation must return a mapping of invariant observations")
        # Copy through canonical JSON so output hashing and field comparisons
        # cannot observe later mutation by the implementation.
        frozen = json.loads(_canonical_json(dict(value)))
        return {"value": frozen, "error_type": None, "output_sha256": _sha256(frozen)}
    except Exception as exc:  # receipts preserve type, never raw exception text
        signature = {"error_type": type(exc).__name__}
        return {
            "value": {},
            "error_type": type(exc).__name__,
            "output_sha256": _sha256(signature),
        }


def _callable_hash(function: Callable[..., Any]) -> str:
    code = getattr(function, "__code__", None)
    if code is None:
        return _sha256({"callable_type": f"{type(function).__module__}.{type(function).__qualname__}"})
    material = {
        "module": getattr(function, "__module__", ""),
        "qualname": getattr(function, "__qualname__", ""),
        "bytecode": code.co_code.hex(),
        "constants": [repr(item) for item in code.co_consts],
        "names": list(code.co_names),
        "defaults": repr(getattr(function, "__defaults__", None)),
        "kwdefaults": repr(getattr(function, "__kwdefaults__", None)),
        "closure": [repr(cell.cell_contents) for cell in (getattr(function, "__closure__", None) or ())],
    }
    return _sha256(material)
