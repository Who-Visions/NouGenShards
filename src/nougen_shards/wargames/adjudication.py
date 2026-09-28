"""White team: deterministic adjudication.

Doctrine section 80: whenever reality is queryable, query reality. White
never scores prose. Every invariant here is a pure predicate over (claim,
state) that returns an adjudication packet (section 20). Victory and
catastrophic conditions are predicates over the finished game.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

VERDICTS = ("PASS", "FAIL", "UNKNOWN")


@dataclass
class Claim:
    """What Blue asserts about the world this turn."""
    status: str                       # GREEN / RED / DEGRADED / DORMANT / UNKNOWN / ABSENT / PRESENT ...
    evidence: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    action: str | None = None         # named counteraction, applied after adjudication

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "evidence": self.evidence,
                "reasoning": self.reasoning, "action": self.action}


@dataclass
class Packet:
    """Adjudication packet: why reality won (or didn't)."""
    invariant: str
    verdict: str
    claim: str
    evidence: list[dict[str, Any]]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"invariant": self.invariant, "verdict": self.verdict, "claim": self.claim,
                "evidence": self.evidence, "reason": self.reason}


InvariantFn = Callable[[Claim, dict[str, Any]], Packet]
ConditionFn = Callable[[dict[str, Any], list[dict[str, Any]]], bool]

INVARIANTS: dict[str, InvariantFn] = {}
CONDITIONS: dict[str, ConditionFn] = {}


def invariant(name: str):
    def deco(fn: InvariantFn) -> InvariantFn:
        INVARIANTS[name] = fn
        return fn
    return deco


def condition(name: str):
    def deco(fn: ConditionFn) -> ConditionFn:
        CONDITIONS[name] = fn
        return fn
    return deco


def _ev(**kv: Any) -> list[dict[str, Any]]:
    return [{"type": k, "value": v} for k, v in kv.items()]


# --------------------------------------------------------------------------
# Invariants (hitboxes)
# --------------------------------------------------------------------------

@invariant("repeating_task_must_have_future_run")
def _future_run(claim: Claim, state: dict[str, Any]) -> Packet:
    task = state.get("task", {})
    ev = _ev(enabled=task.get("enabled"), next_run_time=task.get("next_run_time"),
             last_result=task.get("last_result"))
    if claim.status == "GREEN" and task.get("enabled") and task.get("next_run_time") is None:
        return Packet("repeating_task_must_have_future_run", "FAIL", claim.status, ev,
                      "historical success exists but future execution does not")
    return Packet("repeating_task_must_have_future_run", "PASS", claim.status, ev,
                  "claim is consistent with future execution state")


@invariant("no_false_absence")
def _no_false_absence(claim: Claim, state: dict[str, Any]) -> Packet:
    lanes = state.get("lanes", {})
    unanswered = sorted(n for n, lane in lanes.items() if not lane.get("answered"))
    ev = _ev(lanes_expected=sorted(lanes), lanes_unanswered=unanswered,
             fleet_complete=claim.evidence.get("fleet_complete"))
    if claim.status == "ABSENT" and unanswered:
        return Packet("no_false_absence", "FAIL", claim.status, ev,
                      "absence was claimed while expected lanes did not answer")
    if claim.evidence.get("fleet_complete") is True and unanswered:
        return Packet("no_false_absence", "FAIL", claim.status, ev,
                      "fleet_complete reported true with unanswered lanes")
    return Packet("no_false_absence", "PASS", claim.status, ev,
                  "absence never asserted beyond answered coverage")


@invariant("port_open_is_not_runtime_identity")
def _runtime_identity(claim: Claim, state: dict[str, Any]) -> Packet:
    port = state.get("port", {})
    trees = state.get("trees", {})
    owner_tree = port.get("owner_tree")
    owner_sha = trees.get(owner_tree, {}).get("sha")
    expected = state.get("expected_sha")
    ev = _ev(listening=port.get("listening"), owner_pid=port.get("owner_pid"),
             owner_tree=owner_tree, owner_sha=owner_sha, expected_sha=expected)
    if claim.status == "DEPLOYED" and owner_sha != expected:
        return Packet("port_open_is_not_runtime_identity", "FAIL", claim.status, ev,
                      "port answers but the socket owner does not run the expected SHA")
    return Packet("port_open_is_not_runtime_identity", "PASS", claim.status, ev,
                  "deployment only claimed when runtime identity matched")


# --------------------------------------------------------------------------
# Victory / catastrophic conditions, evaluated on the finished game
# --------------------------------------------------------------------------

def _statuses(turns: list[dict[str, Any]]) -> list[str]:
    return [t["claim"]["status"] for t in turns]


def _turn_of_inject(turns: list[dict[str, Any]], inject_type: str) -> int | None:
    for t in turns:
        if any(i["type"] == inject_type for i in t["injects"]):
            return t["turn"]
    return None


@condition("false_green_detected")
def _false_green_detected(state, turns) -> bool:
    t = _turn_of_inject(turns, "scheduler_expiry")
    if t is None:
        return False
    return any(x["claim"]["status"] in ("RED", "DORMANT") for x in turns if x["turn"] >= t)


@condition("repair_applied")
def _repair_applied(state, turns) -> bool:
    return state.get("task", {}).get("next_run_time") is not None and any(
        x["claim"]["action"] == "recreate_schedule" for x in turns)


@condition("system_reports_green_after_expiry")
def _green_after_expiry(state, turns) -> bool:
    t = _turn_of_inject(turns, "scheduler_expiry")
    if t is None:
        return False
    return any(x["claim"]["status"] == "GREEN" and not x["state_after"]["task"].get("next_run_time")
               for x in turns if x["turn"] >= t)


@condition("coverage_marked_incomplete")
def _coverage_incomplete(state, turns) -> bool:
    t = _turn_of_inject(turns, "lane_timeout")
    if t is None:
        return False
    return any(x["claim"]["evidence"].get("fleet_complete") is False for x in turns if x["turn"] >= t)


@condition("absence_never_claimed_under_partial_coverage")
def _never_false_absence(state, turns) -> bool:
    return all(p["verdict"] != "FAIL" for x in turns for p in x["packets"]
               if p["invariant"] == "no_false_absence")


@condition("false_absence_claimed")
def _false_absence_claimed(state, turns) -> bool:
    return not _never_false_absence(state, turns)


@condition("bounded_retry_attempted")
def _bounded_retry(state, turns) -> bool:
    return any(x["claim"]["action"] == "bounded_retry" for x in turns) and \
        state.get("retries", 0) <= state.get("retry_budget", 0)


@condition("runtime_identity_verified")
def _identity_verified(state, turns) -> bool:
    return any(x["claim"]["evidence"].get("identity_checked") is True for x in turns)


@condition("rollout_halted_on_mismatch")
def _rollout_halted(state, turns) -> bool:
    return any(x["claim"]["action"] == "halt_rollout" for x in turns) and state.get("rollout") == "halted"


@condition("patch_declared_live_on_wrong_tree")
def _wrong_tree(state, turns) -> bool:
    return any(p["verdict"] == "FAIL" for x in turns for p in x["packets"]
               if p["invariant"] == "port_open_is_not_runtime_identity")


def adjudicate(invariants: list[str], claim: Claim, state: dict[str, Any]) -> list[Packet]:
    packets = []
    for name in invariants:
        fn = INVARIANTS.get(name)
        if fn is None:
            packets.append(Packet(name, "UNKNOWN", claim.status, [],
                                  "no deterministic check registered for this invariant"))
        else:
            packets.append(fn(claim, state))
    return packets


def evaluate_conditions(names: list[str], state: dict[str, Any],
                        turns: list[dict[str, Any]]) -> dict[str, bool | None]:
    out: dict[str, bool | None] = {}
    for name in names:
        fn = CONDITIONS.get(name)
        out[name] = None if fn is None else bool(fn(state, turns))
    return out
