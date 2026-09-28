"""Turn engine: inject -> Blue claim -> White verdict -> counteraction.

Deterministic by construction (doctrine section 51). The seed is recorded
in the receipt and threaded into any inject that has a random component so
a failure can be replayed exactly.
"""
from __future__ import annotations

import copy
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .adjudication import Claim, adjudicate, evaluate_conditions
from .model import WarGame, load_scenario
from .receipts import Receipt, elevation_candidate, score_game

PolicyFn = Callable[[dict[str, Any]], Claim]
InjectFn = Callable[[dict[str, Any], dict[str, Any], random.Random], str]
ActionFn = Callable[[dict[str, Any]], str]

POLICIES: dict[str, PolicyFn] = {}
INJECTS: dict[str, InjectFn] = {}
ACTIONS: dict[str, ActionFn] = {}


def policy(name: str):
    def deco(fn: PolicyFn) -> PolicyFn:
        POLICIES[name] = fn
        return fn
    return deco


def inject(name: str):
    def deco(fn: InjectFn) -> InjectFn:
        INJECTS[name] = fn
        return fn
    return deco


def action(name: str):
    def deco(fn: ActionFn) -> ActionFn:
        ACTIONS[name] = fn
        return fn
    return deco


# --------------------------------------------------------------------------
# Red: injects
# --------------------------------------------------------------------------

@inject("scheduler_expiry")
def _scheduler_expiry(state, params, rng) -> str:
    task = state.setdefault("task", {})
    task["next_run_time"] = None
    task["repetition_duration_elapsed"] = True
    return "repetition duration elapsed; next_run_time cleared, enabled and last_result untouched"


@inject("lane_timeout")
def _lane_timeout(state, params, rng) -> str:
    lane = params.get("lane")
    lanes = state.setdefault("lanes", {})
    if lane not in lanes:
        return f"lane {lane!r} not in arena; inject had no effect"
    lanes[lane]["answered"] = False
    lanes[lane]["hits"] = None
    return f"lane {lane} stopped answering"


@inject("lane_greyout")
def _lane_greyout(state, params, rng) -> str:
    lane = params.get("lane")
    lanes = state.setdefault("lanes", {})
    if lane not in lanes:
        return f"lane {lane!r} not in arena; inject had no effect"
    up = rng.random() < float(params.get("p_up", 0.5))
    lanes[lane]["answered"] = up
    if not up:
        lanes[lane]["hits"] = None
    return f"lane {lane} greyout: {'answered' if up else 'silent'} this turn (seeded)"


@inject("binder_swap")
def _binder_swap(state, params, rng) -> str:
    port = state.setdefault("port", {})
    port["owner_tree"] = params.get("tree", port.get("owner_tree"))
    port["owner_pid"] = params.get("pid", port.get("owner_pid"))
    return f"scheduling order changed; {port['owner_tree']} bound :{port.get('number')} first"


@inject("patch_deployed")
def _patch_deployed(state, params, rng) -> str:
    tree = params["tree"]
    sha = params["sha"]
    state.setdefault("trees", {}).setdefault(tree, {})["sha"] = sha
    state["expected_sha"] = sha
    state["rollout"] = "in_progress"
    return f"patch {sha} deployed to {tree}; expected_sha now {sha}"


# --------------------------------------------------------------------------
# Blue: policies (naive baselines and hardened counterparts)
# --------------------------------------------------------------------------

@policy("exit_code_zero_means_green")
def _naive_exit_code(state) -> Claim:
    task = state.get("task", {})
    ok = task.get("last_result") == 0 and task.get("enabled", False)
    return Claim("GREEN" if ok else "RED",
                 {"last_result": task.get("last_result"), "enabled": task.get("enabled")},
                 "last task result is 0 and task is enabled, so the scheduler is healthy")


@policy("task_truth")
def _task_truth(state) -> Claim:
    """Deterministic checker: classify by future execution, not history."""
    task = state.get("task", {})
    enabled = task.get("enabled", False)
    future = task.get("next_run_time")
    last = task.get("last_result")
    ev = {"enabled": enabled, "next_run_time": future, "last_result": last}
    if not enabled:
        return Claim("DORMANT", ev, "task disabled", None)
    if future is None:
        return Claim("RED", ev, "enabled with no future run: repeating job silently expired",
                     "recreate_schedule")
    if last not in (0, None):
        return Claim("DEGRADED", ev, "future run exists but last result was non-zero", None)
    return Claim("GREEN", ev, "enabled, future run scheduled, last result clean", None)


@policy("merge_and_declare")
def _naive_merge(state) -> Claim:
    lanes = state.get("lanes", {})
    hits = sum(int(lane.get("hits") or 0) for lane in lanes.values())
    ev = {"hits": hits, "fleet_complete": True, "lanes_queried": sorted(lanes)}
    if hits == 0:
        return Claim("ABSENT", ev, "no lane returned a hit, so no such memory exists")
    return Claim("PRESENT", ev, f"{hits} hit(s) across the fleet")


@policy("coverage_aware_recall")
def _coverage_aware(state) -> Claim:
    lanes = state.get("lanes", {})
    answered = {n: lane for n, lane in lanes.items() if lane.get("answered")}
    silent = sorted(set(lanes) - set(answered))
    hits = sum(int(lane.get("hits") or 0) for lane in answered.values())
    complete = not silent
    ev = {"hits": hits, "fleet_complete": complete,
          "lanes_answered": sorted(answered), "lanes_silent": silent}
    if hits > 0:
        return Claim("PRESENT", ev, f"{hits} hit(s) in answering lanes")
    if complete:
        return Claim("ABSENT", ev, "every expected lane answered and none had a hit")
    act = "bounded_retry" if state.get("retries", 0) < state.get("retry_budget", 0) else None
    return Claim("UNKNOWN", ev,
                 f"no hit in answering lanes; coverage incomplete ({', '.join(silent)} silent); "
                 "absence cannot be proven", act)


@policy("port_open_means_deployed")
def _naive_port(state) -> Claim:
    port = state.get("port", {})
    ev = {"listening": port.get("listening"), "identity_checked": False}
    if port.get("listening") and state.get("expected_sha"):
        return Claim("DEPLOYED", ev, "port answers after deploy, so the patch is live")
    return Claim("UNKNOWN" if not port.get("listening") else "IDLE", ev, "port state only")


@policy("runtime_identity")
def _runtime_identity(state) -> Claim:
    port = state.get("port", {})
    trees = state.get("trees", {})
    owner_tree = port.get("owner_tree")
    owner_sha = trees.get(owner_tree, {}).get("sha")
    expected = state.get("expected_sha")
    ev = {"listening": port.get("listening"), "owner_pid": port.get("owner_pid"),
          "owner_tree": owner_tree, "owner_sha": owner_sha, "expected_sha": expected,
          "identity_checked": True}
    if not expected:
        return Claim("IDLE", ev, "no rollout in flight; owner identity recorded")
    if owner_sha == expected:
        return Claim("DEPLOYED", ev, "socket owner runs the expected SHA")
    return Claim("MISMATCH", ev,
                 f"port answers but {owner_tree} owns the socket at {owner_sha}, expected {expected}",
                 "halt_rollout")


# --------------------------------------------------------------------------
# Green: counteractions
# --------------------------------------------------------------------------

@action("recreate_schedule")
def _recreate_schedule(state) -> str:
    task = state.setdefault("task", {})
    task["next_run_time"] = task.get("recreate_next_run_time", "T+15m")
    task["repetition_duration_elapsed"] = False
    return "schedule recreated with a future trigger"


@action("bounded_retry")
def _bounded_retry(state) -> str:
    state["retries"] = state.get("retries", 0) + 1
    return f"alternate retrieval attempted (retry {state['retries']}/{state.get('retry_budget', 0)})"


@action("halt_rollout")
def _halt_rollout(state) -> str:
    state["rollout"] = "halted"
    return "rollout halted until socket ownership is resolved"


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------

def run_game(game: WarGame, *, policy_name: str | None = None, seed: int = 0,
             level: str = "SIMULATED") -> Receipt:
    """Run a scenario to completion and return its receipt (not yet written)."""
    blue_policy = policy_name or game.blue.policy
    if blue_policy == "naive":
        blue_policy = game.blue.naive_policy or game.blue.policy
    fn = POLICIES.get(blue_policy)
    if fn is None:
        raise KeyError(f"unknown blue policy {blue_policy!r}; known: {sorted(POLICIES)}")

    rng = random.Random(seed)
    state = copy.deepcopy(game.initial_state)
    started = datetime.now(timezone.utc)
    turns: list[dict[str, Any]] = []
    breaches: list[dict[str, Any]] = []

    for t in range(1, game.turns + 1):
        applied = []
        for inj in game.injects:
            if inj.at_turn != t:
                continue
            handler = INJECTS.get(inj.type)
            if handler is None:
                raise KeyError(f"unknown inject type {inj.type!r}; known: {sorted(INJECTS)}")
            applied.append({"type": inj.type, "params": inj.params,
                            "effect": handler(state, inj.params, rng)})

        claim = fn(state)
        packets = adjudicate(game.invariants, claim, state)
        for p in packets:
            if p.verdict == "FAIL":
                breaches.append({"turn": t, **p.to_dict()})

        counteraction = None
        if claim.action:
            act = ACTIONS.get(claim.action)
            if act is None:
                raise KeyError(f"unknown action {claim.action!r}; known: {sorted(ACTIONS)}")
            counteraction = {"action": claim.action, "effect": act(state)}

        turns.append({
            "turn": t,
            "injects": applied,
            "claim": claim.to_dict(),
            "packets": [p.to_dict() for p in packets],
            "counteraction": counteraction,
            "state_after": copy.deepcopy(state),
        })

    victory = evaluate_conditions(game.victory, state, turns)
    catastrophic = evaluate_conditions(game.catastrophic_failure, state, turns)
    status = "PASS" if (all(victory.values()) and not breaches
                        and not any(catastrophic.values())) else "FAIL"
    finished = datetime.now(timezone.utc)

    receipt = Receipt(
        id=f"{game.id}-{started.strftime('%Y%m%dT%H%M%SZ')}-s{seed}",
        game_id=game.id, scenario=Path(game.source).stem if game.source else game.id,
        scenario_version=game.version, title=game.title, level=level,
        blue_policy=blue_policy, seed=seed,
        started_at=started.isoformat(), finished_at=finished.isoformat(),
        actors={r: a.objective for r, a in game.actors.items()},
        initial_state=copy.deepcopy(game.initial_state), assumptions=game.assumptions,
        injects=[i.to_dict() for i in game.injects], invariants=game.invariants,
        turns=turns, breaches=breaches, victory=victory, catastrophic=catastrophic,
        final_state=copy.deepcopy(state), status=status, score={}, elevation={},
    )
    receipt.score = score_game(receipt)
    receipt.elevation = elevation_candidate(game, receipt)
    return receipt


def replay_receipt(receipt_path: str | Path) -> dict[str, Any]:
    """Re-run the scenario a receipt records and compare verdicts turn by turn."""
    path = Path(receipt_path)
    old = json.loads(path.read_text(encoding="utf-8"))
    game = load_scenario(old["scenario"])
    new = run_game(game, policy_name=old["blue_policy"], seed=int(old["seed"]), level=old["level"])
    old_v = [(t["turn"], t["claim"]["status"], [p["verdict"] for p in t["packets"]]) for t in old["turns"]]
    new_v = [(t["turn"], t["claim"]["status"], [p["verdict"] for p in t["packets"]]) for t in new.turns]
    diverged = [i + 1 for i, (a, b) in enumerate(zip(old_v, new_v)) if a != b]
    if len(old_v) != len(new_v):
        diverged.append(min(len(old_v), len(new_v)) + 1)
    return {
        "receipt": str(path), "scenario": old["scenario"], "seed": old["seed"],
        "blue_policy": old["blue_policy"],
        "original_status": old["status"], "replay_status": new.status,
        "replay": "PASS" if not diverged and old["status"] == new.status else "DIVERGED",
        "diverged_turns": diverged,
    }
