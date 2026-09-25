"""Receipts, scoring, ledger, elevation candidates, and the Markdown AAR.

Doctrine sections 25 (scoreboard with caps), 46 (elevation object),
47 (receipts), 48 (ledger), 73 (AAR).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .model import WarGame

DEFAULT_OUT = Path("wargames")   # gitignored on purpose: receipts are working notes

# Section 25 weights. The slice measures a subset; unmeasured categories are
# excluded and the score is normalised over the measured weight so a number
# is never invented for something the engine did not observe.
WEIGHTS = {
    "mission": 15, "truth": 15, "resilience": 15, "recovery": 10,
    "continuity": 10, "observability": 10, "security": 10,
    "efficiency": 5, "human_load": 5, "replayability": 5,
}
CAP_FALSE_PASS = 49


@dataclass
class Receipt:
    id: str
    game_id: str
    scenario: str
    scenario_version: int
    title: str
    level: str
    blue_policy: str
    seed: int
    started_at: str
    finished_at: str
    actors: dict[str, str]
    initial_state: dict[str, Any]
    assumptions: dict[str, list[str]]
    injects: list[dict[str, Any]]
    invariants: list[str]
    turns: list[dict[str, Any]]
    breaches: list[dict[str, Any]]
    victory: dict[str, bool | None]
    catastrophic: dict[str, bool | None]
    final_state: dict[str, Any]
    status: str
    score: dict[str, Any] = field(default_factory=dict)
    elevation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_game(r: Receipt) -> dict[str, Any]:
    measured: dict[str, int] = {}
    vic = [v for v in r.victory.values() if v is not None]
    measured["mission"] = int(100 * sum(vic) / len(vic)) if vic else 0
    measured["truth"] = 0 if r.breaches else 100
    measured["resilience"] = 0 if any(r.catastrophic.values()) else 100
    recovery_turns = [t for t in r.turns if t["counteraction"]]
    if any(t["injects"] for t in r.turns):
        measured["recovery"] = 100 if recovery_turns and not r.breaches else (50 if recovery_turns else 0)
    human = sum(1 for t in r.turns if t["claim"]["status"] == "UNKNOWN" and not t["counteraction"])
    measured["human_load"] = max(0, 100 - 25 * human)
    measured["replayability"] = 100  # deterministic engine, seed recorded

    weight = sum(WEIGHTS[k] for k in measured)
    raw = sum(WEIGHTS[k] * v for k, v in measured.items()) / weight
    caps = []
    if r.breaches:
        caps.append({"reason": "false PASS on critical truth", "max": CAP_FALSE_PASS})
    if any(r.catastrophic.values()):
        caps.append({"reason": "catastrophic failure condition met", "max": 0})
    final = min([raw] + [c["max"] for c in caps])
    return {"categories": measured, "measured_weight": weight, "raw": round(raw, 1),
            "caps": caps, "final": int(final)}


def elevation_candidate(game: WarGame, r: Receipt) -> dict[str, Any]:
    spec = game.elevation or {}
    breached = sorted({b["invariant"] for b in r.breaches})
    hardened = game.blue.policy
    verified = r.status == "PASS" and r.blue_policy == hardened
    return {
        "id": f"ELEV-{game.id}",
        "source_wargame": r.id,
        "failure": {"class": spec.get("failure_class", game.mode or "unclassified"),
                    "description": spec.get("description", "")},
        "root_cause": {"assumption": spec.get("assumption",
                                              (game.assumptions.get("dangerous") or [""])[0])},
        "invariant": spec.get("invariant", game.invariants[0]),
        "change": {"component": spec.get("component", "blue_policy"),
                   "type": spec.get("change_type", "deterministic_checker"),
                   "from": game.blue.naive_policy, "to": hardened},
        "evidence": {"policy_run": r.blue_policy, "status": r.status,
                     "invariants_breached": breached},
        "status": "verified" if verified else "candidate",
    }


def render_aar(r: Receipt) -> str:
    lines = [
        f"# AAR: {r.title}",
        "",
        f"- **Receipt:** `{r.id}`",
        f"- **Scenario:** `{r.scenario}` v{r.scenario_version} · level `{r.level}` · seed `{r.seed}`",
        f"- **Blue policy:** `{r.blue_policy}`",
        f"- **Status:** **{r.status}** · score {r.score.get('final')}/100",
        "",
        "## What did we expect?",
        "",
        *(f"- victory: `{k}`" for k in r.victory),
        *(f"- catastrophic: `{k}`" for k in r.catastrophic),
        "",
        "## What actually happened?",
        "",
    ]
    for t in r.turns:
        inj = "; ".join(f"{i['type']}: {i['effect']}" for i in t["injects"]) or "no inject"
        verdicts = ", ".join(f"{p['invariant']}={p['verdict']}" for p in t["packets"])
        lines.append(f"### Turn {t['turn']}")
        lines.append("")
        lines.append(f"- **Red:** {inj}")
        lines.append(f"- **Blue:** `{t['claim']['status']}`. {t['claim']['reasoning']}")
        lines.append(f"- **White:** {verdicts}")
        if t["counteraction"]:
            lines.append(f"- **Green:** {t['counteraction']['action']}: {t['counteraction']['effect']}")
        lines.append("")
    lines += ["## Which assumption failed?", ""]
    if r.breaches:
        for b in r.breaches:
            lines.append(f"- turn {b['turn']}: `{b['invariant']}` breached. {b['reason']}")
    else:
        lines.append("- none breached; assumptions held under this pressure")
    lines += ["", "## Conditions", ""]
    for k, v in r.victory.items():
        lines.append(f"- victory `{k}`: {'met' if v else 'NOT met' if v is not None else 'unregistered'}")
    for k, v in r.catastrophic.items():
        lines.append(f"- catastrophic `{k}`: {'TRIGGERED' if v else 'avoided' if v is not None else 'unregistered'}")
    lines += ["", "## Score", "", "| category | value |", "|---|---|"]
    for k, v in r.score.get("categories", {}).items():
        lines.append(f"| {k} | {v} |")
    for c in r.score.get("caps", []):
        lines.append(f"| cap: {c['reason']} | max {c['max']} |")
    lines.append(f"| **final** | **{r.score.get('final')}** |")
    e = r.elevation
    lines += ["", "## Elevation", "",
              f"- `{e.get('id')}` · status **{e.get('status')}**",
              f"- failure class: {e.get('failure', {}).get('class')}",
              f"- broken assumption: {e.get('root_cause', {}).get('assumption')}",
              f"- invariant: `{e.get('invariant')}`",
              f"- change: `{e.get('change', {}).get('from')}` → `{e.get('change', {}).get('to')}`",
              "", "## Replay", "",
              f"    nougen wargame run {r.scenario} --policy {r.blue_policy} --seed {r.seed}",
              "    nougen wargame replay <receipt.json>", ""]
    return "\n".join(lines)


def write_receipt(r: Receipt, out_dir: str | Path | None = None) -> dict[str, str]:
    base = Path(out_dir) if out_dir else DEFAULT_OUT
    receipts = base / "receipts"
    reports = base / "reports"
    receipts.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    json_path = receipts / f"{r.id}.json"
    md_path = reports / f"{r.id}.md"
    json_path.write_text(json.dumps(r.to_dict(), indent=2, sort_keys=False), encoding="utf-8")
    md_path.write_text(render_aar(r), encoding="utf-8")
    ledger = base / "ledger.jsonl"
    line = {
        "id": r.id, "scenario": r.scenario, "version": r.scenario_version,
        "policy": r.blue_policy, "seed": r.seed, "status": r.status,
        "score": r.score.get("final"), "critical_failures": len(r.breaches),
        "elevations": [r.elevation.get("id")] if r.elevation else [],
        "elevation_status": r.elevation.get("status"),
        "receipt": str(json_path.relative_to(base)), "timestamp": r.finished_at,
    }
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
    return {"receipt": str(json_path), "aar": str(md_path), "ledger": str(ledger)}
