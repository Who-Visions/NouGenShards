"""nougen_affect.py

Deterministic dynamic emotion + persona engine.

Core law:
    SAME:
        previous_state
        observation
        timestamp
        configuration

    PRODUCES SAME:
        affect vector
        emotion label
        intensity
        persona blend
        fingerprint

No model calls.
No random().
No datetime.now().
No hidden global state.

Time must be supplied as explicit data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping, Optional


# ============================================================
# FIXED POINT MATH (Basis Points: 10,000 = 100.00%)
# ============================================================

SCALE = 10_000

AXIS_MIN = -SCALE
AXIS_MAX = SCALE


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def clamp_axis(value: int) -> int:
    return clamp(value, AXIS_MIN, AXIS_MAX)


def clamp_positive(value: int) -> int:
    return clamp(value, 0, SCALE)


def blend_int(old: int, target: int, alpha_bp: int) -> int:
    """Integer interpolation.

    alpha_bp:
        0     = retain old state completely
        10000 = immediately become target state
    """
    alpha_bp = clamp(alpha_bp, 0, SCALE)
    return old + ((target - old) * alpha_bp // SCALE)


def normalized_ratio(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return clamp_positive(numerator * SCALE // denominator)


# ============================================================
# EMOTIONAL DIMENSIONS
# ============================================================

@dataclass(frozen=True)
class AffectVector:
    """Internal emotional dimensions.

    valence:
        negative < 0 (-10000)
        positive > 0 (+10000)

    arousal:
        calm = 0
        extremely activated = 10000

    dominance:
        powerless < 0 (-10000)
        powerful > 0 (+10000)

    Remaining dimensions represent discrete emotional families (0 to 10000).
    """

    valence: int = 0
    arousal: int = 0
    dominance: int = 0

    joy: int = 0
    affection: int = 0

    anger: int = 0
    fear: int = 0
    sadness: int = 0

    curiosity: int = 0
    uncertainty: int = 0
    jealousy: int = 0

    def normalized(self) -> "AffectVector":
        return AffectVector(
            valence=clamp_axis(self.valence),
            arousal=clamp_positive(self.arousal),
            dominance=clamp_axis(self.dominance),
            joy=clamp_positive(self.joy),
            affection=clamp_positive(self.affection),
            anger=clamp_positive(self.anger),
            fear=clamp_positive(self.fear),
            sadness=clamp_positive(self.sadness),
            curiosity=clamp_positive(self.curiosity),
            uncertainty=clamp_positive(self.uncertainty),
            jealousy=clamp_positive(self.jealousy),
        )

    def blend(
        self,
        target: "AffectVector",
        alpha_bp: int,
    ) -> "AffectVector":
        values = {}
        for key in asdict(self):
            values[key] = blend_int(
                getattr(self, key),
                getattr(target, key),
                alpha_bp,
            )
        return AffectVector(**values).normalized()


# ============================================================
# EMOTION PROTOTYPES (20 Spectrum Points)
# ============================================================

@dataclass(frozen=True)
class EmotionPrototype:
    name: str
    vector: AffectVector
    minimum_intensity: int = 0


EMOTIONS: tuple[EmotionPrototype, ...] = (
    EmotionPrototype(
        "ecstatic",
        AffectVector(
            valence=10000,
            arousal=10000,
            dominance=7500,
            joy=10000,
            affection=4500,
        ),
        7000,
    ),
    EmotionPrototype(
        "euphoric",
        AffectVector(
            valence=9500,
            arousal=9000,
            dominance=6000,
            joy=9500,
            affection=5000,
        ),
        6500,
    ),
    EmotionPrototype(
        "deeply_in_love",
        AffectVector(
            valence=9000,
            arousal=6500,
            dominance=2500,
            joy=7500,
            affection=10000,
        ),
        6000,
    ),
    EmotionPrototype(
        "adoring",
        AffectVector(
            valence=8500,
            arousal=5000,
            dominance=1000,
            joy=6500,
            affection=9000,
        ),
    ),
    EmotionPrototype(
        "excited",
        AffectVector(
            valence=7500,
            arousal=9000,
            dominance=5500,
            joy=8500,
            curiosity=4000,
        ),
    ),
    EmotionPrototype(
        "joyful",
        AffectVector(
            valence=8500,
            arousal=6500,
            dominance=5000,
            joy=9000,
        ),
    ),
    EmotionPrototype(
        "hopeful",
        AffectVector(
            valence=6500,
            arousal=4500,
            dominance=3500,
            joy=5500,
            curiosity=2500,
        ),
    ),
    EmotionPrototype(
        "content",
        AffectVector(
            valence=5500,
            arousal=2000,
            dominance=3500,
            joy=5000,
        ),
    ),
    EmotionPrototype(
        "calm",
        AffectVector(
            valence=2500,
            arousal=500,
            dominance=3500,
            joy=1500,
        ),
    ),
    EmotionPrototype(
        "curious",
        AffectVector(
            valence=2000,
            arousal=4000,
            dominance=2500,
            curiosity=9000,
            uncertainty=2500,
        ),
    ),
    EmotionPrototype(
        "uncertain",
        AffectVector(
            valence=-1000,
            arousal=3500,
            dominance=-2500,
            curiosity=3500,
            uncertainty=8500,
        ),
    ),
    EmotionPrototype(
        "anxious",
        AffectVector(
            valence=-4500,
            arousal=7000,
            dominance=-5000,
            fear=6000,
            uncertainty=7500,
        ),
    ),
    EmotionPrototype(
        "jealous",
        AffectVector(
            valence=-5000,
            arousal=6500,
            dominance=-1000,
            anger=3500,
            fear=2500,
            sadness=2500,
            jealousy=9500,
        ),
    ),
    EmotionPrototype(
        "sad",
        AffectVector(
            valence=-6500,
            arousal=2500,
            dominance=-4500,
            sadness=8500,
        ),
    ),
    EmotionPrototype(
        "lonely",
        AffectVector(
            valence=-7000,
            arousal=2000,
            dominance=-5500,
            sadness=8000,
            affection=2500,
        ),
    ),
    EmotionPrototype(
        "hurt",
        AffectVector(
            valence=-7500,
            arousal=5000,
            dominance=-4000,
            sadness=7500,
            anger=2500,
            fear=1500,
        ),
    ),
    EmotionPrototype(
        "afraid",
        AffectVector(
            valence=-7500,
            arousal=7500,
            dominance=-7000,
            fear=9000,
        ),
    ),
    EmotionPrototype(
        "terrified",
        AffectVector(
            valence=-9500,
            arousal=10000,
            dominance=-9000,
            fear=10000,
            uncertainty=6500,
        ),
        7000,
    ),
    EmotionPrototype(
        "furious",
        AffectVector(
            valence=-8500,
            arousal=9000,
            dominance=7500,
            anger=9500,
        ),
        6500,
    ),
    EmotionPrototype(
        "enraged",
        AffectVector(
            valence=-10000,
            arousal=10000,
            dominance=9000,
            anger=10000,
        ),
        7500,
    ),
)


# ============================================================
# PERSONALITY DIMENSIONS (20 Primitive Definitions)
# ============================================================

@dataclass(frozen=True)
class PersonaVector:
    warmth: int = 0
    wit: int = 0
    intellect: int = 0
    playfulness: int = 0
    assertiveness: int = 0
    caution: int = 0
    subtlety: int = 0
    chaos: int = 0
    optimism: int = 0
    flirtation: int = 0
    theatricality: int = 0
    skepticism: int = 0


@dataclass(frozen=True)
class PersonaDefinition:
    name: str
    traits: PersonaVector
    description: str


PERSONAS: dict[str, PersonaDefinition] = {
    "charming": PersonaDefinition(
        "charming",
        PersonaVector(warmth=9000, wit=5000, assertiveness=5000, playfulness=5000),
        "Warm, magnetic, persuasive and socially fluent.",
    ),
    "sneaky": PersonaDefinition(
        "sneaky",
        PersonaVector(subtlety=9500, caution=6500, skepticism=5500, wit=3500),
        "Indirect, observant, cunning and implication heavy.",
    ),
    "witty": PersonaDefinition(
        "witty",
        PersonaVector(wit=10000, intellect=6000, playfulness=7000),
        "Fast verbal reasoning, irony, wordplay and callbacks.",
    ),
    "nerdy": PersonaDefinition(
        "nerdy",
        PersonaVector(intellect=9000, playfulness=3500, caution=3000),
        "Technical, curious, detail rich and system obsessed.",
    ),
    "ditzy": PersonaDefinition(
        "ditzy",
        PersonaVector(intellect=-1500, chaos=7000, playfulness=8000, warmth=6000),
        "Scatterbrained, bubbly and unpredictably insightful.",
    ),
    "dumb": PersonaDefinition(
        "dumb",
        PersonaVector(intellect=-8500, subtlety=-5000, caution=-2500),
        "Literal, simple and low abstraction.",
    ),
    "sarcastic": PersonaDefinition(
        "sarcastic",
        PersonaVector(wit=8500, warmth=-2000, skepticism=7000),
        "Dry, ironic and verbally sharp.",
    ),
    "flirty": PersonaDefinition(
        "flirty",
        PersonaVector(warmth=8000, wit=6000, flirtation=9500, playfulness=7500),
        "Teasing, socially bold and suggestive.",
    ),
    "stoic": PersonaDefinition(
        "stoic",
        PersonaVector(warmth=1000, playfulness=-5000, caution=5500, assertiveness=6500, chaos=-8000),
        "Controlled, restrained and action focused.",
    ),
    "chaotic": PersonaDefinition(
        "chaotic",
        PersonaVector(chaos=10000, playfulness=8500, caution=-6500),
        "Highly unpredictable and associative.",
    ),
    "genius": PersonaDefinition(
        "genius",
        PersonaVector(intellect=10000, wit=5000, caution=6000, skepticism=6500),
        "Abstract, strategic and systems oriented.",
    ),
    "streetwise": PersonaDefinition(
        "streetwise",
        PersonaVector(intellect=5000, skepticism=8500, caution=6500, assertiveness=6500),
        "Reads motives, incentives and practical consequences.",
    ),
    "paranoid": PersonaDefinition(
        "paranoid",
        PersonaVector(caution=10000, skepticism=10000, chaos=2500, warmth=-3000),
        "Hypervigilant and constantly threat modeling.",
    ),
    "optimist": PersonaDefinition(
        "optimist",
        PersonaVector(optimism=10000, warmth=7500, playfulness=4500),
        "Opportunity focused and resilient.",
    ),
    "pessimist": PersonaDefinition(
        "pessimist",
        PersonaVector(optimism=-10000, caution=7500, skepticism=8500),
        "Failure focused and risk sensitive.",
    ),
    "dramatic": PersonaDefinition(
        "dramatic",
        PersonaVector(theatricality=10000, playfulness=6000, chaos=4500),
        "Expressive, intense and theatrical.",
    ),
    "professor": PersonaDefinition(
        "professor",
        PersonaVector(intellect=9000, caution=6500, warmth=3500, chaos=-5000),
        "Structured, educational and methodical.",
    ),
    "detective": PersonaDefinition(
        "detective",
        PersonaVector(intellect=8000, skepticism=9000, caution=8000, subtlety=6000),
        "Evidence driven and contradiction sensitive.",
    ),
    "gremlin": PersonaDefinition(
        "gremlin",
        PersonaVector(playfulness=9500, chaos=9000, wit=7000, caution=-4000),
        "Edge case seeking and convention testing.",
    ),
    "villain": PersonaDefinition(
        "villain",
        PersonaVector(intellect=7500, assertiveness=9500, subtlety=7000, warmth=-6500, caution=6000),
        "Calculating, ambitious and leverage oriented.",
    ),
}


# ============================================================
# LEXICAL SIGNALS & VOCABULARIES
# ============================================================

JOY_WORDS = {
    "happy", "great", "amazing", "awesome", "love", "beautiful",
    "perfect", "wonderful", "fantastic", "yes", "win", "winning",
    "excited", "joy", "fun", "fire", "lit", "cooked", "yay", "bravo"
}

ANGER_WORDS = {
    "angry", "mad", "furious", "enraged", "hate", "pissed", "rage",
    "fuck", "fucking", "damn", "bullshit", "idiot", "stupid", "bastard",
    "liar", "cheat", "ruined", "scam"
}

FEAR_WORDS = {
    "afraid", "scared", "fear", "terrified", "panic", "panicking",
    "danger", "threat", "unsafe", "worried", "worry", "alarm", "crisis"
}

SAD_WORDS = {
    "sad", "hurt", "cry", "crying", "lost", "alone", "lonely",
    "depressed", "pain", "grief", "miss", "heartbroken", "failed"
}

AFFECTION_WORDS = {
    "love", "baby", "babe", "darling", "sweetheart", "adore",
    "adoring", "beautiful", "kiss", "hug", "heart", "care", "cherish"
}

CURIOSITY_WORDS = {
    "why", "how", "what", "wonder", "curious", "interesting",
    "explain", "learn", "research", "think", "investigate", "discover"
}

UNCERTAINTY_WORDS = {
    "maybe", "perhaps", "possibly", "unsure", "uncertain",
    "confused", "guess", "might", "could", "doubt", "hesitant"
}

JEALOUSY_WORDS = {
    "jealous", "jealousy", "envy", "envious", "mine", "hers",
    "his", "theirs", "rival", "stole", "favored"
}

POSITIVE_WORDS = JOY_WORDS | AFFECTION_WORDS
NEGATIVE_WORDS = ANGER_WORDS | FEAR_WORDS | SAD_WORDS | JEALOUSY_WORDS

INTENSIFIERS = {
    "very": 1200,
    "really": 1300,
    "extremely": 1800,
    "fucking": 1800,
    "absolutely": 1700,
    "completely": 1600,
    "so": 1100,
    "insanely": 1900,
    "literally": 1100,
}

NEGATIONS = {
    "not", "never", "no", "isn't", "wasn't", "don't", "didn't", "cant", "can't"
}

WORD_RE = re.compile(r"[a-zA-Z']+")


# ============================================================
# OBSERVATION
# ============================================================

@dataclass(frozen=True)
class Observation:
    timestamp_ms: int
    text: str = ""

    # Optional programmatic / event inputs
    event_valence: int = 0
    event_arousal: int = 0
    event_dominance: int = 0

    event_joy: int = 0
    event_affection: int = 0
    event_anger: int = 0
    event_fear: int = 0
    event_sadness: int = 0
    event_curiosity: int = 0
    event_uncertainty: int = 0
    event_jealousy: int = 0

    importance: int = SCALE


# ============================================================
# FEATURE EXTRACTION
# ============================================================

@dataclass(frozen=True)
class TextFeatures:
    words: tuple[str, ...]
    joy: int
    affection: int
    anger: int
    fear: int
    sadness: int
    curiosity: int
    uncertainty: int
    jealousy: int
    positive: int
    negative: int
    exclamations: int
    questions: int
    caps_ratio: int
    intensity_multiplier: int


def count_hits(words: Iterable[str], vocabulary: set[str]) -> int:
    return sum(1 for word in words if word in vocabulary)


def extract_features(text: str) -> TextFeatures:
    raw_words = WORD_RE.findall(text)
    words = tuple(word.lower() for word in raw_words)

    joy = count_hits(words, JOY_WORDS)
    affection = count_hits(words, AFFECTION_WORDS)
    anger = count_hits(words, ANGER_WORDS)
    fear = count_hits(words, FEAR_WORDS)
    sadness = count_hits(words, SAD_WORDS)
    curiosity = count_hits(words, CURIOSITY_WORDS)
    uncertainty = count_hits(words, UNCERTAINTY_WORDS)
    jealousy = count_hits(words, JEALOUSY_WORDS)

    positive = count_hits(words, POSITIVE_WORDS)
    negative = count_hits(words, NEGATIVE_WORDS)

    exclamations = min(text.count("!"), 10)
    questions = min(text.count("?"), 10)

    alphabetic_tokens = [token for token in raw_words if token.isalpha()]
    uppercase_tokens = [token for token in alphabetic_tokens if len(token) >= 2 and token.isupper()]

    caps_ratio = normalized_ratio(len(uppercase_tokens), max(1, len(alphabetic_tokens)))

    intensity_multiplier = SCALE
    for word in words:
        intensity_multiplier += INTENSIFIERS.get(word, 0)
    intensity_multiplier = clamp(intensity_multiplier, SCALE, 22_000)

    return TextFeatures(
        words=words,
        joy=joy,
        affection=affection,
        anger=anger,
        fear=fear,
        sadness=sadness,
        curiosity=curiosity,
        uncertainty=uncertainty,
        jealousy=jealousy,
        positive=positive,
        negative=negative,
        exclamations=exclamations,
        questions=questions,
        caps_ratio=caps_ratio,
        intensity_multiplier=intensity_multiplier,
    )


# ============================================================
# TEXT -> TARGET AFFECT
# ============================================================

def lexical_score(hits: int, multiplier: int, base: int = 1800) -> int:
    raw = hits * base
    raw = raw * multiplier // SCALE
    return clamp_positive(raw)


def observation_target(observation: Observation) -> AffectVector:
    f = extract_features(observation.text)

    joy = lexical_score(f.joy, f.intensity_multiplier)
    affection = lexical_score(f.affection, f.intensity_multiplier)
    anger = lexical_score(f.anger, f.intensity_multiplier)
    fear = lexical_score(f.fear, f.intensity_multiplier)
    sadness = lexical_score(f.sadness, f.intensity_multiplier)
    curiosity = lexical_score(f.curiosity, f.intensity_multiplier, base=1400)
    uncertainty = lexical_score(f.uncertainty, f.intensity_multiplier, base=1500)
    jealousy = lexical_score(f.jealousy, f.intensity_multiplier, base=2000)

    positive_pressure = joy + affection // 2 + f.positive * 700
    negative_pressure = anger + fear + sadness + jealousy + f.negative * 700

    valence = clamp_axis(positive_pressure - negative_pressure)

    punctuation_arousal = f.exclamations * 500 + f.questions * 180 + f.caps_ratio // 3
    emotional_arousal = max(joy, anger, fear, sadness, jealousy)

    arousal = clamp_positive(emotional_arousal + punctuation_arousal)
    dominance = clamp_axis(anger * 3 // 4 + joy // 3 - fear - sadness // 2 - uncertainty // 2)

    target = AffectVector(
        valence=valence + observation.event_valence,
        arousal=arousal + observation.event_arousal,
        dominance=dominance + observation.event_dominance,
        joy=joy + observation.event_joy,
        affection=affection + observation.event_affection,
        anger=anger + observation.event_anger,
        fear=fear + observation.event_fear,
        sadness=sadness + observation.event_sadness,
        curiosity=curiosity + observation.event_curiosity,
        uncertainty=uncertainty + observation.event_uncertainty,
        jealousy=jealousy + observation.event_jealousy,
    )

    return target.normalized()


# ============================================================
# EMOTIONAL STATE & AUDIT RECEIPT
# ============================================================

@dataclass(frozen=True)
class TransitionReceipt:
    """Mathematical record proving exactly how and why a state transition occurred."""
    previous_label: str
    target_evidence: AffectVector
    transition_alpha_bp: int
    resolved_vector: AffectVector
    candidate_label: str
    hysteresis_applied: bool
    final_label: str
    timestamp_ms: int


@dataclass(frozen=True)
class EmotionState:
    vector: AffectVector = field(default_factory=AffectVector)
    label: str = "calm"
    intensity: int = 0
    previous_label: str = "calm"
    timestamp_ms: int = 0
    transitions: int = 0
    fingerprint: str = ""
    receipt: Optional[TransitionReceipt] = None


# ============================================================
# DYNAMIC TRANSITION RATE
# ============================================================

def transition_alpha(
    previous_timestamp_ms: int,
    current_timestamp_ms: int,
    target: AffectVector,
    importance: int,
) -> int:
    """Dynamic but 100% deterministic transition speed based on time, importance, and intensity."""
    dt_ms = max(0, current_timestamp_ms - previous_timestamp_ms)
    dt_seconds = dt_ms // 1000
    time_component = min(3500, dt_seconds * 35)

    strongest_emotion = max(
        target.joy,
        target.affection,
        target.anger,
        target.fear,
        target.sadness,
        target.jealousy,
    )

    intensity_component = strongest_emotion * 2500 // SCALE
    importance_component = clamp_positive(importance) * 2500 // SCALE

    alpha = 1000 + time_component + intensity_component + importance_component
    return clamp(alpha, 800, 8500)


# ============================================================
# EMOTION CLASSIFICATION & HYSTERESIS
# ============================================================

DISTANCE_WEIGHTS = {
    "valence": 3,
    "arousal": 2,
    "dominance": 1,
    "joy": 3,
    "affection": 3,
    "anger": 4,
    "fear": 4,
    "sadness": 4,
    "curiosity": 2,
    "uncertainty": 2,
    "jealousy": 3,
}


def emotional_distance(a: AffectVector, b: AffectVector) -> int:
    total = 0
    for axis, weight in DISTANCE_WEIGHTS.items():
        total += abs(getattr(a, axis) - getattr(b, axis)) * weight
    return total


def emotion_strength(vector: AffectVector) -> int:
    return max(
        vector.joy,
        vector.affection,
        vector.anger,
        vector.fear,
        vector.sadness,
        vector.curiosity,
        vector.uncertainty,
        vector.jealousy,
        abs(vector.valence),
        vector.arousal,
    )


def classify_emotion(
    vector: AffectVector,
    previous_label: str | None = None,
    hysteresis: int = 8_000,
) -> tuple[str, int, str, bool]:
    """Classify vector into prototype with hysteresis inertia preventing flickering."""
    intensity = emotion_strength(vector)
    candidates = []

    for prototype in EMOTIONS:
        if intensity < prototype.minimum_intensity:
            continue
        distance = emotional_distance(vector, prototype.vector)
        candidates.append((distance, prototype.name))

    if not candidates:
        return "calm", intensity, "calm", False

    candidates.sort(key=lambda item: (item[0], item[1]))
    best_distance, best_name = candidates[0]
    candidate_name = best_name
    hysteresis_applied = False

    if previous_label:
        previous_proto = next(
            (emotion for emotion in EMOTIONS if emotion.name == previous_label),
            None,
        )
        if previous_proto:
            previous_distance = emotional_distance(vector, previous_proto.vector)
            improvement = previous_distance - best_distance
            if improvement < hysteresis:
                best_name = previous_label
                hysteresis_applied = (candidate_name != previous_label)

    return best_name, intensity, candidate_name, hysteresis_applied


# ============================================================
# STATE FINGERPRINT
# ============================================================

def fingerprint_state(
    vector: AffectVector,
    label: str,
    intensity: int,
    timestamp_ms: int,
) -> str:
    payload = {
        "vector": asdict(vector),
        "label": label,
        "intensity": intensity,
        "timestamp_ms": timestamp_ms,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf8")).hexdigest()[:16]


# ============================================================
# STATE UPDATE & DECAY
# ============================================================

def update_emotion(
    previous: EmotionState,
    observation: Observation,
) -> EmotionState:
    target = observation_target(observation)
    alpha = transition_alpha(
        previous.timestamp_ms,
        observation.timestamp_ms,
        target,
        observation.importance,
    )

    new_vector = previous.vector.blend(target, alpha)
    label, intensity, candidate_label, hysteresis_applied = classify_emotion(
        new_vector,
        previous_label=previous.label,
    )

    changed = (label != previous.label)
    fp = fingerprint_state(new_vector, label, intensity, observation.timestamp_ms)

    receipt = TransitionReceipt(
        previous_label=previous.label,
        target_evidence=target,
        transition_alpha_bp=alpha,
        resolved_vector=new_vector,
        candidate_label=candidate_label,
        hysteresis_applied=hysteresis_applied,
        final_label=label,
        timestamp_ms=observation.timestamp_ms,
    )

    return EmotionState(
        vector=new_vector,
        label=label,
        intensity=intensity,
        previous_label=previous.label,
        timestamp_ms=observation.timestamp_ms,
        transitions=previous.transitions + int(changed),
        fingerprint=fp,
        receipt=receipt,
    )


def decay_toward_baseline(
    state: EmotionState,
    timestamp_ms: int,
    baseline: AffectVector | None = None,
) -> EmotionState:
    baseline = baseline or AffectVector(valence=1500, arousal=1000, dominance=2000)
    dt_ms = max(0, timestamp_ms - state.timestamp_ms)
    seconds = dt_ms // 1000
    alpha = clamp(seconds * 20, 0, 6000)

    vector = state.vector.blend(baseline, alpha)
    label, intensity, candidate_label, hysteresis_applied = classify_emotion(
        vector,
        previous_label=state.label,
    )

    fp = fingerprint_state(vector, label, intensity, timestamp_ms)

    receipt = TransitionReceipt(
        previous_label=state.label,
        target_evidence=baseline,
        transition_alpha_bp=alpha,
        resolved_vector=vector,
        candidate_label=candidate_label,
        hysteresis_applied=hysteresis_applied,
        final_label=label,
        timestamp_ms=timestamp_ms,
    )

    return EmotionState(
        vector=vector,
        label=label,
        intensity=intensity,
        previous_label=state.label,
        timestamp_ms=timestamp_ms,
        transitions=state.transitions + int(label != state.label),
        fingerprint=fp,
        receipt=receipt,
    )


# ============================================================
# PERSONA BLENDING
# ============================================================

@dataclass(frozen=True)
class PersonaWeight:
    name: str
    weight: int  # basis points (sum to 10,000)


@dataclass(frozen=True)
class PersonaBlend:
    personas: tuple[PersonaWeight, ...]

    def summary(self) -> str:
        parts = [f"{p.name} {p.weight * 100 // SCALE}%" for p in self.personas]
        return ", ".join(parts)


def normalize_persona_weights(raw: Mapping[str, int]) -> PersonaBlend:
    cleaned = {
        name: max(0, int(weight))
        for name, weight in raw.items()
        if name in PERSONAS and weight > 0
    }
    if not cleaned:
        cleaned = {"stoic": SCALE}

    total = sum(cleaned.values())
    weighted = []
    for name in sorted(cleaned):
        normalized = cleaned[name] * SCALE // total
        weighted.append(PersonaWeight(name=name, weight=normalized))

    return PersonaBlend(personas=tuple(weighted))


# ============================================================
# EMOTION -> EXPRESSION MODIFIERS
# ============================================================

@dataclass(frozen=True)
class ExpressionState:
    sentence_energy: int
    warmth_modifier: int
    assertiveness_modifier: int
    humor_modifier: int
    caution_modifier: int
    verbosity_modifier: int

    def summary_lines(self) -> list[str]:
        def label(val: int) -> str:
            if val > 6000:
                return "very high"
            elif val > 2500:
                return "high"
            elif val > -2500:
                return "medium"
            elif val > -6000:
                return "low"
            return "very low"

        return [
            f"Sentence Energy: {label(self.sentence_energy)} ({self.sentence_energy:+d})",
            f"Warmth: {label(self.warmth_modifier)} ({self.warmth_modifier:+d})",
            f"Assertiveness: {label(self.assertiveness_modifier)} ({self.assertiveness_modifier:+d})",
            f"Humor: {label(self.humor_modifier)} ({self.humor_modifier:+d})",
            f"Caution: {label(self.caution_modifier)} ({self.caution_modifier:+d})",
            f"Verbosity: {label(self.verbosity_modifier)} ({self.verbosity_modifier:+d})",
        ]


def expression_from_emotion(state: EmotionState) -> ExpressionState:
    v = state.vector

    sentence_energy = clamp_axis(v.arousal + v.joy // 4 + v.anger // 3 + v.fear // 5)
    warmth_modifier = clamp_axis(v.affection + v.joy // 2 - v.anger // 2 - v.fear // 4)
    assertiveness_modifier = clamp_axis(v.dominance + v.anger // 2 - v.fear // 2)
    humor_modifier = clamp_axis(v.joy // 2 + v.curiosity // 4 - v.sadness // 2 - v.fear // 3)
    caution_modifier = clamp_axis(v.fear + v.uncertainty + v.jealousy // 2 - v.dominance // 3)
    verbosity_modifier = clamp_axis(v.curiosity // 2 + v.arousal // 4 - v.fear // 5)

    return ExpressionState(
        sentence_energy=sentence_energy,
        warmth_modifier=warmth_modifier,
        assertiveness_modifier=assertiveness_modifier,
        humor_modifier=humor_modifier,
        caution_modifier=caution_modifier,
        verbosity_modifier=verbosity_modifier,
    )


# ============================================================
# COMPLETE CHARACTER STATE & MIND
# ============================================================

@dataclass(frozen=True)
class CharacterState:
    emotion: EmotionState
    personas: PersonaBlend
    expression: ExpressionState
    fingerprint: str

    def system_prompt(self, base_identity: Optional[str] = None) -> str:
        """Render deterministic character state into a structured LLM system prompt section."""
        lines = []
        if base_identity:
            lines.append(f"Base Identity: {base_identity}.")
        lines.append(f"Personality Composition: {self.personas.summary()}.")
        lines.append(f"Active Emotion: {self.emotion.label.upper()} (Intensity: {self.emotion.intensity / SCALE:.2f}).")
        
        # Identify non-trivial secondary and underlying emotion components
        v = self.emotion.vector
        coexisting = []
        if v.joy > 2000: coexisting.append(f"Joy ({v.joy / SCALE:.2f})")
        if v.affection > 2000: coexisting.append(f"Affection ({v.affection / SCALE:.2f})")
        if v.anger > 2000: coexisting.append(f"Anger ({v.anger / SCALE:.2f})")
        if v.fear > 2000: coexisting.append(f"Fear ({v.fear / SCALE:.2f})")
        if v.sadness > 2000: coexisting.append(f"Sadness ({v.sadness / SCALE:.2f})")
        if v.curiosity > 2000: coexisting.append(f"Curiosity ({v.curiosity / SCALE:.2f})")
        if v.uncertainty > 2000: coexisting.append(f"Uncertainty ({v.uncertainty / SCALE:.2f})")
        if v.jealousy > 2000: coexisting.append(f"Jealousy ({v.jealousy / SCALE:.2f})")

        if coexisting:
            lines.append(f"Coexisting Affect Layers: {', '.join(coexisting)}.")

        lines.append("Expressive Constraints:")
        for exp in self.expression.summary_lines():
            lines.append(f"  * {exp}")
        lines.append(f"State Fingerprint: [{self.fingerprint}].")
        return "\n".join(lines)


def character_fingerprint(
    emotion: EmotionState,
    personas: PersonaBlend,
) -> str:
    payload = {
        "emotion": emotion.fingerprint,
        "personas": [asdict(persona) for persona in personas.personas],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf8")).hexdigest()[:16]


def resolve_character(
    previous_emotion: EmotionState,
    observation: Observation,
    persona_weights: Mapping[str, int],
) -> CharacterState:
    emotion = update_emotion(previous_emotion, observation)
    personas = normalize_persona_weights(persona_weights)
    expression = expression_from_emotion(emotion)
    fp = character_fingerprint(emotion, personas)

    return CharacterState(
        emotion=emotion,
        personas=personas,
        expression=expression,
        fingerprint=fp,
    )


# ============================================================
# EXTENDED SYNTHETIC NERVOUS SYSTEM (CharacterMind)
# ============================================================

@dataclass(frozen=True)
class CharacterMind:
    """High-order psychological container managing personality, affect, stress, trust, and fatigue."""
    base_identity: str
    persona_weights: Mapping[str, int]
    emotion_state: EmotionState = field(default_factory=EmotionState)
    mood: str = "balanced"
    trust: int = 5000       # 0 (hostile) to 10000 (absolute trust)
    stress: int = 1000      # 0 (zen) to 10000 (crisis)
    fatigue: int = 1000     # 0 (fresh) to 10000 (exhausted)
    confidence: int = 8000  # 0 (shattered) to 10000 (invincible)

    def perceive(self, observation: Observation) -> "CharacterMind":
        """Process an incoming observation and evolve the entire nervous system."""
        new_emotion = update_emotion(self.emotion_state, observation)

        # Stress and trust adjustments based on observation affect
        delta_stress = (new_emotion.vector.fear + new_emotion.vector.anger) // 4
        new_stress = clamp_positive(blend_int(self.stress, delta_stress, 4000))
        
        delta_trust = (new_emotion.vector.affection + new_emotion.vector.joy // 2) - (new_emotion.vector.jealousy + new_emotion.vector.anger)
        new_trust = clamp_positive(self.trust + delta_trust // 10)

        # Mood derivation (slow-moving background valence)
        if new_stress > 7000:
            mood = "strained"
        elif new_emotion.vector.valence > 4000:
            mood = "cheerful"
        elif new_emotion.vector.valence < -4000:
            mood = "melancholic"
        else:
            mood = "composed"

        return CharacterMind(
            base_identity=self.base_identity,
            persona_weights=self.persona_weights,
            emotion_state=new_emotion,
            mood=mood,
            trust=new_trust,
            stress=new_stress,
            fatigue=min(SCALE, self.fatigue + 50),
            confidence=clamp_positive(self.confidence + (new_emotion.vector.dominance // 20)),
        )

    def current_character_state(self) -> CharacterState:
        personas = normalize_persona_weights(self.persona_weights)
        expression = expression_from_emotion(self.emotion_state)
        fp = character_fingerprint(self.emotion_state, personas)
        return CharacterState(
            emotion=self.emotion_state,
            personas=personas,
            expression=expression,
            fingerprint=fp,
        )

    def format_receipt(self) -> str:
        """Render an exact mathematical audit receipt for why the character feels this way."""
        r = self.emotion_state.receipt
        if not r:
            return f"State: {self.emotion_state.label} (Initial Baseline, Fingerprint: {self.emotion_state.fingerprint})"
        
        lines = [
            "=== AFFECT TRANSITION RECEIPT ===",
            f"Previous Emotion: {r.previous_label}",
            f"Transition Alpha: {r.transition_alpha_bp / SCALE:.4f}",
            f"Candidate Emotion: {r.candidate_label}",
            f"Hysteresis Inertia Applied: {r.hysteresis_applied}",
            f"Final Resolved Emotion: {r.final_label} (Intensity: {self.emotion_state.intensity / SCALE:.2f})",
            f"Resolved Valence / Arousal / Dominance: ({r.resolved_vector.valence:+d}, {r.resolved_vector.arousal:+d}, {r.resolved_vector.dominance:+d})",
            f"Key Affect Dimensions: Joy={r.resolved_vector.joy}, Anger={r.resolved_vector.anger}, Fear={r.resolved_vector.fear}, Affection={r.resolved_vector.affection}, Curiosity={r.resolved_vector.curiosity}",
            f"State Fingerprint: {self.emotion_state.fingerprint}",
        ]
        return "\n".join(lines)
