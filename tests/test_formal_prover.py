"""Tests for NouGen Formal Prover Engine (Lean 4 & Z3 SMT solver)."""
import pytest
from nougen_shards.formal_prover import engine
from nougen_shards.formal_prover import _parse_smt_expression


def test_toolchain_inspection():
    tc = engine.inspect_toolchain()
    assert isinstance(tc, dict)
    assert "z3_installed" in tc
    assert "lean4_installed" in tc


def test_lean4_strict_rejection_of_sorry():
    bad_code = """
theorem fake_proof (n : Nat) : n + 1 = 1 + n := by
  sorry
"""
    res = engine.verify_lean4_code(bad_code, allow_sorry=False)
    assert res.status == "rejected"
    assert res.verified is False
    assert "sorry" in (res.error or "").lower()


def test_allow_sorry_never_reports_verified():
    res = engine.verify_lean4_code("theorem fake : True := by sorry", allow_sorry=True)
    assert res.status == "rejected"
    assert res.verified is False


def test_smt_expression_rejects_python_execution():
    with pytest.raises(ValueError):
        _parse_smt_expression("z3.__dict__", {}, None)
    with pytest.raises(ValueError):
        _parse_smt_expression("__import__('os').system('true')", {}, None)


def test_formal_suite_module_is_importable_and_honest_without_z3():
    from nougen_shards.formal_verification import run_full_formal_verification_suite
    report = run_full_formal_verification_suite()
    assert report["suite"] == "information_dynamics_bounded_models_v1"
    assert report["implementation_refinement"] == "not_established"
    assert report["obligations"]["O3_provider_invariants"]["status"] in ("empirical_required", "not_run")
    if not engine.has_z3:
        assert report["status"] == "unavailable"


def test_formal_suite_is_registered_in_fleet_proxy():
    from pathlib import Path
    proxy = Path(__file__).resolve().parents[1] / "tools" / "nougen-fleet-mcp-patched.js"
    source = proxy.read_text(encoding="utf-8")
    assert '"name": "formal_verification_suite"' in source
    assert "async formal_verification_suite(args, env)" in source


@pytest.mark.skipif(not engine.has_z3, reason="z3-solver not installed")
def test_z3_satisfiability():
    # Find x > 10 and x < 20
    decls = [("x", "Int")]
    assertions = ["x > 10", "x < 20"]
    res = engine.solve_smt_constraint(decls, assertions)
    assert res["status"] == "sat"
    assert "x" in res["model"]
    val = int(res["model"]["x"])
    assert 10 < val < 20


@pytest.mark.skipif(not engine.has_z3, reason="z3-solver not installed")
def test_z3_unsat_contradiction():
    # Contradiction: x > 5 and x < 3
    decls = [("x", "Int")]
    assertions = ["x > 5", "x < 3"]
    res = engine.solve_smt_constraint(decls, assertions)
    assert res["status"] == "unsat"


@pytest.mark.skipif(not engine.has_z3, reason="z3-solver not installed")
def test_z3_theorem_proving_valid():
    # Prove De Morgan's Law for boolean logic: not (A and B) == (not A or not B)
    decls = [("a", "Bool"), ("b", "Bool")]
    assertions = []  # no extra axioms
    query = "z3.Not(z3.And(a, b)) == z3.Or(z3.Not(a), z3.Not(b))"
    res = engine.solve_smt_constraint(decls, assertions, query=query)
    assert res["status"] == "proven"
    assert res["valid"] is True


@pytest.mark.skipif(not engine.has_z3, reason="z3-solver not installed")
def test_z3_theorem_refutation_with_counterexample():
    # Disprove false conjecture: for all integers x, x > 0 implies x * x > 1
    # Counterexample is x = 1 where 1 * 1 = 1 which is not > 1
    decls = [("x", "Int")]
    assertions = ["x > 0"]
    query = "x * x > 1"
    res = engine.solve_smt_constraint(decls, assertions, query=query)
    assert res["status"] == "refuted"
    assert res["valid"] is False
    assert "counterexample" in res
    assert res["counterexample"].get("x") == "1"


@pytest.mark.skipif(not engine.has_z3, reason="z3-solver not installed")
def test_ramsey_exact_bound_r33():
    # R(3,3) is exactly 6:
    # 1. A 5-cycle graph has no triangle and no independent set of size 3 -> R(3,3) > 5 (SAT)
    res5 = engine.solve_ramsey_bound(n_vertices=5, clique_size=3, indep_size=3)
    assert res5["status"] == "sat"
    assert res5["lower_bound_proven"] is True
    assert res5["witness_edge_count"] == 5

    # 2. Every 2-coloring of K_6 contains a monochromatic triangle -> R(3,3) <= 6 (UNSAT)
    res6 = engine.solve_ramsey_bound(n_vertices=6, clique_size=3, indep_size=3)
    assert res6["status"] == "unsat"
    assert res6["upper_bound_proven"] is True
