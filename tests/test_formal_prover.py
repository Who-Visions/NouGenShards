"""Tests for NouGen Formal Prover Engine (Lean 4 & Z3 SMT solver)."""
import pytest
from nougen_shards.formal_prover import FormalProverEngine, engine


def test_toolchain_inspection():
    tc = engine.inspect_toolchain()
    assert isinstance(tc, dict)
    assert "z3_installed" in tc
    assert tc["z3_installed"] is True


def test_lean4_strict_rejection_of_sorry():
    bad_code = """
theorem fake_proof (n : Nat) : n + 1 = 1 + n := by
  sorry
"""
    res = engine.verify_lean4_code(bad_code, allow_sorry=False)
    assert res.status == "rejected"
    assert res.verified is False
    assert "sorry" in (res.error or "").lower()


def test_z3_satisfiability():
    # Find x > 10 and x < 20
    decls = [("x", "Int")]
    assertions = ["x > 10", "x < 20"]
    res = engine.solve_smt_constraint(decls, assertions)
    assert res["status"] == "sat"
    assert "x" in res["model"]
    val = int(res["model"]["x"])
    assert 10 < val < 20


def test_z3_unsat_contradiction():
    # Contradiction: x > 5 and x < 3
    decls = [("x", "Int")]
    assertions = ["x > 5", "x < 3"]
    res = engine.solve_smt_constraint(decls, assertions)
    assert res["status"] == "unsat"


def test_z3_theorem_proving_valid():
    # Prove De Morgan's Law for boolean logic: not (A and B) == (not A or not B)
    decls = [("a", "Bool"), ("b", "Bool")]
    assertions = []  # no extra axioms
    query = "z3.Not(z3.And(a, b)) == z3.Or(z3.Not(a), z3.Not(b))"
    res = engine.solve_smt_constraint(decls, assertions, query=query)
    assert res["status"] == "proven"
    assert res["valid"] is True


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
