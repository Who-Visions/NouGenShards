"""
RSI (Recursive Self-Improvement) lane: a native NouGen tool, same family as
dream.py and evolution.py, for a target repo (default NouGenRemote-Android).

Gate-don't-write, matching the Dream Lane contract: this module never
authors or applies a code edit itself. Each run checks the target repo's
ground truth (does it build, is the self-update chain healthy), anchors
exact temporal provenance (nougen_time + temporal_fabric), queries Exa MCP /
live temporal search for latest ecosystem patterns (with Keymaker EXA_API_KEY
and startPublishedDate filtering), asks a local/free fleet model to PROPOSE
one small improvement grounded in both recent shards and latest Exa signals,
and writes that proposal to a private report + relay leg for a Coach-level
agent session to review and implement.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from nougen_time import __version__ as NOUGEN_TIME_VERSION, now as nougen_now
from . import core
from . import keymaker
from . import temporal_fabric

REPORTS_DIR_DEFAULT = str(Path.home() / "Watchtower" / "NouGen" / "rsi")
EXA_API_URL = "https://api.exa.ai/search"
EXA_MCP_URL = "https://mcp.exa.ai/mcp"


def _env_path(name: str, fallback: str) -> str:
    raw = os.environ.get(name)
    return raw.strip() if raw and raw.strip() else fallback


def _repo_path() -> Path:
    return Path(_env_path("NOUGEN_RSI_REPO", str(Path.home() / "Watchtower" / "NouGenRemote-Android")))


def _reports_dir() -> Path:
    d = Path(_env_path("NOUGEN_RSI_REPORTS_DIR", REPORTS_DIR_DEFAULT))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(cmd: List[str], cwd: Path, timeout: int = 300) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
            shell=(os.name == "nt"),
        )
        return {"ok": proc.returncode == 0, "code": proc.returncode,
                "stdout_tail": proc.stdout[-1500:], "stderr_tail": proc.stderr[-1500:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "error": "timeout"}
    except Exception as exc:  # pylint: disable=broad-except
        return {"ok": False, "code": None, "error": str(exc)}


def check_builds(repo: Path) -> Dict[str, Any]:
    """Ground truth: does the target repo currently compile. Report-only."""
    gradlew = repo / "gradlew.bat" if os.name == "nt" else repo / "gradlew"
    if not gradlew.exists():
        return {"checked": False, "reason": "no gradlew in repo - not a Gradle project or wrong NOUGEN_RSI_REPO"}
    result = _run([str(gradlew), "compileDebugKotlin"], cwd=repo, timeout=300)
    return {"checked": True, **result}


def check_self_update_health(version_url: Optional[str] = None) -> Dict[str, Any]:
    """Confirms the self-update chain this lane depends on is actually alive.

    The version URL comes from the caller or NOUGEN_RSI_VERSION_URL; no
    operator host may appear as a default in shipped runtime code.
    """
    url = (version_url or os.environ.get("NOUGEN_RSI_VERSION_URL") or "").strip()
    if not url:
        return {"checked": False, "reason": "no version URL configured (set NOUGEN_RSI_VERSION_URL)"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nougen-rsi/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": resp.status == 200, "status": resp.status, "body": json.loads(resp.read().decode())}
    except Exception as exc:  # pylint: disable=broad-except
        return {"ok": False, "error": str(exc)}


def _resolve_exa_keys() -> List[str]:
    """Resolves all Exa API keys across keymaker aliases (EXA_API_KEY, EXA_API_KEY_1..4)."""
    keys: List[str] = []
    for candidate in ("EXA_API_KEY", "EXA_API_KEY_2", "EXA_API_KEY_3", "EXA_API_KEY_4", "EXA_API_KEY_1"):
        val = keymaker.get_secret(candidate)
        if val and val.strip() and val.strip() not in keys:
            keys.append(val.strip())
    return keys


def fetch_exa_temporal_latest(
    query: str = "Jetpack Compose Android Credential Manager OkHttp Material3 best practices bugfix",
    days_back: int = 90,
    num_results: int = 3,
) -> Dict[str, Any]:
    """
    Queries Exa (REST API or Exa MCP JSON-RPC) with strict temporal freshness filtering
    (`startPublishedDate` anchored via `nougen_time.now()`) so RSI proposals stay
    grounded in the latest upstream Android/Compose/Kotlin advisories and patterns.
    Rotates across Keymaker EXA_API_KEY slots automatically on 401/429.
    """
    instant = nougen_now()
    cutoff_dt = instant.utc_dt - datetime.timedelta(days=max(1, days_back))
    start_published = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    exa_keys = _resolve_exa_keys()
    if not exa_keys:
        return {
            "ok": False,
            "source": "exa_temporal",
            "reason": "no EXA_API_KEY in keymaker vault or environment",
            "start_published_date": start_published,
            "hits": [],
        }

    payload = {
        "query": query,
        "type": "auto",
        "numResults": max(1, min(num_results, 5)),
        "startPublishedDate": start_published,
        "contents": {"text": {"maxCharacters": 600}},
    }

    last_error = "unknown"
    for exa_key in exa_keys:
        try:
            req = urllib.request.Request(
                EXA_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": exa_key,
                    "User-Agent": "Mozilla/5.0 (compatible; NouGenRSI-ExaMCP/1.0)",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            results = raw.get("results") or []
            hits: List[Dict[str, Any]] = []
            for item in results[:num_results]:
                hits.append({
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "published_date": item.get("publishedDate") or "",
                    "snippet": (item.get("text") or "")[:300].strip(),
                })
            return {
                "ok": True,
                "source": "exa_temporal",
                "mcp_endpoint": EXA_MCP_URL,
                "query": query,
                "start_published_date": start_published,
                "evaluated_at_utc": instant.utc_iso,
                "hits": hits,
            }
        except Exception as exc:  # pylint: disable=broad-except
            last_error = str(exc)
            continue

    return {
        "ok": False,
        "source": "exa_temporal",
        "query": query,
        "start_published_date": start_published,
        "error": last_error,
        "hits": [],
    }


def _pick_model() -> str:
    """Env-preferred > custom fleet e2b/e4b > refuse-never (Rule 0.4). Caller probes /api/tags at use time."""
    return os.environ.get("NOUGEN_RSI_MODEL", "dav1d:e2b")


def propose_improvement(
    repo: Path,
    recent_shard_titles: Optional[List[str]] = None,
    exa_hits: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Asks a local/free model for ONE small, concrete, verifiable improvement
    idea grounded in recent shards and latest Exa temporal intelligence.
    This is a PROPOSAL only - rsi.py never edits repo files itself.
    """
    model = _pick_model()
    instant = nougen_now()
    context = "\n".join(f"- {t}" for t in (recent_shard_titles or [])[:10])
    exa_context = "\n".join(
        f"- [{h.get('published_date', 'recent')}] {h.get('title', '')}: {h.get('snippet', '')[:160]}"
        for h in (exa_hits or [])[:3]
        if isinstance(h, dict) and (h.get("title") or h.get("snippet"))
    )
    prompt = (
        f"Current temporal anchor: {instant.utc_iso} ({instant.display_full}).\n"
        f"You are reviewing the Android app at {repo.name} for its next small, "
        "real, verifiable improvement - a bug fix, a missing confirm dialog, "
        "a UX gap, nothing architectural. Recent work already shipped:\n"
        f"{context or '(no recent history available)'}\n\n"
        "Latest temporal web intelligence (Exa MCP):\n"
        f"{exa_context or '(no external Exa advisories needed)'}\n\n"
        "Propose exactly ONE improvement NOT already covered above. Reply as "
        "JSON only: {\"title\": str, \"description\": str, \"risk\": "
        "\"trivial|low|medium\", \"touches_secrets\": bool}."
    )
    try:
        ollama_host = "http://127.0.0.1:11434"  # OLLAMA_HOST env is a bind addr, never dial it (known trap)
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                            "stream": False, "format": "json"}).encode()
        req = urllib.request.Request(f"{ollama_host}/api/chat", data=body,
                                      headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
        content = (data.get("message", {}) or {}).get("content", "{}")
        proposal = json.loads(content)
        proposal["model_used"] = model
        proposal["temporal_anchor_utc"] = instant.utc_iso
        return proposal
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": str(exc), "model_used": model, "temporal_anchor_utc": instant.utc_iso}


def _record_bitemporal_receipt(summary: Dict[str, Any], instant_ms: int) -> Dict[str, Any]:
    """Records a deterministic HybridLogicalClock + bitemporal receipt for the RSI cycle."""
    event_seed = f"{summary.get('repo')}:{instant_ms}:{summary.get('status')}"
    event_id = "rsi-" + hashlib.sha256(event_seed.encode("utf-8")).hexdigest()[:12]
    hlc = temporal_fabric.advance_hlc(now_ms=instant_ms, node_id=os.environ.get("NOUGEN_MACHINE", "blade1tb"), event_id=event_id)
    return {
        "event_id": event_id,
        "valid_from_ms": instant_ms,
        "known_from_ms": instant_ms,
        "hlc": {
            "physical_ms": hlc.physical_ms,
            "logical_counter": hlc.logical_counter,
            "node_id": hlc.node_id,
        },
    }


def run(apply_trivial: bool = False, exa_query: Optional[str] = None) -> Dict[str, Any]:
    """
    One RSI cycle with Exa MCP temporal grounding and bitemporal provenance.
    Always report-only for anything beyond the trivial allow-list.
    """
    repo = _repo_path()
    instant = nougen_now()
    timestamp = instant.utc_iso
    instant_ms = instant.unix_timestamp_us // 1_000

    build = check_builds(repo)
    health = check_self_update_health()

    recent_titles: List[str] = []
    try:
        hits = core._title_retrieve(query="nougenremote-android", limit=10,
                                     domain_key=None, include_research=False)
        recent_titles = [h.get("title", "") for h in (hits or []) if isinstance(h, dict) and h.get("title")]
    except Exception:  # pylint: disable=broad-except
        pass  # Best-effort context only

    query = exa_query or f"{repo.name} Jetpack Compose Android Credential Manager OkHttp latest best practices"
    exa_temporal = fetch_exa_temporal_latest(query=query)

    proposal = (
        propose_improvement(repo, recent_titles, exa_hits=exa_temporal.get("hits"))
        if build.get("ok", True)
        else {"skipped": True, "reason": "build is currently broken - fix that before proposing new work"}
    )

    summary: Dict[str, Any] = {
        "timestamp_utc": timestamp,
        "temporal": instant.to_dict(NOUGEN_TIME_VERSION),
        "repo": str(repo),
        "build": build,
        "self_update_health": health,
        "exa_temporal_latest": exa_temporal,
        "proposal": proposal,
        "applied": False,  # gate-don't-write: this module never flips this to true itself
        "status": "ok" if build.get("ok", True) else "BUILD_BROKEN",
    }
    summary["bitemporal_receipt"] = _record_bitemporal_receipt(summary, instant_ms)

    report_path = _reports_dir() / f"rsi_{instant.utc_dt.strftime('%Y-%m-%d')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    summary["report_path"] = str(report_path)
    return summary
