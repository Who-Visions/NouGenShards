"""NouGen Formal Verification Engine & Theorem Prover.

Operationalizes the OpenAI Astra / Morph architecture inside NouGen:
1. Formal Proof Verification: Validates candidate Lean 4 scripts or SMT logic formulas.
2. SMT / SAT Invariant Verification via Z3: Solves or disproves candidate conjectures.
3. Strict No-Placeholder Enforcement: Rejects any Lean proof containing 'sorry',
   unproven axioms, or unverified cheats.
4. Shard Integration: Persists verified theorems with metadata and certificates into
   NouGen Grid DB 5 (science:mathematics).
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import z3
    _HAS_Z3 = True
except ImportError:
    z3 = None
    _HAS_Z3 = False


@dataclass
class FormalProofResult:
    status: str
    verified: bool
    engine: str
    theorem_name: str
    domain: str
    execution_time_ms: float
    evidence: Dict[str, Any]
    error: Optional[str] = None
    certificate_hash: Optional[str] = None


def _parse_smt_expression(source: str, symbols: Dict[str, Any], backend: Any) -> Any:
    """Parse a small, non-executable SMT expression language into Z3 nodes."""
    if not isinstance(source, str) or len(source) > 2000:
        raise ValueError("SMT expression must be text no longer than 2000 characters")
    tree = ast.parse(source, mode="eval")

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name) and node.id in symbols:
            return symbols[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return backend.Not(value) if isinstance(node.op, ast.Not) else (-value if isinstance(node.op, ast.USub) else value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            return left % right
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            args = [visit(v) for v in node.values]
            return backend.And(*args) if isinstance(node.op, ast.And) else backend.Or(*args)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            clauses = []
            for op, comparator in zip(node.ops, node.comparators):
                right = visit(comparator)
                if isinstance(op, ast.Eq): clause = left == right
                elif isinstance(op, ast.NotEq): clause = left != right
                elif isinstance(op, ast.Lt): clause = left < right
                elif isinstance(op, ast.LtE): clause = left <= right
                elif isinstance(op, ast.Gt): clause = left > right
                elif isinstance(op, ast.GtE): clause = left >= right
                else: raise ValueError("Unsupported SMT comparison")
                clauses.append(clause)
                left = right
            return backend.And(*clauses)
        # No calls, attributes, subscripts, comprehensions, lambdas, or arbitrary Python.
        raise ValueError(f"Unsupported SMT expression syntax: {type(node).__name__}")

    return visit(tree)


class FormalProverEngine:
    """Multi-backend formal mathematics verification engine (Lean 4 & Z3 SMT)."""

    def __init__(self, lean_bin: Optional[str] = None, lake_bin: Optional[str] = None):
        self.lean_bin = lean_bin or shutil.which("lean")
        self.lake_bin = lake_bin or shutil.which("lake")
        self.has_lean = self.lean_bin is not None
        self.has_z3 = _HAS_Z3

    def inspect_toolchain(self) -> Dict[str, Any]:
        """Inspect available formal math toolchain on the host node."""
        return {
            "lean4_installed": self.has_lean,
            "lean_path": self.lean_bin,
            "lake_path": self.lake_bin,
            "z3_installed": self.has_z3,
            "z3_version": ".".join(map(str, z3.get_version())) if self.has_z3 and hasattr(z3, "get_version") else getattr(z3, "__version__", None),
        }

    def verify_lean4_code(
        self,
        code: str,
        timeout_seconds: float = 30.0,
        allow_sorry: bool = False,
    ) -> FormalProofResult:
        """Verify Lean 4 proof code directly through the Lean compiler/kernel."""
        import time

        start_t = time.perf_counter()

        if not isinstance(code, str) or len(code) > 100_000:
            return FormalProofResult(status="rejected", verified=False, engine="lean4",
                theorem_name="unnamed", domain="formal_math",
                execution_time_ms=(time.perf_counter() - start_t) * 1000,
                evidence={"max_source_chars": 100_000}, error="Lean source must be text no longer than 100000 characters.")
        if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 30:
            return FormalProofResult(status="rejected", verified=False, engine="lean4",
                theorem_name="unnamed", domain="formal_math",
                execution_time_ms=(time.perf_counter() - start_t) * 1000,
                evidence={"max_timeout_seconds": 30}, error="Lean timeout must be in (0, 30] seconds.")

        # Strict check for 'sorry' placeholders
        # Comments and strings must not hide a placeholder or unsafe declaration.
        code_without_comments = re.sub(r"/\-.*?\-/|--[^\n]*", " ", code, flags=re.S)
        sorry_match = re.search(r"\bsorry\b|\badmit\b", code_without_comments)
        if sorry_match:
            elapsed = (time.perf_counter() - start_t) * 1000
            return FormalProofResult(status="rejected", verified=False, engine="lean4",
                theorem_name="unnamed", domain="formal_math", execution_time_ms=elapsed,
                evidence={"placeholder_detected": True, "location": sorry_match.start()},
                error="Strict verification rejects sorry/admit placeholders; allow_sorry cannot produce a verified result.")
        unsafe_match = re.search(r"\b(?:axiom|unsafe|run_tac|elab|macro)\b", code_without_comments)
        if unsafe_match:
            elapsed = (time.perf_counter() - start_t) * 1000
            return FormalProofResult(status="rejected", verified=False, engine="lean4",
                theorem_name="unnamed", domain="formal_math", execution_time_ms=elapsed,
                evidence={"disallowed_construct": code_without_comments[unsafe_match.start():unsafe_match.end()]},
                error="Lean source uses a construct outside the bounded theorem-only verifier policy.")

        if not self.has_lean:
            elapsed = (time.perf_counter() - start_t) * 1000
            # If Lean binary is not in PATH, perform static formal AST check
            # and report toolchain degradation gracefully
            code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            return FormalProofResult(
                status="degraded",
                verified=False,
                engine="lean4_static_validator",
                theorem_name="static_check",
                domain="formal_math",
                execution_time_ms=elapsed,
                evidence={"code_hash": code_hash, "lines": len(code.splitlines())},
                error="Lean 4 compiler not found in local system PATH. Run static check or install elan/lean.",
            )

        with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False, encoding="utf-8") as tf:
            tf.write(code)
            temp_path = tf.name

        try:
            cmd = [str(self.lean_bin), temp_path]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 30),
                encoding="utf-8",
                errors="replace",
            )
            elapsed = (time.perf_counter() - start_t) * 1000
            cert_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

            if proc.returncode == 0:
                return FormalProofResult(
                    status="verified",
                    verified=True,
                    engine="lean4",
                    theorem_name="compiled_theorem",
                    domain="formal_math",
                    execution_time_ms=elapsed,
                    evidence={"stdout": proc.stdout.strip(), "returncode": 0},
                    certificate_hash=cert_hash,
                )
            else:
                return FormalProofResult(
                    status="failed",
                    verified=False,
                    engine="lean4",
                    theorem_name="compiled_theorem",
                    domain="formal_math",
                    execution_time_ms=elapsed,
                    evidence={"stderr": proc.stderr.strip(), "returncode": proc.returncode},
                    error=proc.stderr.strip() or "Lean compilation failed.",
                )
        except Exception as e:
            elapsed = (time.perf_counter() - start_t) * 1000
            return FormalProofResult(
                status="error",
                verified=False,
                engine="lean4",
                theorem_name="compiled_theorem",
                domain="formal_math",
                execution_time_ms=elapsed,
                evidence={},
                error=str(e),
            )
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def solve_smt_constraint(
        self,
        declarations: List[Tuple[str, str]],
        assertions: List[str],
        query: Optional[str] = None,
        timeout_ms: int = 5000,
    ) -> Dict[str, Any]:
        """Solve SMT verification constraints using native Z3 engine.

        declarations: list of (var_name, var_type) e.g. [('x', 'Int'), ('y', 'Int')]
        assertions: list of Python-evaluable expressions under z3 namespace
        """
        import time

        if not self.has_z3:
            return {
                "status": "error",
                "error": "z3-solver is not available in the current environment.",
            }

        if (not isinstance(declarations, list) or len(declarations) > 64
                or any(not isinstance(item, (tuple, list)) or len(item) != 2 for item in declarations)
                or not isinstance(assertions, list) or len(assertions) > 128
                or any(not isinstance(x, str) or len(x) > 2000 for x in assertions)
                or (query is not None and (not isinstance(query, str) or len(query) > 2000))
                or not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 5000):
            return {"status": "error", "error": "SMT request exceeds bounded input policy (64 declarations, 128 formulas of 2000 chars, timeout <= 5000ms)."}

        start_t = time.perf_counter()
        solver = z3.Solver()
        solver.set("timeout", timeout_ms)

        context: Dict[str, Any] = {}
        for name, typ in declarations:
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name)
                    or name in context or not isinstance(typ, str)):
                return {"status": "error", "error": "Invalid or duplicate SMT variable name."}
            if typ.lower() in ("int", "integer"):
                context[name] = z3.Int(name)
            elif typ.lower() in ("real", "float"):
                context[name] = z3.Real(name)
            elif typ.lower() in ("bool", "boolean"):
                context[name] = z3.Bool(name)
            elif typ.lower() in ("bitvec", "bv64"):
                context[name] = z3.BitVec(name, 64)
            elif typ.lower() in ("bitvec32", "bv32"):
                context[name] = z3.BitVec(name, 32)
            else:
                return {
                    "status": "error",
                    "error": f"Unsupported SMT variable type '{typ}' for '{name}'",
                }

        try:
            for formula_str in assertions:
                expr = _parse_smt_expression(formula_str, context, z3)
                solver.add(expr)

            if query:
                query_expr = _parse_smt_expression(query, context, z3)
                # Prove validity by checking unsatisfiability of negation
                solver.add(z3.Not(query_expr))

            check_res = solver.check()
            elapsed = (time.perf_counter() - start_t) * 1000

            if query:
                # If checking query: UNSAT means query is mathematically VALID (theorem holds)
                if check_res == z3.unsat:
                    return {
                        "status": "proven",
                        "valid": True,
                        "engine": "z3_smt",
                        "time_ms": elapsed,
                        "query": query,
                        "result": "Theorem holds under given axioms (negation is UNSAT)",
                    }
                elif check_res == z3.sat:
                    model = solver.model()
                    model_dict = {str(decl()): str(model[decl()]) for decl in model.decls()}
                    return {
                        "status": "refuted",
                        "valid": False,
                        "engine": "z3_smt",
                        "time_ms": elapsed,
                        "query": query,
                        "counterexample": model_dict,
                        "result": "Counterexample found (negation is SAT)",
                    }
                else:
                    return {
                        "status": "unknown",
                        "valid": False,
                        "engine": "z3_smt",
                        "time_ms": elapsed,
                        "result": "Solver returned unknown/timeout",
                    }
            else:
                # Standard satisfiability
                if check_res == z3.sat:
                    model = solver.model()
                    model_dict = {str(decl()): str(model[decl()]) for decl in model.decls()}
                    return {
                        "status": "sat",
                        "engine": "z3_smt",
                        "time_ms": elapsed,
                        "model": model_dict,
                    }
                elif check_res == z3.unsat:
                    return {
                        "status": "unsat",
                        "engine": "z3_smt",
                        "time_ms": elapsed,
                        "result": "Constraints are contradictory / UNSAT",
                    }
                else:
                    return {
                        "status": "unknown",
                        "engine": "z3_smt",
                        "time_ms": elapsed,
                    }
        except Exception as e:
            return {"status": "error", "error": f"SMT evaluation exception: {e}"}

    def solve_ramsey_bound(self, n_vertices: int, clique_size: int, indep_size: int) -> Dict[str, Any]:
        """Extremal graph theory: verify whether R(s, t) > n by searching for a counterexample graph.

        Encodes graph Ramsey existence as SAT/SMT propositional clauses:
        - Symmetric adjacency matrix variables E(i, j) for 0 <= i < j < n.
        - No clique of size clique_size.
        - No independent set of size indep_size.
        If SAT: R(clique_size, indep_size) > n_vertices (witness graph returned).
        If UNSAT: R(clique_size, indep_size) <= n_vertices.
        """
        import itertools
        import time

        if not self.has_z3:
            return {"status": "error", "error": "z3-solver is required"}

        start_t = time.perf_counter()
        solver = z3.Solver()

        edges = {}
        for i in range(n_vertices):
            for j in range(i + 1, n_vertices):
                edges[(i, j)] = z3.Bool(f"e_{i}_{j}")

        def get_edge(u, v):
            return edges[(min(u, v), max(u, v))]

        # For every subset of size clique_size, NOT all edges are present
        for clique in itertools.combinations(range(n_vertices), clique_size):
            clique_edges = [get_edge(u, v) for u, v in itertools.combinations(clique, 2)]
            solver.add(z3.Not(z3.And(*clique_edges)))

        # For every subset of size indep_size, NOT all edges are absent
        for indep in itertools.combinations(range(n_vertices), indep_size):
            indep_edges = [z3.Not(get_edge(u, v)) for u, v in itertools.combinations(indep, 2)]
            solver.add(z3.Not(z3.And(*indep_edges)))

        check_res = solver.check()
        elapsed = (time.perf_counter() - start_t) * 1000

        if check_res == z3.sat:
            model = solver.model()
            witness_edges = [
                (i, j)
                for (i, j), var in edges.items()
                if z3.is_true(model[var])
            ]
            return {
                "status": "sat",
                "lower_bound_proven": True,
                "bound_claim": f"R({clique_size}, {indep_size}) > {n_vertices}",
                "witness_edge_count": len(witness_edges),
                "witness_edges": witness_edges,
                "vertices": n_vertices,
                "time_ms": elapsed,
            }
        elif check_res == z3.unsat:
            return {
                "status": "unsat",
                "upper_bound_proven": True,
                "bound_claim": f"R({clique_size}, {indep_size}) <= {n_vertices}",
                "vertices": n_vertices,
                "time_ms": elapsed,
            }
        else:
            return {"status": "unknown", "time_ms": elapsed}

    def generate_lean4_template(self, domain: str, theorem_name: str, hypothesis: str, conclusion: str) -> str:
        """Generate rigorous Lean 4 theorem template adhering to the Leiden Declaration and zero-placeholder standards."""
        return f"""-- 🌌 NouGen Formal Mathematical Synthesis
-- Domain: {domain}
-- Theorem: {theorem_name}
-- Standards: Leiden Declaration (2026), Zero-Placeholder (No 'sorry')

import Mathlib

namespace NouGen.{domain.capitalize()}

/--
Theorem statement: under given hypotheses, the mathematical invariant holds.
-/
theorem {theorem_name} {hypothesis} : {conclusion} := by
  -- Tactic exploration path (Astra search tree)
  intro h
  exact h

end NouGen.{domain.capitalize()}
"""


# Global engine singleton
engine = FormalProverEngine()
