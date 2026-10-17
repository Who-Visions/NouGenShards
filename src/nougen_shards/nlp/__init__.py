"""
NouGenMorph NLP Subsystem (`nougen_shards.nlp`).

Sovereign deterministic execution engine transmuted from Christopher Howard's
*Breakthrough to Success* (7 CDs / 64 Tracks + 34-Page Workbook).
"""

from typing import Any, Dict, Optional, Sequence, Union

from .wfo import WFOCriterionResult, WFOEngine, WFOResult
from .values import DRIVER_CATALOG, ValueConflictResolution, ValueEntry, ValuesMatrix
from .decision_destroyer import CollapsedSubmodalities, DecisionDestroyer, DecisionDestroyerResult
from .timeline import StrategicVisionPlan, TimelineEngine, TimelineMilestone
from .unconscious import DirectiveAuditResult, DirectiveCheck, UnconsciousLoop


class BreakthroughEngine:
    """
    Unified Facade combining all 5 deterministic Breakthrough to Success NLP engines:
    1. WFOEngine (10-Criterion Well-Formed Outcome Validator)
    2. ValuesMatrix (5-Driver Elicitation, Polarity & Conflict Resolution)
    3. DecisionDestroyer (C > E Agency Reframer & Submodality Collapse)
    4. TimelineEngine (In-Time / Through-Time & Strategic Visioning Future-Pacer)
    5. UnconsciousLoop (6 Prime Directives Autonomic Telemetry Auditor)
    """

    def __init__(self, pass_threshold: float = 0.8):
        self.wfo = WFOEngine(pass_threshold=pass_threshold)
        self.values = ValuesMatrix()
        self.destroyer = DecisionDestroyer()
        self.timeline = TimelineEngine()
        self.unconscious = UnconsciousLoop()

    def run_breakthrough(
        self,
        goal: Union[str, Dict[str, Any]],
        values: Optional[Sequence[str]] = None,
        limiting_belief: Optional[str] = None,
        horizon_days: int = 7,
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run a complete end-to-end 7-Day Breakthrough synthesis on an objective."""
        wfo_res = self.wfo.evaluate(goal)
        val_list = self.values.build_hierarchy(
            values or ["Freedom", "Competency", "Security", "Self-Expression", "Belonging"]
        )
        conflict_res = (
            self.values.resolve_conflict(val_list[0], val_list[1]).to_dict()
            if len(val_list) >= 2
            else None
        )
        dd_res = self.destroyer.destroy_limiting_decision(
            limiting_belief or ("" if wfo_res.passed else f"I can't complete {wfo_res.goal}")
        )
        vision_plan = self.timeline.future_pace(wfo_res.goal or "Sovereign Objective", horizon_days=horizon_days)
        audit_res = self.unconscious.audit_telemetry(telemetry)

        return {
            "wfo": wfo_res.to_dict(),
            "values_hierarchy": [v.to_dict() for v in val_list],
            "top_conflict_alignment": conflict_res,
            "decision_destroyer": dd_res.to_dict(),
            "strategic_vision": vision_plan.to_dict(),
            "unconscious_directives": audit_res.to_dict(),
        }


__all__ = [
    "BreakthroughEngine",
    "WFOEngine",
    "WFOResult",
    "WFOCriterionResult",
    "ValuesMatrix",
    "ValueEntry",
    "ValueConflictResolution",
    "DRIVER_CATALOG",
    "DecisionDestroyer",
    "DecisionDestroyerResult",
    "CollapsedSubmodalities",
    "TimelineEngine",
    "TimelineMilestone",
    "StrategicVisionPlan",
    "UnconsciousLoop",
    "DirectiveCheck",
    "DirectiveAuditResult",
]
