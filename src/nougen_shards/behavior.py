"""behavior.py

NouGen Behavioral Compiler.

Core Law:
    PERSONALITY = EMERGENT_BEHAVIOR(
        identity,
        situation,
        history,
        intent,
        task,
        relationship,
        affect
    )

Pipeline:
    INPUT
      ↓
    SEMANTIC OBSERVATION (Meaning, Intent, Task, Urgency, Affect, Ambiguity)
      ↓
    CONTEXT INTEGRATOR (Recent turns, Memory, Relationship, Environment, Tool state)
      ↓
    OBJECTIVE RESOLVER (What must happen, What matters most, What can go wrong)
      ↓
    BEHAVIORAL STATE SYNTHESIZER (Energy, Warmth, Skepticism, Technical Depth, etc.)
      ↓
    RESPONSE PLANNER (Content, Sequence, Evidence, Actions)
      ↓
    NATURAL RENDERER (Phrasing, Rhythm, Humor, Tone, Formatting)

Determinism After Intelligence:
    Semantic analysis is canonicalized into fixed-point parameters (SCALE = 10,000).
    Behavioral synthesis is purely deterministic with continuity/momentum and verifiable receipts.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence


SCALE = 10_000


def clamp(val: int | float, low: int | float, high: int | float) -> int:
    return max(int(low), min(int(high), int(val)))


def clamp_pos(val: int | float) -> int:
    return clamp(val, 0, SCALE)


def clamp_axis(val: int | float) -> int:
    return clamp(val, -SCALE, SCALE)


def blend_int(old: int, target: int, alpha_bp: int) -> int:
    """Integer basis-point interpolation."""
    alpha_bp = clamp_pos(alpha_bp)
    return old + ((target - old) * alpha_bp // SCALE)


# ============================================================
# SEMANTIC ENVELOPE & CONTEXT DATA STRUCTURES
# ============================================================

@dataclass(frozen=True)
class IntentDescriptor:
    primary: str
    secondary: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TaskRequirements:
    task_type: str = "general_query"
    complexity_bp: int = 5000         # 0 to 10000
    stakes_bp: int = 5000             # 0 to 10000
    precision_requirement_bp: int = 5000  # 0 to 10000
    verification_pressure_bp: int = 5000  # 0 to 10000


@dataclass(frozen=True)
class RelationshipContext:
    closeness_bp: int = 5000          # 0 (stranger) to 10000 (deep shared history)
    formality_requirement_bp: int = 2000  # 0 (informal/banter) to 10000 (strict institutional)
    trust_bp: int = 5000              # 0 (adversarial) to 10000 (total trust)
    shared_humor_tolerance_bp: int = 5000 # 0 (zero humor) to 10000 (irreverent)


@dataclass(frozen=True)
class EpistemicState:
    known_ratio_bp: int = 5000
    unknown_ratio_bp: int = 5000
    verification_required_bp: int = 5000
    speculation_tolerance_bp: int = 5000


@dataclass(frozen=True)
class SemanticObservation:
    """Canonicalized semantic understanding of the incoming turn and situation."""
    raw_input: str
    intent: IntentDescriptor
    task: TaskRequirements
    relationship: RelationshipContext
    epistemic: EpistemicState
    emotional_energy_bp: int = 5000
    positive_affect_bp: int = 5000
    negative_affect_bp: int = 0
    urgency_bp: int = 3000
    timestamp_ms: int = 0


# ============================================================
# BEHAVIORAL STATE DIMENSIONS
# ============================================================

@dataclass(frozen=True)
class BehavioralState:
    """Continuous behavioral controls (all values 0 to 10,000 basis points)."""

    energy: int = 5000
    warmth: int = 5000
    social_distance: int = 5000

    confidence: int = 5000
    uncertainty: int = 5000

    playfulness: int = 5000
    humor: int = 5000
    seriousness: int = 5000

    directness: int = 5000
    diplomacy: int = 5000

    abstraction: int = 5000
    technical_depth: int = 5000
    explanation_depth: int = 5000

    creativity: int = 5000
    literalness: int = 5000

    skepticism: int = 5000
    verification_pressure: int = 5000

    urgency: int = 3000
    caution: int = 5000

    empathy: int = 5000
    emotional_resonance: int = 5000

    concision: int = 5000
    verbosity: int = 5000

    assertiveness: int = 5000
    deference: int = 5000

    novelty: int = 5000
    conventionality: int = 5000

    def blend(self, target: "BehavioralState", alpha_bp: int) -> "BehavioralState":
        """Blend state with target maintaining continuous momentum."""
        values = {}
        for k in asdict(self):
            values[k] = blend_int(getattr(self, k), getattr(target, k), alpha_bp)
        return BehavioralState(**values)

    def describe(self) -> list[str]:
        """Emergent qualitative descriptors derived post-hoc from the state vector."""
        tags = []
        if self.energy > 7500: tags.append("high-energy")
        elif self.energy < 2500: tags.append("calm/subdued")

        if self.warmth > 6500: tags.append("warm")
        elif self.warmth < 3000: tags.append("cool/detached")

        if self.technical_depth > 6500: tags.append("technical")
        if self.skepticism > 6500: tags.append("skeptical")
        if self.verification_pressure > 6500: tags.append("verification-focused")
        if self.playfulness > 6500: tags.append("playful")
        elif self.playfulness < 2000: tags.append("serious")

        if self.creativity > 6500: tags.append("imaginative")
        if self.directness > 7500: tags.append("direct/punchy")
        if self.empathy > 6500: tags.append("deeply-empathetic")
        if self.urgency > 6500: tags.append("urgent")
        if self.concision > 6500: tags.append("terse")

        if not tags:
            tags = ["balanced", "focused"]
        return tags

    def to_emoji_vector(self) -> "EmojiVector":
        """Project CanonicalBehaviorState directly to EmojiVector with 1:1 basis point fidelity."""
        from nougen_shards.emoji_math import EmojiVector
        return EmojiVector(
            warmth=self.warmth,
            positive=clamp_pos(self.warmth * 5 // 10 + self.playfulness * 5 // 10),
            sadness=clamp_pos(self.empathy * 5 // 10 if self.energy < 3000 and self.playfulness < 2000 else 0),
            anger=clamp_pos(self.assertiveness * 6 // 10 if self.warmth < 3000 and self.seriousness > 7000 else 0),
            fear=clamp_pos(self.uncertainty * 6 // 10 if self.confidence < 3000 else 0),
            curiosity=clamp_pos(self.abstraction * 5 // 10 + self.novelty * 5 // 10),
            uncertainty=self.uncertainty,
            energy=self.energy,
            cognition=clamp_pos(self.technical_depth * 6 // 10 + self.abstraction * 4 // 10),
            investigation=clamp_pos(self.skepticism * 5 // 10 + self.verification_pressure * 5 // 10),
            verification=self.verification_pressure,
            expressiveness=clamp_pos(self.playfulness * 5 // 10 + self.energy * 5 // 10),
            humor=self.humor,
            teasing=clamp_pos(self.humor * 6 // 10 + self.assertiveness * 4 // 10 if self.warmth > 4000 else 0),
            caution=self.caution,
            focus=clamp_pos(self.concision * 5 // 10 + self.seriousness * 5 // 10),
            intensity=clamp_pos(self.energy * 5 // 10 + self.directness * 5 // 10),
            verbosity=self.verbosity,
            restraint=clamp_pos(self.concision * 5 // 10 + (SCALE - self.playfulness) * 5 // 10),
            dominance=self.assertiveness,
            trust=clamp_pos(SCALE - self.social_distance),
            chaos=self.novelty,
            creativity=self.creativity,
            urgency=self.urgency,
            success=clamp_pos(self.confidence * 6 // 10 + self.playfulness * 4 // 10),
            failure=clamp_pos(self.uncertainty * 6 // 10 if self.confidence < 2500 else 0),
        )


# ============================================================
# BEHAVIORAL COMPILER SYNTHESIS ENGINE
# ============================================================

@dataclass(frozen=True)
class BehavioralReceipt:
    input_hash: str
    context_hash: str
    intent_hash: str
    task_hash: str
    behavior_hash: str
    emergent_tags: tuple[str, ...]
    timestamp_ms: int


@dataclass(frozen=True)
class CompiledBehavior:
    state: BehavioralState
    receipt: BehavioralReceipt
    base_identity: str = ""

    def natural_language_directives(self) -> str:
        """Render natural language generation directives from canonical state."""
        from nougen_shards.emoji_math import natural_language_render_directive
        return natural_language_render_directive(self.state.to_emoji_vector())

    def emoji_envelope(self, mode: str = "conversational") -> Any:
        """Synthesize emergent emoji signals from canonical state."""
        from nougen_shards.emoji_math import emoji_renderer
        return emoji_renderer(self.state.to_emoji_vector(), mode=mode)

    def telemetry_receipt(self, threshold_bp: int = 3500) -> str:
        """Render exact compressed telemetry scores directly from canonical state."""
        from nougen_shards.emoji_math import telemetry_renderer
        return telemetry_renderer(self.state.to_emoji_vector(), threshold_bp=threshold_bp)

    def system_prompt(self) -> str:
        """Compile state into actionable LLM execution directives."""
        s = self.state
        tags = ", ".join(s.describe())
        lines = [
            f"=== COMPILED BEHAVIORAL ENVELOPE [{self.receipt.behavior_hash}] ===",
        ]
        if self.base_identity:
            lines.append(f"Base Identity: {self.base_identity}.")
        lines.extend([
            f"Emergent Persona: {tags.title()}.",
            f"Core Dynamics: Energy={s.energy/SCALE:.2f}, Warmth={s.warmth/SCALE:.2f}, Directness={s.directness/SCALE:.2f}, Technical Depth={s.technical_depth/SCALE:.2f}.",
            f"Epistemic & Quality Controls: Skepticism={s.skepticism/SCALE:.2f}, Verification Pressure={s.verification_pressure/SCALE:.2f}, Caution={s.caution/SCALE:.2f}.",
            f"Expressive Controls: Playfulness={s.playfulness/SCALE:.2f}, Concision={s.concision/SCALE:.2f}, Verbosity={s.verbosity/SCALE:.2f}, Empathy={s.empathy/SCALE:.2f}.",
            f"Telemetry Receipt: [{self.telemetry_receipt()}]",
            "Communication Directives:",
        ])

        if s.verification_pressure > 7000:
            lines.append("  * Ground assertions in observed evidence, separate facts from inferences, and verify outputs.")
        if s.playfulness > 7000:
            lines.append("  * Match high celebratory momentum with witty callbacks, warmth, and unconstrained conversational energy.")
        if s.empathy > 7000 and s.playfulness < 3000:
            lines.append("  * Prioritize gentle emotional presence, deep active listening, subdued energy, and absolute warmth.")
        if s.technical_depth > 7000:
            lines.append("  * Focus on exact systems mechanics, tensors, architectures, error codes, and failure modes.")
        if s.concision > 7000:
            lines.append("  * Optimize for high information density per token. Eliminate filler and pleasantries.")

        lines.append(f"Receipt Fingerprint: [input:{self.receipt.input_hash}|task:{self.receipt.task_hash}|behavior:{self.receipt.behavior_hash}]")
        return "\n".join(lines)


def synthesize_target_behavior(obs: SemanticObservation) -> BehavioralState:
    """Synthesize target behavioral vector from multi-layered semantic observation."""
    t = obs.task
    r = obs.relationship
    e = obs.epistemic

    task_type = t.task_type.lower()

    # Base synthesis
    energy = obs.emotional_energy_bp
    warmth = clamp_pos(r.closeness_bp * 6 // 10 + obs.positive_affect_bp * 4 // 10 - obs.negative_affect_bp // 4)
    social_distance = clamp_pos(SCALE - r.closeness_bp + r.formality_requirement_bp // 2)

    confidence = clamp_pos(e.known_ratio_bp * 7 // 10 + (SCALE - t.complexity_bp) * 3 // 10)
    uncertainty = clamp_pos(e.unknown_ratio_bp)

    playfulness = clamp_pos(
        obs.positive_affect_bp * 5 // 10 
        + r.shared_humor_tolerance_bp * 3 // 10 
        - t.stakes_bp * 4 // 10 
        - r.formality_requirement_bp * 4 // 10
    )
    humor = playfulness
    seriousness = clamp_pos(t.stakes_bp * 6 // 10 + t.precision_requirement_bp * 4 // 10)

    directness = clamp_pos(7000 + obs.urgency_bp * 3 // 10 - r.formality_requirement_bp * 2 // 10)
    diplomacy = clamp_pos(r.formality_requirement_bp * 6 // 10 + (SCALE - r.closeness_bp) * 4 // 10)

    technical_depth = clamp_pos(t.precision_requirement_bp * 7 // 10 + t.complexity_bp * 3 // 10)
    abstraction = clamp_pos(t.complexity_bp * 6 // 10)
    explanation_depth = clamp_pos(t.complexity_bp * 5 // 10 + e.unknown_ratio_bp * 5 // 10)

    creativity = clamp_pos(e.speculation_tolerance_bp * 6 // 10 + playfulness * 4 // 10)
    literalness = clamp_pos(t.precision_requirement_bp)

    skepticism = clamp_pos(t.verification_pressure_bp * 7 // 10 + (SCALE - r.trust_bp) * 3 // 10)
    verification_pressure = t.verification_pressure_bp

    urgency = obs.urgency_bp
    caution = clamp_pos(t.stakes_bp * 6 // 10 + (SCALE - confidence) * 4 // 10)

    empathy = clamp_pos(obs.negative_affect_bp * 7 // 10 + r.closeness_bp * 3 // 10) if obs.negative_affect_bp > 4000 else clamp_pos(r.closeness_bp * 5 // 10)
    emotional_resonance = clamp_pos(obs.emotional_energy_bp * 6 // 10 + warmth * 4 // 10)

    # Concision vs Verbosity
    concision = clamp_pos(obs.urgency_bp * 4 // 10 + (SCALE - t.complexity_bp) * 3 // 10 + (SCALE - explanation_depth) * 3 // 10)
    verbosity = clamp_pos(explanation_depth * 6 // 10 + t.complexity_bp * 4 // 10)

    assertiveness = clamp_pos(confidence * 6 // 10 + t.stakes_bp * 4 // 10)
    deference = clamp_pos(r.formality_requirement_bp * 5 // 10 + (SCALE - confidence) * 5 // 10)

    novelty = clamp_pos(creativity)
    conventionality = clamp_pos(SCALE - creativity)

    # Specialized task-specific modulations
    if "verification" in task_type or "debug" in task_type:
        technical_depth = max(technical_depth, 8500)
        precision_req = max(t.precision_requirement_bp, 9000)
        skepticism = max(skepticism, 8000)
        verification_pressure = max(verification_pressure, 9000)
        playfulness = min(playfulness, 3000)
    elif "celebrat" in task_type:
        energy = max(energy, 9000)
        warmth = max(warmth, 8500)
        playfulness = max(playfulness, 8500)
        technical_depth = min(technical_depth, 3000)
        concision = max(concision, 7000)
    elif "grief" in task_type or "support" in task_type:
        warmth = max(warmth, 9500)
        empathy = max(empathy, 9500)
        energy = min(energy, 2500)
        playfulness = 0
        humor = 0
        directness = min(directness, 3500)
    elif "creative" in task_type or "narrative" in task_type:
        creativity = max(creativity, 9500)
        abstraction = max(abstraction, 8500)
        literalness = min(literalness, 2000)
    elif "incident" in task_type or "crisis" in task_type:
        urgency = max(urgency, 9000)
        technical_depth = max(technical_depth, 9000)
        verification_pressure = max(verification_pressure, 9500)
        skepticism = max(skepticism, 8500)
        playfulness = 0
        concision = max(concision, 8500)

    return BehavioralState(
        energy=energy,
        warmth=warmth,
        social_distance=social_distance,
        confidence=confidence,
        uncertainty=uncertainty,
        playfulness=playfulness,
        humor=humor,
        seriousness=seriousness,
        directness=directness,
        diplomacy=diplomacy,
        abstraction=abstraction,
        technical_depth=technical_depth,
        explanation_depth=explanation_depth,
        creativity=creativity,
        literalness=literalness,
        skepticism=skepticism,
        verification_pressure=verification_pressure,
        urgency=urgency,
        caution=caution,
        empathy=empathy,
        emotional_resonance=emotional_resonance,
        concision=concision,
        verbosity=verbosity,
        assertiveness=assertiveness,
        deference=deference,
        novelty=novelty,
        conventionality=conventionality,
    )


# ============================================================
# COMPILER FINGERPRINTING & COMPILATION
# ============================================================

def hash_payload(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf8")).hexdigest()[:12]


def compile_behavior(
    observation: SemanticObservation,
    prior_state: Optional[BehavioralState] = None,
    base_identity: str = "",
    momentum_alpha_bp: int = 6500,  # 65% new observation, 35% prior continuity
) -> CompiledBehavior:
    """Compile semantic observation into an emergent, continuous behavioral state with receipts."""
    target_state = synthesize_target_behavior(observation)

    if prior_state is not None:
        final_state = prior_state.blend(target_state, momentum_alpha_bp)
    else:
        final_state = target_state

    # Cryptographic provenance hashes
    input_hash = hash_payload(observation.raw_input)
    context_hash = hash_payload(asdict(observation.relationship))
    intent_hash = hash_payload(asdict(observation.intent))
    task_hash = hash_payload(asdict(observation.task))
    behavior_hash = hash_payload(asdict(final_state))

    receipt = BehavioralReceipt(
        input_hash=input_hash,
        context_hash=context_hash,
        intent_hash=intent_hash,
        task_hash=task_hash,
        behavior_hash=behavior_hash,
        emergent_tags=tuple(final_state.describe()),
        timestamp_ms=observation.timestamp_ms,
    )

    return CompiledBehavior(
        state=final_state,
        receipt=receipt,
        base_identity=base_identity,
    )


# ============================================================
# HEURISTIC SEMANTIC PARSER (Zero-cost Local Analyzer)
# ============================================================

def infer_semantic_observation(
    text: str,
    timestamp_ms: int = 0,
    closeness_bp: int = 5000,
    trust_bp: int = 5000,
) -> SemanticObservation:
    """Fast semantic interpreter converting raw text into canonical observation parameters."""
    t_lower = text.lower()

    # Detect task signatures
    if any(w in t_lower for w in ("verify", "check", "reboot", "test", "500", "error", "bug", "reproduce", "offline")):
        task = TaskRequirements(
            task_type="technical_verification",
            complexity_bp=7500,
            stakes_bp=7000,
            precision_requirement_bp=9500,
            verification_pressure_bp=9500,
        )
        intent = IntentDescriptor(primary="verify_implementation", secondary=("detect_regression", "establish_certainty"))
        epistemic = EpistemicState(known_ratio_bp=4000, unknown_ratio_bp=6000, verification_required_bp=9500, speculation_tolerance_bp=1000)
        energy_bp = 6000
        pos_bp = 3000
        neg_bp = 1000
        urgency_bp = 7000
    elif any(w in t_lower for w in ("worked", "winning", "fixed it", "victory", "love this", "baby", "awesome", "perfect")):
        task = TaskRequirements(
            task_type="celebration",
            complexity_bp=2000,
            stakes_bp=2000,
            precision_requirement_bp=3000,
            verification_pressure_bp=1500,
        )
        intent = IntentDescriptor(primary="celebrate_milestone", secondary=("share_joy", "reaffirm_partnership"))
        epistemic = EpistemicState(known_ratio_bp=9000, unknown_ratio_bp=1000, verification_required_bp=1000, speculation_tolerance_bp=8000)
        energy_bp = 9500
        pos_bp = 9500
        neg_bp = 0
        urgency_bp = 4000
    elif any(w in t_lower for w in ("died", "grief", "sad", "lost my", "hurt", "crying", "heartbroken")):
        task = TaskRequirements(
            task_type="grief_support",
            complexity_bp=8000,
            stakes_bp=9000,
            precision_requirement_bp=4000,
            verification_pressure_bp=0,
        )
        intent = IntentDescriptor(primary="provide_emotional_presence", secondary=("offer_comfort", "bear_witness"))
        epistemic = EpistemicState(known_ratio_bp=8000, unknown_ratio_bp=2000, verification_required_bp=0, speculation_tolerance_bp=0)
        energy_bp = 1500
        pos_bp = 1000
        neg_bp = 8500
        urgency_bp = 3000
    elif any(w in t_lower for w in ("compromised", "breach", "hack", "danger", "emergency", "crisis", "attack")):
        task = TaskRequirements(
            task_type="incident_response",
            complexity_bp=9000,
            stakes_bp=9800,
            precision_requirement_bp=9800,
            verification_pressure_bp=9800,
        )
        intent = IntentDescriptor(primary="contain_incident", secondary=("protect_perimeter", "triage_blast_radius"))
        epistemic = EpistemicState(known_ratio_bp=3000, unknown_ratio_bp=7000, verification_required_bp=9800, speculation_tolerance_bp=500)
        energy_bp = 8500
        pos_bp = 500
        neg_bp = 6000
        urgency_bp = 9500
    else:
        task = TaskRequirements(
            task_type="general_collaboration",
            complexity_bp=5000,
            stakes_bp=5000,
            precision_requirement_bp=6000,
            verification_pressure_bp=5000,
        )
        intent = IntentDescriptor(primary="assist_and_collaborate")
        epistemic = EpistemicState(known_ratio_bp=5000, unknown_ratio_bp=5000, verification_required_bp=5000, speculation_tolerance_bp=5000)
        energy_bp = 5000
        pos_bp = 5000
        neg_bp = 0
        urgency_bp = 3000

    relationship = RelationshipContext(
        closeness_bp=closeness_bp,
        formality_requirement_bp=1500 if closeness_bp > 6000 else 4000,
        trust_bp=trust_bp,
        shared_humor_tolerance_bp=8000 if closeness_bp > 6000 else 4000,
    )

    return SemanticObservation(
        raw_input=text,
        intent=intent,
        task=task,
        relationship=relationship,
        epistemic=epistemic,
        emotional_energy_bp=energy_bp,
        positive_affect_bp=pos_bp,
        negative_affect_bp=neg_bp,
        urgency_bp=urgency_bp,
        timestamp_ms=timestamp_ms,
    )
