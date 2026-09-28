import math
import pytest
from nougen_shards.xoah_combat_elevated import (
    CombatState,
    FighterVector,
    ChoreographyFrame,
    XoahCombatEngine,
)


def test_fighter_vector_kinetic_energy():
    f = FighterVector(mass=70.0, vx=10.0, vy=0.0, vz=0.0)
    assert f.speed == 10.0
    # E_k = 0.5 * 70 * 100 = 3500.0
    assert pytest.approx(f.kinetic_energy, 1e-5) == 3500.0


def test_compute_teleport_momentum():
    engine = XoahCombatEngine(decay_rate=0.1, temperature=1.0)
    v_entry = (10.0, 0.0, 0.0)
    dt = 1.0
    boost = 1.0
    v_exit = engine.compute_teleport_momentum(v_entry, dt, boost=boost)
    expected_x = 10.0 * math.exp(-0.1) + 1.0
    assert pytest.approx(v_exit[0], 1e-5) == expected_x


def test_transition_probabilities_softmax():
    engine = XoahCombatEngine(temperature=1.0)
    logits = {
        CombatState.GUARD: 2.0,
        CombatState.ATTACK: 1.0,
        CombatState.RECOVERY: 0.0,
    }
    probs = engine.transition_probabilities(CombatState.GUARD, logits)
    assert sum(probs.values()) == pytest.approx(1.0, 1e-5)
    assert probs[CombatState.GUARD] > probs[CombatState.ATTACK] > probs[CombatState.RECOVERY]


def test_chronocut_causality_index():
    engine = XoahCombatEngine()
    past = [(1.0, 0.0, 0.0)]
    future = [(1.0, 0.0, 0.0)]
    causality = engine.calculate_chronocut_causality(past, future)
    assert pytest.approx(causality, 1e-5) == 1.0


def test_engine_step_attack_and_teleport():
    engine = XoahCombatEngine()
    fa = FighterVector(mass=80.0, vx=10.0, vy=0.0, vz=0.0, health=100.0)
    fb = FighterVector(mass=70.0, vx=0.0, vy=0.0, vz=0.0, health=100.0)

    # Teleport step
    frame1 = engine.step(1, CombatState.TELEPORT_TEAR, fa, fb)
    assert frame1.micro_tear_active is True
    assert fa.speed > 10.0

    # Attack step
    frame2 = engine.step(2, CombatState.ATTACK, fa, fb)
    assert frame2.damage_dealt > 0.0
    assert fb.health < 100.0
    assert len(engine.history) == 2
