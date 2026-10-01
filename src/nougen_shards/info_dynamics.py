"""NouGen information-dynamics metrics: separately observable, versioned, provenance-tagged.

Leg 20261001T180631Z (HURRICANE KICK). Nothing here is wired into retrieval, relay or the
live loop, and nothing mutates durable state. Each metric returns a ``Metric`` carrying its
own ``calibration_version`` and provenance; there is deliberately NO combined score.

Anchors (abstract/title level only; the paper bodies were not read for this module):
  2605.10870  decision-based rate-distortion for agent memory  -> decision_distortion
  2604.09521  semantic rate-distortion, capacity-derived space  -> semantic_survival
  2609.38119  looped working memory vs semantic thrashing       -> project, belief_shift_kl
  2606.05711  latent communication in multi-agent systems       -> provenance is canonical
  2609.40195 / 2609.39765 / 2607.25380 / 2607.01224 (memory systems) -> context for project()

Equations (bits throughout):
  I(o)            = -log2 P(o | M)                           surprisal_bits  (information_gain)
  ΔKL             = D_KL(P_t || P_{t-1})                     belief_shift_kl
  distortion      = EU_full(a*_full) - EU_full(a*_proj)  >= 0  decision_distortion
                    a* = argmax_a Σ_h P(h) U(a, h)           (loss in decision quality, not text)
  stop            = sufficiency >= tau  AND  E[decision gain] < acquisition cost   should_stop
  error energy    = Σ_k w_k · c_k   over fleet error components; drift = E_{t+1} - E_t

CALIBRATION_VERSION marks every default weight and threshold as UNCALIBRATED. Changing any
default requires bumping it so results from different calibrations are never compared.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

CALIBRATION_VERSION = "infodyn-0.1.0-uncalibrated"

ERROR_WEIGHTS: Dict[str, float] = {
    "state_divergence": 1.0,
    "stale_beliefs": 0.5,
    "unacked_critical_relays": 2.0,
    "provenance_violations": 3.0,
    "duplicate_work": 0.5,
}


@dataclass(frozen=True)
class Metric:
    name: str
    value: Any
    calibration_version: str = CALIBRATION_VERSION
    provenance: Dict[str, Any] = field(default_factory=dict)


def _metric(name: str, value: Any, **inputs: Any) -> Metric:
    return Metric(name, value, CALIBRATION_VERSION,
                  {"kind": "computed", "metric": name, "inputs": inputs})


def surprisal_bits(memory: Any, event: Iterable[str]) -> Metric:
    """I(o) against an information_gain.MemoryState. Non-mutating."""
    g = memory.gain(event)
    return _metric("surprisal_bits", g.bits, size=g.size, memory_events=memory.events)


# -- beliefs --------------------------------------------------------------

def bayes_update(prior: Mapping[str, float], likelihood: Mapping[str, float]) -> Dict[str, float]:
    post = {h: prior[h] * likelihood[h] for h in sorted(prior)}
    z = sum(post.values())
    if z <= 0:
        raise ValueError("evidence has zero likelihood under every hypothesis")
    return {h: p / z for h, p in post.items()}


def belief_shift_kl(prior: Mapping[str, float], posterior: Mapping[str, float]) -> Metric:
    """ΔKL = D_KL(posterior || prior) in bits; inf if posterior has mass where prior has none."""
    if set(prior) != set(posterior):
        raise ValueError("belief states must share a hypothesis set")
    kl = 0.0
    for h in sorted(prior):
        q, p = posterior[h], prior[h]
        if q == 0:
            continue
        if p == 0:
            kl = math.inf
            break
        kl += q * math.log2(q / p)
    return _metric("belief_shift_kl_bits", kl)


# -- decision distortion ----------------------------------------------------

def _best_action(belief: Mapping[str, float], utility: Mapping[str, Mapping[str, float]]) -> str:
    return max(sorted(utility), key=lambda a: sum(belief[h] * utility[a][h] for h in belief))


def decision_distortion(full: Mapping[str, float], projected: Mapping[str, float],
                        utility: Mapping[str, Mapping[str, float]]) -> Metric:
    """Expected utility lost by acting on the projected belief instead of the full one."""
    eu = lambda a: sum(full[h] * utility[a][h] for h in full)  # noqa: E731
    a_full, a_proj = _best_action(full, utility), _best_action(projected, utility)
    return _metric("decision_distortion", max(0.0, eu(a_full) - eu(a_proj)),
                   a_full=a_full, a_proj=a_proj)


def should_stop(sufficiency: float, tau: float, expected_gain: float, cost: float) -> Metric:
    """Stop retrieving only when sufficient AND another fetch is not worth its cost."""
    return _metric("should_stop", sufficiency >= tau and expected_gain < cost,
                   sufficiency=sufficiency, tau=tau, expected_gain=expected_gain, cost=cost)


def action_allowed(sufficiency: float, reversible: bool,
                   tau: float = 0.6, tau_irreversible: float = 0.95) -> Metric:
    """Irreversible actions need a far higher evidence bar than reversible ones."""
    bar = tau if reversible else tau_irreversible
    return _metric("action_allowed", sufficiency >= bar, sufficiency=sufficiency, bar=bar,
                   reversible=reversible)


# -- fleet error energy ------------------------------------------------------

def error_energy(components: Mapping[str, float], weights: Mapping[str, float] = ERROR_WEIGHTS) -> Metric:
    unknown = set(components) - set(weights)
    if unknown:
        raise ValueError(f"unknown error components: {sorted(unknown)}")
    return _metric("fleet_error_energy",
                   sum(weights[k] * components.get(k, 0.0) for k in sorted(weights)),
                   components=dict(components))


def drift(previous: Metric, current: Metric) -> Metric:
    """E_{t+1} - E_t. Negative means the fleet is converging."""
    return _metric("error_drift", current.value - previous.value)


# -- channels ---------------------------------------------------------------

def semantic_survival(task_rate: float, critical_rate: float,
                      transport_ok: bool, intent_verified: bool | None = None) -> Metric:
    """Transport capacity is not semantic capacity. 'verified' needs an explicit end-to-end
    intent check; below the critical task rate intent is 'lost' and never assumed."""
    if task_rate < critical_rate:
        state = "lost"
    elif transport_ok and intent_verified is True:
        state = "verified"
    else:
        state = "unverified"
    return _metric("semantic_survival", state, task_rate=task_rate, critical_rate=critical_rate,
                   transport_ok=transport_ok, intent_verified=intent_verified)


# -- bounded projection over an append-only durable store ---------------------

def _digest(items: Sequence[Any]) -> str:
    return hashlib.sha256(json.dumps(list(items), sort_keys=True, default=str).encode()).hexdigest()


def project(durable: Sequence[Any], budget: int,
            score: Callable[[Any], float]) -> Tuple[List[Any], Metric]:
    """W_t: the top-`budget` items by score, kept in durable (chronological) order.
    The durable store is read, never rewritten; its digest is returned to prove it."""
    before = _digest(durable)
    keep = set(sorted(range(len(durable)), key=lambda i: (-score(durable[i]), i))[:max(0, budget)])
    working = [durable[i] for i in sorted(keep)]
    assert _digest(durable) == before, "durable store must not change"
    return working, _metric("projection", {"kept": len(working), "of": len(durable),
                                           "durable_digest": before})


# -- provider/node swap -------------------------------------------------------

def swap_invariants(before: Mapping[str, Any], after: Mapping[str, Any]) -> Metric:
    """Violations when a provider/node swap changes identity, chronology, provenance or
    durable semantics. Expects keys: identity, events=[(id, ts)], provenance=[..], durable=[..]."""
    v: List[str] = []
    if before["identity"] != after["identity"]:
        v.append("identity changed")
    b, a = list(before["events"]), list(after["events"])
    if a[:len(b)] != b:
        v.append("chronology rewritten (existing positions changed)")
    if not set(before["provenance"]) <= set(after["provenance"]):
        v.append("provenance lost")
    if _digest(before["durable"]) != _digest(after["durable"][:len(before["durable"])]):
        v.append("durable semantics changed")
    return _metric("swap_invariant_violations", v)
