"""
Xoah Deterministic Combat Choreography Engine (Elevated Module)

Implements deterministic state machine dynamics, micro-tear teleport momentum conservation,
and chronocutting temporal causality parsing for combat choreography.

Mathematical Formulations:
1. Momentum Conservation across Micro-tears:
   v_exit = v_entry * exp(-lambda_decay * dt) + a_boost * dt

2. State Transition Softmax Normalization:
   T_{ij} = exp(Q_{ij} / tau) / sum_k(exp(Q_{ik} / tau))

3. Kinetic Energy & Damage Potential:
   E_k = 0.5 * m * ||v||^2
   Damage = E_k * (1 - armor_mitigation) * hit_accuracy

4. Chronocutting Temporal Causality Index:
   C_chrono = sum_i(w_i * cos_sim(v_past_i, v_future_i)) / N
"""

from dataclasses import dataclass, field
from enum import Enum, auto
import math
from typing import Dict, List, Optional, Tuple


class CombatState(Enum):
    GUARD = auto()
    ATTACK = auto()
    TELEPORT_TEAR = auto()
    CHRONOCUT = auto()
    COUNTER = auto()
    RECOVERY = auto()


@dataclass
class FighterVector:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    mass: float = 70.0
    health: float = 100.0
    stamina: float = 100.0

    @property
    def speed(self) -> float:
        return math.sqrt(self.vx**2 + self.vy**2 + self.vz**2)

    @property
    def kinetic_energy(self) -> float:
        return 0.5 * self.mass * (self.speed**2)


@dataclass
class ChoreographyFrame:
    frame_index: int
    state: CombatState
    fighter_a: FighterVector
    fighter_b: FighterVector
    micro_tear_active: bool = False
    chronocut_debt: float = 0.0
    damage_dealt: float = 0.0
    causal_consistency: float = 1.0


class XoahCombatEngine:
    """
    Deterministic Combat Choreography & State Machine Engine.
    """

    def __init__(self, decay_rate: float = 0.05, temperature: float = 1.0, seed: Optional[int] = None):
        self.decay_rate = decay_rate
        self.temperature = max(1e-5, temperature)
        self.seed = seed
        import random
        self.rng = random.Random(seed) if seed is not None else random.Random()
        self.history: List[ChoreographyFrame] = []

    def compute_teleport_momentum(
        self, v_entry: Tuple[float, float, float], dt: float, boost: float = 0.0
    ) -> Tuple[float, float, float]:
        """
        Calculates momentum preservation across micro-tear teleportation.
        v_exit = v_entry * exp(-lambda * dt) + boost
        """
        factor = math.exp(-self.decay_rate * dt)
        return (
            v_entry[0] * factor + boost,
            v_entry[1] * factor + boost,
            v_entry[2] * factor + boost,
        )

    def transition_probabilities(
        self, current_state: CombatState, logits: Dict[CombatState, float]
    ) -> Dict[CombatState, float]:
        """
        Computes deterministic softmax transition probabilities from logits.
        """
        exp_values = {
            s: math.exp(val / self.temperature) for s, val in logits.items()
        }
        sum_exp = sum(exp_values.values())
        if sum_exp == 0:
            return {s: 1.0 / len(logits) for s in logits}
        return {s: val / sum_exp for s, val in exp_values.items()}

    def calculate_chronocut_causality(
        self, past_vectors: List[Tuple[float, float, float]], future_vectors: List[Tuple[float, float, float]]
    ) -> float:
        """
        Evaluates chronocutting temporal causality coherence C_chrono in [0, 1].
        C_chrono = sum_i(cos_sim(v_past_i, v_future_i)) / N
        """
        if not past_vectors or not future_vectors or len(past_vectors) != len(future_vectors):
            return 1.0

        total_sim = 0.0
        n = len(past_vectors)
        for vp, vf in zip(past_vectors, future_vectors):
            dot = vp[0] * vf[0] + vp[1] * vf[1] + vp[2] * vf[2]
            mag_p = math.sqrt(vp[0]**2 + vp[1]**2 + vp[2]**2)
            mag_f = math.sqrt(vf[0]**2 + vf[1]**2 + vf[2]**2)
            if mag_p > 1e-6 and mag_f > 1e-6:
                cos_sim = dot / (mag_p * mag_f)
                total_sim += max(-1.0, min(1.0, cos_sim))
            else:
                total_sim += 1.0

        normalized = (total_sim / n + 1.0) / 2.0
        return max(0.0, min(1.0, normalized))

    def step(
        self,
        frame_idx: int,
        action_a: CombatState,
        fighter_a: FighterVector,
        fighter_b: FighterVector,
        dt: float = 0.01667,
    ) -> ChoreographyFrame:
        """
        Executes a deterministic choreography tick.
        """
        micro_tear = action_a == CombatState.TELEPORT_TEAR
        chronocut = action_a == CombatState.CHRONOCUT

        if micro_tear:
            vx, vy, vz = self.compute_teleport_momentum(
                (fighter_a.vx, fighter_a.vy, fighter_a.vz), dt, boost=2.0
            )
            fighter_a.vx, fighter_a.vy, fighter_a.vz = vx, vy, vz

        damage = 0.0
        if action_a == CombatState.ATTACK:
            dmg_raw = fighter_a.kinetic_energy * 0.001
            damage = max(0.0, dmg_raw)
            fighter_b.health = max(0.0, fighter_b.health - damage)

        causal_index = 1.0
        chronocut_debt = 0.0
        if chronocut:
            past_vecs = [(fighter_a.vx, fighter_a.vy, fighter_a.vz)]
            future_vecs = [(fighter_b.vx, fighter_b.vy, fighter_b.vz)]
            causal_index = self.calculate_chronocut_causality(past_vecs, future_vecs)
            chronocut_debt = (1.0 - causal_index) * 10.0

        frame = ChoreographyFrame(
            frame_index=frame_idx,
            state=action_a,
            fighter_a=fighter_a,
            fighter_b=fighter_b,
            micro_tear_active=micro_tear,
            chronocut_debt=chronocut_debt,
            damage_dealt=damage,
            causal_consistency=causal_index,
        )
        self.history.append(frame)
        return frame
