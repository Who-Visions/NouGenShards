"""Capability- and policy-aware provider scheduler, with Hugging Face as a
provider-of-providers.

One registry (canon/provider_registry.json, env NOUGEN_PROVIDER_REGISTRY),
one score function, one decision envelope with reason codes and the layered
identity fields the legs demand (role, harness, inference_fabric, model,
downstream_provider, routing_policy, toolset, account, lane, machine), and one
optional provenance shard per decision. The existing routers (agents.run_agent,
rhea_noir._chat, shadow_xoah._chat) keep working; this is additive and opt-in.

Hard rules (legs 234016Z / 234426Z):
  * policy_unknown -> no quota pooling, ever: a provider whose policy is not
    verified is never combined across accounts;
  * an HF credit budget that is unknown or spent scores the HF lane to zero and
    the decision names the swap (DEGRADE_SWAP); throughput degrades, nothing
    else does;
  * every decision carries reason codes; nothing routes silently.

Env: NOUGEN_PROVIDER_REGISTRY, NOUGEN_HF_CREDIT_BUDGET_USD, NOUGEN_HF_CREDITS_SPENT_USD,
NOUGEN_SCHEDULER_MACHINE, NOUGEN_SCHEDULER_PROVENANCE (1 = capture a shard per decision),
NOUGEN_HF_CATALOG_TTL_S.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LATENCY_SCORE = {"fast": 1.0, "medium": 0.6, "slow": 0.2}
COST_SCORE = {"free": 1.0, "credits": 0.6, "paid": 0.2}
QUOTA_SCORE = {"unlimited-local": 1.0, "daily-per-account": 0.7, "50-per-day": 0.5, "monthly-credits": 0.5, "subscription": 0.8}


def registry_path() -> Path:
    raw = os.environ.get("NOUGEN_PROVIDER_REGISTRY", "").strip()
    return Path(raw) if raw else Path(__file__).resolve().parent / "canon" / "provider_registry.json"


def load_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path) if path else registry_path()
    reg = json.loads(p.read_text(encoding="utf-8"))
    for prov in reg.get("providers", []):
        prov.setdefault("policy", {})
        prov.setdefault("tags", [])
        prov.setdefault("models", [])
    return reg


# --------------------------------------------------------------------------- #
# HF catalog adapter (provider-of-providers)
# --------------------------------------------------------------------------- #
def hf_catalog_path() -> Path:
    from . import core
    return Path(core.GLOBAL_DIR) / "hf_catalog.json"


def _hf_token() -> Optional[str]:
    for k in ("HF_TOKEN", "HUGGINGFACE_API_KEY", "NGS_INFERENCE_TOKEN"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    try:
        from . import keymaker
        for k in ("HF_TOKEN", "HUGGINGFACE_API_KEY", "NGS_INFERENCE_TOKEN"):
            v = keymaker.get_secret(k)
            if v:
                return v
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("keymaker unavailable for HF token: %s", exc)
    return None


def normalize_hf_catalog(raw: Any) -> List[Dict[str, Any]]:
    """GET /v1/models -> [{model, providers:[{provider, status, context, price_in, price_out,
    is_free, tools, structured, latency_ms}], modalities}]. Nothing invented: missing
    fields stay None."""
    data = raw.get("data", raw) if isinstance(raw, dict) else raw
    out = []
    for m in data or []:
        if not isinstance(m, dict):
            continue
        provs = []
        for p in m.get("providers") or []:
            if not isinstance(p, dict):
                continue
            pricing = p.get("pricing") or {}
            provs.append({"provider": p.get("provider"), "status": p.get("status"),
                          "context": p.get("context_length"), "price_in": pricing.get("input"), "price_out": pricing.get("output"),
                          "is_free": bool(p.get("is_free")), "tools": bool(p.get("supports_tools")),
                          "structured": bool(p.get("supports_structured_output")), "latency_ms": p.get("first_token_latency_ms")})
        arch = m.get("architecture") or {}
        out.append({"model": m.get("id"), "owner": m.get("owned_by"), "providers": provs,
                    "input": arch.get("input_modalities") or [], "output": arch.get("output_modalities") or []})
    return out


def fetch_hf_catalog(*, ttl_s: Optional[float] = None, force: bool = False) -> Dict[str, Any]:
    """Cached read of the HF router catalog. Returns {"fetched_utc", "source", "models": [...]}.
    Without a token or network the cache (or an empty catalog) is returned and the
    decision will say so; the scheduler never invents a provider."""
    ttl = float(os.environ.get("NOUGEN_HF_CATALOG_TTL_S", "3600")) if ttl_s is None else ttl_s
    path = hf_catalog_path()
    if not force and path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # pylint: disable=broad-except
            pass
    tok = _hf_token()
    if not tok:
        return {"fetched_utc": None, "source": "none: no HF token", "models": []}
    import urllib.request
    req = urllib.request.Request(os.environ.get("NOUGEN_HF_CATALOG_URL", "https://router.huggingface.co/v1/models"),
                                 headers={"Authorization": "Bearer " + tok, "User-Agent": "nougen-scheduler/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("NOUGEN_HF_CATALOG_TIMEOUT_S", "25"))) as r:
            raw = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("HF catalog fetch failed: %s", exc)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # pylint: disable=broad-except
                pass
        return {"fetched_utc": None, "source": f"error: {type(exc).__name__}", "models": []}
    cat = {"fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "router.huggingface.co/v1/models",
           "models": normalize_hf_catalog(raw)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cat), encoding="utf-8")
    except Exception:  # pylint: disable=broad-except
        pass
    return cat


def hf_pick(catalog: Dict[str, Any], *, policy: str = "cheapest", need_tools: bool = False,
            need_structured: bool = False, min_context: int = 0, pinned: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Choose a model+downstream provider from the catalog under :fastest / :cheapest /
    :preferred(pinned) policies. Only live providers; only what the catalog states."""
    best, best_key = None, None
    for m in catalog.get("models", []):
        if pinned and m.get("model") != pinned and not (m.get("model") or "").endswith("/" + pinned):
            continue
        if "text" not in (m.get("output") or ["text"]):
            continue
        for p in m.get("providers", []):
            if p.get("status") != "live":
                continue
            if need_tools and not p.get("tools"):
                continue
            if need_structured and not p.get("structured"):
                continue
            if min_context and (p.get("context") or 0) < min_context:
                continue
            known = p.get("price_in") is not None and p.get("price_out") is not None
            # an unknown price is never "cheapest": it sorts behind every known one
            price = (p["price_in"] + p["price_out"]) if known else 1e9
            lat = p.get("latency_ms") if p.get("latency_ms") is not None else 1e9
            if policy == "fastest":
                key = (lat, price)
            else:  # cheapest / preferred fall back to price
                key = (0 if p.get("is_free") else 1, price, lat)
            if best_key is None or key < best_key:
                best, best_key = {"model": m["model"], "downstream_provider": p["provider"], "price_in": p.get("price_in"),
                                  "price_out": p.get("price_out"), "is_free": p.get("is_free"), "latency_ms": p.get("latency_ms"),
                                  "context": p.get("context"), "routing_policy": f":{policy}" if not pinned else "pinned"}, key
    return best


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
def hf_credits_ok() -> Dict[str, Any]:
    """Credit budget check for the HF lane. Unknown spend = not ok (the leg's
    'policy_unknown => no pooling' spirit applied to money)."""
    budget = os.environ.get("NOUGEN_HF_CREDIT_BUDGET_USD", "").strip()
    spent = os.environ.get("NOUGEN_HF_CREDITS_SPENT_USD", "").strip()
    if not budget:
        return {"ok": False, "reason": "CREDIT_BUDGET", "detail": "NOUGEN_HF_CREDIT_BUDGET_USD unset"}
    try:
        b = float(budget); s = float(spent) if spent else 0.0
    except ValueError:
        return {"ok": False, "reason": "CREDIT_BUDGET", "detail": "budget/spent not numeric"}
    if s >= b:
        return {"ok": False, "reason": "QUOTA_EXHAUSTED", "detail": f"spent {s:.2f} >= budget {b:.2f}"}
    return {"ok": True, "reason": None, "detail": f"spent {s:.2f} of {b:.2f}"}


def score_provider(prov: Dict[str, Any], role: Dict[str, Any], weights: Dict[str, float], *,
                   last_lane: Optional[str] = None, unavailable: Optional[set] = None) -> Dict[str, Any]:
    reasons: List[str] = []
    needs = set(role.get("needs", []))
    caps = set(prov.get("capabilities", []))
    if not needs <= caps:
        return {"eligible": False, "score": 0.0, "reasons": ["CAP_MISS"], "missing": sorted(needs - caps)}
    pol = prov.get("policy", {})
    if pol.get("multi_account_pooling") and not pol.get("policy_verified"):
        return {"eligible": False, "score": 0.0, "reasons": ["POLICY_BLOCK"], "missing": []}
    if unavailable and prov["lane"] in unavailable:
        return {"eligible": False, "score": 0.0, "reasons": ["QUOTA_EXHAUSTED"], "missing": []}
    if prov.get("cost_class") == "credits":
        cr = hf_credits_ok()
        if not cr["ok"]:
            return {"eligible": False, "score": 0.0, "reasons": [cr["reason"]], "missing": [], "detail": cr["detail"]}
    s = weights.get("capability", 3.0) * (len(caps & needs) / max(1, len(needs)))
    s += weights.get("latency", 1.0) * LATENCY_SCORE.get(prov.get("latency_class"), 0.5)
    s += weights.get("cost", 2.0) * COST_SCORE.get(prov.get("cost_class"), 0.5)
    s += weights.get("quota", 2.0) * QUOTA_SCORE.get(prov.get("quota_class"), 0.5)
    s += weights.get("reliability", 1.5) * float(prov.get("reliability", 0.5))
    s += weights.get("eval", 2.0) * float(prov.get("eval_score", 0.5))
    prefs = set(role.get("prefers", []))
    matched = prefs & set(prov.get("tags", []))
    if matched:
        s += 1.0 * len(matched)
        reasons.append("PREFERENCE")
    if last_lane and prov["lane"] == last_lane:
        s += weights.get("cache_affinity", 1.0)
        reasons.append("CACHE_AFFINITY")
    return {"eligible": True, "score": round(s, 3), "reasons": reasons, "missing": []}


# --------------------------------------------------------------------------- #
# the decision
# --------------------------------------------------------------------------- #
def classify_role(task: str, registry: Dict[str, Any], hint: Optional[str] = None) -> str:
    roles = registry.get("roles", {})
    if hint and hint in roles:
        return hint
    low = (task or "").lower()
    if "privileged" in roles and any(w in low for w in ("permission", "credential", "secret", "billing", "production deploy",
                                                          "deploy to production", "schema migration", "grant access", "acl")):
        return "privileged"
    if any(w in low for w in ("embed", "vector", "similarity")):
        return "embed"
    if any(w in low for w in ("image", "photo", "screenshot", "vision")):
        return "vision"
    if any(w in low for w in ("war-game", "wargame", "architecture", "design the")):
        return "wargame"
    if any(w in low for w in ("review", "audit the diff", "code review")):
        return "code_review"
    if any(w in low for w in ("judge", "score", "grade", "rank")):
        return "judge"
    if any(w in low for w in ("call the tool", "use tools", "mcp", "agent")):
        return "tool_agent"
    if any(w in low for w in ("summar", "digest", "tl;dr")):
        return "summarize"
    if any(w in low for w in ("triage", "classify", "label")):
        return "triage"
    if "recon" in roles and any(w in low for w in ("dig through", "grep", "log", "distill", "recon", "inspect", "search the", "find where")):
        return "recon"
    return "bulk_draft"


# --------------------------------------------------------------------------- #
# coach mode: Rule 0.0 inside the router
# --------------------------------------------------------------------------- #
def coach_enabled(registry: Dict[str, Any]) -> bool:
    """NOUGEN_COACH_MODE=0/1 wins; otherwise the registry's coach_mode.enabled."""
    raw = os.environ.get("NOUGEN_COACH_MODE", "").strip()
    if raw in ("0", "1"):
        return raw == "1"
    return bool(registry.get("coach_mode", {}).get("enabled"))


def coach_tier(role_name: str, registry: Dict[str, Any]) -> Optional[str]:
    tiers = registry.get("coach_mode", {}).get("tiers", {})
    for tier, roles in tiers.items():
        if role_name in roles:
            return tier
    return None


def apply_coach_policy(scored: List[Dict[str, Any]], tier: Optional[str], registry: Dict[str, Any], *,
                       escalate: Optional[str] = None) -> List[Dict[str, Any]]:
    """Mutate the candidate table per tier. delegable: judgment lanes drop out
    (COACH_DELEGATE) unless `escalate` names why the free lanes failed
    (COACH_ESCALATE). privileged: everything but judgment lanes drops out
    (COACH_PRIVILEGED). judgment: judgment lanes get the bonus (COACH_JUDGMENT),
    free lanes stay eligible for second opinions."""
    cm = registry.get("coach_mode", {})
    judgment_lanes = set(cm.get("judgment_lanes", []))
    bonus = float(cm.get("judgment_bonus", 2.0))
    for s in scored:
        is_judgment_lane = s["lane"] in judgment_lanes
        if not s["eligible"]:
            continue
        if tier == "delegable" and is_judgment_lane:
            if escalate:
                s["reasons"] = s["reasons"] + ["COACH_ESCALATE"]
            else:
                s.update({"eligible": False, "score": 0.0, "reasons": ["COACH_DELEGATE"]})
        elif tier == "privileged" and not is_judgment_lane:
            s.update({"eligible": False, "score": 0.0, "reasons": ["COACH_PRIVILEGED"]})
        elif tier == "judgment" and is_judgment_lane:
            s["score"] = round(s["score"] + bonus, 3)
            s["reasons"] = s["reasons"] + ["COACH_JUDGMENT"]
    return scored


def routing_log_path() -> Optional[Path]:
    raw = os.environ.get("NOUGEN_ROUTING_LOG", "").strip()
    if raw == "0":
        return None
    return Path(raw) if raw else Path.home() / ".nougen" / "state" / "routing_decisions.jsonl"


def _est_tokens(text: str) -> int:
    return len(text or "") // 4 + 1


def log_decision(decision: Dict[str, Any], task: str, registry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Append one JSONL line per decision: provider chosen, reason, fallback
    reason, and the cloud tokens the free lane saved (an estimate, and labelled
    as one until lane responses report real counts). Never the task text."""
    path = routing_log_path()
    if path is None:
        return None
    cm = registry.get("coach_mode", {})
    judgment_lanes = set(cm.get("judgment_lanes", []))
    est_out_table = cm.get("est_output_tokens", {})
    est_out = int(est_out_table.get(decision.get("role"), est_out_table.get("default", _env_int("NOUGEN_EST_OUTPUT_TOKENS", 600))))
    est_in = _est_tokens(task)
    on_free_lane = bool(decision.get("lane")) and decision["lane"] not in judgment_lanes
    row = {
        "decided_utc": decision.get("decided_utc"), "task_sha12": hashlib.sha256((task or "").encode("utf-8")).hexdigest()[:12],
        "harness": decision.get("harness"), "role": decision.get("role"), "tier": decision.get("tier"),
        "lane": decision.get("lane"), "model": decision.get("model"), "reason_codes": decision.get("reason_codes", []),
        "fallback_reason": decision.get("fallback_reason"), "escalate_required": decision.get("escalate_required", False),
        "est_input_tokens": est_in, "est_output_tokens": est_out,
        "cloud_tokens_avoided_est": (est_in + est_out) if on_free_lane else 0,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        return None
    return row


def coach_report(path: Optional[Path] = None, last_n: Optional[int] = None) -> Dict[str, Any]:
    """Roll the decision log up: decisions per lane and tier, escalations, and
    the estimated cloud tokens the free lanes absorbed."""
    p = path or routing_log_path()
    rows: List[Dict[str, Any]] = []
    if p and p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    if last_n:
        rows = rows[-last_n:]
    by_lane: Dict[str, int] = {}
    by_tier: Dict[str, int] = {}
    for r in rows:
        by_lane[str(r.get("lane"))] = by_lane.get(str(r.get("lane")), 0) + 1
        by_tier[str(r.get("tier"))] = by_tier.get(str(r.get("tier")), 0) + 1
    return {"log": str(p) if p else None, "decisions": len(rows), "by_lane": by_lane, "by_tier": by_tier,
            "escalations": sum(1 for r in rows if r.get("fallback_reason")),
            "escalate_required": sum(1 for r in rows if r.get("escalate_required")),
            "cloud_tokens_avoided_est": sum(int(r.get("cloud_tokens_avoided_est") or 0) for r in rows),
            "first_utc": rows[0].get("decided_utc") if rows else None, "last_utc": rows[-1].get("decided_utc") if rows else None}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def route(task: str, *, role: Optional[str] = None, harness: str = "unknown", toolset: Optional[List[str]] = None,
          pinned_lane: Optional[str] = None, pinned_model: Optional[str] = None, hf_policy: str = "cheapest",
          last_lane: Optional[str] = None, unavailable: Optional[List[str]] = None,
          registry: Optional[Dict[str, Any]] = None, catalog: Optional[Dict[str, Any]] = None,
          provenance: Optional[bool] = None, coach_mode: Optional[bool] = None,
          escalate: Optional[str] = None) -> Dict[str, Any]:
    """Classify, score, decide. Returns the decision envelope with reason codes
    and every identity layer named; optionally captures a provenance shard.
    coach_mode (default: env NOUGEN_COACH_MODE, else registry) applies the
    tier policy; `escalate` is the caller's reason a delegable task may reach a
    judgment lane (free lanes failed a quality gate, quota, or were down)."""
    reg = registry or load_registry()
    role_name = classify_role(task, reg, role)
    role_spec = reg["roles"].get(role_name, {"needs": ["text"], "prefers": []})
    weights = reg.get("weights", {})
    unavailable_set = set(unavailable or [])
    scored = []
    for prov in reg["providers"]:
        sc = score_provider(prov, role_spec, weights, last_lane=last_lane, unavailable=unavailable_set)
        scored.append({"lane": prov["lane"], **sc})
    coach_on = coach_enabled(reg) if coach_mode is None else bool(coach_mode)
    tier = coach_tier(role_name, reg) if coach_on else None
    if coach_on:
        apply_coach_policy(scored, tier, reg, escalate=escalate)
    eligible = [s for s in scored if s["eligible"]]
    reasons: List[str] = []
    chosen = None
    if pinned_lane:
        chosen = next((s for s in eligible if s["lane"] == pinned_lane), None)
        if chosen:
            reasons.append("PINNED")
        else:
            reasons.append("DEGRADE_SWAP")
    if chosen is None and eligible:
        eligible.sort(key=lambda s: -s["score"])
        chosen = eligible[0]
        if last_lane and chosen["lane"] != last_lane and any(s["lane"] == last_lane for s in scored if not s["eligible"]):
            reasons.append("DEGRADE_SWAP")
    prov = next((p for p in reg["providers"] if chosen and p["lane"] == chosen["lane"]), None)
    hf_choice = None
    if prov and prov.get("fabric", "").startswith("huggingface"):
        cat = catalog if catalog is not None else fetch_hf_catalog()
        hf_choice = hf_pick(cat, policy=hf_policy, need_tools="tools" in role_spec.get("needs", []),
                            need_structured="structured_output" in role_spec.get("needs", []), pinned=pinned_model)
        if hf_choice:
            reasons.append("PINNED" if pinned_model else "PREFERENCE")
        else:
            reasons.append("CAP_MISS")
    decision = {
        "task": task[:200], "role": role_name, "harness": harness, "toolset": toolset or [],
        "machine": os.environ.get("NOUGEN_SCHEDULER_MACHINE") or platform.node(),
        "lane": prov["lane"] if prov else None, "inference_fabric": prov.get("fabric") if prov else None,
        "account": prov.get("account") if prov else None,
        "model": (hf_choice or {}).get("model") or (pinned_model if pinned_model else ((prov.get("models") or [None])[0] if prov else None)),
        "downstream_provider": (hf_choice or {}).get("downstream_provider"),
        "routing_policy": (hf_choice or {}).get("routing_policy") or ("pinned" if pinned_lane else "score"),
        "reason_codes": sorted(set(reasons + (chosen.get("reasons", []) if chosen else []))) or (["POLICY_BLOCK"] if not eligible else []),
        "score": chosen["score"] if chosen else 0.0,
        "candidates": [{"lane": s["lane"], "eligible": s["eligible"], "score": s["score"], "reasons": s["reasons"], "missing": s.get("missing", []), "detail": s.get("detail")} for s in scored],
        "hf": hf_choice, "decided_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "no_pooling": True, "coach_mode": coach_on, "tier": tier,
        "fallback_reason": escalate or ("DEGRADE_SWAP" if "DEGRADE_SWAP" in reasons else None),
        "escalate_required": bool(coach_on and tier == "delegable" and not chosen and not escalate
                                  and any("COACH_DELEGATE" in s["reasons"] for s in scored)),
    }
    if decision["escalate_required"]:
        decision["reason_codes"] = sorted(set(decision["reason_codes"] + ["ESCALATE_REQUIRED"]))
    if not chosen:
        decision["error"] = "no eligible provider"
    decision["logged"] = log_decision(decision, task, reg) is not None
    want_prov = provenance if provenance is not None else os.environ.get("NOUGEN_SCHEDULER_PROVENANCE", "").strip() == "1"
    if want_prov:
        try:
            from . import core
            core.capture("DISPATCH", f"dispatch {role_name} -> {decision['lane']}",
                         json.dumps({k: decision[k] for k in ("role", "harness", "lane", "inference_fabric", "model", "downstream_provider", "routing_policy", "toolset", "account", "machine", "reason_codes", "score", "decided_utc")}),
                         tags=["dispatch", "scheduler", f"lane:{decision['lane']}", f"role:{role_name}"])
            decision["provenance"] = "captured"
        except Exception as exc:  # pylint: disable=broad-except
            decision["provenance"] = f"capture failed: {type(exc).__name__}"
    return decision


# --------------------------------------------------------------------------- #
# CLI: decide, optionally execute on an ollama lane, or roll up the log
# --------------------------------------------------------------------------- #
def ollama_candidates() -> List[str]:
    """Dialable base URLs, most specific first. OLLAMA_HOST is a bind address
    (0.0.0.0 is not dialable, and it often carries no port), so it is
    normalised rather than trusted; then the known local ports
    (NOUGEN_OLLAMA_PORTS, default 11434,11436: the fleet proxy and the daemon)."""
    out: List[str] = []
    raw = os.environ.get("OLLAMA_HOST", "").strip()
    default_port = os.environ.get("NOUGEN_OLLAMA_PORT", "11434").strip() or "11434"
    if raw:
        if not raw.startswith("http"):
            raw = "http://" + raw
        raw = raw.replace("0.0.0.0", "127.0.0.1").rstrip("/")
        hostport = raw.split("://", 1)[1]
        if ":" not in hostport:
            raw = f"{raw}:{default_port}"
        out.append(raw)
    for port in (p.strip() for p in os.environ.get("NOUGEN_OLLAMA_PORTS", "11434,11436").split(",")):
        if port:
            url = f"http://127.0.0.1:{port}"
            if url not in out:
                out.append(url)
    return out


def ollama_base_url(*, probe_timeout_s: Optional[float] = None) -> str:
    """First candidate whose /api/tags answers; the first candidate as a logged
    fallback when none does (the caller's request will then fail honestly)."""
    import urllib.request
    cands = ollama_candidates()
    timeout = probe_timeout_s if probe_timeout_s is not None else float(os.environ.get("NOUGEN_OLLAMA_PROBE_S", "1.5"))
    for url in cands:
        try:
            with urllib.request.urlopen(url + "/api/tags", timeout=timeout) as resp:
                if resp.status == 200:
                    return url
        except Exception:  # pylint: disable=broad-except
            continue
    logging.getLogger(__name__).warning("no ollama endpoint answered among %s; falling back to %s", cands, cands[0])
    return cands[0]


def run_on_lane(decision: Dict[str, Any], prompt: str, *, timeout_s: Optional[float] = None) -> Dict[str, Any]:
    """Execute the prompt on the decided lane. Only ollama fabrics are wired
    here (the free lanes coach mode exists to use); anything else returns
    an honest 'not wired' so the caller escalates on purpose, never by accident."""
    import urllib.request
    lane = decision.get("lane") or ""
    if not lane.startswith("ollama"):
        return {"ok": False, "lane": lane, "error": "lane not wired for direct execution here"}
    body = json.dumps({"model": decision.get("model"), "messages": [{"role": "user", "content": prompt}], "stream": False}).encode("utf-8")
    req = urllib.request.Request(ollama_base_url() + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s or float(os.environ.get("NOUGEN_LANE_TIMEOUT_S", "180"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pylint: disable=broad-except
        return {"ok": False, "lane": lane, "model": decision.get("model"), "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"ok": True, "lane": lane, "model": data.get("model") or decision.get("model"),
            "content": (data.get("message") or {}).get("content", ""), "elapsed_s": round(time.time() - t0, 1),
            "prompt_tokens": data.get("prompt_eval_count"), "output_tokens": data.get("eval_count")}


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="provider_scheduler", description="coach-mode routing: decide, run, report")
    ap.add_argument("--route", metavar="TASK", help="decide a lane for TASK and print the envelope")
    ap.add_argument("--role", help="role hint (registry role name)")
    ap.add_argument("--escalate", help="why the free lanes failed (lets a delegable task reach a judgment lane)")
    ap.add_argument("--run", action="store_true", help="after --route, execute on the decided ollama lane")
    ap.add_argument("--prompt-file", help="prompt body for --run (default: the TASK text)")
    ap.add_argument("--report", action="store_true", help="roll up the decision log")
    ap.add_argument("--last", type=int, help="--report: only the last N decisions")
    a = ap.parse_args(argv)
    if a.report:
        print(json.dumps(coach_report(last_n=a.last), indent=1))
        return 0
    if not a.route:
        ap.print_help()
        return 2
    d = route(a.route, role=a.role, harness=os.environ.get("NOUGEN_AGENT", "cli"), escalate=a.escalate)
    slim = {k: d.get(k) for k in ("role", "tier", "lane", "model", "reason_codes", "fallback_reason", "escalate_required", "score", "logged")}
    print(json.dumps(slim))
    if a.run:
        prompt = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else a.route
        res = run_on_lane(d, prompt)
        print(json.dumps({k: v for k, v in res.items() if k != "content"}))
        if res.get("ok"):
            print(res["content"])
        return 0 if res.get("ok") else 1
    return 0 if d.get("lane") else 1


if __name__ == "__main__":
    raise SystemExit(main())
