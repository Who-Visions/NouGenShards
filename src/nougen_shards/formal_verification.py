"""Bounded model checks for the information-dynamics proof obligations.

These checks establish properties of the finite SMT encodings only. They do not
establish that production implementations refine those encodings.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .formal_prover import engine


OBLIGATIONS = {
    "O1_idempotent_capture": "Applying Boolean set insertion twice is observationally equivalent to once.",
    "O2_append_only_identity": "For bounded integer identities, appending after the tail preserves prior order.",
    "O3_provider_invariants": "EMPIRICAL_REQUIRED: schema and behavior invariants require production provider evidence; not proven here.",
    "O4_bounded_projection": "The bounded min(count, k) projection contains between zero and k records.",
    "O5_relay_state_safety": "Every declared transition in the three-state lifecycle stays within valid states.",
    "O6_decision_equivalence": "The two-element membership decision is invariant under merge input permutation.",
}


def run_full_formal_verification_suite() -> Dict[str, Any]:
    """Run fixed, bounded checks and report empirical/implementation gaps explicitly."""
    source = json.dumps(OBLIGATIONS, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(source.encode()).hexdigest()
    report: Dict[str, Any] = {
        "suite": "information_dynamics_bounded_models_v1",
        "encoding_sha256": digest,
        "solver_version": engine.inspect_toolchain().get("z3_version"),
        "bound": "Two Boolean membership bits; three-state lifecycle; integer counts, limits, and identities bounded to 0..5",
        "assumptions": ["Each formula is an abstraction, not an implementation refinement proof.",
                        "O3 provider behavior is empirical and is never labeled proven."],
        "obligations": {},
        "implementation_refinement": "not_established",
    }
    if not engine.has_z3:
        report["status"] = "unavailable"
        report["error"] = "z3-solver is unavailable; no obligation was evaluated."
        for key, statement in OBLIGATIONS.items():
            report["obligations"][key] = {"status": "not_run", "statement": statement}
        return report

    checks = {
        "O1_idempotent_capture": ([ ("x", "Bool"), ("event", "Bool") ], [], "((x or event) or event) == (x or event)"),
        "O2_append_only_identity": ([ ("old", "Int"), ("tail", "Int"), ("new", "Int") ], ["old >= 0", "old <= tail", "tail < new", "new <= 5"], "old < new"),
        "O4_bounded_projection": ([ ("count", "Int"), ("k", "Int"), ("selected", "Int") ], ["count >= 0", "count <= 5", "k >= 0", "k <= 5", "(count <= k and selected == count) or (k < count and selected == k)"], "selected >= 0 and selected <= k"),
        "O5_relay_state_safety": ([ ("state", "Int"), ("action", "Int"), ("next_state", "Int") ], ["state >= 0", "state <= 2", "action >= 0", "action <= 2", "(action == 0 and next_state == state) or (action == 1 and state == 0 and next_state == 1) or (action == 2 and (state == 0 or state == 1) and next_state == 2)"], "next_state >= 0 and next_state <= 2"),
        "O6_decision_equivalence": ([ ("a", "Bool"), ("b", "Bool") ], [], "(a or b) == (b or a)"),
    }
    for key, statement in OBLIGATIONS.items():
        if key == "O3_provider_invariants":
            report["obligations"][key] = {"status": "empirical_required", "statement": statement}
            continue
        declarations, assumptions, property_formula = checks[key]
        result = engine.solve_smt_constraint(declarations, assumptions, query=property_formula)
        report["obligations"][key] = {
            "status": "bounded_model_proven" if result.get("status") == "proven" else result.get("status", "error"),
            "statement": statement,
            "bound": len(declarations),
            "assumptions": assumptions,
            "solver_result": result,
        }
    statuses = [item["status"] for item in report["obligations"].values()]
    report["status"] = "bounded_checks_complete" if all(s in ("bounded_model_proven", "empirical_required") for s in statuses) else "incomplete"
    return report
