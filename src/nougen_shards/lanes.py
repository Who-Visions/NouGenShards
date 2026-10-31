"""Dynamic lane resolution for NouGenShards: hosts, models and secrets discovered from the
machine, never hardcoded (Rule 0.0 §4, Rule 0.4; GM mandate 2026-10-26).

This module composes three resolvers that already exist in the package instead of adding a
fourth opinion:

* :mod:`nougen_shards.ollama_host` — env -> sanitized -> logged fallback base URL, and the
  candidate port list (the fleet proxy and the real engine).
* :mod:`nougen_shards.custom_model_resolver` — custom fleet model detection and scoring.
* :mod:`nougen_shards.keymaker` — ``get_secret`` over the DPAPI store.

On top it adds the two things callers kept re-implementing: a **live probe** of each
candidate host's ``/api/tags`` through an injectable prober (so tests run offline), and a
single **Rule 0.4 pick order** that also knows about cloud tags:

    env-preferred (if served and allowed) > custom e2b/e4b > gemma4 e2b/e4b
    > cloud tag (only when ``allow_cloud``) > None

Nothing returned here is a constant that was not either found in env/keymaker or confirmed
by a probe. When nothing resolves the result says ``status == "deterministic_only"`` so the
caller degrades honestly instead of inventing a lane.

Public surface: :func:`candidate_hosts`, :func:`pick_model`, :func:`resolve_lane`,
:func:`resolve_secret`, :func:`default_prober`, :func:`fingerprint`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence

from nougen_shards import ollama_host

try:  # optional: custom model detection; fall back to a family heuristic
    from nougen_shards.custom_model_resolver import is_custom_user_model, is_embedding_model
except Exception:  # noqa: BLE001 - keep lanes importable even if the resolver changes
    is_custom_user_model = None  # type: ignore[assignment]
    is_embedding_model = None  # type: ignore[assignment]

Prober = Callable[[str], List[str]]

STOCK_FAMILIES = ("gemma", "llama", "qwen", "mistral", "phi", "deepseek", "gpt", "nemotron",
                  "glm", "embed", "hf.co")
#: Local size classes banned on every fleet machine (Rule 0.4).
BANNED_LOCAL_SIZES = re.compile(r"(?<![0-9])(12b|27b|31b|70b|120b)(?![0-9])", re.I)
SMALL_LOCAL = re.compile(r":e?[24]b", re.I)
CLOUD_SUFFIX = "-cloud"


def fingerprint(secret: str) -> str:
    """SHA-256 prefix, the only form a secret may appear in logs or messages."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------------------
# Hosts
# --------------------------------------------------------------------------------------
def candidate_hosts(env: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
    """Ordered candidate Ollama base URLs with provenance.

    1. ``NOUGEN_OLLAMA_HOSTS`` (comma list) in order, source ``env:NOUGEN_OLLAMA_HOSTS``;
    2. the single env-resolved URL from :func:`ollama_host.resolve_ollama_url`
       (``NOUGEN_OLLAMA_URL`` / ``NOUGEN_OLLAMA_HOST`` / ``OLLAMA_HOST``), sanitized so a
       bind address such as ``0.0.0.0`` becomes dialable;
    3. the logged fallbacks: the default client host on every candidate port.
    """
    e = os.environ if env is None else env
    out: List[Dict[str, str]] = []
    seen: set = set()

    def add(url: str, source: str) -> None:
        url = ollama_host.sanitize_ollama_url(url)
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "source": source})

    for h in (e.get("NOUGEN_OLLAMA_HOSTS") or "").split(","):
        if h.strip():
            add(h, "env:NOUGEN_OLLAMA_HOSTS")
    if any(e.get(k) for k in ("NOUGEN_OLLAMA_URL", "NOUGEN_OLLAMA_HOST", "OLLAMA_HOST")):
        add(ollama_host.resolve_ollama_url(env=e, log=False), "env")
    for port in ollama_host.candidate_ports():
        add(f"http://{ollama_host.DEFAULT_CLIENT_HOST}:{port}", "fallback")
    return out


def default_prober(timeout: float = 3.0) -> Prober:
    """Return a prober that lists served tags at ``<base>/api/tags`` (empty on any error)."""
    def probe(base: str) -> List[str]:
        try:
            with urllib.request.urlopen(ollama_host.api("/api/tags", base=base), timeout=timeout) as r:
                data = json.load(r)
        except Exception:  # noqa: BLE001
            return []
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    return probe


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------
def is_cloud(tag: str) -> bool:
    """Both Ollama cloud conventions: ``name:31b-cloud`` and ``name:cloud``
    (matches chat_service.discover_chat_model)."""
    low = tag.lower()
    return low.endswith(CLOUD_SUFFIX) or low.endswith(":cloud")


def is_custom(tag: str) -> bool:
    if is_custom_user_model is not None:
        try:
            return bool(is_custom_user_model(tag))
        except Exception:  # noqa: BLE001
            pass
    family = tag.split(":")[0].lower()
    return not any(family.startswith(f) for f in STOCK_FAMILIES)


def _is_embedding(tag: str) -> bool:
    if is_embedding_model is not None:
        try:
            return bool(is_embedding_model(tag))
        except Exception:  # noqa: BLE001
            pass
    return "embed" in tag.lower()


def pick_model(
    tags: Sequence[str],
    *,
    allow_cloud: bool = False,
    preferred: Optional[str] = None,
    exclude: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Rule 0.4 pick order over the tags a host actually serves.

    ``exclude`` removes tags by substring (personas that must not be borrowed as workers);
    it defaults to ``NOUGEN_LANE_EXCLUDE_MODELS`` or nothing. Banned local sizes are never
    returned; cloud tags only when ``allow_cloud``; ``preferred`` wins only if served and allowed.
    """
    env_excl = (os.environ.get("NOUGEN_LANE_EXCLUDE_MODELS") or "").split(",")
    excl = [x.strip().lower() for x in (exclude if exclude is not None else env_excl) if x and x.strip()]

    def allowed(t: str) -> bool:
        low = t.lower()
        if not t or _is_embedding(t) or any(x in low for x in excl):
            return False
        if is_cloud(t):
            return allow_cloud
        return not BANNED_LOCAL_SIZES.search(t)

    served = [t for t in tags if allowed(t)]
    if preferred and preferred in served:
        return preferred
    local_small = [t for t in served if not is_cloud(t) and SMALL_LOCAL.search(t)]
    for pool in ([t for t in local_small if is_custom(t)],
                 [t for t in local_small if t.lower().startswith("gemma4")]):
        for size in (":e2b", ":e4b", ":2b", ":4b"):
            for t in pool:
                if size in t.lower():
                    return t
    if allow_cloud:
        for t in served:
            if is_cloud(t):
                return t
    return None


# --------------------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------------------
def resolve_secret(
    name: str,
    env: Optional[Dict[str, str]] = None,
    *,
    min_len: int = 20,
    validator: Optional[Callable[[str], bool]] = None,
    slots: int = 8,
) -> Dict[str, Any]:
    """Resolve ``name`` from env, then keymaker slots ``name``, ``name_1`` .. ``name_<slots>``.

    ``NOUGEN_<name>_NAME`` pins one keymaker key. With a ``validator`` the first accepted
    value wins, so a dead slot can never shadow a live one. ``value`` is for in-process use;
    only ``fp`` may be logged.
    """
    e = os.environ if env is None else env
    val = (e.get(name) or "").strip()
    if len(val) >= min_len and (validator is None or validator(val)):
        return {"name": name, "value": val, "fp": fingerprint(val), "source": "env"}
    try:
        from nougen_shards import keymaker  # pylint: disable=import-outside-toplevel
    except Exception:  # noqa: BLE001
        keymaker = None  # type: ignore[assignment]
    if keymaker is not None:
        pinned = (e.get(f"NOUGEN_{name}_NAME") or "").strip()
        keys = [pinned] if pinned else [name] + [f"{name}_{i}" for i in range(1, slots + 1)]
        for key in keys:
            try:
                got = keymaker.get_secret(key)
            except Exception:  # noqa: BLE001
                got = None
            if got and len(got) >= min_len and (validator is None or validator(got)):
                return {"name": key, "value": got, "fp": fingerprint(got), "source": "keymaker"}
    return {"name": name, "value": None, "fp": None, "source": "unresolved"}


# --------------------------------------------------------------------------------------
# Lane
# --------------------------------------------------------------------------------------
def resolve_lane(
    purpose: str = "worker",
    *,
    allow_cloud: bool = False,
    env: Optional[Dict[str, str]] = None,
    prober: Optional[Prober] = None,
    exclude: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Resolve an inference lane for ``purpose`` from this machine.

    Returns ``{"status": "ready"|"deterministic_only", "purpose", "host", "host_source",
    "model", "served_count", "api_key_fp", "tried": [...]}``. ``NOUGEN_<PURPOSE>_MODEL``
    (or ``NOUGEN_LANE_MODEL``) names a preferred tag that wins only if served and allowed.
    """
    e = os.environ if env is None else env
    probe = prober or default_prober()
    preferred = e.get(f"NOUGEN_{purpose.upper()}_MODEL") or e.get("NOUGEN_LANE_MODEL")
    hosts = candidate_hosts(e)
    served: Dict[str, List[str]] = {h["url"]: probe(h["url"]) for h in hosts}  # one probe per host
    tried: List[Dict[str, Any]] = [
        {"url": h["url"], "source": h["source"], "served": len(served[h["url"]]), "picked": None} for h in hosts]

    def ready(host: Dict[str, str], model: str) -> Dict[str, Any]:
        for t in tried:
            if t["url"] == host["url"]:
                t["picked"] = model
        key = resolve_secret("OLLAMA_API_KEY", e) if is_cloud(model) else {"fp": None}
        return {"status": "ready", "purpose": purpose, "host": host["url"], "host_source": host["source"],
                "model": model, "served_count": len(served[host["url"]]), "api_key_fp": key.get("fp"),
                "tried": tried}

    # Pass 1: the env-preferred tag wins on ANY host before the small-model fallback is
    # considered anywhere (documented order: env-preferred > custom e2b/e4b > gemma4 e2b/e4b).
    if preferred:
        for host in hosts:
            if pick_model([preferred] if preferred in served[host["url"]] else [],
                          allow_cloud=allow_cloud, preferred=preferred, exclude=exclude):
                return ready(host, preferred)
    # Pass 2: first host that serves any selectable model.
    for host in hosts:
        model = pick_model(served[host["url"]], allow_cloud=allow_cloud, exclude=exclude)
        if model:
            return ready(host, model)
    return {"status": "deterministic_only", "purpose": purpose, "host": None, "host_source": None,
            "model": None, "served_count": 0, "api_key_fp": None, "tried": tried}
