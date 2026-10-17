"""
NouGenMorph NLP Engine — Module 3: Decision Destroyer & Cause > Effect Reframer.

Provenance:
- Source: Christopher Howard, Breakthrough to Success (CD 2: Cause & Effect, CD 3 & CD 6: Decision Destroyer)
- War-Gamed & Drafted By: Free Fleet Lane (`ollama-cloud-contact-whovisions`) + Local `gemma4:e2b-qat`
- Reviewed By: Antigravity Coach (UDCT Architecture Solver)
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List


EFFECT_PATTERNS = re.compile(
    r"\b(because\s+of\s+them|made\s+me|can't|cannot|impossible|too\s+hard|no\s+way|stuck|forced\s+to|fault|blame|they\s+won't|not\s+enough|helpless|victim|unfair|blocked\s+by)\b",
    re.IGNORECASE,
)

LIMITING_PREFIX_RE = re.compile(
    r"^(?:i\s+can't|i\s+cannot|we\s+can't|we\s+cannot|it\s+is\s+impossible\s+to|i'm\s+stuck\s+on|i\s+am\s+unable\s+to)\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CollapsedSubmodalities:
    """Submodality state after running the Decision Destroyer collapse."""

    brightness: float
    size: float
    distance_meters: float
    clarity: float
    volume: float
    dissociated: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brightness": round(self.brightness, 3),
            "size": round(self.size, 3),
            "distance_meters": round(self.distance_meters, 2),
            "clarity": round(self.clarity, 3),
            "volume": round(self.volume, 3),
            "dissociated": self.dissociated,
        }


@dataclass(frozen=True)
class DecisionDestroyerResult:
    """Result of running the Decision Destroyer on a limiting belief or blocker."""

    original_statement: str
    initial_locus: str
    final_locus: str
    root_gestalt: str
    reframed_statement: str
    collapsed_limiting_submodalities: CollapsedSubmodalities
    installed_empowering_submodalities: Dict[str, Any]
    timeline_release_step: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_statement": self.original_statement,
            "initial_locus": self.initial_locus,
            "final_locus": self.final_locus,
            "root_gestalt": self.root_gestalt,
            "reframed_statement": self.reframed_statement,
            "collapsed_limiting_submodalities": self.collapsed_limiting_submodalities.to_dict(),
            "installed_empowering_submodalities": dict(self.installed_empowering_submodalities),
            "timeline_release_step": self.timeline_release_step,
        }


class DecisionDestroyer:
    """
    CD 2 Cause > Effect (C > E) & CD 6 Decision Destroyer Engine.

    Transforms Effect-side excuses (E > C) into Cause-side agency (C > E),
    collapses the sensory submodalities of limiting decisions, and installs
    high-resolution empowering beliefs along the timeline.
    """

    def classify_locus(self, statement: str) -> str:
        """Return 'EFFECT' if the statement exhibits E > C language, otherwise 'CAUSE'."""
        text = (statement or "").strip()
        if not text:
            return "EFFECT"
        if EFFECT_PATTERNS.search(text):
            return "EFFECT"
        return "CAUSE"

    def collapse_submodalities(self, initial: Dict[str, Any] | None = None) -> CollapsedSubmodalities:
        """
        Shrink, dim, mute, and push away the internal representation of a limiting decision
        so its neurological charge drops to near zero.
        """
        src = initial or {}
        b = max(0.0, min(1.0, float(src.get("brightness", 0.8)) * 0.05))
        s = max(0.0, min(1.0, float(src.get("size", 1.0)) * 0.05))
        d = max(10.0, float(src.get("distance_meters", 1.0)) * 25.0)
        c = max(0.0, min(1.0, float(src.get("clarity", 0.9)) * 0.1))
        v = max(0.0, min(1.0, float(src.get("volume", 0.8)) * 0.0))
        return CollapsedSubmodalities(
            brightness=b,
            size=s,
            distance_meters=d,
            clarity=c,
            volume=v,
            dissociated=True,
        )

    def extract_root_gestalt(self, statement: str) -> str:
        """Identify the underlying limiting presupposition or Gestalt behind an Effect statement."""
        text = (statement or "").strip()
        if not text:
            return "Unspecified limiting presupposition"
        lowered = text.lower()
        if "because" in lowered:
            cause_part = text.split("because", 1)[1].strip(" .!;")
            return f"Externalized attribution: '{cause_part}'"
        if any(w in lowered for w in ("can't", "cannot", "impossible", "unable")):
            return "Assumed capability boundary (confused current strategy with permanent identity)"
        if any(w in lowered for w in ("stuck", "blocked", "hard")):
            return "Static state fixation (missing multi-option Frank/Cecil pivot)"
        return "Unexamined past generalization projected onto present capability"

    def destroy_limiting_decision(
        self,
        statement: str,
        initial_submodalities: Dict[str, Any] | None = None,
    ) -> DecisionDestroyerResult:
        """
        Execute the full Decision Destroyer protocol:
        1. Classify initial locus (CAUSE vs EFFECT).
        2. Isolate the root Gestalt.
        3. Float above the timeline to BEFORE the limiting decision was formed.
        4. Collapse the limiting submodalities (black-and-white postage stamp in the distance).
        5. Reframe into an active C > E agency directive and lock bright panoramic submodalities.
        """
        raw = (statement or "").strip()
        initial_locus = self.classify_locus(raw)
        gestalt = self.extract_root_gestalt(raw)
        collapsed = self.collapse_submodalities(initial_submodalities)

        if not raw:
            reframed = "I own the outcome and engineer a deterministic path to completion."
        else:
            core_action = LIMITING_PREFIX_RE.sub("", raw)
            if "because" in core_action.lower():
                core_action = re.split(r"\bbecause\b", core_action, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            core_action = EFFECT_PATTERNS.sub("solve", core_action).strip(" .,;!")
            reframed = (
                f"I am at Cause (C > E): I systematically engineer and verify the solution for '{core_action}' "
                f"by testing 3+ concrete options."
            )

        empowering_submod = {
            "brightness": 1.0,
            "size": 2.0,
            "distance_meters": 0.5,
            "clarity": 1.0,
            "color": "panoramic_full_spectrum",
            "associated": True,
        }

        release_step = (
            "Floated above timeline past the root Gestalt, released old limiting imprint, "
            "and illuminated all forward milestones with C > E agency."
        )

        return DecisionDestroyerResult(
            original_statement=raw,
            initial_locus=initial_locus,
            final_locus="CAUSE",
            root_gestalt=gestalt,
            reframed_statement=reframed,
            collapsed_limiting_submodalities=collapsed,
            installed_empowering_submodalities=empowering_submod,
            timeline_release_step=release_step,
        )
