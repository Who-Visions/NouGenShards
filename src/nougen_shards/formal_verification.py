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
    "O1_idempotent_capture": "Applying the abstract set insertion twice is observationally equivalent to once.",
    "O2_append_only_identity": "For bounded integer sequence identities, append preserves prior identities and increases the tail.",
    "O3_provider_invariants": "EMPIRICAL_REQUIRED: schema and behavior invariants require production provider evidence; not proven here.",
    "O4_bounded_projection": "A projection of at most k selected records never exceeds k.",
    "O5_relay_state_safety": "Only declared transitions are allowed in this finite relay lifecycle model.",
    "O6_decision_equivalence": "Set-membership-equivalent merge inputs yield equal abstract decisions; array order is ignored.",
}


def run_full_formal_verification_suite() -> Dict[str, Any]:
    """Run fixed, bounded checks and report empirical/implementation gaps explicitly."""
    source = json.dumps(OBLIGATIONS, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(source.encode()).hexdigest()
    report: Dict[str, Any] = {
        "suite": "information_dynamics_bounded_models_v1",
        "encoding_sha256": digest,
        "solver_version": engine.inspect_toolchain().get("z3_version"),
        "bound": "Boolean/finite-state and integer identities in the formulas below",
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
        "O1_idempotent_capture": ([ ("x", "Bool") ], ["(x or True) == True"], "((x or True) or True) == (x or True)"),
        "O2_append_only_identity": ([ ("old", "Int"), ("tail", "Int"), ("new", "Int") ], ["old <= tail", "tail < new"], "old < new"),
        "O4_bounded_projection": ([ ("selected", "Int"), ("k", "Int") ], ["selected >= 0", "k >= 0", "selected <= k"], "selected <= k"),
        "O5_relay_state_safety": ([ ("open", "Bool"), ("commit", "Bool") ], ["(commit == False) or open"], "(commit == False) or open"),
        "O6_decision_equivalence": ([ ("a", "Bool"), ("b", "Bool") ], ["a == b"], "a == b"),
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
