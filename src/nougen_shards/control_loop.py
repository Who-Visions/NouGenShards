"""Control-loop checks: intent alignment, projection, stale policy, destiny
readiness, post-run learning.

Pure functions over data the grid already produces (claims, tool health,
destiny rows, recall envelopes). Nothing here writes to a vault, a destiny
store or a relay; every function returns a verdict plus the evidence it
stands on, and callers decide what to do with it.

Design notes
------------
The shapes were borrowed from a commercial self-development course used only
as a process donor. Its psychological
and physical claims are the author's assertions and are not relied on here.
What survives is plain control engineering:

* stated intent vs the state that actually executes a task can disagree;
* any observation is a filtered view and should say which filters applied;
* an old rule can outlive the context that justified it;
* a goal without a verification procedure is not ready to pursue;
* both failures and successes are worth a bounded look afterwards.

No new control plane: statuses reuse ``status_semantics`` vocabulary, recall
input is a ``ReconstructionEnvelope.to_dict()`` (or any dict with the same
coverage keys), and destiny input is a ``destiny.get_destiny()`` row.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

log = logging.getLogger(__name__)

_logged_fallbacks: set = set()


def _env_num(name: str, fallback: float, cast=float):
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            return cast(raw)
        except ValueError:
            log.warning("control_loop: bad %s=%r, using fallback %r", name, raw, fallback)
            return fallback
    if name not in _logged_fallbacks:
        _logged_fallbacks.add(name)
        log.info("control_loop: %s unset, fallback %r", name, fallback)
    return fallback


def _cfg() -> Dict[str, float]:
    """Resolve every threshold at call time so env changes take effect."""
    try:
        from .status_semantics import DEFAULT_MAX_AGE_S as status_age
    except Exception:  # pragma: no cover - module always ships alongside
        status_age = 300.0
    return {
        "health_max_age_s": _env_num("NOUGEN_CONTROL_HEALTH_MAX_AGE_S", status_age),
        "policy_max_age_days": _env_num("NOUGEN_POLICY_MAX_AGE_DAYS", 180.0),
        "coverage_warn": _env_num("NOUGEN_PROJECTION_COVERAGE_WARN", 0.8),
        "coverage_high": _env_num("NOUGEN_PROJECTION_COVERAGE_HIGH_RISK", 0.5),
        "freshness_warn_s": _env_num("NOUGEN_PROJECTION_FRESHNESS_WARN_S", 3600.0),
        "learning_max_items": _env_num("NOUGEN_LEARNING_MAX_ITEMS", 5, int),
        "priority_inversion_margin": _env_num("NOUGEN_PRIORITY_INVERSION_MARGIN", 0.10),
    }


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# 1. Intent alignment: stated goal vs execution plane
# --------------------------------------------------------------------------
ALIGNED, CONFLICTED, UNKNOWN = "ALIGNED", "CONFLICTED", "UNKNOWN"


def _health(execution: dict, node: str, now: datetime, max_age: float) -> str:
    h = (execution.get("tool_health") or {}).get(node)
    if not h:
        return "UNKNOWN"
    ts = _parse_ts(h.get("observed_utc"))
    if ts is None or (now - ts).total_seconds() > max_age:
        return "UNKNOWN"  # stale evidence is not evidence of failure either
    return str(h.get("status", "UNKNOWN")).upper()


def intent_alignment_check(goal: dict, execution: dict, *,
                           now: Optional[datetime] = None) -> dict:
    """Compare a task contract with the state that will actually run it.

    ``goal``: ``task_id``, ``actor``, ``constraints`` (``dynamic_failover``,
    ``preserve_canon``, ``token_budget``, ``no_duplicate``) and optional
    ``priorities`` (ordered list).
    ``execution``: ``provider_affinity``, ``tool_health``, ``branch_claims``,
    ``leases``, ``claims``, ``revealed_share`` - each item may carry ``source``.

    A missing premise yields UNKNOWN, never ALIGNED.
    """
    cfg = _cfg()
    now = _now(now)
    cons = goal.get("constraints") or {}
    conflicts: List[dict] = []
    unknowns: List[dict] = []

    if cons.get("dynamic_failover"):
        aff = execution.get("provider_affinity")
        if aff is None:
            unknowns.append({"check": "provider_affinity", "why": "affinity state not observed"})
        elif aff.get("pinned"):
            status = _health(execution, aff["pinned"], now, cfg["health_max_age_s"])
            if status == "RED":
                conflicts.append({
                    "check": "provider_affinity",
                    "evidence": f"pinned to {aff['pinned']} which is RED",
                    "source": aff.get("source"),
                    "repair": f"clear affinity pin on {aff['pinned']}; let failover pick a GREEN node",
                    "reversible": True})
            elif status == "UNKNOWN":
                unknowns.append({"check": "provider_affinity",
                                 "why": f"no fresh health for pinned {aff['pinned']}"})

    if cons.get("preserve_canon"):
        stale = [c for c in execution.get("branch_claims") or []
                 if str(c.get("state", "")).lower() in {"draft", "stale", "superseded"}]
        for c in stale:
            conflicts.append({
                "check": "canon_state",
                "evidence": f"branch claim {c.get('id')} is {c.get('state')}",
                "source": c.get("source"),
                "repair": f"exclude {c.get('id')} from active context or amend with provenance",
                "reversible": True})

    budget = cons.get("token_budget")
    if budget is not None:
        leases = execution.get("leases")
        if leases is None:
            unknowns.append({"check": "lease_budget", "why": "lease state not observed"})
        for lease in leases or []:
            cap = lease.get("token_cap")
            if cap is None or cap > budget:
                conflicts.append({
                    "check": "lease_budget",
                    "evidence": f"lease {lease.get('id')} cap={cap} exceeds budget {budget}",
                    "source": lease.get("source"),
                    "repair": f"cap lease {lease.get('id')} at {budget} tokens",
                    "reversible": True})

    if cons.get("no_duplicate"):
        claims = execution.get("claims")
        if claims is None:
            unknowns.append({"check": "duplicate_claim", "why": "claim registry not read"})
        for c in claims or []:
            exp = _parse_ts(c.get("expires_utc"))
            live = exp is None or exp > now
            if live and c.get("task_id") == goal.get("task_id") and c.get("owner") != goal.get("actor"):
                conflicts.append({
                    "check": "duplicate_claim",
                    "evidence": f"task {c.get('task_id')} already claimed by {c.get('owner')}",
                    "source": c.get("source"),
                    "repair": f"coordinate with {c.get('owner')} before acting",
                    "reversible": False})

    inversions = priority_inversions(goal.get("priorities") or [],
                                     execution.get("revealed_share") or {},
                                     margin=cfg["priority_inversion_margin"])
    for inv in inversions:
        conflicts.append({"check": "priority_inversion", "evidence": inv["evidence"],
                          "source": "revealed_share", "repair": inv["repair"],
                          "reversible": True})

    verdict = CONFLICTED if conflicts else (UNKNOWN if unknowns else ALIGNED)
    return {
        "verdict": verdict,
        "conflicts": conflicts,
        "unknowns": unknowns,
        "cheapest_repair": next((c["repair"] for c in conflicts if c["reversible"]),
                                conflicts[0]["repair"] if conflicts else None),
        "requires_confirmation": any(not c["reversible"] for c in conflicts),
        "action_mode": _conflict_action_mode(),
        "auto_apply": False,
    }


def _conflict_action_mode() -> str:
    """``NOUGEN_CONFLICT_ACTION``: only ``report`` is supported. Any other value is
    logged and ignored; this module never acts on a conflict by itself."""
    raw = os.environ.get("NOUGEN_CONFLICT_ACTION", "").strip().lower()
    if raw and raw != "report":
        log.warning("control_loop: NOUGEN_CONFLICT_ACTION=%r unsupported, report only", raw)
    return "report"


def priority_inversions(declared: Sequence[str], revealed: Dict[str, float], *,
                        margin: float) -> List[dict]:
    """Declared rank vs where effort actually went (e.g. token share).

    Flags a pair when a lower-ranked priority received more share than a
    higher-ranked one by more than ``margin``. Unobserved priorities are
    skipped rather than assumed zero.
    """
    out = []
    ranked = [p for p in declared if p in revealed]
    for i, hi in enumerate(ranked):
        for lo in ranked[i + 1:]:
            if revealed[lo] - revealed[hi] > margin:
                out.append({"evidence": f"'{lo}' (rank {declared.index(lo) + 1}) got "
                                        f"{revealed[lo]:.2f} vs '{hi}' (rank {declared.index(hi) + 1}) "
                                        f"{revealed[hi]:.2f}",
                            "repair": f"rebalance toward '{hi}' or re-rank priorities explicitly"})
    return out


# --------------------------------------------------------------------------
# 2. Projection envelope: what this answer could and could not see
# --------------------------------------------------------------------------
def projection_envelope(recall: dict, *, filters_applied: Iterable[str] = (),
                        assumptions: Iterable[str] = (),
                        observed_utc: Optional[str] = None,
                        now: Optional[datetime] = None) -> dict:
    """Annotate an existing recall payload; does not redefine its fields.

    Reads ``vault_coverage`` (``total``/``reachable``/``failed``) the way
    ``ReconstructionEnvelope`` emits it. Absent coverage -> risk ``high`` and
    ``complete`` False: an unmeasured view is never presented as the world.
    """
    cfg = _cfg()
    cov = recall.get("vault_coverage") or {}
    total, reachable = cov.get("total"), cov.get("reachable")
    failed = dict(cov.get("failed") or {})
    coverage = (reachable / total) if total else None

    ts = _parse_ts(observed_utc)
    freshness_s = (_now(now) - ts).total_seconds() if ts else None

    reasons = []
    if coverage is None:
        risk = "high"
        reasons.append("coverage not measured")
    elif coverage < cfg["coverage_high"]:
        risk = "high"
        reasons.append(f"coverage {coverage:.2f} < {cfg['coverage_high']}")
    elif coverage < cfg["coverage_warn"]:
        risk = "medium"
        reasons.append(f"coverage {coverage:.2f} < {cfg['coverage_warn']}")
    else:
        risk = "low"
    if freshness_s is None:
        reasons.append("observation time unknown")
        risk = "high" if risk == "high" else "medium"
    elif freshness_s > cfg["freshness_warn_s"]:
        reasons.append(f"observation {int(freshness_s)}s old")
        risk = "high" if risk == "high" else "medium"
    if recall.get("absence_proven") is False and not recall.get("candidate_sources"):
        reasons.append("empty result without proven absence")
        risk = "high"

    return {
        "observed_sources": reachable if reachable is not None else 0,
        "unavailable_sources": sorted(failed),
        "filters_applied": list(filters_applied),
        "freshness_s": freshness_s,
        "coverage": None if coverage is None else round(coverage, 4),
        "assumptions": list(assumptions),
        "projection_risk": risk,
        "risk_reasons": reasons,
        "complete": risk == "low",
    }


# --------------------------------------------------------------------------
# 3. Stale-policy pressure test
# --------------------------------------------------------------------------
POLICY_VERDICTS = ("still_valid", "context_bound", "superseded", "contradicted",
                   "insufficient_evidence")


def policy_pressure_test(policy: dict, evidence: Sequence[dict], *,
                         dependents: Sequence[str] = (),
                         now: Optional[datetime] = None) -> dict:
    """Is a rule still earning its place?

    ``policy``: ``id``, ``value``, ``context`` (dict of premises that held when
    it was set), ``set_utc``, optional ``superseded_by``.
    ``evidence``: observations ``{"premise", "observed", "observed_utc", "source"}``.

    Order: superseded > contradicted > context_bound > still_valid >
    insufficient_evidence. Never deletes; ``migration`` is a suggestion.
    """
    cfg = _cfg()
    now = _now(now)
    pid = policy.get("id")
    base = {"policy_id": pid, "dependents": list(dependents)}

    if policy.get("superseded_by"):
        return {**base, "verdict": "superseded", "evidence": [],
                "migration": f"point dependents at {policy['superseded_by']}; keep {pid} as history"}

    premises = policy.get("context") or {}
    checked, contradictions = [], []
    for ev in evidence:
        key = ev.get("premise")
        if key not in premises:
            continue
        checked.append(ev)
        if ev.get("observed") != premises[key]:
            contradictions.append(ev)

    if contradictions:
        return {**base, "verdict": "contradicted", "evidence": contradictions,
                "migration": "amend policy from live observation; supersede with provenance, "
                             "do not delete the old row"}

    set_ts = _parse_ts(policy.get("set_utc"))
    age_days = (now - set_ts).total_seconds() / 86400 if set_ts else None
    unverified = [k for k in premises if k not in {e.get("premise") for e in checked}]

    if premises and not checked:
        if age_days is not None and age_days > cfg["policy_max_age_days"]:
            return {**base, "verdict": "context_bound", "evidence": [],
                    "age_days": round(age_days, 1), "unverified_premises": unverified,
                    "migration": "probe the premises before relying on this policy"}
        return {**base, "verdict": "insufficient_evidence", "evidence": [],
                "unverified_premises": unverified,
                "migration": "probe the premises; do not act on the policy as fact"}

    if not premises:
        return {**base, "verdict": "insufficient_evidence", "evidence": [],
                "migration": "record the context this policy assumed"}

    if unverified:
        return {**base, "verdict": "context_bound", "evidence": checked,
                "unverified_premises": unverified,
                "migration": "probe remaining premises"}
    return {**base, "verdict": "still_valid", "evidence": checked, "migration": None}


# --------------------------------------------------------------------------
# 4. Destiny readiness (validator over a destiny row; no schema change)
# --------------------------------------------------------------------------
_DESTINY_REQUIRED = ("goal", "verification", "deadline", "required_events")
_DESTINY_ADVISED = ("forbidden_outcomes", "trigger")


def destiny_readiness(destiny: dict, *, first_action: Optional[str] = None,
                      environment: Optional[dict] = None) -> dict:
    """Decide/commit/act/focus/environment checklist over a destiny row.

    A destiny with no verification procedure is never ready: a goal that
    cannot be checked cannot be distinguished from a wish.
    """
    missing = [f for f in _DESTINY_REQUIRED if not destiny.get(f)]
    advised = [f for f in _DESTINY_ADVISED if not destiny.get(f)]
    links = destiny.get("links") or []
    env = environment or {}
    checklist = {
        "decide": bool(destiny.get("goal")) and bool(destiny.get("verification")),
        "commit": any(link.get("kind") == "agent" for link in links),
        "act": bool(first_action),
        "focus": destiny.get("status") in {"active", "dormant"} and not destiny.get("superseded_by"),
        "environment": (all(str(v).upper() == "GREEN" for v in env.values()) if env else None),
    }
    blockers = list(missing)
    blockers += [k for k, v in checklist.items() if v is False]
    if checklist["environment"] is None:
        blockers.append("environment_unobserved")
    return {"ready": not blockers, "missing_fields": missing, "advised_fields": advised,
            "checklist": checklist, "blockers": blockers}


# --------------------------------------------------------------------------
# 5. Bounded post-run learning hook
# --------------------------------------------------------------------------
def post_run_learning(run: dict) -> dict:
    """Suggest what to keep from a finished run. Writes nothing.

    ``run``: ``outcome`` (``success``/``failure``), ``steps`` (each with
    ``name``, ``ok``, optional ``shard_refs``, ``error_type``, ``verified``).
    Success recipes are proposed only from verified steps. ``NOUGEN_LEARNING_HOOK``
    (``verified`` default / ``all`` / ``off``) gates which runs are read at all:
    by default only runs carrying ``verified: True``.
    """
    cap = int(_cfg()["learning_max_items"])
    hook = os.environ.get("NOUGEN_LEARNING_HOOK", "").strip().lower() or "verified"
    if hook not in ("verified", "all", "off"):
        log.warning("control_loop: unknown NOUGEN_LEARNING_HOOK=%r, using verified", hook)
        hook = "verified"
    if hook == "off" or (hook == "verified" and not run.get("verified")):
        return {"outcome": run.get("outcome"), "items": [], "truncated": False,
                "cap": cap, "skipped": f"hook={hook}"}
    steps = run.get("steps") or []
    items: List[dict] = []
    if run.get("outcome") == "failure":
        for s in steps:
            if not s.get("ok"):
                items.append({"kind": "failure_class", "step": s.get("name"),
                              "class": s.get("error_type") or "unclassified",
                              "next_evidence": f"reproduce '{s.get('name')}' in isolation"})
    elif run.get("outcome") == "success":
        verified = [s for s in steps if s.get("ok") and s.get("verified")]
        for s in verified:
            for ref in s.get("shard_refs") or []:
                items.append({"kind": "mark_useful", "shard": ref, "step": s.get("name")})
        if verified:
            items.append({"kind": "recipe_candidate",
                          "steps": [s.get("name") for s in verified],
                          "note": "verified steps only; confirm before saving"})
    truncated = len(items) > cap
    return {"outcome": run.get("outcome"), "items": items[:cap],
            "truncated": truncated, "cap": cap}
