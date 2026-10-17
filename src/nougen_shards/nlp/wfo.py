"""
NouGenMorph NLP Engine — Module 1: Well-Formed Outcome (WFO) Validator.

Provenance:
- Source: Christopher Howard, Breakthrough to Success (CD 5: The Blueprints of the Mind & Workbook)
- War-Gamed & Drafted By: Free Fleet Lane (`ollama-cloud-ediebrikell12` / `ollama-cloud-eatsruger`) + Local `gemma4:e2b-qat`
- Reviewed By: Antigravity Coach (UDCT Architecture Solver)
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Union


NEGATION_PATTERNS = re.compile(
    r"\b(not|never|no\s+longer|stop|avoid|quit|don't|dont|won't|wont|can't|cant|without|less\s+of|rid\s+of|escape|prevent)\b",
    re.IGNORECASE,
)

SENSORY_PATTERNS = re.compile(
    r"(?:\$\d+|\d+(?:x|k|m|ms|s|gb|mb|tb|h|%)?|\b(?:see|hear|feel|touch|sound|look|bright|clear|voice|metric|pass|test|percent|ms|gb|mb|usd|green|verified|verify|log|output|concrete|visible|audible|tangible|ship|deploy|complete|deliver|engineer|build)\b)",
    re.IGNORECASE,
)

CONTEXT_PATTERNS = re.compile(
    r"\b(when|where|by\s+\w+|on\s+\w+|at\s+\w+|in\s+\w+|during|within|deadline|date|time|node|apollo|hyperion|phoebus|whoart|blade|production|staging|repo|branch|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)

META_PATTERNS = re.compile(
    r"\b(so\s+that|in\s+order\s+to|because|for\s+the\s+purpose|unlock|enable|empower|revenue|roi|freedom|security|belonging|competence|expression|scale|autonomy|value)\b",
    re.IGNORECASE,
)

ECOLOGY_RISK_PATTERNS = re.compile(
    r"\b(destroy\s+all|wipe\s+prod|force\s+push|drop\s+table|delete\s+database|burn\s+out|sacrifice\s+health|break\s+other|ignore\s+safety|bypass\s+gate)\b",
    re.IGNORECASE,
)

EXTERNAL_DEPENDENCY_PATTERNS = re.compile(
    r"\b(make\s+them|force\s+him|force\s+her|wait\s+for\s+luck|hope\s+they|if\s+they\s+let\s+me|depends\s+entirely\s+on\s+others|someone\s+else\s+must)\b",
    re.IGNORECASE,
)

AGENCY_PATTERNS = re.compile(
    r"\b(i\s+will|i\s+am|we\s+will|we\s+build|execute|implement|deliver|create|design|verify|own|commit|ship|deploy|achieve|construct)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WFOCriterionResult:
    """Evaluation result for a single WFO criterion."""

    key: str
    index: int
    name: str
    passed: bool
    score: float
    evidence: str
    remediation: Optional[str] = None


@dataclass(frozen=True)
class WFOResult:
    """Aggregate deterministic evaluation of a 10-point Well-Formed Outcome."""

    goal: str
    passed: bool
    score: float
    passed_count: int
    total_criteria: int
    criteria: Dict[str, WFOCriterionResult] = field(default_factory=dict)
    remediations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "passed": self.passed,
            "score": round(self.score, 4),
            "passed_count": self.passed_count,
            "total_criteria": self.total_criteria,
            "criteria": {
                k: {
                    "index": v.index,
                    "name": v.name,
                    "passed": v.passed,
                    "score": round(v.score, 4),
                    "evidence": v.evidence,
                    "remediation": v.remediation,
                }
                for k, v in self.criteria.items()
            },
            "remediations": list(self.remediations),
        }


class WFOEngine:
    """
    Deterministic 10-Criterion Well-Formed Outcome (WFO) Validator.

    The 10 Canonical WFO Criteria:
    1. positive_terms: Stated in positive terms (what you want, not what you want to avoid).
    2. sensory_specific: Measurable, observable VAK (Visual/Auditory/Kinesthetic) or metric proof.
    3. context_defined: Grounded in specific Where, When, and With Whom context.
    4. meta_outcome: Clear higher-level purpose ('so that...' / ROI / driver alignment).
    5. ecology_safe: Systemic impact audited; preserves health, fleet integrity, and relationships.
    6. self_initiated: Owned and maintained by the actor (Cause > Effect, C > E).
    7. contrast_leverage: Contrast Island leverage established (cost of inaction vs reward of action).
    8. ras_tuned: Reticular Activating System tuned to possibilities and resources.
    9. attractor_basin: Backed by 7-10 reference successes or concrete incremental steps.
    10. submodality_locked: Submodality dashboard parameters locked (bright, close, panoramic, resonant).
    """

    CRITERIA_META = (
        ("positive_terms", 1, "Stated in Positive Terms"),
        ("sensory_specific", 2, "Sensory Specific & Measurable"),
        ("context_defined", 3, "Contextualized (Where/When)"),
        ("meta_outcome", 4, "Meta-Outcome & Purpose"),
        ("ecology_safe", 5, "Systemic Ecology Verified"),
        ("self_initiated", 6, "Self-Initiated & Maintained (C > E)"),
        ("contrast_leverage", 7, "Contrast Island Leverage"),
        ("ras_tuned", 8, "RAS Possibility Tuning"),
        ("attractor_basin", 9, "Attractor Basin (7-10 Proofs/Steps)"),
        ("submodality_locked", 10, "Submodality Dashboard Locked"),
    )

    def __init__(self, pass_threshold: float = 0.8):
        if not 0.0 <= pass_threshold <= 1.0:
            raise ValueError("pass_threshold must be between 0.0 and 1.0")
        self.pass_threshold = pass_threshold

    def evaluate(self, outcome: Union[str, Dict[str, Any]]) -> WFOResult:
        """Evaluate a goal string or structured outcome specification against all 10 WFO criteria."""
        if isinstance(outcome, str):
            spec: Dict[str, Any] = {"goal": outcome.strip()}
        elif isinstance(outcome, dict):
            spec = dict(outcome)
        else:
            raise TypeError("outcome must be a str or dict")

        goal_text = str(spec.get("goal") or spec.get("title") or spec.get("outcome") or "").strip()
        if not goal_text:
            criteria_map: Dict[str, WFOCriterionResult] = {}
            rems: List[str] = []
            for key, idx, name in self.CRITERIA_META:
                rem = f"Provide a non-empty goal statement to evaluate {name}."
                criteria_map[key] = WFOCriterionResult(
                    key=key,
                    index=idx,
                    name=name,
                    passed=False,
                    score=0.0,
                    evidence="Empty goal statement",
                    remediation=rem,
                )
                rems.append(rem)
            return WFOResult(
                goal="",
                passed=False,
                score=0.0,
                passed_count=0,
                total_criteria=10,
                criteria=criteria_map,
                remediations=rems,
            )

        results: Dict[str, WFOCriterionResult] = {}

        # 1. Positive Terms
        neg_matches = NEGATION_PATTERNS.findall(goal_text)
        explicit_pos = spec.get("positive_terms")
        if explicit_pos is not None:
            c1_pass = bool(explicit_pos) and len(neg_matches) == 0
        else:
            c1_pass = len(neg_matches) == 0
        results["positive_terms"] = WFOCriterionResult(
            key="positive_terms",
            index=1,
            name="Stated in Positive Terms",
            passed=c1_pass,
            score=1.0 if c1_pass else 0.0,
            evidence="Zero negation tokens detected" if c1_pass else f"Negation tokens found: {neg_matches}",
            remediation=None if c1_pass else "Reframe what you want to create positively instead of what you want to avoid or stop.",
        )

        # 2. Sensory Specific
        sensory_text = f"{goal_text} {spec.get('sensory_evidence', '')} {spec.get('metrics', '')}"
        s_matches = SENSORY_PATTERNS.findall(sensory_text)
        c2_pass = bool(spec.get("sensory_specific")) or len(s_matches) >= 1
        results["sensory_specific"] = WFOCriterionResult(
            key="sensory_specific",
            index=2,
            name="Sensory Specific & Measurable",
            passed=c2_pass,
            score=1.0 if c2_pass else 0.0,
            evidence=f"Sensory/metric markers: {s_matches[:4]}" if c2_pass else "No VAK or measurable evidence markers",
            remediation=None if c2_pass else "Specify what you will see, hear, feel, or measure when the outcome is achieved.",
        )

        # 3. Context Defined
        ctx_text = f"{goal_text} {spec.get('context', '')} {spec.get('where', '')} {spec.get('when', '')}"
        ctx_matches = CONTEXT_PATTERNS.findall(ctx_text)
        c3_pass = bool(spec.get("context") or spec.get("where") or spec.get("when")) or len(ctx_matches) >= 1
        results["context_defined"] = WFOCriterionResult(
            key="context_defined",
            index=3,
            name="Contextualized (Where/When)",
            passed=c3_pass,
            score=1.0 if c3_pass else 0.0,
            evidence=f"Context markers: {ctx_matches[:4]}" if c3_pass else "Missing temporal/spatial context",
            remediation=None if c3_pass else "Anchor the outcome in a concrete time, place, or target environment.",
        )

        # 4. Meta-Outcome
        meta_text = f"{goal_text} {spec.get('meta_outcome', '')} {spec.get('why', '')}"
        meta_matches = META_PATTERNS.findall(meta_text)
        c4_pass = bool(spec.get("meta_outcome") or spec.get("why")) or len(meta_matches) >= 1
        results["meta_outcome"] = WFOCriterionResult(
            key="meta_outcome",
            index=4,
            name="Meta-Outcome & Purpose",
            passed=c4_pass,
            score=1.0 if c4_pass else 0.0,
            evidence=f"Purpose markers: {meta_matches[:4]}" if c4_pass else "Missing higher-purpose ('so that...') link",
            remediation=None if c4_pass else "Define the higher meta-outcome ('so that...') linking this goal to core values or ROI.",
        )

        # 5. Ecology Safe
        eco_text = f"{goal_text} {spec.get('ecology', '')}"
        eco_risks = ECOLOGY_RISK_PATTERNS.findall(eco_text)
        explicit_eco = spec.get("ecology_safe")
        if explicit_eco is False or len(eco_risks) > 0:
            c5_pass = False
        else:
            c5_pass = True
        results["ecology_safe"] = WFOCriterionResult(
            key="ecology_safe",
            index=5,
            name="Systemic Ecology Verified",
            passed=c5_pass,
            score=1.0 if c5_pass else 0.0,
            evidence="Systemic ecology clean" if c5_pass else f"Ecological hazard detected: {eco_risks}",
            remediation=None if c5_pass else "Remove destructive side effects so the outcome serves the whole system ecologically.",
        )

        # 6. Self-Initiated (Cause > Effect)
        ext_deps = EXTERNAL_DEPENDENCY_PATTERNS.findall(goal_text)
        agency_hits = AGENCY_PATTERNS.findall(goal_text)
        if spec.get("self_initiated") is False or len(ext_deps) > 0:
            c6_pass = False
        else:
            c6_pass = bool(spec.get("self_initiated")) or len(agency_hits) > 0 or len(ext_deps) == 0
        results["self_initiated"] = WFOCriterionResult(
            key="self_initiated",
            index=6,
            name="Self-Initiated & Maintained (C > E)",
            passed=c6_pass,
            score=1.0 if c6_pass else 0.0,
            evidence="Locus of control is internal (C > E)" if c6_pass else f"External dependency detected: {ext_deps}",
            remediation=None if c6_pass else "Rewrite the outcome so initiation and maintenance remain within your direct control (Cause > Effect).",
        )

        # 7. Contrast Island Leverage
        contrast = spec.get("contrast_leverage") or spec.get("leverage")
        c7_pass = bool(contrast) or ("so that" in goal_text.lower() or len(goal_text.split()) >= 6)
        results["contrast_leverage"] = WFOCriterionResult(
            key="contrast_leverage",
            index=7,
            name="Contrast Island Leverage",
            passed=c7_pass,
            score=1.0 if c7_pass else 0.0,
            evidence="Contrast leverage established" if c7_pass else "Insufficient contrast/stakes definition",
            remediation=None if c7_pass else "Establish Contrast Island leverage: contrast the cost of staying still against the payoff of execution.",
        )

        # 8. RAS Possibility Tuning
        ras = spec.get("ras_tuned")
        c8_pass = bool(ras) if ras is not None else (c1_pass and c2_pass)
        results["ras_tuned"] = WFOCriterionResult(
            key="ras_tuned",
            index=8,
            name="RAS Possibility Tuning",
            passed=c8_pass,
            score=1.0 if c8_pass else 0.0,
            evidence="RAS tuned to positive sensory targets" if c8_pass else "RAS blocked by negation or vague target",
            remediation=None if c8_pass else "Pair positive terms with sensory specifics so the Reticular Activating System filters for opportunities.",
        )

        # 9. Attractor Basin (7-10 Reference Successes / Milestones)
        refs = spec.get("attractor_basin") or spec.get("references") or spec.get("steps")
        if isinstance(refs, (list, tuple)):
            c9_pass = len(refs) >= 3
            c9_ev = f"{len(refs)} attractor references/steps provided"
        elif isinstance(refs, int):
            c9_pass = refs >= 7
            c9_ev = f"{refs} reference successes recorded"
        else:
            c9_pass = bool(refs) or (c2_pass and c3_pass)
            c9_ev = "Implicit step basin derived from contextual metrics" if c9_pass else "No reference basin"
        results["attractor_basin"] = WFOCriterionResult(
            key="attractor_basin",
            index=9,
            name="Attractor Basin (7-10 Proofs/Steps)",
            passed=c9_pass,
            score=1.0 if c9_pass else 0.0,
            evidence=c9_ev,
            remediation=None if c9_pass else "Anchor the outcome with 7-10 reference successes or concrete milestone steps.",
        )

        # 10. Submodality Dashboard Locked
        submod = spec.get("submodalities") or spec.get("submodality_locked")
        if isinstance(submod, dict):
            brightness = float(submod.get("brightness", 0.8))
            clarity = float(submod.get("clarity", 0.8))
            c10_pass = brightness >= 0.5 and clarity >= 0.5
            c10_ev = f"Submodalities locked (brightness={brightness}, clarity={clarity})"
        else:
            c10_pass = bool(submod) if submod is not None else c2_pass
            c10_ev = "Default high-resolution submodalities active" if c10_pass else "Submodalities dim/unlocked"
        results["submodality_locked"] = WFOCriterionResult(
            key="submodality_locked",
            index=10,
            name="Submodality Dashboard Locked",
            passed=c10_pass,
            score=1.0 if c10_pass else 0.0,
            evidence=c10_ev,
            remediation=None if c10_pass else "Lock submodalities: make the internal representation bright, close, high-clarity, and resonant.",
        )

        passed_count = sum(1 for r in results.values() if r.passed)
        total = len(self.CRITERIA_META)
        total_score = passed_count / float(total)
        remediations = [r.remediation for r in results.values() if not r.passed and r.remediation]

        return WFOResult(
            goal=goal_text,
            passed=total_score >= self.pass_threshold and results["positive_terms"].passed and results["ecology_safe"].passed,
            score=total_score,
            passed_count=passed_count,
            total_criteria=total,
            criteria=results,
            remediations=remediations,
        )
