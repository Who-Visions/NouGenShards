"""nougen_verse: a clean-room rap and rhyme construction engine.

Deterministic, offline modes:

- PLAN:    :func:`plan_verse` turns a VerseRequest into a VerseBlueprint.
- COMPILE: :func:`compile_prompt` turns a blueprint into a provider-neutral prompt packet.
- ANALYZE: :func:`analyze_verse` diagnoses a user-owned draft.
- SCORE:   :func:`score_verse` reports separate craft dimensions with their components.
- REPAIR:  :func:`suggest_repairs` gives targeted, voice-preserving revision steps.

``find_rhymes`` searches for graded rhymes. GENERATE lives in
``nougen_verse.providers`` and is disabled by default.

The craft vocabulary (content, flow and delivery as separate layers; advanced
flow ideas such as triplets, flams, lazy tails and breaking patterns) follows
high-level concepts publicly described by Paul Edwards in "How to Rap: The Art
and Science of the Hip-Hop MC" and "How to Rap 2: Advanced Flow and Delivery
Techniques". No text from those books is included.
"""

from .analyzer import AnalysisContext, analyze_verse
from .compiler import compile_prompt
from .config import Config, load_config
from .models import CompiledPrompt, RepairPlan, ScoreReport, VerseAnalysis, VerseBlueprint, VerseRequest
from .persona import Persona, load_persona
from .phonetics import PhoneticDictionary
from .planner import plan_verse
from .repair import apply_repairs, repair_before_after, suggest_repairs
from .rhyme import RhymeCandidate, find_rhymes
from .scorer import score_verse

__version__ = "0.1.0"

__all__ = [
    "AnalysisContext", "CompiledPrompt", "Config", "Persona", "PhoneticDictionary", "RepairPlan", "RhymeCandidate",
    "ScoreReport", "VerseAnalysis", "VerseBlueprint", "VerseRequest", "analyze_verse", "apply_repairs", "compile_prompt",
    "find_rhymes", "load_config", "load_persona", "plan_verse", "repair_before_after", "score_verse", "suggest_repairs",
    "__version__",
]
