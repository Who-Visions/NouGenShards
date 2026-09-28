"""War Game scenario model and loader.

A scenario is a JSON document (see ``schema/war-game.schema.json``). The
Markdown doctrine explains meaning; this module makes it executable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCENARIO_DIR = Path(__file__).parent / "scenarios"
SCHEMA_PATH = Path(__file__).parent / "schema" / "war-game.schema.json"

REQUIRED_TOP = (
    "id", "title", "mission", "initial_state", "actors",
    "injects", "invariants", "victory", "turns",
)
KNOWN_ROLES = ("gm", "blue", "red", "white", "green", "gold", "purple")


class ScenarioError(ValueError):
    """Raised when a scenario file cannot be loaded or fails validation."""


@dataclass
class Inject:
    type: str
    at_turn: int
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    reversible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type, "at_turn": self.at_turn, "params": self.params,
            "description": self.description, "reversible": self.reversible,
        }


@dataclass
class Actor:
    role: str
    objective: str = ""
    policy: str | None = None          # Blue only: hardened policy name
    naive_policy: str | None = None    # Blue only: the doomed baseline


@dataclass
class WarGame:
    id: str
    title: str
    mission: dict[str, Any]
    initial_state: dict[str, Any]
    actors: dict[str, Actor]
    injects: list[Inject]
    invariants: list[str]
    victory: list[str]
    turns: int
    status: str = "candidate"
    level: str = "skirmish"
    mode: str = ""
    arena: dict[str, Any] = field(default_factory=dict)
    assumptions: dict[str, list[str]] = field(default_factory=dict)
    telemetry: list[str] = field(default_factory=list)
    catastrophic_failure: list[str] = field(default_factory=list)
    fog: dict[str, Any] = field(default_factory=dict)
    elevation: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    version: int = 1

    @property
    def blue(self) -> Actor:
        return self.actors["blue"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "status": self.status,
            "level": self.level, "mode": self.mode, "version": self.version,
            "mission": self.mission, "arena": self.arena,
            "initial_state": self.initial_state, "assumptions": self.assumptions,
            "actors": {
                r: {"objective": a.objective, "policy": a.policy,
                    "naive_policy": a.naive_policy}
                for r, a in self.actors.items()
            },
            "injects": [i.to_dict() for i in self.injects],
            "invariants": self.invariants, "telemetry": self.telemetry,
            "victory": self.victory,
            "catastrophic_failure": self.catastrophic_failure,
            "turns": self.turns, "fog": self.fog, "elevation": self.elevation,
        }


def validate_scenario(raw: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["scenario must be a JSON object"]
    for key in REQUIRED_TOP:
        if key not in raw:
            errors.append(f"missing required key: {key}")
    if errors:
        return errors
    if not isinstance(raw["turns"], int) or raw["turns"] < 1:
        errors.append("turns must be a positive integer")
    if not isinstance(raw["initial_state"], dict):
        errors.append("initial_state must be an object")
    actors = raw["actors"]
    if not isinstance(actors, dict) or "blue" not in actors or "white" not in actors:
        errors.append("actors must include at least blue and white")
    else:
        for role in actors:
            if role not in KNOWN_ROLES:
                errors.append(f"unknown actor role: {role}")
        blue = actors.get("blue") or {}
        if not blue.get("policy"):
            errors.append("actors.blue.policy is required")
    if not isinstance(raw["injects"], list):
        errors.append("injects must be a list")
    else:
        for n, inj in enumerate(raw["injects"]):
            if not isinstance(inj, dict) or "type" not in inj or "at_turn" not in inj:
                errors.append(f"injects[{n}] needs type and at_turn")
            elif not isinstance(inj["at_turn"], int) or not (1 <= inj["at_turn"] <= raw["turns"]):
                errors.append(f"injects[{n}].at_turn must be within 1..turns")
    for key in ("invariants", "victory"):
        if not isinstance(raw[key], list) or not all(isinstance(x, str) for x in raw[key]):
            errors.append(f"{key} must be a list of names")
    if not raw["invariants"]:
        errors.append("a war game needs at least one invariant (hitbox)")
    return errors


def from_dict(raw: dict[str, Any], source: str = "") -> WarGame:
    errors = validate_scenario(raw)
    if errors:
        raise ScenarioError(f"invalid scenario {source or raw.get('id', '?')}: " + "; ".join(errors))
    actors = {
        role: Actor(
            role=role, objective=spec.get("objective", ""),
            policy=spec.get("policy"), naive_policy=spec.get("naive_policy"),
        )
        for role, spec in raw["actors"].items()
    }
    injects = [
        Inject(
            type=i["type"], at_turn=i["at_turn"], params=i.get("params", {}),
            description=i.get("description", ""), reversible=i.get("reversible", True),
        )
        for i in raw["injects"]
    ]
    return WarGame(
        id=raw["id"], title=raw["title"], status=raw.get("status", "candidate"),
        level=raw.get("level", "skirmish"), mode=raw.get("mode", ""),
        version=raw.get("version", 1),
        mission=raw["mission"], arena=raw.get("arena", {}),
        initial_state=raw["initial_state"], assumptions=raw.get("assumptions", {}),
        actors=actors, injects=injects, invariants=list(raw["invariants"]),
        telemetry=raw.get("telemetry", []), victory=list(raw["victory"]),
        catastrophic_failure=raw.get("catastrophic_failure", []),
        turns=raw["turns"], fog=raw.get("fog", {}), elevation=raw.get("elevation", {}),
        source=source,
    )


def _resolve(ref: str | Path) -> Path:
    p = Path(ref)
    if p.suffix == ".json" and p.exists():
        return p
    candidate = SCENARIO_DIR / f"{ref}.json"
    if candidate.exists():
        return candidate
    raise ScenarioError(f"scenario not found: {ref} (looked in {SCENARIO_DIR})")


def load_scenario(ref: str | Path) -> WarGame:
    """Load by built-in name (``false-green-scheduler``) or by path to a JSON file."""
    path = _resolve(ref)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"{path}: {exc}") from exc
    return from_dict(raw, source=str(path))


def list_scenarios() -> list[WarGame]:
    return [load_scenario(p) for p in sorted(SCENARIO_DIR.glob("*.json"))]
