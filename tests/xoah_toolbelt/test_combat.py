"""Xoah combat engine. No scene text, no lore beyond locked system names."""
import json

import pytest

from nougen_shards.xoah_toolbelt import combat as c
from nougen_shards.xoah_toolbelt.combat import (CATALOGUE, Beat, CanonViolation, Environment,
                                                 Intent, Opponent, Range, Root, Situation, Weapon,
                                                 XoahCombatEngine, allowed)

VOL1 = Situation(level=2, weapon=Weapon.KAGE_TANAK, intent=Intent.ESCAPE, range=Range.MID,
                 env=Environment(terrain="stair", verticality=0.7))
L9 = Situation(level=9, weapon=Weapon.KAGE_TANAK, intent=Intent.KILL, range=Range.MID,
               env=Environment(terrain="stair", verticality=0.7))


# --- spec test 1: same seed = same fight ------------------------------------------
def test_same_seed_same_fight_byte_identical():
    a = XoahCombatEngine(42).fight(VOL1, beats=16)
    b = XoahCombatEngine(42).fight(VOL1, beats=16)
    assert XoahCombatEngine.fingerprint(a) == XoahCombatEngine.fingerprint(b)
    assert XoahCombatEngine.to_json(a, VOL1, 42) == XoahCombatEngine.to_json(b, VOL1, 42)


def test_different_seed_different_fight():
    a = XoahCombatEngine(1).fight(VOL1, beats=16)
    b = XoahCombatEngine(2).fight(VOL1, beats=16)
    assert XoahCombatEngine.fingerprint(a) != XoahCombatEngine.fingerprint(b)


# --- spec test 2: different terrain changes choices ---------------------------------
def test_terrain_changes_choices():
    flat = Situation(level=2, range=Range.MID, env=Environment(terrain="open", verticality=0.0))
    stair = Situation(level=2, range=Range.MID, env=Environment(terrain="stair", verticality=0.9))
    # the situation's pull on the roots differs, and so does the fight
    assert c.situation_weights(flat) != c.situation_weights(stair)
    assert XoahCombatEngine.fingerprint(XoahCombatEngine(7).fight(flat, 16)) != \
        XoahCombatEngine.fingerprint(XoahCombatEngine(7).fight(stair, 16))


def test_low_traction_pulls_toward_rooted_power_and_away_from_rotation():
    grip = c.situation_weights(Situation(env=Environment(traction=0.9)))
    dust = c.situation_weights(Situation(env=Environment(traction=0.1, dust=0.9)))
    assert dust[Root.GOJU_RYU] > grip[Root.GOJU_RYU] and dust[Root.WUSHU] < grip[Root.WUSHU]


# --- spec test 3: Level 1 never emits Level 9 techniques -------------------------
@pytest.mark.parametrize("level", [1, 2, 3])
def test_vol1_never_emits_shadow_slice_or_veil(level):
    s = Situation(level=level, weapon=Weapon.KAGE_TANAK, range=Range.MID)
    for seed in range(25):
        for b in XoahCombatEngine(seed).fight(s, beats=24):
            assert not b.veil, (seed, b.action)
            assert b.action not in ("nonlocal line", "tear-routed arc", "positional theft",
                                    "causal-line read", "axis reset after displacement")


def test_level_9_can_emit_shadow_slice_and_it_still_arrests():
    seen = set()
    for seed in range(40):
        for b in XoahCombatEngine(seed).fight(L9, beats=16):
            if b.veil:
                seen.add(b.action)
                assert b.continuity["arrested_by_contact"]
    assert "nonlocal line" in seen or "tear-routed arc" in seen


def test_shadow_slice_gate_is_exactly_level_9():
    ok, why = allowed(next(a for a in CATALOGUE if a.name == "nonlocal line"),
                      Situation(level=8, weapon=Weapon.KAGE_TANAK, range=Range.MID))
    assert not ok and "needs level 9" in why


# --- spec test 4: style blending stays coherent -------------------------------------
def test_every_action_traces_to_multiple_roots():
    for a in CATALOGUE:
        assert len(a.trace()) >= 2, a.name  # no single-style move exists in the catalogue
        assert abs(sum(a.roots.values()) - 1.0) < 1e-6, a.name


def test_no_beat_is_labelable_by_one_style():
    for b in XoahCombatEngine(3).fight(L9, beats=24):
        assert len(b.roots) >= 2, b.action


def test_tire_machet_is_always_present_in_the_pull():
    for s in (VOL1, L9, Situation(range=Range.GROUND), Situation(range=Range.LONG, weapon=Weapon.STAFF)):
        assert c.situation_weights(s)[Root.TIRE_MACHET] > 0.2


# --- fingerprint guardrails ---------------------------------------------------------
def test_collision_beat_is_never_skipped_and_leaves_her_exposed():
    for seed in range(10):
        beats = XoahCombatEngine(seed).fight(VOL1, beats=16)
        cols = [b for b in beats if b.beat == "COLLISION"]
        assert cols
        assert all(b.continuity["exposed_at_finish"] and b.continuity["arrested_by_contact"] for b in cols)


def test_weapon_never_leaves_frame():
    for seed in range(10):
        for b in XoahCombatEngine(seed).fight(L9, beats=16):
            assert b.continuity["weapon_in_frame"]


def test_verticality_favours_fighting_downward():
    flat = Situation(level=2, range=Range.CLOSE, env=Environment(verticality=0.0))
    drop = Situation(level=2, range=Range.CLOSE, env=Environment(verticality=0.9))
    def drops(s):
        return sum(b.action == "the drop" for seed in range(30)
                   for b in XoahCombatEngine(seed).fight(s, beats=8))
    assert drops(drop) > drops(flat)


# --- BJJ as survival geometry ---------------------------------------------------------
def test_ground_collapse_inserts_ground_beat_biased_to_weapon_recovery():
    s = Situation(level=2, weapon=Weapon.KAGE_TANAK, range=Range.CLINCH, injury=0.7)
    found = False
    for seed in range(40):
        beats = XoahCombatEngine(seed).fight(s, beats=12)
        ground = [b for b in beats if b.beat == "GROUND"]
        if ground:
            found = True
            assert all(b.action != "finish on the ground" for b in ground)  # weapon in reach
    assert found


def test_ground_finish_only_when_weapon_out_of_reach():
    a = next(x for x in CATALOGUE if x.name == "finish on the ground")
    assert not allowed(a, Situation(weapon=Weapon.KAGE_TANAK, range=Range.GROUND))[0]
    assert allowed(a, Situation(weapon=Weapon.EMPTY_HAND, range=Range.GROUND))[0]


# --- anti-repetition, weapon state, output ------------------------------------------
def test_anti_repetition_memory_penalises_recent_actions():
    a = next(x for x in CATALOGUE if x.name == "committed line")
    sw = c.situation_weights(VOL1)
    assert c.score(a, VOL1, sw, []) > c.score(a, VOL1, sw, ["committed line"])


def test_weapon_state_gates_actions():
    staff = Situation(weapon=Weapon.STAFF, range=Range.LONG)
    assert allowed(next(a for a in CATALOGUE if a.name == "staff sweep"), staff)[0]
    assert not allowed(next(a for a in CATALOGUE if a.name == "committed line"),
                       Situation(weapon=Weapon.STAFF, range=Range.MID))[0]


def test_no_legal_action_raises_canon_violation_not_a_bad_beat():
    eng = XoahCombatEngine(1, catalogue=[a for a in CATALOGUE if a.beat != Beat.READ])
    with pytest.raises(CanonViolation, match="no legal READ"):
        eng.fight(VOL1, beats=2)


def test_json_and_screenplay_outputs():
    beats = XoahCombatEngine(5).fight(VOL1, beats=8)
    doc = json.loads(XoahCombatEngine.to_json(beats, VOL1, 5))
    assert doc["seed"] == 5 and len(doc["beats"]) == 8
    for b in doc["beats"]:
        assert {"rationale", "roots", "camera", "safety", "mechanics", "continuity"} <= set(b)
    sp = XoahCombatEngine.to_screenplay(beats)
    assert sp.count("\n") >= 8 * 3 - 1 and "camera:" in sp


def test_invalid_level_rejected():
    with pytest.raises(ValueError):
        Situation(level=10)


# --- eighth system: Gun Kata (lock 030006Z) ---------------------------------------
def test_gun_kata_is_a_weighted_layer_not_a_gun_mode():
    # every firearm action still traces to multiple roots; none is pure gun_kata
    guns = [a for a in CATALOGUE if Root.GUN_KATA in a.roots]
    assert guns
    for a in guns:
        assert len(a.trace()) >= 2, a.name
        assert a.roots[Root.GUN_KATA] < 1.0


def test_firearm_state_pulls_toward_gun_kata_without_silencing_the_others():
    blade = c.situation_weights(Situation(weapon=Weapon.KAGE_TANAK, range=Range.CLOSE))
    gun = c.situation_weights(Situation(weapon=Weapon.FIREARM, range=Range.CLOSE))
    assert gun[Root.GUN_KATA] > blade[Root.GUN_KATA]
    assert gun[Root.TIRE_MACHET] > 0.2 and gun[Root.GOJU_RYU] > 0.2  # still one nervous system


def test_multiple_opponents_raise_gun_kata_spatial_pull():
    one = c.situation_weights(Situation(range=Range.CHAOS, opponent=Opponent(count=1)))
    many = c.situation_weights(Situation(range=Range.CHAOS, opponent=Opponent(count=4)))
    assert many[Root.GUN_KATA] > one[Root.GUN_KATA]


def test_firearm_actions_require_the_firearm_and_keep_it_in_frame():
    shot = next(a for a in CATALOGUE if a.name == "angle-controlled shot")
    assert not allowed(shot, Situation(weapon=Weapon.KAGE_TANAK, range=Range.MID))[0]
    assert allowed(shot, Situation(weapon=Weapon.FIREARM, range=Range.MID))[0]
    assert shot.weapon_in_frame and shot.safety == "blank-fire"


def test_a_firearm_fight_is_still_one_language():
    s = Situation(level=2, weapon=Weapon.FIREARM, range=Range.CLOSE,
                  opponent=Opponent(count=3), env=Environment(terrain="market", crowd_density=0.8))
    roots = set()
    for b in XoahCombatEngine(11).fight(s, beats=16):
        roots.update(b.roots)
        assert len(b.roots) >= 2
    assert "gun_kata" in roots and len(roots) >= 4   # not a gun-only sequence
