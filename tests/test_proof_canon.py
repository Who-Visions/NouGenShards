"""Proof-to-Canon gate: machine-verified is not canon-ready."""
import copy

import pytest

from nougen_shards import proof_canon as pc
from nougen_shards.formal_prover import FormalProofResult

CERT = "c" * 64
EVIDENCE = [
    {"checker": "lean4:thm", "certificate_hash": CERT, "verified": True},
    {"provenance_handles": ["src:arxiv:2609.1"]},
    {"author": "agent-a", "attributed_at": "2026-10-03T12:00:00-04:00"},
    {"method_summary": "induction on n", "explanation_ref": "#expl-1"},
    {"reproducer": "node-b", "result_hash": CERT},
]


def _climb(upto):
    a = pc.discover("thm-1", provenance_handles=["src:paper"], dependency_handles=["dep:lemma-9"])
    hist = [a]
    for ev in EVIDENCE[:upto]:
        a = pc.advance(a, ev)
        hist.append(a)
    return a, hist


def test_full_climb_reaches_canon_ready_with_complete_vector():
    a, hist = _climb(5)
    a = pc.advance(a, {})
    assert a.state == "CANON_READY" and a.readiness == dict.fromkeys("TPAXR", True)
    assert pc.canon_candidate(a)["gate_handle"] == a.handle


@pytest.mark.parametrize("upto", [1, 2, 3, 4, 5])
def test_nothing_short_of_canon_ready_reaches_canon(upto):
    a, _ = _climb(upto)
    with pytest.raises(pc.GateError):
        pc.canon_candidate(a)


def test_machine_verified_but_unattributed_unexplained_cannot_be_canon_ready():
    a, _ = _climb(2)  # verified + provenance linked, no A / X / R
    assert a.readiness["T"] and not a.readiness["A"] and not a.readiness["X"]
    with pytest.raises(pc.GateError, match="missing evidence: author"):
        pc.advance(a, {})
    with pytest.raises(pc.GateError):
        pc.canon_candidate(a)


def test_no_skipping_each_step_demands_its_own_evidence():
    a = pc.discover("x")
    with pytest.raises(pc.GateError):
        pc.advance(a, {"verified": False, "checker": "c", "certificate_hash": CERT})
    with pytest.raises(pc.GateError):
        pc.advance(a, {"author": "a", "attributed_at": "t"})  # wrong evidence for this step
    assert a.state == "DISCOVERED"


def test_reproduction_must_match_certificate_and_be_independent():
    a, _ = _climb(4)
    with pytest.raises(pc.GateError, match="does not match"):
        pc.advance(a, {"reproducer": "node-b", "result_hash": "0" * 64})
    with pytest.raises(pc.GateError, match="independent"):
        pc.advance(a, {"reproducer": "lean4:thm", "result_hash": CERT})


def test_handles_survive_every_transition_and_chain_verifies():
    _, hist = _climb(5)
    hist.append(pc.advance(hist[-1], {}))
    for a in hist:
        assert "dep:lemma-9" in a.dependency_handles and "src:paper" in a.provenance_handles
    assert "src:arxiv:2609.1" in hist[-1].provenance_handles
    assert pc.verify_chain(hist)
    tampered = copy.copy(hist[3])
    object.__setattr__(tampered, "state", "CANON_READY")
    assert not pc.verify_chain(hist[:3] + [tampered])


def test_provenance_step_needs_at_least_one_handle():
    a = pc.advance(pc.discover("x"), EVIDENCE[0])
    with pytest.raises(pc.GateError, match="provenance_handles"):
        pc.advance(a, {})


def test_epistemic_debt_reports_backlog_without_mutating_truth_state():
    verified_only = [pc.advance(pc.discover(f"a{i}"), EVIDENCE[0]) for i in range(5)]
    explained, _ = _climb(4)
    pool = verified_only + [explained]
    before = [(a.state, a.handle, dict(a.readiness)) for a in pool]
    rep = pc.epistemic_debt(pool, digest_capacity=3)
    assert rep["debt"] == 5 and rep["over_capacity"] is True
    assert rep["by_state"]["MACHINE_VERIFIED"] == 5 and rep["verified_unreproduced"] == 6
    assert before == [(a.state, a.handle, dict(a.readiness)) for a in pool]


def test_formal_result_grafts_to_machine_verified_only():
    res = FormalProofResult(status="proved", verified=True, engine="z3", theorem_name="t",
                            domain="math", execution_time_ms=1.0, evidence={}, certificate_hash=CERT)
    a = pc.from_formal_result(res, artifact_id="t1", provenance_handles=["src:x"])
    assert a.state == "MACHINE_VERIFIED" and a.readiness == {"T": True, "P": False, "A": False, "X": False, "R": False}
    with pytest.raises(pc.GateError):
        pc.canon_candidate(a)
    bad = FormalProofResult(status="failed", verified=False, engine="z3", theorem_name="t",
                            domain="math", execution_time_ms=1.0, evidence={}, certificate_hash=None)
    with pytest.raises(pc.GateError):
        pc.from_formal_result(bad, artifact_id="t2")


def test_real_prover_result_cannot_shortcut_to_canon():
    from nougen_shards.formal_prover import FormalProverEngine
    eng = FormalProverEngine()
    try:
        res = eng.solve_ramsey_bound(3, 3, 3)
    except Exception as exc:  # toolchain absent
        pytest.skip(f"prover backend unavailable: {exc}")
    r = FormalProofResult(status="proved", verified=True, engine="ramsey", theorem_name="R33",
                          domain="combinatorics", execution_time_ms=0.0, evidence=res, certificate_hash=CERT)
    assert pc.from_formal_result(r, artifact_id="R33").state == "MACHINE_VERIFIED"
