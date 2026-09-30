"""Spoken postflight briefs rendered through persona.py behavioral masks.

Pipeline: PostflightEnvelope -> persona.py masks -> PersonaSpeechPolicy ->
ProsodyPlan -> backend lowering -> (synthesis) -> acoustic measurement -> drift check.

persona.py stays the only persona source: each archetype is a blend of existing
BEHAVIORAL_MASKS, and a mask's speech effect is a delta table keyed by mask name.
Persona changes delivery only. Facts are carried verbatim and extract back
byte-equal. Plans are deterministic for identical envelope + CONFIG_VERSION.

Agent -> speaker bindings are overridable via NOUGEN_VOICE_AGENTS (path to a JSON
object shaped like DEFAULT_AGENTS).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import persona

CONFIG_VERSION = "voice-persona.v1"
OUTCOMES = ("success", "warning", "failure", "discovery", "decision")

BASE = {"rate": 1.0, "pause_ms": 250.0, "pitch_range_st": 4.0, "energy": 1.0, "group_words": 8.0}
BOUNDS = {"rate": (0.7, 1.4), "pause_ms": (80.0, 900.0), "pitch_range_st": (0.5, 10.0),
          "energy": (0.6, 1.4), "group_words": (2.0, 16.0)}

# Speech deltas per persona.py mask. Masks absent here are reported as unmapped, never guessed.
MASK_PROSODY = {
    "stoic":      {"rate": -0.08, "pause_ms": 120, "pitch_range_st": -1.5, "energy": -0.10, "group_words": -3},
    "sarcastic":  {"rate": 0.02, "pause_ms": 40, "pitch_range_st": -0.5, "group_words": -1},
    "charming":   {"pitch_range_st": 1.0, "energy": 0.10, "group_words": 1},
    "professor":  {"rate": -0.05, "pause_ms": 60, "group_words": 3},
    "witty":      {"rate": 0.10, "pause_ms": -60, "pitch_range_st": 1.5, "group_words": -2},
    "chaotic":    {"rate": 0.12, "pause_ms": -80, "pitch_range_st": 2.0, "energy": 0.15},
    "genius":     {"rate": -0.10, "pause_ms": -40, "pitch_range_st": -0.5, "group_words": 4},
    "detective":  {"rate": -0.06, "pause_ms": 0, "group_words": 2},
    "streetwise": {"rate": -0.10, "pause_ms": 150, "pitch_range_st": -2.0, "energy": -0.05, "group_words": -4},
}

ARCHETYPES = {
    "tactical_sentinel": ("stoic", "sarcastic"),
    "field_commander":   ("charming", "professor"),
    "rapid_scout":       ("witty", "chaotic"),
    "analyst":           ("genius", "detective"),
    "heavy":             ("stoic", "streetwise"),
}

OUTCOME_PROSODY = {
    "success":   {},
    "warning":   {"rate": -0.03, "pause_ms": 40},
    "failure":   {"rate": -0.08, "pause_ms": 100, "energy": -0.10, "pitch_range_st": -1.0},
    "discovery": {"pitch_range_st": 1.0, "energy": 0.05},
    "decision":  {"rate": -0.05, "pause_ms": 150},
}

DEFAULT_AGENTS = {
    "claude-code": {"profile": "Apollo",   "engine": "kokoro", "voice": "am_michael", "archetype": "field_commander"},
    "antigravity": {"profile": "Atlas",    "engine": "kokoro", "voice": "bm_george",  "archetype": "rapid_scout"},
    "codex":       {"profile": "Onyx",     "engine": "kokoro", "voice": "am_onyx",    "archetype": "analyst"},
    "sol-ai":      {"profile": "Sentinel", "engine": "kokoro", "voice": "am_eric",    "archetype": "tactical_sentinel"},
    "dav1d":       {"profile": "Fenrir",   "engine": "kokoro", "voice": "am_fenrir",  "archetype": "heavy"},
}

# Controls each backend can realize. Anything else in a policy is reported unsupported.
BACKEND_CAPS = {"kokoro": ("rate", "pause_ms", "group_words")}


def agents() -> dict:
    path = os.environ.get("NOUGEN_VOICE_AGENTS")
    if path and Path(path).is_file():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return DEFAULT_AGENTS


@dataclass(frozen=True)
class PostflightEnvelope:
    agent: str
    outcome: str
    changed: tuple[str, ...] = ()
    verified: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    next_action: str = ""

    def facts(self) -> tuple[str, ...]:
        """Canonical ordered facts; the only content a brief may speak."""
        if self.outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}")
        out = [*self.changed, *self.verified, *self.issues]
        if self.next_action:
            out.append(self.next_action)
        return tuple(f.strip() for f in out if f.strip())


@dataclass(frozen=True)
class PersonaSpeechPolicy:
    archetype: str
    masks: tuple[str, ...]
    unmapped_masks: tuple[str, ...]
    rate: float
    pause_ms: float
    pitch_range_st: float
    energy: float
    group_words: int


@dataclass(frozen=True)
class ProsodyPlan:
    agent: str
    profile: str
    engine: str
    voice: str
    outcome: str
    policy: PersonaSpeechPolicy
    groups: tuple[tuple[str, ...], ...]   # per fact: its thought groups, words verbatim
    config_version: str
    fingerprint: str


@dataclass(frozen=True)
class LoweredRequest:
    text: str
    engine: str
    voice: str
    profile: str
    params: dict
    unsupported: tuple[str, ...]


def speech_policy(archetype: str, outcome: str) -> PersonaSpeechPolicy:
    masks = ARCHETYPES[archetype]
    persona.blend(*masks)  # fails loudly if persona.py no longer defines a mask
    v = dict(BASE)
    for delta in [MASK_PROSODY.get(m, {}) for m in masks] + [OUTCOME_PROSODY[outcome]]:
        for k, d in delta.items():
            v[k] += d
    v = {k: min(max(x, BOUNDS[k][0]), BOUNDS[k][1]) for k, x in v.items()}
    return PersonaSpeechPolicy(
        archetype=archetype, masks=masks,
        unmapped_masks=tuple(m for m in masks if m not in MASK_PROSODY),
        rate=round(v["rate"], 4), pause_ms=round(v["pause_ms"], 1),
        pitch_range_st=round(v["pitch_range_st"], 2), energy=round(v["energy"], 3),
        group_words=int(round(v["group_words"])),
    )


def _chunk(words: Sequence[str], size: int) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(words[i:i + size]) for i in range(0, len(words), size))


def plan(env: PostflightEnvelope, archetype: Optional[str] = None) -> ProsodyPlan:
    binding = agents().get(env.agent)
    if binding is None:
        raise KeyError(f"no voice binding for agent {env.agent!r}")
    facts = env.facts()  # validates outcome before any policy lookup
    pol = speech_policy(archetype or binding["archetype"], env.outcome)
    groups = tuple(_chunk(f.split(" "), pol.group_words) for f in facts)
    body = {"v": CONFIG_VERSION, "agent": env.agent, "binding": binding,
            "policy": asdict(pol), "groups": groups, "outcome": env.outcome}
    fp = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return ProsodyPlan(env.agent, binding["profile"], binding["engine"], binding["voice"],
                       env.outcome, pol, groups, CONFIG_VERSION, fp)


def extract_facts(p: ProsodyPlan) -> tuple[str, ...]:
    """Invert a plan back to its facts; must equal the envelope's facts byte-for-byte."""
    return tuple(" ".join(w for g in fact for w in g) for fact in p.groups)


def lower(p: ProsodyPlan) -> LoweredRequest:
    """Lower a plan to one backend request; unsupported controls are listed, not dropped silently."""
    caps = BACKEND_CAPS.get(p.engine, ())
    long_pause = p.policy.pause_ms >= 400
    joiner = " — " if long_pause else ", "
    sentences = []
    for fact in p.groups:
        s = joiner.join(" ".join(g) for g in fact).rstrip(".!?")
        sentences.append(s + ".")
    params = {"speed": p.policy.rate} if "rate" in caps else {}
    controls = ("rate", "pause_ms", "pitch_range_st", "energy", "group_words")
    unsupported = tuple(c for c in controls if c not in caps) + tuple(
        f"mask:{m}" for m in p.policy.unmapped_masks)
    return LoweredRequest(" ".join(sentences), p.engine, p.voice, p.profile, params, unsupported)


def rhythm_signature(p: ProsodyPlan) -> dict:
    """Planned rhythm: what acoustic measurement should find within tolerance."""
    words = sum(len(g) for fact in p.groups for g in fact)
    boundaries = sum(len(fact) - 1 for fact in p.groups) + max(len(p.groups) - 1, 0)
    speech_s = words / (2.5 * p.policy.rate)
    pause_s = boundaries * p.policy.pause_ms / 1000
    total = speech_s + pause_s
    return {
        "words_per_s": round(words / total, 3) if total else 0.0,
        "pause_share": round(pause_s / total, 3) if total else 0.0,
        "mean_group_words": round(words / max(sum(len(f) for f in p.groups), 1), 3),
        "pause_ms": p.policy.pause_ms,
    }


def rhythm_distance(a: dict, b: dict) -> float:
    scale = {"words_per_s": 2.5, "pause_share": 0.5, "mean_group_words": 8.0, "pause_ms": 500.0}
    return math.sqrt(sum(((a[k] - b[k]) / s) ** 2 for k, s in scale.items()))


def measure_pauses(samples: Iterable[float], sample_rate: int, frame_ms: float = 20.0,
                   silence_ratio: float = 0.05, min_pause_ms: float = 60.0) -> dict:
    """Energy-envelope pause measurement on mono float samples."""
    xs = list(samples)
    n = max(int(sample_rate * frame_ms / 1000), 1)
    rms = [math.sqrt(sum(x * x for x in xs[i:i + n]) / len(xs[i:i + n])) for i in range(0, len(xs), n)]
    if not rms:
        return {"pause_count": 0, "mean_pause_ms": 0.0, "pause_share": 0.0}
    floor = max(rms) * silence_ratio
    runs, cur = [], 0
    started = False
    for r in rms:
        if r <= floor:
            cur += 1
        else:
            if started and cur:
                runs.append(cur * frame_ms)
            cur, started = 0, True
    pauses = [r for r in runs if r >= min_pause_ms]
    return {
        "pause_count": len(pauses),
        "mean_pause_ms": round(sum(pauses) / len(pauses), 1) if pauses else 0.0,
        "pause_share": round(sum(pauses) / (len(rms) * frame_ms), 3),
    }


def drift(p: ProsodyPlan, measured: dict, tolerance: float = 0.35) -> list[str]:
    """Compare measured pauses to the plan; returns human-readable drift findings."""
    want = p.policy.pause_ms
    got = measured.get("mean_pause_ms", 0.0)
    if want and abs(got - want) / want > tolerance:
        return [f"mean_pause_ms {got} vs planned {want} (>{int(tolerance * 100)}%)"]
    return []


# --- Role gating and speak-worthiness (relay 20260929T193234Z) ---------------

NEUTRAL_ARCHETYPE = "neutral"
ARCHETYPES[NEUTRAL_ARCHETYPE] = ()
ROLE_MIN_CONFIDENCE = float(os.environ.get("NOUGEN_VOICE_ROLE_MIN_CONFIDENCE", "0.6"))


def gated_archetype(archetype: str, confidence: float, relevance: float = 1.0) -> str:
    """A role overlay applies only when confidence*relevance clears the gate; else neutral delivery."""
    if archetype not in ARCHETYPES:
        return NEUTRAL_ARCHETYPE
    return archetype if confidence * relevance >= ROLE_MIN_CONFIDENCE else NEUTRAL_ARCHETYPE


# --- Canonical identity producer for consumers (relay 20260930T043437Z) ------

# The wire contract Voice's PersonaIdentity pins. Deliberately NOT CONFIG_VERSION:
# tuning delivery deltas must not silently change the identity contract a
# consumer validates against; bump this only when the identity shape changes.
IDENTITY_CONTRACT_VERSION = "voice-persona.v1"


def _unit_interval(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number in [0, 1]")
    x = float(value)
    if not math.isfinite(x) or not 0.0 <= x <= 1.0:
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    return x


def identity_for(agent: str, confidence: float, relevance: float = 1.0) -> dict:
    """The already-gated identity a consumer (NouGenVoice) adopts, from canonical policy.

    persona_name is the agent's canonical profile; archetype is that agent's role
    overlay passed through gated_archetype(), so confidence/relevance gating and the
    allowed archetype set live ONLY here. source_id pins the contract version, name and
    archetype so a consumer can reject drift. Returns a plain, JSON-serialisable dict.

    Fails closed: an unknown agent has no canonical identity and is never invented,
    and non-numeric / non-finite / out-of-range confidence or relevance is rejected
    rather than silently degraded to neutral.
    """
    entry = agents().get(agent)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown agent {agent!r}: no canonical persona identity")
    name = entry.get("profile")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"agent {agent!r} has no canonical profile name")
    name = name.strip()
    archetype = gated_archetype(
        str(entry.get("archetype", NEUTRAL_ARCHETYPE)),
        _unit_interval("confidence", confidence),
        _unit_interval("relevance", relevance),
    )
    return {
        "persona_name": name,
        "archetype": archetype,
        "source_id": f"{IDENTITY_CONTRACT_VERSION}:{name}:{archetype}",
    }


SPEAK_DECISIONS = ("HOLD", "SPEAK", "INTERRUPT", "ABSTAIN")
_SEVERITY = {"success": 0.2, "discovery": 0.5, "warning": 0.6, "decision": 0.8, "failure": 0.9}


@dataclass(frozen=True)
class SpeakDecision:
    decision: str
    score: float
    reason: str


def speak_policy(outcome: str, *, novelty: float, operator_relevance: float,
                 evidence_confidence: float, operator_speaking: bool = False) -> SpeakDecision:
    """Content-aware turn decision, separate from any duplex backend.

    ABSTAIN: nothing worth saying or too little evidence to say it.
    HOLD:    worth saying but not urgent enough to talk over the operator.
    INTERRUPT: urgent and well evidenced while the operator is speaking.
    """
    if outcome not in _SEVERITY:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    for name, v in (("novelty", novelty), ("operator_relevance", operator_relevance),
                    ("evidence_confidence", evidence_confidence)):
        if not (isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0):
            raise ValueError(f"{name} must be a number from 0 to 1")
    score = round(_SEVERITY[outcome] * 0.5 + novelty * 0.2 + operator_relevance * 0.3, 4)
    min_ev = float(os.environ.get("NOUGEN_VOICE_MIN_EVIDENCE", "0.3"))
    speak_at = float(os.environ.get("NOUGEN_VOICE_SPEAK_AT", "0.35"))
    interrupt_at = float(os.environ.get("NOUGEN_VOICE_INTERRUPT_AT", "0.8"))
    if evidence_confidence < min_ev or score < speak_at:
        return SpeakDecision("ABSTAIN", score, "low evidence" if evidence_confidence < min_ev else "low salience")
    if operator_speaking:
        if score >= interrupt_at and evidence_confidence >= 0.8:
            return SpeakDecision("INTERRUPT", score, "urgent and well evidenced")
        return SpeakDecision("HOLD", score, "operator speaking")
    return SpeakDecision("SPEAK", score, "salient")
