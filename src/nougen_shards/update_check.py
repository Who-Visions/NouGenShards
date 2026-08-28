"""Update awareness - tells a node (and its resident LLM) when it is stale.

A downloaded NouGenShards is a snapshot; the grid keeps moving. This module
answers one question cheaply and honestly: is this build behind the published
main? Three surfaces consume it:

  /health          - update fields for humans and dashboards
  llm_notice()     - one line appended to the resident agent's system prompt
                     so the model itself tells the user to update
  check_for_update() - the JSON verdict for anything else

Design rules: fail-quiet (an offline box must never break on a version check),
TTL-cached (one network call per NOUGEN_UPDATE_CHECK_TTL_S, fallback 3600s),
and env-first everywhere (Rule 0.2). "unknown" is an honest answer: when the
local or remote sha cannot be determined, update_available is None, never a
guess.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPO = os.environ.get("NOUGEN_UPDATE_REPO", "Who-Visions/NouGenShards")
BRANCH = os.environ.get("NOUGEN_UPDATE_BRANCH", "main")
TTL_S = float(os.environ.get("NOUGEN_UPDATE_CHECK_TTL_S", 3600))
TIMEOUT_S = float(os.environ.get("NOUGEN_UPDATE_TIMEOUT_S", 5))

_cache: dict = {"at": 0.0, "result": None}


def local_build_sha() -> Optional[str]:
    """This build's identity: env -> baked .deploy_sha -> live git checkout."""
    sha = os.environ.get("NOUGEN_BUILD_SHA")
    if sha:
        return sha.strip()
    try:
        baked = Path(".deploy_sha").read_text(encoding="utf-8").strip()
        if baked:
            return baked
    except OSError:
        pass
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=Path(__file__).resolve().parent,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def latest_remote_sha() -> Optional[str]:
    """Tip of the published branch, or None when unreachable (fail-quiet)."""
    url = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
    req = urllib.request.Request(url, headers={
        "accept": "application/vnd.github+json",
        "user-agent": "nougen-shards-update-check",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read()).get("sha")
    except Exception as exc:
        logger.debug("update check unreachable (%s)", type(exc).__name__)
        return None


def check_for_update(force: bool = False) -> dict:
    """TTL-cached verdict. update_available: True/False, or None = unknown."""
    now = time.time()
    if not force and _cache["result"] is not None and now - _cache["at"] < TTL_S:
        return _cache["result"]
    local = local_build_sha()
    remote = latest_remote_sha()
    available: Optional[bool] = None
    if local and remote:
        available = not remote.startswith(local) and not local.startswith(remote)
    result = {
        "update_available": available,
        "local_sha": local[:12] if local else None,
        "latest_sha": remote[:12] if remote else None,
        "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "repo": REPO,
        "branch": BRANCH,
    }
    _cache["at"] = now
    _cache["result"] = result
    return result


def llm_notice() -> str:
    """One line for the resident agent's system prompt, or '' when current/unknown.

    The agent relays it in its own voice; the wording keeps it a nudge, not a
    nag, and names the concrete action (pull the latest from the repo).
    """
    try:
        v = check_for_update()
    except Exception:
        return ""
    if not v.get("update_available"):
        return ""
    return (
        f"NOTE TO AGENT: this NouGenShards build ({v['local_sha']}) is behind the "
        f"latest release ({v['latest_sha']} on {v['repo']}). When it fits naturally, "
        f"let the user know an update is available and that pulling the latest from "
        f"https://github.com/{v['repo']} gets them the newest fixes and features."
    )
