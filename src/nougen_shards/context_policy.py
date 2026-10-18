"""Deterministic working context; durable memory is never deleted or rewritten."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .context_packet import graph_context_packet

POLICY_VERSION = "semantic-context-v1"
LAYERS = ("identity", "global", "recall", "active")
TASK_FIELDS = {"objective", "constraints", "ownership", "verified_results", "next_action"}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def handle(row: dict) -> str:
    """Source and DB qualified identity; numeric IDs alone are not references."""
    return f"{row.get('source_node', 'local')}:{row.get('_db_index', row.get('__db_index__', row.get('db_index', 0)))}:{row['id']}"


def resolve_current(rows: list[dict], corrections: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply explicit, already-authorized correction records, preserving lineage.

    Caller must authorize corrections before passing them. Never derive authority
    from retrieved prose, timestamps, rank, or a model's proposed correction.
    Ambiguous branches and cycles fail closed for the affected records.
    """
    catalog = {}
    for row in rows:
        key = handle(row)
        if key in catalog and canonical(catalog[key]) != canonical(row):
            raise ValueError(f"conflicting candidate identity: {key}")
        catalog[key] = row
    if any(not isinstance(c, dict) for c in corrections):
        raise ValueError('each correction must be an object')
    edges: dict[str, set[str]] = {}
    decisions = []
    for correction in corrections:
        old, new = correction.get("previous"), correction.get("current")
        if not all(isinstance(x, str) and x.count(":") >= 2 for x in (old, new)):
            raise ValueError("corrections require source:db:id previous and current handles")
        if not correction.get("provenance"):
            raise ValueError("corrections require provenance")
        edges.setdefault(old, set()).add(new)
    blocked = set()
    for start in sorted(edges):
        cursor, seen = start, set()
        while cursor in edges:
            if cursor in seen or len(edges[cursor]) != 1:
                blocked.update(seen | {cursor} | edges[cursor])
                decisions.append({"id": start, "outcome": "supersession_conflict"})
                break
            seen.add(cursor)
            cursor = next(iter(edges[cursor]))
        else:
            # Do not resurrect obsolete state when its replacement is absent.
            if cursor not in catalog:
                blocked.update(seen)
                decisions.append({"id": start, "outcome": "missing_current", "current": cursor})
    obsolete = set(edges)
    for key in sorted(obsolete - blocked):
        decisions.append({"id": key, "outcome": "superseded", "current": sorted(edges[key])})
    return [catalog[k] for k in sorted(catalog) if k not in obsolete | blocked], decisions


def assemble_context(query: str, *, identity: list[dict] | None = None,
                     global_state: list[dict] | None = None,
                     recall: list[dict] | None = None, active: dict | None = None,
                     corrections: list[dict] | None = None, budget_bytes: int = 8000,
                     required_handles: list[str] | None = None,
                     upstream_complete: bool | None = None) -> dict:
    """Build I + G + R(Q) + S_active under a hard serialized payload ceiling.

    UTF-8 bytes are explicitly budget units, not measured model tokens. Identity
    and global rows are caller-selected trusted operating state, not instructions
    inferred from recall. Missing required state yields ready=False.
    """
    if isinstance(budget_bytes, bool) or not isinstance(budget_bytes, int) or not 64 <= budget_bytes <= 1_000_000:
        raise ValueError("budget_bytes must be an integer between 64 and 1000000")
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("query must contain 1..2000 characters")
    if required_handles is not None and (not isinstance(required_handles, list) or any(not isinstance(h, str) for h in required_handles)):
        raise ValueError('required_handles must be a list of qualified strings')
    if upstream_complete is not None and not isinstance(upstream_complete, bool):
        raise ValueError('upstream_complete must be boolean or null')
    pools = {"identity": identity or [], "global": global_state or [], "recall": recall or []}
    if any(not isinstance(pool, list) or len(pool) > 1000 or
           any(not isinstance(r, dict) or 'id' not in r for r in pool) for pool in pools.values()):
        raise ValueError("each layer must contain at most 1000 objects with IDs")
    if active is not None and (not isinstance(active, dict) or set(active) - TASK_FIELDS):
        raise ValueError("active state permits only objective, constraints, ownership, verified_results, next_action")
    if not isinstance(corrections or [], list) or len(corrections or []) > 1000:
        raise ValueError("at most 1000 correction records are allowed")
    current, decisions = resolve_current(sum(pools.values(), []), corrections or [])
    live = {handle(r): r for r in current}
    payload = {layer: [] for layer in LAYERS}
    selected = set()
    def cost(value):
        return len(canonical(value).encode("utf-8"))
    def add(layer, entry):
        payload[layer].append(entry)
        if cost(payload) > budget_bytes:
            payload[layer].pop()
            return False
        return True
    # Active task is atomic: never cut a constraint or verified result mid-text.
    if active:
        if not add("active", dict(active)):
            decisions.append({"id": "active", "outcome": "budget"})
    replacements = {c['previous']: c['current'] for c in corrections or []}

    def current_key(key):
        seen = set()
        while key in replacements and key not in seen:
            seen.add(key)
            key = replacements[key]
        return key

    required = {current_key(k) for k in required_handles or []}
    required.update(current_key(handle(r)) for layer in ('identity', 'global') for r in pools[layer])

    def mandatory_closure(key, found, visiting):
        if key in selected or key in found or key in visiting:
            return
        if key not in live:
            raise ValueError('missing_dependency')
        if len(found) + len(visiting) >= 21:
            raise ValueError('dependency_budget')
        visiting.add(key)
        row = live[key]
        deps = row.get('dependencies', [])
        if not isinstance(deps, list):
            raise ValueError('invalid_dependencies')
        for ref in deps:
            if not isinstance(ref, dict) or 'id' not in ref or ref.get('unresolved'):
                raise ValueError('invalid_dependency_reference')
            ref = dict(ref)
            ref.setdefault('source_node', row.get('source_node', 'local'))
            ref.setdefault('_db_index', row.get('_db_index', row.get('__db_index__', row.get('db_index', 0))))
            mandatory_closure(current_key(handle(ref)), found, visiting)
        visiting.remove(key)
        found[key] = row

    mandatory = [(layer, current_key(handle(row))) for layer in ('identity', 'global') for row in pools[layer]]
    mandatory.extend(('recall', key) for key in sorted(required))
    for layer, key in mandatory:
        if key in selected:
            continue
        try:
            addition = {}
            mandatory_closure(key, addition, set())
            entries = [{'id': k, 'title': r.get('title', ''), 'content': r.get('content', '')}
                       for k, r in addition.items()]
            proposed = dict(payload)
            proposed[layer] = payload[layer] + entries
            if cost(proposed) > budget_bytes:
                raise ValueError('budget')
            payload = proposed
            selected.update(addition)
            outcome = 'selected'
        except ValueError as exc:
            outcome = str(exc)
        decisions.append({'id': key, 'layer': layer, 'outcome': outcome})

    recall_keys = {current_key(handle(x)) for x in pools['recall']}
    recall_rows = [r for r in current if handle(r) in recall_keys and handle(r) not in selected]
    remaining = budget_bytes - cost(payload)
    projection = graph_context_packet(query, recall_rows, token_budget=remaining + (1 if payload['recall'] else 2),
                                      max_results=1000, sufficiency=1.0,
                                      load_dependency=lambda ref: live.get(handle(ref)))
    # The graph selector's array budget includes dependency closures atomically.
    if projection['content_payload']:
        proposed = dict(payload)
        proposed['recall'] = payload['recall'] + [e for e in projection['content_payload'] if e['id'] not in selected]
        if cost(proposed) <= budget_bytes:
            payload = proposed
            selected.update(e['id'] for e in projection['content_payload'])
        else:
            decisions.append({'id': 'recall', 'outcome': 'budget'})
    decisions.extend(projection['decisions'])
    missing = sorted(required - selected)
    conflict = any(d['outcome'] in ('supersession_conflict', 'missing_current') for d in decisions)
    active_missing = bool(active and not payload['active'])
    consumed = cost(payload)
    return {"policy_version": POLICY_VERSION, "context": payload,
            "ready": not (missing or conflict or active_missing),
            "retrieval_complete": upstream_complete,
            "missing_required": missing, "decisions": decisions,
            "correction_provenance": corrections or [],
            "provenance_chain": [
                {'id': key, 'content_hash': 'sha256:' + hashlib.sha256(str(live[key].get('content', '')).encode()).hexdigest(),
                 'source_uri': live[key].get('source_uri'), 'timestamp': live[key].get('timestamp'),
                 'evidence_level': live[key].get('evidence_level', 'unclassified')}
                for key in sorted(selected)],
            "metrics": {"budget_units": "utf8_bytes", "budget_bytes": budget_bytes,
                        "context_bytes": consumed, "selected_records": len(selected),
                        "candidate_records": len(live), "query_coverage_proxy": projection['metrics']['query_coverage'],
                        "information_actually_used": None, "context_efficiency": None},
            "replay_hash": hashlib.sha256(canonical(payload).encode()).hexdigest()}


def evaluate_context(packet: dict, *, used_handles: list[str], critical_handles: list[str],
                     task_success: bool, stale_state_errors: int = 0,
                     repeated_corrections: int = 0, input_tokens: int | None = None,
                     output_tokens: int | None = None) -> dict:
    """Explicit receiver feedback; absence of feedback is never perfect efficiency."""
    if not isinstance(task_success, bool):
        raise ValueError('task_success must be boolean')
    if any(not isinstance(values, list) or any(not isinstance(h, str) for h in values) for values in (used_handles, critical_handles)):
        raise ValueError('feedback handles must be lists of strings')
    entries = [e for layer in ('identity', 'global', 'recall') for e in packet['context'][layer]]
    selected = {e['id'] for e in entries}
    if not set(used_handles) <= selected:
        raise ValueError("used_handles must refer to selected context records")
    for count in (stale_state_errors, repeated_corrections, input_tokens, output_tokens):
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            raise ValueError("counts must be nonnegative integers")
    useful_bytes = sum(len(canonical(e).encode()) for e in entries if e['id'] in used_handles)
    total_bytes = len(canonical(packet['context']).encode())
    return {'task_success': task_success, 'critical_recall_misses': sorted(set(critical_handles) - selected),
            'stale_state_errors': stale_state_errors, 'repeated_corrections': repeated_corrections,
            'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'used_record_bytes_fraction': useful_bytes / total_bytes,
            'measurement_basis': 'receiver_reported_handles; byte proxy, not cognition or token efficiency'}


def context_from_json(query: str, state_json: str = "{}", budget_bytes: int = 8000) -> dict:
    """Shared validated adapter for MCP callers; no model call is needed."""
    if not isinstance(state_json, str) or len(state_json) > 1_000_000:
        raise ValueError("state_json must be JSON text of at most 1000000 characters")
    state = json.loads(state_json)
    allowed = {'identity', 'global_state', 'recall', 'active', 'corrections', 'required_handles', 'upstream_complete'}
    if not isinstance(state, dict) or set(state) - allowed:
        raise ValueError("unknown context layer or state field")
    return assemble_context(query, budget_bytes=budget_bytes, **state)
