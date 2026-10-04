"""
NouGenCode Intelligence & Cleanup Scoring Engine.
Implements deterministic scoring formulas for code optimization, refactoring triage,
dead code elimination, and trust-boundary security assessment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Set


def compute_intelligence_density(unique_tokens: int, capabilities: int, loc: int) -> float:
    """
    Computes Intelligence Density:
    Density = (UniqueTokens * VerifiedCapabilities) / (LOC + 1)
    """
    if loc < 0 or capabilities < 0 or unique_tokens < 0:
        raise ValueError("Inputs to intelligence density must be non-negative")
    raw = (unique_tokens * max(1, capabilities)) / (loc + 1)
    return round(raw, 4)


def compute_repair_priority(severity: float, blast_radius: float, complexity: float) -> float:
    """
    Computes Repair Priority Score:
    Priority = (Severity * BlastRadius) / (Complexity + 1)
    """
    if severity < 0 or blast_radius < 0 or complexity < 0:
        raise ValueError("Inputs to repair priority must be non-negative")
    raw = (severity * blast_radius) / (complexity + 1.0)
    return round(raw, 4)


def compute_redundancy_similarity(tokens_a: Set[str], tokens_b: Set[str]) -> float:
    """
    Computes Sørensen-Dice redundancy similarity between two token sets:
    Similarity = 2 * |A ∩ B| / (|A| + |B|)
    """
    total = len(tokens_a) + len(tokens_b)
    if total == 0:
        return 0.0
    intersection = len(tokens_a.intersection(tokens_b))
    return round((2.0 * intersection) / total, 4)


def compute_refactor_value(loc_delta: int, maintenance_multiplier: float = 1.2, regression_risk: float = 0.1) -> float:
    """
    Computes Net Value of Delete / Merge / Parameterization Refactor:
    Value = (DeltaLOC * MaintenanceMultiplier) - RegressionRisk
    """
    val = (loc_delta * maintenance_multiplier) - regression_risk
    return round(val, 4)


def compute_dead_code_probability(reference_count: int, max_expected_refs: int = 10) -> float:
    """
    Computes Dead Code Probability:
    Prob = 1.0 - (ReferenceCount / MaxExpectedRefs)
    Clamped to [0.0, 1.0].
    """
    if reference_count <= 0:
        return 1.0
    if reference_count >= max_expected_refs:
        return 0.0
    return round(1.0 - (reference_count / max_expected_refs), 4)


def compute_trust_boundary_risk(unsanitized_inputs: int, privilege_level: int, network_exposure: float) -> float:
    """
    Computes Trust-Boundary Security Risk:
    Risk = UnsanitizedInputs * PrivilegeLevel * NetworkExposure
    """
    if unsanitized_inputs < 0 or privilege_level < 0 or network_exposure < 0:
        raise ValueError("Risk parameters must be non-negative")
    return round(float(unsanitized_inputs * privilege_level * network_exposure), 4)


def evaluate_refactor_acceptance(
    tests_passing: bool,
    capability_loss: int,
    old_density: float,
    new_density: float,
) -> bool:
    """
    Evaluates Refactor Acceptance Gate:
    Acceptance = (TestsPassing == True) AND (CapabilityLoss == 0) AND (NewDensity >= OldDensity)
    """
    return bool(tests_passing and capability_loss == 0 and new_density >= old_density)


def compute_simplification_gain(old_complexity: float, new_complexity: float) -> float:
    """
    Computes Simplification Gain percentage:
    Gain = ((OldComplexity - NewComplexity) / OldComplexity) * 100%
    """
    if old_complexity <= 0:
        return 0.0
    gain = ((old_complexity - new_complexity) / old_complexity) * 100.0
    return round(gain, 2)


@dataclass
class CodeAuditReport:
    file_path: str
    loc: int
    unique_tokens: int
    capabilities: int
    intelligence_density: float
    dead_code_probability: float
    trust_boundary_risk: float
    refactor_candidate: bool
    refactor_reason: str


class NouGenCodeAuditor:
    """Deterministic Code Auditor for NouGen Fleet repositories."""

    @staticmethod
    def audit_source_text(source_text: str, file_name: str = "module.py", ref_count: int = 5) -> CodeAuditReport:
        lines = [l for l in source_text.splitlines() if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("//")]
        loc = len(lines)
        
        # Token extraction
        tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", source_text))
        unique_tokens = len(tokens)
        
        # Approximate capability functions / exports
        capabilities = max(1, len(re.findall(r"(def |class |export function |export const )", source_text)))
        
        density = compute_intelligence_density(unique_tokens, capabilities, loc)
        dead_prob = compute_dead_code_probability(ref_count)
        
        # Check for potential injection / unsanitized points
        unsanitized = len(re.findall(r"(eval\(|innerHTML|exec\(|subprocess\.Popen\([^,]*shell=True)", source_text))
        trust_risk = compute_trust_boundary_risk(unsanitized, privilege_level=2, network_exposure=0.5)
        
        refactor_candidate = False
        reason = "Clean"
        if dead_prob >= 0.8:
            refactor_candidate = True
            reason = "High dead code probability"
        elif trust_risk > 1.0:
            refactor_candidate = True
            reason = "Trust boundary risk detected"
        elif loc > 250 and density < 2.0:
            refactor_candidate = True
            reason = "Low intelligence density / high boilerplate"

        return CodeAuditReport(
            file_path=file_name,
            loc=loc,
            unique_tokens=unique_tokens,
            capabilities=capabilities,
            intelligence_density=density,
            dead_code_probability=dead_prob,
            trust_boundary_risk=trust_risk,
            refactor_candidate=refactor_candidate,
            refactor_reason=reason,
        )
