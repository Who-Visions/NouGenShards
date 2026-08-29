"""Adaptive first-run onboarding: discover, ask, compile a profile.

Leg 20260829T050012Z, gated behind the capability-layer doctrine and the
clean-room reproducibility work.

The point of "adaptive" is that the questions are chosen from what was actually
FOUND, not from a fixed script. NouGen runs on infrastructure the operator
already owns (README: "a capability layer, not an inference provider"), so
onboarding has no business asking which local model to prefer on a machine with
no local runtime, or asking about GPU limits when no GPU lane answered. A fixed
questionnaire would be asserting a provider rather than discovering one.

Discovery never reads a secret VALUE -- only whether a name is set. Nothing
here requires a credential; a clean clone must complete onboarding with none.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

PROFILE_VERSION = 1
DEFAULT_OLLAMA = "http://localhost:11434"

# Presence-only. Same contract as tools/bootstrap.py: names, never values.
CREDENTIAL_NAMES = (
    "OPENROUTER_API_KEY",
    "NGS_INFERENCE_TOKENS",
    "HF_TOKEN",
    "NOUGEN_OLLAMA_CLOUD_KEYS",
    "NOUGEN_RELAY_GITHUB_TOKEN",
)


def profile_path(root: Path | None = None) -> Path:
    return (root or Path.home()) / ".nougen" / "profile.json"


def _is_generative(entry: dict) -> bool:
    """Exclude embedding-only models from the chat lane.

    /api/tags reports capabilities; an embedding model advertises ["embedding"]
    and no completion. Ranking purely by size picks these first -- they are the
    smallest things installed -- and produces a default lane that cannot hold a
    conversation. Size is not usability.
    """
    caps = entry.get("capabilities")
    if caps:
        return any(c in ("completion", "chat", "vision", "tools") for c in caps)
    # Older daemons omit capabilities; fall back to the naming convention.
    name = (entry.get("name") or "").lower()
    return not any(tok in name for tok in ("embed", "reranker", "rerank"))


def _probe_ollama(base: str, timeout: float = 3.0) -> dict:
    """Ask the local runtime what it actually has. Never raises."""
    try:
        req = urllib.request.Request(f"{base.rstrip('/')}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        entries = [m for m in data.get("models", []) if m.get("name")]
        usable = [m for m in entries if _is_generative(m)]
        return {
            "reachable": True,
            "models": sorted(m["name"] for m in usable),
            "sizes": {m["name"]: m.get("size") for m in usable},
            "excluded_non_generative": sorted(
                m["name"] for m in entries if not _is_generative(m)),
        }
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return {"reachable": False, "models": [], "sizes": {}, "excluded_non_generative": []}


def discover_capabilities(ollama_url: str | None = None, env: dict | None = None) -> dict:
    """What this machine can actually do, right now."""
    env = os.environ if env is None else env
    base = ollama_url or env.get("NOUGEN_OLLAMA_URL") or DEFAULT_OLLAMA
    local = _probe_ollama(base)
    return {
        "local_runtime": {"url": base, **local},
        # Presence only -- the value never enters this process.
        "credentials_present": sorted(n for n in CREDENTIAL_NAMES if env.get(n)),
        "credentials_absent": sorted(n for n in CREDENTIAL_NAMES if not env.get(n)),
        "has_local_lane": local["reachable"] and bool(local["models"]),
        "has_free_lane": bool(env.get("OPENROUTER_API_KEY")),
        "has_paid_lane": bool(env.get("NGS_INFERENCE_TOKENS") or env.get("HF_TOKEN")),
    }


def question_bank(caps: dict) -> list[dict]:
    """Pick 3-5 questions that this machine can actually answer.

    Each question is skipped when discovery already settles it -- asking an
    operator to confirm something we just measured is how onboarding earns a
    reputation for wasting time.
    """
    q: list[dict] = []

    if caps["has_local_lane"]:
        models = caps["local_runtime"]["models"]
        # Smallest resident model first: it is the one that reliably fits.
        sizes = caps["local_runtime"].get("sizes") or {}
        ranked = sorted(models, key=lambda m: sizes.get(m) or float("inf"))
        q.append({
            "id": "local_model",
            "prompt": "Which local model should be the default lane?",
            "options": ranked[:5],
            "default": ranked[0] if ranked else None,
            "why": "found on your local runtime",
        })
    else:
        q.append({
            "id": "local_runtime_wanted",
            "prompt": "No local model runtime answered. Set one up later?",
            "options": ["yes", "no"],
            "default": "yes",
            "why": "nothing reachable at the configured runtime URL",
        })

    q.append({
        "id": "cost_ceiling",
        "prompt": "How far may routing escalate when the local lane cannot serve?",
        # Never offer a paid tier that has no credential behind it.
        "options": (["local-only", "free-lanes"] + (["metered"] if caps["has_paid_lane"] else [])),
        "default": "free-lanes" if caps["has_free_lane"] else "local-only",
        "why": "lanes detected on this machine",
    })

    q.append({
        "id": "memory_scope",
        "prompt": "What may be captured to the shard substrate automatically?",
        "options": ["decisions-only", "decisions-and-artifacts", "nothing-automatic"],
        "default": "decisions-only",
        "why": "capture policy is yours; shards live on your storage",
    })

    if caps["credentials_absent"]:
        q.append({
            "id": "configure_credentials_now",
            "prompt": f"{len(caps['credentials_absent'])} credential(s) unset. Configure now?",
            "options": ["later", "now"],
            "default": "later",
            "why": "deployment configuration, not needed to build or test",
        })

    if caps["has_local_lane"] and caps["has_free_lane"]:
        q.append({
            "id": "prefer_local_over_free",
            "prompt": "Prefer the local lane over free cloud lanes even when slower?",
            "options": ["yes", "no"],
            "default": "yes",
            "why": "both lanes are available, so the tie-break is a real choice",
        })

    return q[:5]


def compile_profile(caps: dict, answers: dict) -> dict:
    """Turn discovery + answers into the routing profile the fleet reads."""
    ceiling = answers.get("cost_ceiling", "local-only")
    order: list[str] = []
    if caps["has_local_lane"]:
        order.append("local")
    if ceiling in ("free-lanes", "metered") and caps["has_free_lane"]:
        order.append("free")
    if ceiling == "metered" and caps["has_paid_lane"]:
        order.append("metered")
    if answers.get("prefer_local_over_free") == "no" and "free" in order and "local" in order:
        order.remove("local")
        order.insert(order.index("free") + 1, "local")

    return {
        "profile_version": PROFILE_VERSION,
        "route_order": order,
        "default_local_model": answers.get("local_model"),
        "cost_ceiling": ceiling,
        "memory_scope": answers.get("memory_scope", "decisions-only"),
        # Escalation is never silent: with nothing routable we say so.
        "on_all_lanes_down": "report",
        "discovered": {
            "local_runtime_url": caps["local_runtime"]["url"],
            "local_models": caps["local_runtime"]["models"],
            "credentials_present": caps["credentials_present"],
        },
    }


def default_answers(questions: list[dict]) -> dict:
    return {q["id"]: q["default"] for q in questions if q.get("default") is not None}


def write_profile(profile: dict, root: Path | None = None) -> Path:
    path = profile_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return path


def run(root: Path | None = None, ollama_url: str | None = None,
        assume_defaults: bool = False, ask=None) -> dict:
    """Discover, ask, compile, persist. Returns the compiled profile."""
    caps = discover_capabilities(ollama_url)
    questions = question_bank(caps)
    if assume_defaults or ask is None:
        answers = default_answers(questions)
    else:
        answers = {}
        for q in questions:
            answers[q["id"]] = ask(q)
    profile = compile_profile(caps, answers)
    profile["profile_path"] = str(write_profile(profile, root))
    return profile
