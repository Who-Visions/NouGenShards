"""PR-A: Adaptive Information Budget, shadow mode (owner leg 20260923T034258Z,
shard 25097@db1; process donor Bialek 2002 arXiv:physics/0205030).

Translation, not biology: a nervous system adapts its coding to the
statistics of its input. Here: for a given bounded task description, decide
how much evidence, context and model strength the task is actually worth,
instead of a fixed budget for every task.

TaskSignature -> BudgetDecision is a PURE, DETERMINISTIC function: same
signature, same decision, every time. It is a rule-first scorer (bounded
thresholds over bounded inputs), not a model call -- matching the fleet's
"rules get first right of refusal" law (decision/plane.py) and giving
reproducible replay for free.

SHADOW MODE ONLY. This module computes a BudgetDecision and a receipt
explaining it; nothing in this file, or reachable from it, calls a retrieval
system, a router or a model. Wiring an actual route to obey this decision is
a SEPARATE, later change gated by explicit code elsewhere, not by anything
here. mode() defaults to "off" and fails closed on an unrecognised value, so
a typo can never turn this on. This mirrors decision.policy.mode(), kept as
its own flag (NOUGEN_ADAPTIVE_BUDGET) rather than overloading the shared one,
so it can roll out and roll back independently of the rest of the Decision
Plane.

No Shadow Dweller lore: every fixture and example here is sanitized/synthetic.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

MODES = ("off", "shadow", "assist", "enforce")


def mode(env: Mapping[str, str] = os.environ) -> str:
    """NOUGEN_ADAPTIVE_BUDGET: off | shadow | assist | enforce. Anything
    unrecognised fails closed to 'off' -- rollback is just unsetting this."""
    v = str(env.get("NOUGEN_ADAPTIVE_BUDGET", "off")).strip().lower()
    return v if v in MODES else "off"


class TaskFamily(str, Enum):
    LOOKUP = "lookup"                   # single-fact retrieval, low ambiguity
    TRIAGE = "triage"                   # classify/route, bounded outcomes
    SYNTHESIS = "synthesis"             # combine several sources into one answer
    CODE_CHANGE = "code_change"         # write/modify code
    CANON_JUDGMENT = "canon_judgment"   # a canon/lore ruling or conflict check
    OPEN_ENDED = "open_ended"           # broad, ambiguous, high-dimensional


class LatencyClass(str, Enum):
    INTERACTIVE = "interactive"   # a human is waiting right now
    BACKGROUND = "background"     # queued/batch, no one waiting
    DEFERRED = "deferred"         # can wait indefinitely


class RouteClass(str, Enum):
    RULES = "rules"
    FAST_MODEL = "fast_model"
    DEEP_MODEL = "deep_model"
    ENSEMBLE = "ensemble"


class ModelStrengthClass(str, Enum):
    NONE = "none"          # rules only, no model call
    LIGHT = "light"
    STANDARD = "standard"
    STRONG = "strong"


@dataclass(frozen=True)
class TaskSignature:
    """Bounded inputs only -- every field is either an enum or a 0..1 float,
    so the same signature always reads the same way regardless of source."""
    task_family: TaskFamily
    uncertainty: float                  # 0 = fully determined, 1 = maximally ambiguous
    recurrence: float                   # 0 = never seen before, 1 = extremely routine
    canon_safety_sensitivity: float     # 0 = no stakes, 1 = high stakes (canon lock, secret, money)
    latency_class: LatencyClass
    tool_topology: Tuple[str, ...] = ()  # tool names this task is expected to touch
    prior_failure_rate: float = 0.0     # 0..1, this task family's recent failure rate

    def __post_init__(self) -> None:
        for name, v in (("uncertainty", self.uncertainty), ("recurrence", self.recurrence),
                        ("canon_safety_sensitivity", self.canon_safety_sensitivity),
                        ("prior_failure_rate", self.prior_failure_rate)):
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {v}")

    def fingerprint(self) -> str:
        blob = json.dumps({"task_family": self.task_family.value, "uncertainty": self.uncertainty,
                           "recurrence": self.recurrence, "canon_safety_sensitivity": self.canon_safety_sensitivity,
                           "latency_class": self.latency_class.value, "tool_topology": sorted(self.tool_topology),
                           "prior_failure_rate": self.prior_failure_rate}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class BudgetDecision:
    retrieval_depth: int                     # 0..3: how many recall passes are worth running
    context_budget: int                      # approx tokens of context worth supplying
    route_class: RouteClass
    model_strength_class: ModelStrengthClass
    tool_budget: int                         # max tool calls worth spending
    expected_information_gain_proxy: float   # 0..1, NOT a real measurement -- see docs below
    reasons: Tuple[str, ...]                 # every threshold that fired, in order
    signature_fingerprint: str
    mode: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["route_class"] = self.route_class.value
        d["model_strength_class"] = self.model_strength_class.value
        return d


# ---------------------------------------------------------------- the rules
def decide_budget(sig: TaskSignature) -> BudgetDecision:
    """Deterministic thresholds, not a model. Every branch appends its own
    reason so the receipt can show exactly why a budget was sized this way."""
    reasons: List[str] = []

    depth = 0
    if sig.uncertainty >= 0.3 or sig.canon_safety_sensitivity >= 0.3:
        depth = 1
        reasons.append("uncertainty or stakes >= 0.3: at least one retrieval pass")
    if sig.uncertainty >= 0.6 or sig.canon_safety_sensitivity >= 0.6:
        depth = 2
        reasons.append("uncertainty or stakes >= 0.6: a second, cross-checking pass")
    if sig.uncertainty >= 0.85 and sig.canon_safety_sensitivity >= 0.5:
        depth = 3
        reasons.append("high uncertainty AND real stakes together: a third, adversarial pass")
    if sig.recurrence >= 0.8 and depth > 0:
        depth = max(0, depth - 1)
        reasons.append("recurrence >= 0.8: this task family is well-trodden, one retrieval pass saved")

    base_context = {
        TaskFamily.LOOKUP: 1_000, TaskFamily.TRIAGE: 2_000, TaskFamily.SYNTHESIS: 8_000,
        TaskFamily.CODE_CHANGE: 12_000, TaskFamily.CANON_JUDGMENT: 10_000, TaskFamily.OPEN_ENDED: 16_000,
    }[sig.task_family]
    context_budget = int(base_context * (0.5 + sig.uncertainty))
    reasons.append(f"{sig.task_family.value} base context {base_context}, scaled by uncertainty to {context_budget}")

    if sig.uncertainty < 0.25 and sig.canon_safety_sensitivity < 0.25 and sig.task_family in (
            TaskFamily.LOOKUP, TaskFamily.TRIAGE):
        route = RouteClass.RULES
        strength = ModelStrengthClass.NONE
        reasons.append("low uncertainty, low stakes, bounded task family: rules handle this, no model call")
    elif sig.uncertainty < 0.6 and sig.canon_safety_sensitivity < 0.6:
        route = RouteClass.FAST_MODEL
        strength = ModelStrengthClass.LIGHT if sig.recurrence >= 0.5 else ModelStrengthClass.STANDARD
        reasons.append("moderate uncertainty/stakes: a fast model, strength scaled by recurrence")
    elif sig.uncertainty >= 0.85 and sig.canon_safety_sensitivity >= 0.7:
        route = RouteClass.ENSEMBLE
        strength = ModelStrengthClass.STRONG
        reasons.append("high uncertainty AND high stakes together: ensemble, strongest model class")
    else:
        route = RouteClass.DEEP_MODEL
        strength = ModelStrengthClass.STRONG
        reasons.append("high uncertainty or high stakes alone: a deep-reasoning single model")

    if sig.prior_failure_rate >= 0.3 and route in (RouteClass.RULES, RouteClass.FAST_MODEL):
        route = RouteClass.DEEP_MODEL
        strength = ModelStrengthClass.STRONG if strength is ModelStrengthClass.NONE else strength
        reasons.append(f"prior failure rate {sig.prior_failure_rate:.2f} >= 0.3: escalated one tier regardless "
                       f"of uncertainty/stakes")

    base_tools = max(1, len(sig.tool_topology))
    if sig.latency_class is LatencyClass.INTERACTIVE:
        tool_budget = max(1, round(base_tools * 0.75))
        reasons.append("interactive latency class: tool budget trimmed, someone is waiting")
    elif sig.latency_class is LatencyClass.DEFERRED:
        tool_budget = base_tools * 2
        reasons.append("deferred latency class: tool budget doubled, no rush")
    else:
        tool_budget = base_tools
        reasons.append("background latency class: tool budget matches expected topology")

    gain = round(min(1.0, 0.5 * sig.uncertainty + 0.3 * sig.canon_safety_sensitivity
                     + 0.2 * (1.0 - sig.recurrence)), 4)
    reasons.append(f"information-gain proxy {gain:.2f} = 0.5*uncertainty + 0.3*stakes + 0.2*novelty (NOT measured)")

    return BudgetDecision(depth, context_budget, route, strength, tool_budget, gain,
                          tuple(reasons), sig.fingerprint(), mode())


# --------------------------------------------------------- receipts / adapter
@dataclass(frozen=True)
class BudgetReceipt:
    """What a caller stores/logs. Carries the mode it ran under, so a shadow-
    mode receipt can never be mistaken for one that actually gated a route."""
    signature: Mapping[str, object]
    decision: Mapping[str, object]
    mode: str
    would_mutate_routing: bool   # always False in this module; see module docstring

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, default=str)


def budget_receipt(sig: TaskSignature) -> BudgetReceipt:
    """The integration adapter's whole surface: a caller (Context Gate /
    Decision Plane) may call this, read the receipt, and choose to act on it
    or not -- calling this function NEVER itself changes a route."""
    d = decide_budget(sig)
    sig_dict = asdict(sig)
    sig_dict["task_family"] = sig.task_family.value
    sig_dict["latency_class"] = sig.latency_class.value
    return BudgetReceipt(sig_dict, d.to_dict(), d.mode, False)


# ---------------------------------------------------------------- benchmark
def fixed_budget_baseline(sig: TaskSignature) -> BudgetDecision:
    """The comparison point: one budget for every task, no adaptation at all."""
    return BudgetDecision(2, 8_000, RouteClass.DEEP_MODEL, ModelStrengthClass.STRONG, 4, 0.5,
                          ("fixed baseline: identical budget regardless of signature",),
                          sig.fingerprint(), "baseline")


@dataclass(frozen=True)
class BenchmarkRow:
    signature_fingerprint: str
    task_family: str
    adaptive_context: int
    baseline_context: int
    adaptive_tool_budget: int
    baseline_tool_budget: int
    context_saved: int
    tool_budget_saved: int


def benchmark_vs_fixed(signatures: Sequence[TaskSignature]) -> List[BenchmarkRow]:
    """Per-signature delta of the adaptive decision against the fixed baseline.
    Positive *_saved means adaptive spent LESS than the fixed budget; negative
    means it spent more (e.g. a high-stakes task correctly asking for more)."""
    rows = []
    for sig in signatures:
        a, b = decide_budget(sig), fixed_budget_baseline(sig)
        rows.append(BenchmarkRow(sig.fingerprint(), sig.task_family.value, a.context_budget, b.context_budget,
                                 a.tool_budget, b.tool_budget, b.context_budget - a.context_budget,
                                 b.tool_budget - a.tool_budget))
    return rows


__all__ = ["TaskFamily", "LatencyClass", "RouteClass", "ModelStrengthClass", "TaskSignature",
           "BudgetDecision", "BudgetReceipt", "decide_budget", "budget_receipt",
           "fixed_budget_baseline", "benchmark_vs_fixed", "mode", "MODES"]
