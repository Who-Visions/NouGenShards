"""
NouGenMorph NLP Engine — Module 4: Timeline & Strategic Visioning Engine.

Provenance:
- Source: Christopher Howard, Breakthrough to Success (CD 3: About Time, CD 5 & CD 7: Strategic Visioning)
- War-Gamed & Drafted By: Free Fleet Lane (`ollama-cloud-davemeralus` / `ollama-cloud-ediebrikell12`) + Local `gemma4:e2b-qat`
- Reviewed By: Antigravity Coach (UDCT Architecture Solver)
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List


THROUGH_TIME_PATTERNS = re.compile(
    r"\b(schedule|timeline|plan|roadmap|sequence|milestone|deadline|calendar|from\s+left\s+to\s+right|overview|dissociated|checkpoint|horizon)\b",
    re.IGNORECASE,
)

IN_TIME_PATTERNS = re.compile(
    r"\b(right\s+now|in\s+the\s+moment|immersed|spontaneous|flow|present|instant|associated|feeling\s+it\s+now|here\s+and\s+now)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TimelineMilestone:
    """Single future-paced checkpoint along the Strategic Visioning timeline."""

    step: int
    day_offset: int
    phase: str
    objective: str
    sensory_anchor: str
    verification_gate: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "day_offset": self.day_offset,
            "phase": self.phase,
            "objective": self.objective,
            "sensory_anchor": self.sensory_anchor,
            "verification_gate": self.verification_gate,
        }


@dataclass(frozen=True)
class StrategicVisionPlan:
    """Compiled Strategic Visioning timeline with neurological lock-in anchors."""

    goal: str
    temporal_mode: str
    horizon_days: int
    milestones: List[TimelineMilestone] = field(default_factory=list)
    look_back_integration: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "temporal_mode": self.temporal_mode,
            "horizon_days": self.horizon_days,
            "milestones": [m.to_dict() for m in self.milestones],
            "look_back_integration": self.look_back_integration,
        }


class TimelineEngine:
    """
    CD 3 & CD 7 Temporal Encoding (In-Time vs. Through-Time) and Strategic Visioning Engine.
    """

    PHASE_LABELS = (
        "Foundation & Repatterning",
        "Resource & Values Calibration",
        "Momentum & Threshold Execution",
        "Systemic Verification & Hardening",
        "Full Neurological Lock-In & Completion",
    )

    def classify_temporal_mode(self, text: str) -> str:
        """
        Classify temporal encoding as:
        - 'IN_TIME': Timeline runs front-to-back through the operator (associated, present-focused).
        - 'THROUGH_TIME': Timeline runs left-to-right in front of the operator (dissociated, sequential planner).
        """
        raw = (text or "").strip()
        if not raw:
            return "THROUGH_TIME"
        in_hits = len(IN_TIME_PATTERNS.findall(raw))
        through_hits = len(THROUGH_TIME_PATTERNS.findall(raw))
        if in_hits > through_hits:
            return "IN_TIME"
        return "THROUGH_TIME"

    def future_pace(
        self,
        goal: str,
        horizon_days: int = 7,
        milestones_count: int = 5,
    ) -> StrategicVisionPlan:
        """
        Project a Well-Formed Outcome into the future timeline (CD 5 'Putting A Goal In Your Future'
        & CD 7 'Strategic Visioning'), generating deterministic milestones and looking back from
        the completed future state to lock in the pathway.
        """
        clean_goal = (goal or "").strip() or "Achieve sovereign fleet objective"
        days = max(1, int(horizon_days))
        count = max(1, min(20, int(milestones_count)))

        mode = self.classify_temporal_mode(clean_goal)
        milestones: List[TimelineMilestone] = []

        for idx in range(1, count + 1):
            frac = idx / float(count)
            day_offset = max(1, round(days * frac))
            phase_name = self.PHASE_LABELS[(idx - 1) % len(self.PHASE_LABELS)]
            milestones.append(
                TimelineMilestone(
                    step=idx,
                    day_offset=day_offset,
                    phase=phase_name,
                    objective=f"[{ int(frac * 100) }%] Execute {phase_name} for: {clean_goal}",
                    sensory_anchor=f"Step into Day {day_offset} Associated (In-Time): see green scoreboard and feel effortless momentum",
                    verification_gate=f"Deterministic check #{idx} passed at T+{day_offset}d",
                )
            )

        look_back = (
            f"Floated out to T+{days}d beyond completion of '{clean_goal}', turned back toward Now "
            f"(Through-Time overview), and verified all {count} causal steps connecting Present to Future."
        )

        return StrategicVisionPlan(
            goal=clean_goal,
            temporal_mode=mode,
            horizon_days=days,
            milestones=milestones,
            look_back_integration=look_back,
        )
