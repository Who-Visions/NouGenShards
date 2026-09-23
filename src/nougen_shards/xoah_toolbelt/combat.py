"""Xoah deterministic combat-choreography engine (owner leg 20260923T025341Z).

Turns the locked eight-system combat core into scene-aware fight beats.

Design law, from the canon locks (five-system 024859Z, seven-system 025115Z,
eight-system 030006Z):
  * ONE combat identity. There is no style selection. Every action carries a
    ROOT-WEIGHT VECTOR over the eight systems; the situation shifts the
    weights; the chosen action is Xoah-native and traces to several roots at
    once. A beat that could be labelled "the karate move" is a bug.
  * The movement FINGERPRINT (remix v0.1) is enforced as guardrails that
    REFUSE beats, never as notes: she stops (every arc is arrested by
    contact), she is hittable at the finish, the blade never vanishes, she
    fights downward.
  * Veil mechanics AUGMENT physical logic. Shadow Slice exists only at the
    locked level; Vol 1 (Level 1-3) can never emit it.
  * BJJ is survival geometry on clinch/ground collapse, biased to escape,
    reversal and weapon recovery -- never sport grappling.
  * Gun Kata is a weighted layer in the same nervous system, never a "gun
    mode": predictive spatial geometry, angle control, close-range firearm
    retention, and seamless firearm/empty-hand/blade transitions. Fictional
    cinematic grammar transformed into VeilVerse-native choreography via a
    Blackglass lineage; it is not framed as a validated real-world doctrine.

Deterministic: same seed + same situation = byte-identical fight. No lore
beyond the locked system names lives here; scene text is the caller's.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


# --------------------------------------------------------------------------- enums
class Root(str, Enum):
    TIRE_MACHET = "tire_machet"      # sovereign: ancestral survival blade grammar
    GOJU_RYU = "goju_ryu"            # hard/soft spine, rooted power, circular redirection
    KARATE = "karate"                # umbrella: kicking, linear entry, impact, recovery
    KENJUTSU = "kenjutsu"            # sword geometry, maai, committed cutting intent
    WUSHU = "wushu"                  # rotational flow, extended silhouette
    NINJUTSU = "ninjutsu"            # evasion, misdirection, terrain exploitation
    BJJ = "bjj"                      # survival geometry when the fight collapses
    GUN_KATA = "gun_kata"            # close-range firearm geometry, Blackglass lineage


class Range(str, Enum):
    LONG = "long"
    MID = "mid"
    CLOSE = "close"
    CLINCH = "clinch"
    GROUND = "ground"
    CHAOS = "chaos"


class Weapon(str, Enum):
    KAGE_TANAK = "kage_tanak"        # split blade; Xoah carries Mercy -> defensive-first
    MACHETE = "machete"
    DAGGER = "dagger"
    STAFF = "staff"
    EMPTY_HAND = "empty_hand"
    IMPROVISED = "improvised"
    FIREARM = "firearm"


class Intent(str, Enum):
    ESCAPE = "escape"
    DISABLE = "disable"
    SURVIVE = "survive"
    PROTECT = "protect"
    CAPTURE = "capture"
    KILL = "kill"
    STALL = "stall"
    REACH_OBJECTIVE = "reach_objective"


class Beat(str, Enum):
    READ = "READ"
    BAIT = "BAIT"
    ANGLE = "ANGLE"
    STRIKE = "CUT/STRIKE"
    COLLISION = "COLLISION"
    REDIRECT = "REDIRECT"
    GROUND = "GROUND"                # inserted only when COLLISION collapses the range
    RECOVER = "RECOVER"
    REENTER = "RE-ENTER"


SENTENCE: Tuple[Beat, ...] = (Beat.READ, Beat.BAIT, Beat.ANGLE, Beat.STRIKE, Beat.COLLISION,
                              Beat.REDIRECT, Beat.RECOVER, Beat.REENTER)

# Locked range map (025115Z): which roots the situation favours at each range.
RANGE_MAP: Dict[Range, Tuple[Root, ...]] = {
    Range.LONG: (Root.WUSHU, Root.KARATE, Root.KENJUTSU),
    Range.MID: (Root.KENJUTSU, Root.TIRE_MACHET, Root.KARATE),
    Range.CLOSE: (Root.GOJU_RYU, Root.TIRE_MACHET, Root.NINJUTSU, Root.GUN_KATA),
    Range.CLINCH: (Root.GOJU_RYU, Root.BJJ, Root.NINJUTSU, Root.GUN_KATA),
    Range.GROUND: (Root.BJJ,),
    Range.CHAOS: (Root.NINJUTSU, Root.TIRE_MACHET, Root.GUN_KATA),
}

SHADOW_SLICE_MIN_LEVEL = 9   # locked 19536@db3 / 31167@db1: SDX and X2 only
VOL1_MAX_LEVEL = 3           # locked 12051@db9


# --------------------------------------------------------------------------- situation
@dataclass(frozen=True)
class Environment:
    terrain: str = "corridor"            # corridor | market | bike | stair | open | machinery
    gravity: float = 0.38                # Mars default; 1.0 = Earth
    traction: float = 0.8                # 0 = dust/ice, 1 = mag surface
    verticality: float = 0.3             # 0 flat, 1 sheer
    crowd_density: float = 0.0
    dust: float = 0.0


@dataclass(frozen=True)
class Opponent:
    size: float = 1.0                    # relative to Xoah
    reach: float = 1.0
    armor: float = 0.0
    weapon: Optional[Weapon] = None
    training: float = 0.5
    aggression: float = 0.5
    mobility: float = 0.5
    count: int = 1


@dataclass(frozen=True)
class Situation:
    level: int = 1                       # Xoah's Veil level (1-3 Vol 1; 9 = Shadow Slice)
    weapon: Weapon = Weapon.KAGE_TANAK
    intent: Intent = Intent.ESCAPE
    range: Range = Range.MID
    injury: float = 0.0                  # 0 fresh .. 1 barely standing
    fear: float = 0.2                    # emotional state; under fear she gets MORE precise
    env: Environment = field(default_factory=Environment)
    opponent: Opponent = field(default_factory=Opponent)

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 9:
            raise ValueError("level must be 1..9")


# --------------------------------------------------------------------------- actions
@dataclass(frozen=True)
class Action:
    """A Xoah-native action. ``roots`` are weights, NOT a style label."""
    name: str
    beat: Beat
    roots: Mapping[Root, float]
    ranges: Tuple[Range, ...]
    mechanics: str                       # body mechanics, for previs/stunt
    min_level: int = 1
    arrests_by_contact: bool = True      # invariant 1: every arc stops on something
    ends_exposed: bool = True            # invariant 2: hittable at the finish
    weapon_in_frame: bool = True         # invariant 3: the blade never vanishes
    downward: bool = False               # invariant 4 flag (not every action, but the Drop must be available)
    to_range: Optional[Range] = None     # range transition this action causes
    needs_weapon: Tuple[Weapon, ...] = ()  # empty = any
    veil: bool = False                   # uses Veil mechanics (augments, never replaces)
    safety: str = "standard"             # stunt metadata: standard | fall | blade-contact | wire | ground

    def trace(self) -> List[str]:
        """Roots this action traces to, strongest first -- the anti-carousel proof."""
        return [r.value for r, w in sorted(self.roots.items(), key=lambda kv: -kv[1]) if w > 0]


def _w(**kw: float) -> Dict[Root, float]:
    return {Root[k.upper()]: v for k, v in kw.items()}


CATALOGUE: Tuple[Action, ...] = (
    # READ
    Action("room read", Beat.READ, _w(ninjutsu=.5, tire_machet=.3, kenjutsu=.2), tuple(Range),
           "eyes to exits and leverage before the opponent; range and terrain assessed",
           ends_exposed=False),
    Action("angle read", Beat.READ, _w(gun_kata=.4, ninjutsu=.4, kenjutsu=.2), tuple(Range),
           "predictive spatial read: where every opponent's line of fire and line of attack will be next beat",
           ends_exposed=False),
    Action("causal-line read", Beat.READ, _w(ninjutsu=.4, kenjutsu=.4, tire_machet=.2), tuple(Range),
           "reads where the attack came from and where it will land as a line through the room",
           min_level=SHADOW_SLICE_MIN_LEVEL, ends_exposed=False, veil=True),
    # BAIT
    Action("offered finish", Beat.BAIT, _w(tire_machet=.5, kenjutsu=.3, goju_ryu=.2),
           (Range.LONG, Range.MID, Range.CLOSE),
           "holds a committed-line finish position deliberately; the exposure is real"),
    Action("false retreat", Beat.BAIT, _w(ninjutsu=.6, karate=.2, wushu=.2), (Range.LONG, Range.MID),
           "gives ground on a line that leads into terrain she has already read"),
    Action("offered grip", Beat.BAIT, _w(bjj=.4, goju_ryu=.3, ninjutsu=.3), (Range.CLINCH, Range.CLOSE),
           "lets the opponent take a grip she has already planned to break; the exposure is real"),
    Action("bottom bait", Beat.BAIT, _w(bjj=.6, ninjutsu=.2, goju_ryu=.2), (Range.GROUND,),
           "appears pinned; frames are already set for the sweep"),
    Action("terrain bait", Beat.BAIT, _w(ninjutsu=.5, tire_machet=.3, karate=.2), (Range.CHAOS,),
           "shows a line through the crowd or machinery that she has already read the exit of"),
    # ANGLE
    Action("long arc", Beat.ANGLE, _w(wushu=.5, kenjutsu=.2, karate=.2, ninjutsu=.1),
           (Range.LONG, Range.MID), "rotational entry off the line, low; cheap in Mars gravity"),
    Action("linear entry", Beat.ANGLE, _w(karate=.5, kenjutsu=.3, goju_ryu=.2), (Range.MID, Range.CLOSE),
           "straight-line closing step with the lead hip, no rotation"),
    Action("terrain slip", Beat.ANGLE, _w(ninjutsu=.6, tire_machet=.3, wushu=.1),
           (Range.CLOSE, Range.CHAOS), "uses a wall, rail or crowd edge to change the angle"),
    Action("level change", Beat.ANGLE, _w(bjj=.4, goju_ryu=.3, ninjutsu=.3), (Range.CLINCH,),
           "drops her hips under the opponent's base; the angle is vertical, not lateral", downward=True),
    Action("hip escape angle", Beat.ANGLE, _w(bjj=.6, goju_ryu=.2, tire_machet=.2), (Range.GROUND,),
           "shrimps to create the angle for a frame or sweep"),
    Action("tear-routed arc", Beat.ANGLE, _w(wushu=.4, kenjutsu=.4, ninjutsu=.2), (Range.LONG, Range.MID),
           "the arc's second half exits a half-beat earlier through a spacetime tear; rotation still lands legibly",
           min_level=SHADOW_SLICE_MIN_LEVEL, veil=True, safety="wire"),
    # CUT / STRIKE
    Action("committed line", Beat.STRIKE, _w(kenjutsu=.4, tire_machet=.4, karate=.2), (Range.MID,),
           "full-body diagonal cut with a hard stop; with Mercy the cut redirects the weapon, not the arm",
           needs_weapon=(Weapon.KAGE_TANAK, Weapon.MACHETE), safety="blade-contact"),
    Action("short answer", Beat.STRIKE, _w(goju_ryu=.5, karate=.3, tire_machet=.2), (Range.CLOSE,),
           "inside the blade's arc: elbow or forearm, rooted, circular redirect"),
    Action("close weight", Beat.STRIKE, _w(goju_ryu=.4, tire_machet=.3, ninjutsu=.3), (Range.CLINCH,),
           "knee or elbow from the clinch against a doorway, stair or machine"),
    Action("staff sweep", Beat.STRIKE, _w(wushu=.5, kenjutsu=.3, karate=.2), (Range.LONG,),
           "extended-silhouette sweep at the legs", needs_weapon=(Weapon.STAFF,)),
    Action("ground strike", Beat.STRIKE, _w(bjj=.4, goju_ryu=.4, tire_machet=.2), (Range.GROUND,),
           "short elbow or hammer from a controlled position; keeps the weapon hand free"),
    Action("improvised strike", Beat.STRIKE, _w(tire_machet=.4, ninjutsu=.4, karate=.2), (Range.CHAOS,),
           "whatever the terrain hands her: rail, crate, dust thrown"),
    Action("retention strike", Beat.STRIKE, _w(gun_kata=.4, goju_ryu=.3, tire_machet=.3), (Range.CLOSE, Range.CLINCH),
           "close-range shot or muzzle strike with the weapon kept inside her own frame; the off hand controls the opponent's weapon",
           needs_weapon=(Weapon.FIREARM,), safety="blank-fire"),
    Action("angle-controlled shot", Beat.STRIKE, _w(gun_kata=.5, kenjutsu=.3, ninjutsu=.2), (Range.MID, Range.CHAOS),
           "moves through the predicted angle so no opponent has a line on her while she has one on them; continuous motion",
           needs_weapon=(Weapon.FIREARM,), safety="blank-fire"),
    Action("empty-hand line", Beat.STRIKE, _w(karate=.5, goju_ryu=.3, tire_machet=.2), (Range.MID,),
           "linear kick or straight to keep range when the blade is out of reach",
           needs_weapon=(Weapon.EMPTY_HAND, Weapon.IMPROVISED)),
    Action("nonlocal line", Beat.STRIKE, _w(kenjutsu=.4, tire_machet=.3, wushu=.3), (Range.MID, Range.LONG),
           "Shadow Slice: the committed line completes before the opponent's motion finishes; body causality stays readable",
           min_level=SHADOW_SLICE_MIN_LEVEL, needs_weapon=(Weapon.KAGE_TANAK,), veil=True, safety="wire"),
    # COLLISION (never skipped; this is where she is most readable and most vulnerable)
    Action("ground arrest (already down)", Beat.COLLISION, _w(bjj=.5, goju_ryu=.3, tire_machet=.2),
           (Range.GROUND,), "the exchange stops against the floor or the opponent's weight", safety="ground"),
    Action("floor arrest", Beat.COLLISION, _w(karate=.4, wushu=.3, goju_ryu=.3), (Range.LONG, Range.CHAOS),
           "the long arc is stopped by the ground or a fixed object; open for a half-beat", to_range=Range.MID),
    Action("wall arrest", Beat.COLLISION, _w(goju_ryu=.4, tire_machet=.3, karate=.3),
           (Range.MID, Range.CLOSE, Range.CLINCH), "shoulder or hip meets wall/machine; the arc stops; open for a half-beat",
           to_range=Range.CLOSE),
    Action("body arrest", Beat.COLLISION, _w(goju_ryu=.5, bjj=.3, tire_machet=.2),
           (Range.CLOSE, Range.CLINCH), "the arc stops on the opponent; clinch", to_range=Range.CLINCH),
    Action("ground arrest", Beat.COLLISION, _w(bjj=.5, goju_ryu=.3, ninjutsu=.2),
           (Range.CLINCH, Range.CHAOS), "the exchange collapses; she lands on top or bottom", to_range=Range.GROUND,
           downward=True, safety="fall"),
    # REDIRECT
    Action("the drop", Beat.REDIRECT, _w(ninjutsu=.4, bjj=.3, tire_machet=.3),
           (Range.CLOSE, Range.CLINCH), "takes the lower level; steals the front foot with her own descending weight",
           downward=True, to_range=Range.CLINCH, safety="fall"),
    Action("push-off", Beat.REDIRECT, _w(karate=.4, wushu=.3, goju_ryu=.3), (Range.CLOSE, Range.CLINCH),
           "the collision becomes the next entry's launch", to_range=Range.MID),
    Action("weapon transition", Beat.REDIRECT, _w(gun_kata=.4, kenjutsu=.3, tire_machet=.3),
           (Range.CLOSE, Range.CLINCH, Range.MID),
           "seamless firearm-to-empty-hand-to-blade (or back) inside the same motion; nothing leaves the frame",
           to_range=Range.CLOSE),
    Action("range reset", Beat.REDIRECT, _w(kenjutsu=.4, karate=.3, wushu=.3), (Range.LONG, Range.MID),
           "arrested momentum becomes distance; maai re-established", to_range=Range.MID),
    Action("stand to weapon", Beat.REDIRECT, _w(bjj=.5, ninjutsu=.3, tire_machet=.2), (Range.GROUND,),
           "technical stand-up whose end position is weapon access", to_range=Range.CLOSE),
    Action("chaos break", Beat.REDIRECT, _w(ninjutsu=.5, tire_machet=.3, wushu=.2), (Range.CHAOS,),
           "uses the crowd or machinery to break contact and reset", to_range=Range.MID),
    Action("positional theft", Beat.REDIRECT, _w(bjj=.4, ninjutsu=.3, kenjutsu=.3), (Range.CLINCH, Range.CLOSE),
           "the drop executed from a position the opponent's timeline says she cannot occupy",
           min_level=SHADOW_SLICE_MIN_LEVEL, downward=True, veil=True, to_range=Range.CLINCH, safety="wire"),
    # GROUND (BJJ as survival geometry: weapon access first, never sport)
    Action("survive and frame", Beat.GROUND, _w(bjj=.6, goju_ryu=.3, tire_machet=.1), (Range.GROUND,),
           "survive position, recover guard, frame to create space", safety="ground"),
    Action("sweep to weapon", Beat.GROUND, _w(bjj=.6, ninjutsu=.3, tire_machet=.1), (Range.GROUND,),
           "sweep or escape whose end position is weapon access, not a submission", to_range=Range.CLOSE,
           safety="ground"),
    Action("finish on the ground", Beat.GROUND, _w(bjj=.7, goju_ryu=.3), (Range.GROUND,),
           "used ONLY when the weapon is out of reach and the opponent is between her and it", safety="ground"),
    # RECOVER
    Action("guard reset", Beat.RECOVER, _w(karate=.4, goju_ryu=.3, kenjutsu=.3), tuple(Range),
           "fast, unlovely, expected; weapon still in frame", ends_exposed=False),
    Action("axis reset after displacement", Beat.RECOVER, _w(karate=.4, kenjutsu=.3, goju_ryu=.3), tuple(Range),
           "instantaneous guard and axis reset after temporal displacement", min_level=SHADOW_SLICE_MIN_LEVEL,
           ends_exposed=False, veil=True),
    # RE-ENTER
    Action("re-read", Beat.REENTER, _w(ninjutsu=.5, tire_machet=.3, kenjutsu=.2), tuple(Range),
           "the sentence loops; the room has changed", ends_exposed=False),
)


# --------------------------------------------------------------------------- guardrails
class CanonViolation(Exception):
    """Raised instead of emitting a beat that breaks a lock or the fingerprint."""


def allowed(a: Action, s: Situation) -> Tuple[bool, str]:
    if a.min_level > s.level:
        return False, f"{a.name}: needs level {a.min_level}, Xoah is level {s.level}"
    if a.veil and s.level <= VOL1_MAX_LEVEL:
        return False, f"{a.name}: Veil mechanics locked out at Vol 1 level {s.level}"
    if a.needs_weapon and s.weapon not in a.needs_weapon:
        return False, f"{a.name}: needs {[w.value for w in a.needs_weapon]}, holding {s.weapon.value}"
    if s.range not in a.ranges:
        return False, f"{a.name}: not valid at {s.range.value} range"
    if a.beat in (Beat.ANGLE, Beat.STRIKE, Beat.REDIRECT) and not a.arrests_by_contact:
        return False, f"{a.name}: unarrested arc (invariant 1)"
    if not a.weapon_in_frame:
        return False, f"{a.name}: weapon leaves frame (invariant 3)"
    if a.name == "finish on the ground" and s.weapon != Weapon.EMPTY_HAND:
        return False, "finish on the ground: weapon is in reach; ground objective is weapon access (invariant 3)"
    return True, ""


# --------------------------------------------------------------------------- weighting
def situation_weights(s: Situation) -> Dict[Root, float]:
    """The situation's pull on each root. Blending, never selection."""
    w = {r: 0.1 for r in Root}
    for r in RANGE_MAP[s.range]:
        w[r] += 0.6
    if s.range in (Range.CLINCH, Range.GROUND) or s.injury > 0.6:
        w[Root.BJJ] += 0.5            # collapse -> survival geometry
    if s.env.crowd_density > 0.5 or s.env.terrain in ("market", "machinery", "stair"):
        w[Root.NINJUTSU] += 0.3       # terrain exploitation
    if s.env.gravity < 0.6:
        w[Root.WUSHU] += 0.2          # rotation is cheap on Mars
    if s.env.traction < 0.4:
        w[Root.GOJU_RYU] += 0.3       # rooted power when the floor lies
        w[Root.WUSHU] -= 0.2
    if s.weapon in (Weapon.KAGE_TANAK, Weapon.MACHETE):
        w[Root.KENJUTSU] += 0.3
        w[Root.TIRE_MACHET] += 0.3
    if s.weapon == Weapon.FIREARM:
        w[Root.GUN_KATA] += 0.4
        w[Root.KENJUTSU] += 0.1       # blade geometry carries into the gun hand
    if s.opponent.count > 1:
        w[Root.NINJUTSU] += 0.2
        w[Root.WUSHU] += 0.1
        w[Root.GUN_KATA] += 0.2       # multi-opponent spatial awareness
    if s.intent in (Intent.ESCAPE, Intent.REACH_OBJECTIVE, Intent.STALL):
        w[Root.NINJUTSU] += 0.3
    if s.fear > 0.6:
        w[Root.KENJUTSU] += 0.2       # under fear she becomes more precise, not louder
    w[Root.TIRE_MACHET] += 0.15       # culturally sovereign: always present
    return w


def score(a: Action, s: Situation, sw: Mapping[Root, float], recent: Sequence[str]) -> float:
    base = sum(a.roots.get(r, 0.0) * sw[r] for r in Root)
    if a.downward and s.env.verticality > 0.4:
        base += 0.25                   # invariant 4: she fights downward when there is a down
    if a.veil and s.level >= SHADOW_SLICE_MIN_LEVEL:
        base += 0.15                   # at L9 the Veil route is available, not mandatory
    penalty = sum(0.35 for n in recent if n == a.name)   # anti-repetition memory
    return max(base - penalty, 0.01)


# --------------------------------------------------------------------------- engine
@dataclass(frozen=True)
class BeatOut:
    index: int
    beat: str
    action: str
    range_before: str
    range_after: str
    roots: List[str]                     # strongest first: the multi-root trace
    root_weights: Dict[str, float]
    mechanics: str
    rationale: str
    camera: str
    safety: str
    continuity: Dict[str, object]
    veil: bool


def _camera(a: Action, s: Situation) -> str:
    if a.beat == Beat.COLLISION:
        return "medium-wide, hold: this is the readable, vulnerable beat; do not cut through it"
    if a.veil:
        return "full-body geography; the impossible route must land somewhere the audience saw"
    if a.beat == Beat.GROUND:
        return "low and wide; feet, hips and the weapon's position stay visible"
    return "medium-wide; feet, hips, weapon path and recovery in frame"


def _rationale(a: Action, s: Situation, sw: Mapping[Root, float]) -> str:
    top = sorted(a.roots.items(), key=lambda kv: -kv[1] * sw[kv[0]])[:3]
    pulls = ", ".join(f"{r.value}({a.roots[r] * sw[r]:.2f})" for r, _ in top)
    return (f"{s.range.value} range, {s.env.terrain}, intent {s.intent.value}, level {s.level}: "
            f"strongest pulls {pulls}")


class XoahCombatEngine:
    def __init__(self, seed: int, catalogue: Sequence[Action] = CATALOGUE, memory: int = 6):
        self.seed = seed
        self.catalogue = tuple(catalogue)
        self.memory = memory

    def _pick(self, rng: random.Random, beat: Beat, s: Situation, recent: List[str]) -> Action:
        sw = situation_weights(s)
        pool = [a for a in self.catalogue if a.beat == beat and allowed(a, s)[0]]
        if not pool:
            reasons = [allowed(a, s)[1] for a in self.catalogue if a.beat == beat]
            raise CanonViolation(f"no legal {beat.value} action: " + "; ".join(reasons))
        weights = [score(a, s, sw, recent) for a in pool]
        return rng.choices(pool, weights=weights, k=1)[0]

    def fight(self, s: Situation, beats: int = 8) -> List[BeatOut]:
        rng = random.Random(self.seed)
        out: List[BeatOut] = []
        recent: List[str] = []
        state = s
        i = 0
        pos = 0
        while i < beats:
            beat = SENTENCE[pos % len(SENTENCE)]
            a = self._pick(rng, beat, state, recent)
            before = state.range
            after = a.to_range or before
            # Invariant 1: a COLLISION must arrest; invariant 2: it leaves her exposed.
            sw = situation_weights(state)
            out.append(BeatOut(
                i, beat.value, a.name, before.value, after.value, a.trace(),
                {r.value: round(w, 2) for r, w in a.roots.items()}, a.mechanics,
                _rationale(a, state, sw), _camera(a, state), a.safety,
                {"exposed_at_finish": a.ends_exposed, "weapon_in_frame": a.weapon_in_frame,
                 "arrested_by_contact": a.arrests_by_contact, "downward": a.downward,
                 "injury": round(state.injury, 2)},
                a.veil))
            recent = (recent + [a.name])[-self.memory:]
            injury = min(1.0, state.injury + (0.1 if beat == Beat.COLLISION and a.ends_exposed else 0.0))
            state = Situation(state.level, state.weapon, state.intent, after, injury, state.fear,
                              state.env, state.opponent)
            i += 1
            pos += 1
            # The GROUND beat is inserted only when the range collapsed to ground.
            if beat == Beat.COLLISION and after == Range.GROUND and i < beats:
                g = self._pick(rng, Beat.GROUND, state, recent)
                gafter = g.to_range or Range.GROUND
                out.append(BeatOut(
                    i, Beat.GROUND.value, g.name, Range.GROUND.value, gafter.value, g.trace(),
                    {r.value: round(w, 2) for r, w in g.roots.items()}, g.mechanics,
                    _rationale(g, state, situation_weights(state)), _camera(g, state), g.safety,
                    {"exposed_at_finish": g.ends_exposed, "weapon_in_frame": g.weapon_in_frame,
                     "arrested_by_contact": True, "downward": True, "injury": round(state.injury, 2)},
                    g.veil))
                recent = (recent + [g.name])[-self.memory:]
                state = Situation(state.level, state.weapon, state.intent, gafter, state.injury,
                                  state.fear, state.env, state.opponent)
                i += 1
                pos += 1  # skip REDIRECT; the sweep already redirected
        return out

    # ------------------------------------------------------------------ output
    @staticmethod
    def to_json(beats: Sequence[BeatOut], s: Situation, seed: int) -> str:
        doc = {"engine": "xoah-combat-0.1", "seed": seed, "situation": asdict(s),
               "beats": [asdict(b) for b in beats]}
        return json.dumps(doc, indent=1, default=str, sort_keys=True)

    @staticmethod
    def to_screenplay(beats: Sequence[BeatOut]) -> str:
        lines = []
        for b in beats:
            veil = " [VEIL]" if b.veil else ""
            lines.append(f"{b.index + 1}. {b.beat}{veil} — {b.action.upper()} ({b.range_before}"
                         f"{' -> ' + b.range_after if b.range_after != b.range_before else ''})")
            lines.append(f"   {b.mechanics}")
            lines.append(f"   camera: {b.camera}")
        return "\n".join(lines)

    @staticmethod
    def fingerprint(beats: Sequence[BeatOut]) -> str:
        """Content hash of the fight: same seed + situation must reproduce it."""
        blob = json.dumps([asdict(b) for b in beats], sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()


__all__ = ["Root", "Range", "Weapon", "Intent", "Beat", "Environment", "Opponent", "Situation",
           "Action", "CATALOGUE", "RANGE_MAP", "CanonViolation", "XoahCombatEngine", "allowed",
           "situation_weights", "SHADOW_SLICE_MIN_LEVEL", "VOL1_MAX_LEVEL"]
