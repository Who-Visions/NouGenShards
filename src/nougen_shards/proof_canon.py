"""Proof-to-Canon gate: machine verification is necessary, never sufficient.

States advance strictly one step at a time:
    DISCOVERED -> MACHINE_VERIFIED -> PROVENANCE_LINKED -> ATTRIBUTED
               -> EXPLAINED -> REPRODUCED -> CANON_READY

Readiness vector (T, P, A, X, R) = truth, provenance, attribution, explanatory
transmissibility, reproducibility. A checker verdict proves T only. Everything
here is pure: ``advance`` returns a new artifact, ``epistemic_debt`` only reads.
Provenance and dependency handles are carried through every transition, and each
transition is chained by SHA-256 so history is append-only and tamper-evident.
Grafts onto ``formal_prover.FormalProofResult`` and the ``canonical_facts`` path;
it owns no storage.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

STATES = ("DISCOVERED", "MACHINE_VERIFIED", "PROVENANCE_LINKED", "ATTRIBUTED",
          "EXPLAINED", "REPRODUCED", "CANON_READY")
# state entered -> readiness dimension that entry establishes
_ESTABLISHES = {"MACHINE_VERIFIED": "T", "PROVENANCE_LINKED": "P", "ATTRIBUTED": "A",
                "EXPLAINED": "X", "REPRODUCED": "R"}


class GateError(ValueError):
    """A transition was refused; the message names the missing evidence."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, default=str).encode()).hexdigest()


def _handles(value: Any, field: str) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise GateError(f"{field} must be a list of handles")
    out = tuple(value)
    if any(not isinstance(h, str) or not h.strip() for h in out):
        raise GateError(f"{field} entries must be non-empty strings")
    return out


@dataclass(frozen=True)
class ProofArtifact:
    artifact_id: str
    state: str
    provenance_handles: tuple
    dependency_handles: tuple
    evidence: Mapping[str, Mapping[str, Any]]   # dimension -> evidence that established it
    prev_handle: Optional[str]
    handle: str

    @property
    def readiness(self) -> dict:
        return {d: d in self.evidence for d in "TPAXR"}


def _seal(artifact_id, state, prov, deps, evidence, prev) -> ProofArtifact:
    body = {"id": artifact_id, "state": state, "prov": list(prov), "deps": list(deps),
            "evidence": {k: dict(v) for k, v in evidence.items()}, "prev": prev}
    return ProofArtifact(artifact_id, state, prov, deps, dict(evidence), prev, _digest(body))


def discover(artifact_id: str, *, provenance_handles: Iterable[str] = (),
             dependency_handles: Iterable[str] = ()) -> ProofArtifact:
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise GateError("artifact_id is required")
    return _seal(artifact_id, "DISCOVERED", _handles(provenance_handles, "provenance_handles"),
                 _handles(dependency_handles, "dependency_handles"), {}, None)


def _need(evidence: Mapping[str, Any], *fields: str) -> None:
    missing = [f for f in fields if not evidence.get(f)]
    if missing:
        raise GateError(f"missing evidence: {', '.join(missing)}")


def advance(artifact: ProofArtifact, evidence: Mapping[str, Any]) -> ProofArtifact:
    """Move exactly one state forward; refuses anything the evidence does not prove."""
    idx = STATES.index(artifact.state)
    if idx == len(STATES) - 1:
        raise GateError("already CANON_READY")
    target = STATES[idx + 1]
    prov, deps = artifact.provenance_handles, artifact.dependency_handles
    ev = dict(evidence)
    if target == "MACHINE_VERIFIED":
        _need(ev, "checker", "certificate_hash")
        if ev.get("verified") is not True:
            raise GateError("checker did not report verified=True")
    elif target == "PROVENANCE_LINKED":
        # may add handles, can never drop any
        prov = prov + tuple(h for h in _handles(ev.get("provenance_handles"), "provenance_handles") if h not in prov)
        if not prov:
            raise GateError("missing evidence: provenance_handles")
    elif target == "ATTRIBUTED":
        _need(ev, "author", "attributed_at")
    elif target == "EXPLAINED":
        _need(ev, "method_summary", "explanation_ref")
    elif target == "REPRODUCED":
        _need(ev, "reproducer", "result_hash")
        if ev["result_hash"] != artifact.evidence["T"]["certificate_hash"]:
            raise GateError("reproduction result_hash does not match the verified certificate_hash")
        if ev["reproducer"] == artifact.evidence["T"]["checker"]:
            raise GateError("reproducer must be independent of the original checker")
    elif target == "CANON_READY":
        absent = [d for d in "TPAXR" if d not in artifact.evidence]
        if absent:
            raise GateError(f"readiness vector incomplete: {','.join(absent)}")
    dim = _ESTABLISHES.get(target)
    new_evidence = dict(artifact.evidence)
    if dim:
        new_evidence[dim] = ev
    return _seal(artifact.artifact_id, target, prov, deps, new_evidence, artifact.handle)


def verify_chain(history: Iterable[ProofArtifact]) -> bool:
    """True when every link's prev_handle is the prior handle and every handle re-derives."""
    prev = None
    for a in history:
        if a.prev_handle != prev:
            return False
        if _seal(a.artifact_id, a.state, a.provenance_handles, a.dependency_handles,
                 a.evidence, a.prev_handle).handle != a.handle:
            return False
        prev = a.handle
    return True


def from_formal_result(result: Any, *, artifact_id: str, provenance_handles: Iterable[str] = (),
                       dependency_handles: Iterable[str] = ()) -> ProofArtifact:
    """Graft: a ``FormalProofResult`` becomes a MACHINE_VERIFIED artifact, and nothing further."""
    art = discover(artifact_id, provenance_handles=provenance_handles,
                   dependency_handles=dependency_handles)
    return advance(art, {"checker": f"{result.engine}:{result.theorem_name}",
                         "certificate_hash": result.certificate_hash,
                         "verified": bool(result.verified)})


def canon_candidate(artifact: ProofArtifact) -> dict:
    """Read-only canon-path payload; refuses anything short of CANON_READY."""
    if artifact.state != "CANON_READY":
        raise GateError(f"cannot promote {artifact.state}; only CANON_READY reaches canon")
    return {"artifact_id": artifact.artifact_id, "gate_handle": artifact.handle,
            "provenance_handles": list(artifact.provenance_handles),
            "dependency_handles": list(artifact.dependency_handles),
            "readiness": artifact.readiness}


def epistemic_debt(artifacts: Iterable[ProofArtifact], *, digest_capacity: Optional[int] = None) -> dict:
    """Backlog telemetry. Reads artifacts, never mutates them or their truth state.

    debt = machine-verified artifacts still short of EXPLAINED (verified faster than digested).
    """
    arts = list(artifacts)
    by_state = {s: 0 for s in STATES}
    for a in arts:
        by_state[a.state] += 1
    unexplained = sum(1 for a in arts if "T" in a.evidence and "X" not in a.evidence)
    unattributed = sum(1 for a in arts if "T" in a.evidence and "A" not in a.evidence)
    unreproduced = sum(1 for a in arts if "T" in a.evidence and "R" not in a.evidence)
    report = {"total": len(arts), "by_state": by_state, "verified_unexplained": unexplained,
              "verified_unattributed": unattributed, "verified_unreproduced": unreproduced,
              "debt": unexplained}
    if digest_capacity is not None:
        report["digest_capacity"] = digest_capacity
        report["over_capacity"] = unexplained > digest_capacity
    return report
