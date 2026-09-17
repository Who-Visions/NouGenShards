"""emoji_math.py

NouGen Semantic Emoji Compiler & Unified Telemetry Engine.

Core Architecture:
    CanonicalBehaviorState (Single Source of Truth)
            │
            ├── Natural Language Renderer
            │
            ├── Emoji Renderer (Candidate Scoring → Density Budget → Semantic Ordering)
            │
            └── Telemetry Renderer (Direct Projection from Canonical Basis Points)

Emergent Pipeline (Zero Hardcoded String Switches):
    1. Glyph Candidate Scoring (Affinity Dot-Product with Behavioral/Affect Vector)
    2. Contradiction & Redundancy Filtering (Hysteresis & Compatibility Matrix)
    3. Mathematical Density Budget (Function of Restraint, Formality, Seriousness, Energy)
    4. Semantic Sequential Ordering (Causal Syntax: Trigger → Action → Result)
    5. Adaptive Placement (Prefix, Inline, Postfix, Telemetry Footer)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Optional, Sequence


SCALE = 10_000  # Basis points (10000 = 1.00)


def clamp_bp(val: int | float) -> int:
    return max(0, min(SCALE, int(val)))


def blend_bp(old: int, target: int, alpha_bp: int) -> int:
    alpha = clamp_bp(alpha_bp)
    return old + ((target - old) * alpha // SCALE)


# ============================================================
# CANONICAL GLYPH DEFINITION & SEMANTIC AFFINITY TABLE
# ============================================================

@dataclass(frozen=True)
class GlyphDescriptor:
    glyph: str
    dimension_name: str
    role: str  # "trigger", "action", "state", "result", "modifier"
    # Primary dimension weights (0 to 10,000)
    warmth: int = 0
    positive: int = 0
    sadness: int = 0
    anger: int = 0
    fear: int = 0
    curiosity: int = 0
    uncertainty: int = 0
    energy: int = 0
    cognition: int = 0
    investigation: int = 0
    verification: int = 0
    caution: int = 0
    focus: int = 0
    dominance: int = 0
    humor: int = 0
    teasing: int = 0
    creativity: int = 0
    restraint: int = 0
    urgency: int = 0
    success: int = 0
    failure: int = 0


# Declarative Semantic Glyph Registry (Extensible without modifying resolver code)
GLYPH_REGISTRY: tuple[GlyphDescriptor, ...] = (
    GlyphDescriptor("🧠", "cognition", role="action", cognition=9000, focus=7000),
    GlyphDescriptor("🔍", "investigation", role="action", investigation=9500, curiosity=8000, focus=8000),
    GlyphDescriptor("🧪", "verification", role="action", verification=9500, caution=6000, focus=8500),
    GlyphDescriptor("⚙️", "systems", role="state", cognition=7000, verification=7000, focus=7000),
    GlyphDescriptor("✅", "verified_success", role="result", positive=9000, success=10000, verification=8000),
    GlyphDescriptor("❌", "confirmed_failure", role="result", sadness=6000, failure=10000, verification=8000),
    GlyphDescriptor("⚠️", "concern", role="trigger", caution=9000, uncertainty=8000, fear=5000),
    GlyphDescriptor("🚨", "incident", role="trigger", urgency=9500, caution=9000, fear=7000),
    GlyphDescriptor("🛡️", "defense", role="action", caution=9500, restraint=7000, dominance=6000),
    GlyphDescriptor("🔥", "intensity", role="state", energy=9500, positive=7000, dominance=7000),
    GlyphDescriptor("💡", "discovery", role="result", creativity=9500, cognition=8500, positive=7500),
    GlyphDescriptor("❤️", "warmth", role="state", warmth=9500, positive=8000),
    GlyphDescriptor("😊", "positive", role="state", positive=9000, warmth=7000),
    GlyphDescriptor("😢", "sadness", role="state", sadness=9000, energy=0),
    GlyphDescriptor("😡", "anger", role="state", anger=9000, dominance=7000, energy=8000),
    GlyphDescriptor("😨", "fear", role="state", fear=9000, uncertainty=7000),
    GlyphDescriptor("🤔", "curiosity", role="trigger", curiosity=9000, uncertainty=6000),
    GlyphDescriptor("🤨", "skepticism", role="trigger", caution=8000, curiosity=7000, uncertainty=6000),
    GlyphDescriptor("😂", "humor", role="state", humor=9500, positive=8500, energy=7500),
    GlyphDescriptor("😏", "teasing", role="state", teasing=9000, dominance=6000, humor=7000),
    GlyphDescriptor("🎯", "focus", role="modifier", focus=9500, restraint=6000),
    GlyphDescriptor("🌀", "chaos", role="modifier", creativity=7000, uncertainty=7000, restraint=0),
    GlyphDescriptor("🔒", "security", role="state", caution=9000, restraint=8000, verification=8000),
    GlyphDescriptor("🧬", "evolution", role="state", creativity=8500, cognition=8000),
)


# ============================================================
# CANONICAL BEHAVIOR & EMOJI VECTOR
# ============================================================

@dataclass(frozen=True)
class EmojiVector:
    """Continuous behavioral & affective vector mapped to emoji dimensions (0 to 10,000 bp)."""

    warmth: int = 5000         # ❤️
    positive: int = 5000       # 😊
    sadness: int = 0           # 😢
    anger: int = 0             # 😡
    fear: int = 0              # 😨
    curiosity: int = 5000      # 🤔
    uncertainty: int = 2000    # ❓
    energy: int = 5000         # ⚡
    cognition: int = 5000      # 🧠
    investigation: int = 5000  # 🔍
    verification: int = 5000   # 🧪
    expressiveness: int = 5000 # 🎭
    humor: int = 5000          # 😂
    teasing: int = 3000        # 😏
    caution: int = 5000        # 🛡️
    focus: int = 5000          # 🎯
    intensity: int = 5000      # 🔥
    verbosity: int = 5000      # 🗣️
    restraint: int = 5000      # 🤫
    dominance: int = 5000      # 👑
    trust: int = 5000          # 🤝
    chaos: int = 2000          # 🌀
    creativity: int = 5000     # 💡
    urgency: int = 3000        # 🚨
    success: int = 5000        # ✅
    failure: int = 0           # ❌

    def __add__(self, other: "EmojiVector") -> "EmojiVector":
        vals = {k: clamp_bp(getattr(self, k) + getattr(other, k)) for k in asdict(self)}
        return EmojiVector(**vals)

    def __sub__(self, other: "EmojiVector") -> "EmojiVector":
        vals = {k: clamp_bp(getattr(self, k) - getattr(other, k)) for k in asdict(self)}
        return EmojiVector(**vals)

    def __mul__(self, scalar: float) -> "EmojiVector":
        vals = {k: clamp_bp(getattr(self, k) * scalar) for k in asdict(self)}
        return EmojiVector(**vals)

    def blend(self, target: "EmojiVector", alpha_bp: int) -> "EmojiVector":
        vals = {k: blend_bp(getattr(self, k), getattr(target, k), alpha_bp) for k in asdict(self)}
        return EmojiVector(**vals)

    def to_compact_string(self, threshold_bp: int = 3500) -> str:
        """Render exact telemetry scores (e.g. 🧠92 🔍88 🧪97 🛡️82 ⚠️61)."""
        mapping = [
            ("🧠", self.cognition),
            ("🔍", self.investigation),
            ("🧪", self.verification),
            ("🛡️", self.caution),
            ("⚡", self.energy),
            ("❤️", self.warmth),
            ("😊", self.positive),
            ("💡", self.creativity),
            ("🎯", self.focus),
            ("👑", self.dominance),
            ("🤝", self.trust),
            ("😂", self.humor),
            ("😏", self.teasing),
            ("😡", self.anger),
            ("😨", self.fear),
            ("😢", self.sadness),
            ("🤔", self.curiosity),
            ("❓", self.uncertainty),
            ("🚨", self.urgency),
        ]
        active = [f"{emoji}{val // 100}" for emoji, val in mapping if val >= threshold_bp]
        return " ".join(active)

    def one_line_receipt(self, top_n: int = 6) -> str:
        """Render algebraic one-line receipt: 🎭 = 0.91🧪 + 0.88🧠 + 0.74🔍 + 0.67🛡️."""
        mapping = [
            ("🧪", self.verification),
            ("🧠", self.cognition),
            ("🔍", self.investigation),
            ("🛡️", self.caution),
            ("🎯", self.focus),
            ("⚡", self.energy),
            ("❤️", self.warmth),
            ("💡", self.creativity),
            ("👑", self.dominance),
            ("😂", self.humor),
            ("🤝", self.trust),
            ("😡", self.anger),
            ("😨", self.fear),
            ("😢", self.sadness),
            ("🚨", self.urgency),
            ("✅", self.success),
        ]
        sorted_terms = sorted(mapping, key=lambda x: x[1], reverse=True)[:top_n]
        terms = [f"{val / SCALE:.2f}{emoji}" for emoji, val in sorted_terms if val > 1500]
        return "🎭 = " + " + ".join(terms)

    def describe_algebra(self) -> list[str]:
        """Detect emergent psychological constructs from vector interactions."""
        constructs = []
        if self.anger > 4000:
            if self.warmth > 4000 or self.trust > 4000:
                constructs.append("relational anger (angry because they care)")
            elif self.dominance > 6000:
                constructs.append("dominant confrontational anger")
            elif self.sadness > 4000:
                constructs.append("hurt/wounded anger")
            elif self.dominance < 3000:
                constructs.append("frustrated powerlessness")
            else:
                constructs.append("pure anger")

        if self.fear > 4000:
            if self.caution < 3000:
                constructs.append("acute panic (fear without defense)")
            elif self.investigation > 6000:
                constructs.append("hypervigilance (fear + investigation)")
            elif self.uncertainty > 5000:
                constructs.append("anxious dread")

        if self.humor > 6000:
            if self.warmth < 2500:
                constructs.append("biting/dry sarcasm")
            elif self.cognition > 6500:
                constructs.append("rapid witty play")
            elif self.teasing > 6000:
                constructs.append("playful teasing")

        if self.cognition > 6500:
            if self.investigation > 6500 and self.verification > 6500:
                constructs.append("analytical investigation")
            elif self.chaos > 6000 or self.creativity > 6500:
                constructs.append("inventive intelligence")
            elif self.caution < 3000 and self.chaos > 5000:
                constructs.append("reckless cleverness")

        if self.warmth > 6500:
            if self.teasing > 6000:
                constructs.append("charming flirtation")
            elif self.sadness > 4000:
                constructs.append("vulnerable affection")

        if self.positive > 7500 and self.energy > 7500:
            constructs.append("ecstatic celebration")

        if not constructs:
            constructs.append("balanced baseline")

        return constructs


# ============================================================
# DYNAMIC EMOJI COMPILER (Scoring, Density, & Syntax Ordering)
# ============================================================

@dataclass(frozen=True)
class EmojiSignalEnvelope:
    """Compiled semantic emoji signal envelope derived directly from the canonical vector."""
    semantic_combo: str           # e.g. "🚨🛡️🔍", "🔍🧪⚙️", "🔥⚙️✅"
    telemetry_banner: str         # e.g. "🧠92 🔍88 🧪97 🛡️82 ⚠️61"
    telemetry_compact: str        # e.g. "🧠🔍🧪"
    density: int                  # 0 to 4
    position: str                 # "prefix", "postfix", "footer", "none"
    emergent_tags: tuple[str, ...]

    def format_message(self, message: str) -> str:
        """Apply synthesized emoji signals according to position and density rules."""
        if self.density == 0 or not self.semantic_combo:
            return message.strip()

        clean_msg = message.strip()
        if self.position == "prefix":
            return f"{self.semantic_combo} {clean_msg}"
        elif self.position == "postfix":
            return f"{clean_msg} {self.semantic_combo}"
        elif self.position == "footer":
            return f"{clean_msg}\n\n`[{self.telemetry_compact}]`"
        elif self.position == "telemetry":
            return f"{clean_msg}\n\n`[telemetry: {self.telemetry_banner}]`"
        return f"{self.semantic_combo} {clean_msg}"


def compute_glyph_affinity(descriptor: GlyphDescriptor, v: EmojiVector) -> int:
    """Compute dot-product affinity between descriptor dimensions and vector."""
    score = (
        descriptor.warmth * v.warmth // SCALE
        + descriptor.positive * v.positive // SCALE
        + descriptor.sadness * v.sadness // SCALE
        + descriptor.anger * v.anger // SCALE
        + descriptor.fear * v.fear // SCALE
        + descriptor.curiosity * v.curiosity // SCALE
        + descriptor.uncertainty * v.uncertainty // SCALE
        + descriptor.energy * v.energy // SCALE
        + descriptor.cognition * v.cognition // SCALE
        + descriptor.investigation * v.investigation // SCALE
        + descriptor.verification * v.verification // SCALE
        + descriptor.caution * v.caution // SCALE
        + descriptor.focus * v.focus // SCALE
        + descriptor.dominance * v.dominance // SCALE
        + descriptor.humor * v.humor // SCALE
        + descriptor.teasing * v.teasing // SCALE
        + descriptor.creativity * v.creativity // SCALE
        + descriptor.restraint * v.restraint // SCALE
        + descriptor.urgency * v.urgency // SCALE
        + descriptor.success * v.success // SCALE
        + descriptor.failure * v.failure // SCALE
    )
    return score


def calculate_density_budget(v: EmojiVector, formality_bp: int = 2000) -> int:
    """Mathematically compute emoji budget from restraint, seriousness, sadness, and energy."""
    # Restraint and solemnity suppress emojis
    suppression_pressure = (
        v.restraint * 4 // 10 
        + v.sadness * 6 // 10 
        + formality_bp * 4 // 10
    )
    # Expressiveness, playfulness, celebration, and urgency invite signals
    expressive_pressure = (
        v.energy * 3 // 10 
        + v.positive * 3 // 10 
        + v.humor * 2 // 10 
        + v.urgency * 2 // 10
        + v.investigation * 2 // 10
    )

    net_score = expressive_pressure - suppression_pressure

    if net_score < -2000 or v.sadness > 7000:
        return 0  # Solemn / grief restraint
    elif net_score < 1000:
        return 1  # Minimal / focused
    elif net_score < 4000:
        return 2  # Standard conversational
    elif net_score < 7000:
        return 3  # High activation / alert / celebratory
    else:
        return 4  # Maximum expressive


def sort_semantic_syntax(candidates: list[GlyphDescriptor], trigger_first: bool = True) -> list[GlyphDescriptor]:
    """Sort glyphs according to semantic narrative syntax: Trigger → Action → State → Result → Modifier.
    
    Syntactic order examples:
      🚨🛡️🔍: incident (trigger) → defend (action) → investigate (action)
      🔍⚠️🛡️: investigation (action) → concern (trigger/discovery) → defense (action)
      🧪✅🔥: verification (action) → success (result) → celebration (state)
      🔥🧪✅: enthusiasm (state) → verification (action) → confirmed success (result)
    """
    role_order = {
        "trigger": 0,  # 🚨, ⚠️, 🐛, 🤔, 🤨
        "action": 1,   # 🔍, 🧪, 🛡️, 🧠
        "state": 2,    # ⚙️, 🔥, ❤️, 🔒
        "result": 3,   # ✅, ❌, 💡
        "modifier": 4, # 🎯, 🌀
    }
    return sorted(candidates, key=lambda g: role_order.get(g.role, 2))


# ============================================================
# DYNAMIC GLYPH DISCOVERY & AFFINITY INFERENCE ENGINE
# ============================================================

# Lexical semantic anchors used to infer multidimensional affinities from Unicode metadata / descriptions
SEMANTIC_LEXICAL_ANCHORS: dict[str, dict[str, int]] = {
    # Cognition & Reasoning
    "brain": {"cognition": 9000, "focus": 7000},
    "think": {"cognition": 8500, "curiosity": 6000},
    "robot": {"cognition": 8000, "verification": 7500, "restraint": 6000},
    "gear": {"cognition": 7000, "verification": 7000, "focus": 7000},
    "microscope": {"investigation": 9500, "verification": 9500, "focus": 9000},
    "search": {"investigation": 9500, "curiosity": 8000},
    "key": {"investigation": 7500, "verification": 8000, "caution": 7000},
    
    # Emotion & Social
    "heart": {"warmth": 9500, "positive": 8500, "trust": 8000},
    "love": {"warmth": 10000, "positive": 9000},
    "smile": {"positive": 8500, "warmth": 7000},
    "joy": {"positive": 9500, "energy": 8000},
    "laugh": {"humor": 9500, "positive": 8500, "energy": 7500},
    "wink": {"teasing": 9000, "humor": 7500, "dominance": 5500},
    "cry": {"sadness": 9000, "positive": 0, "energy": 1500},
    "grief": {"sadness": 9500, "restraint": 9000, "energy": 1000},
    "rage": {"anger": 9500, "energy": 8500, "dominance": 8000},
    "angry": {"anger": 9000, "energy": 7500},
    "fear": {"fear": 9000, "uncertainty": 7500, "caution": 7000},
    
    # Alert, Verification & Security
    "alarm": {"urgency": 9500, "caution": 9000, "fear": 6000},
    "siren": {"urgency": 9500, "caution": 9000},
    "warning": {"caution": 9000, "uncertainty": 8000},
    "shield": {"caution": 9500, "restraint": 7000, "dominance": 6000},
    "lock": {"caution": 9000, "restraint": 8500, "verification": 8000},
    "check": {"positive": 9000, "success": 10000, "verification": 8000},
    "cross": {"failure": 10000, "sadness": 6000, "verification": 8000},
    "fire": {"energy": 9500, "intensity": 9500, "positive": 7000},
    "spark": {"energy": 8500, "creativity": 8500, "positive": 7500},
    "ice": {"restraint": 9000, "warmth": 1000, "focus": 7500},
    "wave": {"creativity": 7500, "chaos": 7000, "energy": 6000},
}


class DynamicGlyphRegistry:
    """Extensible, dynamic Unicode glyph repository with semantic affinity inference and caching."""

    def __init__(self, seed_glyphs: Sequence[GlyphDescriptor] = GLYPH_REGISTRY):
        self._glyphs: dict[str, GlyphDescriptor] = {g.glyph: g for g in seed_glyphs}
        self._learned_cache: dict[str, dict[str, Any]] = {}

    def get_all_glyphs(self) -> list[GlyphDescriptor]:
        return list(self._glyphs.values())

    def get_glyph(self, glyph: str) -> Optional[GlyphDescriptor]:
        return self._glyphs.get(glyph)

    def register_descriptor(self, descriptor: GlyphDescriptor) -> None:
        """Explicitly register a fully specified glyph descriptor."""
        self._glyphs[descriptor.glyph] = descriptor

    def infer_and_register(
        self,
        glyph: str,
        name: str,
        description: str = "",
        role: str = "state",
        keywords: Sequence[str] = (),
    ) -> GlyphDescriptor:
        """Infer continuous dimension affinities from metadata descriptions and register the glyph."""
        tokens = set(re.findall(r"\w+", f"{name} {description} {' '.join(keywords)}".lower()))
        
        # Accumulate dimensions from matching anchors
        accumulated: dict[str, list[int]] = {}
        for token in tokens:
            if token in SEMANTIC_LEXICAL_ANCHORS:
                for dim, weight in SEMANTIC_LEXICAL_ANCHORS[token].items():
                    accumulated.setdefault(dim, []).append(weight)
        
        # Average or take max weight
        kwargs: dict[str, int] = {}
        for dim, weights in accumulated.items():
            kwargs[dim] = max(weights) if weights else 0

        # Infer role if not specified
        inferred_role = role
        if "warning" in tokens or "alarm" in tokens or "question" in tokens or "siren" in tokens:
            inferred_role = "trigger"
        elif "search" in tokens or "microscope" in tokens or "shield" in tokens or "gear" in tokens:
            inferred_role = "action"
        elif "check" in tokens or "cross" in tokens or "light" in tokens or "trophy" in tokens:
            inferred_role = "result"

        descriptor = GlyphDescriptor(
            glyph=glyph,
            dimension_name=name.lower().replace(" ", "_"),
            role=inferred_role,
            **kwargs,
        )
        self._glyphs[glyph] = descriptor
        self._learned_cache[glyph] = {
            "name": name,
            "description": description,
            "role": inferred_role,
            "dimensions": kwargs,
        }
        return descriptor


# Global singleton registry instance
GLOBAL_GLYPH_REGISTRY = DynamicGlyphRegistry()


# ============================================================
# CONTRADICTION & COMPATIBILITY FILTERING
# ============================================================

# Anti-correlated pairs (unless conflict/ambiguity in state is explicitly high)
CONTRADICTION_PAIRS: tuple[tuple[str, str], ...] = (
    ("✅", "❌"),
    ("😊", "😢"),
    ("❤️", "😡"),
    ("😂", "😢"),
    ("🔥", "🧊"),
)


def compute_glyph_compatibility(g1: GlyphDescriptor, g2: GlyphDescriptor, v: EmojiVector) -> int:
    """Compute compatibility penalty/bonus between two glyphs (-10000 to +10000)."""
    # Check direct contradiction pairs
    for a, b in CONTRADICTION_PAIRS:
        if (g1.glyph == a and g2.glyph == b) or (g1.glyph == b and g2.glyph == a):
            # If tension/uncertainty is high, co-existence may represent ambivalence/irony
            if v.uncertainty > 7000 or (v.anger > 5000 and v.warmth > 5000):
                return -1500
            return -8000  # Strong suppression of contradictory combinations

    # Redundancy penalty: Two glyphs serving the exact same primary action
    if g1.role == g2.role and g1.role in ("result", "trigger"):
        return -3000

    return 1000  # Default cooperative bonus


# ============================================================
# UNIFIED RENDERERS (NL, Emoji, Telemetry from Canonical State)
# ============================================================

def natural_language_render_directive(v: EmojiVector) -> str:
    """Generate tone & reasoning directives for natural language generation from canonical state."""
    directives = []
    if v.cognition > 7000:
        directives.append("Deep analytical rigor; explain mechanical causality.")
    if v.verification > 8000:
        directives.append("Prioritize verification receipts, test logs, and falsifiable proof.")
    if v.caution > 7000:
        directives.append("Maintain defensive perimeter; highlight potential risks and blast radius.")
    if v.warmth > 7000:
        directives.append("Warm, collaborative, affirming tone.")
    elif v.warmth < 2500:
        directives.append("Direct, terse, non-sentimental delivery.")
    if v.humor > 7000:
        directives.append("Include witty, irreverent banter.")
    if v.restraint > 7500:
        directives.append("High expressive restraint; keep language concise and solemn.")
    return " ".join(directives) or "Balanced objective assistance."


def telemetry_renderer(v: EmojiVector, threshold_bp: int = 3500) -> str:
    """Direct projection of canonical basis points to compressed telemetry string."""
    return v.to_compact_string(threshold_bp=threshold_bp)


def emoji_renderer(
    vector: EmojiVector,
    registry: Optional[DynamicGlyphRegistry] = None,
    formality_bp: int = 2000,
    mode: str = "conversational",  # "conversational", "restrained", "alert", "telemetry"
) -> EmojiSignalEnvelope:
    """Synthesizes dynamic semantic emoji signals by scoring glyph registry affinities against canonical vector."""
    reg = registry or GLOBAL_GLYPH_REGISTRY
    v = vector

    # Mode-based adjustments
    effective_formality = formality_bp
    if mode == "restrained":
        effective_formality = max(formality_bp, 7000)
    elif mode == "alert":
        v = v + EmojiVector(urgency=3000, caution=2000)

    # 1. Mathematical density budget
    budget = calculate_density_budget(v, formality_bp=effective_formality)

    if budget == 0 or mode == "restrained" and budget <= 1:
        if mode == "restrained" and budget == 1:
            budget = 0
        return EmojiSignalEnvelope(
            semantic_combo="",
            telemetry_banner=telemetry_renderer(v),
            telemetry_compact=v.one_line_receipt(top_n=3),
            density=0,
            position="none",
            emergent_tags=tuple(v.describe_algebra()),
        )

    # 2. Score candidate glyphs via dot-product affinities
    scored: list[tuple[int, GlyphDescriptor]] = []
    for g in reg.get_all_glyphs():
        score = compute_glyph_affinity(g, v)
        if score > 3500:  # Significance threshold
            scored.append((score, g))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 3. Compatibility & contradiction filtering among top candidates
    selected: list[GlyphDescriptor] = []
    for score, candidate in scored:
        if len(selected) >= budget:
            break
        # Verify compatibility against already selected glyphs
        compatible = True
        for existing in selected:
            compat_score = compute_glyph_compatibility(candidate, existing, v)
            if compat_score < -4000:
                compatible = False
                break
        if compatible:
            selected.append(candidate)

    # 4. Apply semantic sequential ordering (Causal syntax: Trigger → Action → State → Result)
    ordered_glyphs = sort_semantic_syntax(selected)
    combo = "".join(g.glyph for g in ordered_glyphs)

    # 5. Determine placement based on syntactic roles
    has_trigger = any(g.role == "trigger" for g in ordered_glyphs)
    has_action = any(g.role == "action" for g in ordered_glyphs)
    has_result = any(g.role == "result" for g in ordered_glyphs)

    if has_trigger or (has_action and not has_result):
        position = "prefix"
    elif has_result or (v.positive > 7500 and v.energy > 7500):
        position = "postfix"
    else:
        position = "prefix"

    telemetry_banner = telemetry_renderer(v, threshold_bp=3500)
    telemetry_compact = "".join(g.glyph for g in selected[:3]) or "🧠"

    return EmojiSignalEnvelope(
        semantic_combo=combo,
        telemetry_banner=telemetry_banner,
        telemetry_compact=telemetry_compact,
        density=len(selected),
        position=position,
        emergent_tags=tuple(v.describe_algebra()),
    )


# Alias synthesize_smart_emojis to emoji_renderer for backward compatibility
def synthesize_smart_emojis(
    vector: EmojiVector,
    intent_primary: str = "general",
    task_type: str = "general",
    urgency_bp: int = 3000,
    closeness_bp: int = 5000,
    formality_bp: int = 2000,
    mode: str = "conversational",
) -> EmojiSignalEnvelope:
    return emoji_renderer(vector, formality_bp=formality_bp, mode=mode)


# ============================================================
# DYNAMIC TASK MODULATOR (Vector Math Only - No Hardcoded Strings)
# ============================================================

def apply_task_modulation(current: EmojiVector, task_trigger: str) -> EmojiVector:
    """Modulate state vector continuously based on task characteristics."""
    t = task_trigger.lower().strip()

    if t in ("🐛", "debug", "verify", "verification", "check"):
        delta = EmojiVector(
            cognition=8800,
            investigation=9000,
            verification=9500,
            caution=7000,
            focus=9200,
            humor=0,
            energy=5000,
        )
        return current.blend(delta, alpha_bp=7500)

    elif t in ("🎉", "celebration", "fixed", "worked", "win"):
        delta = EmojiVector(
            warmth=8500,
            positive=9500,
            energy=9200,
            humor=8500,
            teasing=6500,
            intensity=8500,
            success=9500,
            verification=2000,
            caution=2000,
        )
        return current.blend(delta, alpha_bp=8000)

    elif t in ("🚨", "danger", "incident", "breach", "crisis"):
        delta = EmojiVector(
            urgency=9500,
            caution=9500,
            investigation=9200,
            verification=9500,
            focus=9500,
            fear=6500,
            energy=8500,
            humor=0,
            restraint=8500,
        )
        return current.blend(delta, alpha_bp=8500)

    elif t in ("📖", "creative", "story", "narrative"):
        delta = EmojiVector(
            creativity=9500,
            cognition=8500,
            expressiveness=9500,
            chaos=7500,
            curiosity=8500,
            verification=1500,
            caution=2500,
        )
        return current.blend(delta, alpha_bp=7500)

    elif t in ("💔", "grief", "sadness", "loss", "bereavement"):
        delta = EmojiVector(
            warmth=9500,
            sadness=9000,
            energy=1500,
            restraint=9000,
            humor=0,
            teasing=0,
            positive=500,
            trust=9000,
        )
        return current.blend(delta, alpha_bp=8500)

    return current

