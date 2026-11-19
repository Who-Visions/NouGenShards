"""Validated JSON adapters for the control-plane math and context-packet tools."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Tuple

from .context_packet import graph_context_packet
from .control_plane_math import adherence, route

OBJECTIVES = {
    "quality": "max",
    "truth": "max",
    "latency_ms": "min",
    "cost_usd": "min",
    "robustness": "max",
    "memory_fidelity": "max",
    "safety_score": "max",
}
POLICY_VERSION = "control-plane-v1"
_MAX_JSON_CHARS = 1_000_000


def _load_json(source: str, label: str) -> Any:
    if not isinstance(source, str) or len(source) > _MAX_JSON_CHARS:
        raise ValueError(f"{label} must be JSON text no longer than {_MAX_JSON_CHARS} characters")
    try:
        return json.loads(source)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc


def context_select(query: str, budget_bytes: int, nodes_json: str) -> Dict[str, Any]:
    """Select a bounded graph-aware projection from caller-supplied shard candidates."""
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("query must be non-empty text of at most 2000 characters")
    if isinstance(budget_bytes, bool) or not isinstance(budget_bytes, int) or not 0 <= budget_bytes <= 1_000_000:
        raise ValueError("budget_tokens must be an integer between 0 and 1000000 (UTF-8 byte budget)")
    nodes = _load_json(nodes_json, "nodes_json")
    if not isinstance(nodes, list) or len(nodes) > 1000:
        raise ValueError("nodes_json must be an array containing at most 1000 candidate nodes")
    if any(not isinstance(item, dict) or "id" not in item for item in nodes):
        raise ValueError("each context candidate must be an object with an id")
    return graph_context_packet(query, nodes, token_budget=budget_bytes,
                                policy_version="graph-context-v1")


def pareto_route(routes_json: str, policy_weights_json: str) -> Dict[str, Any]:
    """Route complete candidate profiles using caller-supplied objective weights."""
    candidates = _load_json(routes_json, "routes_json")
    weights = _load_json(policy_weights_json, "policy_weights_json")
    if not isinstance(candidates, list) or not candidates or len(candidates) > 1000:
        raise ValueError("routes_json must contain 1 to 1000 candidate profiles")
    if not isinstance(weights, dict) or set(weights) != set(OBJECTIVES):
        raise ValueError(f"policy_weights_json must provide exactly these objectives: {', '.join(OBJECTIVES)}")
    numeric_weights: Dict[str, float] = {}
    for name, value in weights.items():
        if isinstance(value, bool):
            raise ValueError(f"weight {name} must be a finite nonnegative number")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"weight {name} must be a finite nonnegative number") from exc
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"weight {name} must be a finite nonnegative number")
        numeric_weights[name] = number
    if not any(numeric_weights.values()):
        raise ValueError("at least one objective weight must be positive")

    checked: List[Dict[str, Any]] = []
    seen_ids = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str) or not candidate["id"]:
            raise ValueError(f"candidate {index} must have a non-empty string id")
        if candidate["id"] in seen_ids:
            raise ValueError(f"duplicate candidate id: {candidate['id']}")
        seen_ids.add(candidate["id"])
        row = {"id": candidate["id"]}
        for objective in OBJECTIVES:
            value = candidate.get(objective)
            if isinstance(value, bool):
                raise ValueError(f"candidate {candidate['id']} is missing finite objective {objective}")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"candidate {candidate['id']} is missing finite objective {objective}") from exc
            if not math.isfinite(number):
                raise ValueError(f"candidate {candidate['id']} has non-finite objective {objective}")
            row[objective] = number
        checked.append(row)

    result = route(checked, OBJECTIVES, numeric_weights, POLICY_VERSION)
    result["provenance"]["policy_digest"] = hashlib.sha256(
        json.dumps(numeric_weights, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return result


def _edges(source: str, label: str) -> List[Tuple[str, str]]:
    value = _load_json(source, label)
    if not isinstance(value, list) or len(value) > 10_000:
        raise ValueError(f"{label} must be an array containing at most 10000 edges")
    result = []
    for index, edge in enumerate(value):
        if (not isinstance(edge, list) or len(edge) != 2
                or any(not isinstance(part, str) or not part for part in edge)):
            raise ValueError(f"{label}[{index}] must be a [source, target] string pair")
        result.append((edge[0], edge[1]))
    return result


def adherence_evaluate(declared_edges_json: str, observed_events_json: str,
                       threshold: float = 0.8) -> Dict[str, Any]:
    """Evaluate declared-edge coverage and undeclared observed behavior separately."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("threshold must be a finite number between 0 and 1")
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be a finite number between 0 and 1")
    declared = _edges(declared_edges_json, "declared_edges_json")
    observed = _edges(observed_events_json, "observed_events_json")
    result = adherence(declared, observed)
    coverage = result["coverage"]
    result.update({
        "status": "unmeasured" if coverage is None else ("meets_threshold" if coverage >= threshold else "below_threshold"),
        "threshold": float(threshold),
        "policy_version": POLICY_VERSION,
        "input_digest": hashlib.sha256(json.dumps(
            {"declared": sorted(set(declared)), "observed": sorted(set(observed)), "threshold": threshold},
            sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest(),
    })
    return result
