"""
RSI (Recursive Self-Improvement) lane: a native NouGen tool, same family as
dream.py and evolution.py, for a target repo (default NouGenRemote-Android).

Gate-don't-write, matching the Dream Lane contract: this module never
authors or applies a code edit itself. Each run checks the target repo's
ground truth (does it build, is the self-update chain healthy), asks a
local/free fleet model to PROPOSE one small improvement, and writes that
proposal to a private report + relay leg for a Coach-level agent session to
review and implement. Only a short, explicit allow-list of mechanical,
reversible actions (see TRIVIAL_AUTO_FIXERS) may be applied without a human
or Coach in the loop - everything else is a proposal, never a patch.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import core

REPORTS_DIR_DEFAULT = r"C:\Users\super\Watchtower\NouGen\rsi"


def _env_path(name: str, fallback: str) -> str:
    raw = os.environ.get(name)
    return raw.strip() if raw and raw.strip() else fallback


def _repo_path() -> Path:
    return Path(_env_path("NOUGEN_RSI_REPO", r"C:\Users\super\Watchtower\NouGenRemote-Android"))


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


def check_self_update_health(version_url: str = "https://chat.nougenai.com/version") -> Dict[str, Any]:
    """Confirms the self-update chain this lane depends on is actually alive."""
    try:
        import urllib.request
        req = urllib.request.Request(version_url, headers={"User-Agent": "nougen-rsi/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": resp.status == 200, "status": resp.status, "body": json.loads(resp.read().decode())}
    except Exception as exc:  # pylint: disable=broad-except
        return {"ok": False, "error": str(exc)}


def _pick_model() -> str:
    """Env-preferred > custom fleet e2b/e4b > refuse-never (Rule 0.4). Caller probes /api/tags at use time."""
    return os.environ.get("NOUGEN_RSI_MODEL", "dav1d:e2b")


def propose_improvement(repo: Path, recent_shard_titles: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Asks a local/free model for ONE small, concrete, verifiable improvement
    idea. This is a PROPOSAL only - rsi.py never edits repo files itself.
    """
    model = _pick_model()
    context = "\n".join(f"- {t}" for t in (recent_shard_titles or [])[:10])
    prompt = (
        f"You are reviewing the Android app at {repo.name} for its next small, "
        "real, verifiable improvement - a bug fix, a missing confirm dialog, "
        "a UX gap, nothing architectural. Recent work already shipped:\n"
        f"{context or '(no recent history available)'}\n\n"
        "Propose exactly ONE improvement NOT already covered above. Reply as "
        "JSON only: {\"title\": str, \"description\": str, \"risk\": "
        "\"trivial|low|medium\", \"touches_secrets\": bool}."
    )
    try:
        import urllib.request
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
        return proposal
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": str(exc), "model_used": model}


def run(apply_trivial: bool = False) -> Dict[str, Any]:
    """
    One RSI cycle. Always report-only for anything beyond the trivial
    allow-list (currently empty - no auto-fixer has been judged safe enough
    to ship yet, so apply_trivial is a no-op reserved for future, explicitly
    reviewed mechanical fixes). Writes a report + shard; a relay leg is the
    caller's job (cli.py), same separation dream.py's own callers use.
    """
    repo = _repo_path()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    build = check_builds(repo)
    health = check_self_update_health()

    recent_titles: List[str] = []
    try:
        hits = core._title_retrieve(query="nougenremote-android", limit=10,
                                     domain_key=None, include_research=False)
        recent_titles = [h.get("title", "") for h in (hits or []) if isinstance(h, dict) and h.get("title")]
    except Exception:  # pylint: disable=broad-except
        pass  # Best-effort context only - an empty list just means a thinner prompt, never a hard failure.

    proposal = propose_improvement(repo, recent_titles) if build.get("ok", True) else {
        "skipped": True, "reason": "build is currently broken - fix that before proposing new work"}

    summary = {
        "timestamp_utc": timestamp,
        "repo": str(repo),
        "build": build,
        "self_update_health": health,
        "proposal": proposal,
        "applied": False,  # gate-don't-write: this module never flips this to true itself
        "status": "ok" if build.get("ok", True) else "BUILD_BROKEN",
    }

    report_path = _reports_dir() / f"rsi_{timestamp[:10]}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    summary["report_path"] = str(report_path)
    return summary
