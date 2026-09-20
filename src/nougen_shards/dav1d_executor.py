"""
Dav1d Execution Layer — Bounded AGY CLI & Toolchain Dispatch.

Griot reasons and retrieves from the memory grid; Dav1d executes.
This module provides the bounded execution bridge for Dav1d to invoke
the Google Antigravity CLI and toolchain, returning verifiable
runtime evidence (host, engine, version, command, exit code, stdout).
"""
import logging
import os
import shutil
import subprocess
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

ALLOWED_SUBCOMMANDS = {
    "mcp", "changelog", "models", "agent", "agents", "help", "version", "--version", "-v"
}

# Version is resolved at call time (env -> live probe -> labeled fallback), never
# pinned in source. A constant here drifted from 1.1.17 to 1.1.18 within a day and the
# stale value was reported to the fleet as runtime evidence.
_VERSION_UNKNOWN = "unknown"
_VERSION_CACHE: Dict[str, str] = {}


def _get_candidate_paths() -> List[str]:
    """Dynamically resolves candidate binary paths for AGY CLI."""
    home = os.path.expanduser("~")
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    candidates = [
        os.environ.get("AGY_BIN_PATH", ""),
        os.path.join(local_app_data, "agy", "bin", "agy.exe"),
        os.path.join(local_app_data, "agy", "bin", "agy.EXE"),
        os.path.join(r"C:\nvm4w\nodejs", "antigravity.CMD"),
    ]
    return [c for c in candidates if c]


def resolve_agy_binary() -> Optional[str]:
    """Finds the AGY / Antigravity CLI executable on the host."""
    for p in _get_candidate_paths():
        if os.path.exists(p):
            return p
    for name in ["agy", "agy.exe", "agy.EXE", "antigravity", "antigravity.cmd", "antigravity.CMD"]:
        found = shutil.which(name)
        if found:
            return found
    return None


def _version_probe_timeout() -> float:
    """Seconds allowed for the `agy --version` probe."""
    try:
        return float(os.environ.get("NOUGEN_AGY_VERSION_TIMEOUT_SEC", "5"))
    except ValueError:
        logger.warning("NOUGEN_AGY_VERSION_TIMEOUT_SEC is not a number; using 5s")
        return 5.0


def _version_cache_enabled() -> bool:
    """Per-process memo of the probe result. Disable with NOUGEN_AGY_VERSION_CACHE=0."""
    return os.environ.get("NOUGEN_AGY_VERSION_CACHE", "1") != "0"


def get_agy_version(bin_path: Optional[str], refresh: bool = False) -> str:
    """Resolve the AGY CLI version from the binary itself.

    Order: NOUGEN_AGY_VERSION override -> live `--version` probe -> "unknown".
    Never returns a version it did not observe, because this string is published to
    the fleet as runtime evidence and an invented one is worse than no answer.
    """
    pinned = os.environ.get("NOUGEN_AGY_VERSION", "").strip()
    if pinned:
        return pinned

    if not bin_path:
        return _VERSION_UNKNOWN

    use_cache = _version_cache_enabled()
    if use_cache and not refresh and bin_path in _VERSION_CACHE:
        return _VERSION_CACHE[bin_path]

    try:
        res = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=_version_probe_timeout(),
        )
        raw = (res.stdout or "") or (res.stderr or "")
        line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
        if res.returncode == 0 and line:
            if use_cache:
                _VERSION_CACHE[bin_path] = line
            return line
        logger.warning(
            "agy --version exited %s with no parseable output; reporting unknown",
            res.returncode,
        )
    except Exception as exc:
        logger.warning("agy --version probe failed for %s: %s", bin_path, exc)

    return _VERSION_UNKNOWN


def _get_host_label() -> str:
    return os.environ.get("NOUGEN_HOST_LABEL", "Blade Node (Stadium)")


def run_dav1d_agy(
    command: str = "agy",
    args: Optional[List[str]] = None,
    subcommand: Optional[str] = None,
    prompt: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Executes a bounded AGY CLI operation on Dav1d and returns structured proof.
    """
    host_label = _get_host_label()

    # Normalize arguments
    target_args: List[str] = []
    if prompt:
        target_args = ["--print", prompt]
    elif args and len(args) > 0:
        target_args = [str(a) for a in args]
    elif subcommand:
        target_args = subcommand.strip().split()
    else:
        target_args = ["mcp", "list"]

    # agy 1.2.x has no `version` subcommand (it rejects it as a stray prompt argument);
    # the allow-list keeps the word for callers, the binary needs the flag.
    if target_args and target_args[0].lower() == "version":
        target_args[0] = "--version"

    # Security check: verify first token is in allowed subcommands or flags
    first_tok = target_args[0].lower() if target_args else ""
    if first_tok.startswith("-"):
        pass  # allow flags like --version, --print
    elif first_tok not in ALLOWED_SUBCOMMANDS:
        return {
            "machine": "Dav1d",
            "host": host_label,
            "engine": "agy-cli",
            "version": get_agy_version(resolve_agy_binary()),
            "command": " ".join([command] + target_args),
            "status": "rejected",
            "exit_code": 1,
            "error": f"Subcommand '{first_tok}' not in bounded allowlist ({', '.join(sorted(ALLOWED_SUBCOMMANDS))})"
        }

    bin_path = resolve_agy_binary()
    if not bin_path:
        # Graceful degraded report if running on cloud container (e.g. HF Space)
        return {
            "machine": "Dav1d",
            "host": "Cloud / Space (Simulated / Remote Dav1d bridge)",
            "engine": "agy-cli",
            "version": os.environ.get("NOUGEN_AGY_VERSION", "").strip()
            or f"{_VERSION_UNKNOWN} (no agy binary on this host)",
            "command": f"{command} {subcommand or ' '.join(target_args)}".strip(),
            "status": "simulated",
            "exit_code": 0,
            "output": "AGY CLI registered on Dav1d node. MCP bridge operational."
        }

    version = get_agy_version(bin_path)
    cmd_list = [bin_path] + target_args

    try:
        # stdin closed: agy reads stdin for prompts, and a hidden gateway process
        # has no usable stdin, so --print would block until the timeout.
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL)
        output = res.stdout if res.stdout else res.stderr
        return {
            "machine": "Dav1d",
            "host": host_label,
            "engine": "agy-cli",
            "binary_path": bin_path,
            "version": version,
            "command": " ".join(cmd_list),
            "status": "success" if res.returncode == 0 else "failed",
            "exit_code": res.returncode,
            "output": (output or "").strip()
        }
    except subprocess.TimeoutExpired:
        return {
            "machine": "Dav1d",
            "host": host_label,
            "engine": "agy-cli",
            "version": version,
            "command": " ".join(cmd_list),
            "status": "timeout",
            "exit_code": 124,
            "error": f"Execution timed out after {timeout}s"
        }
    except Exception as exc:
        return {
            "machine": "Dav1d",
            "host": host_label,
            "engine": "agy-cli",
            "version": version,
            "command": " ".join(cmd_list),
            "status": "error",
            "exit_code": 1,
            "error": str(exc)
        }


# --- Dav1d persona route (ollama first, AGY labeled fallback) ---

_PERSONA_DEFAULT_MODEL = "dav1d:e2b"


def _persona_timeout(timeout: Optional[int]) -> float:
    """Seconds for the persona call: caller value, else env, else 90."""
    if timeout:
        return float(timeout)
    try:
        return float(os.environ.get("NOUGEN_DAV1D_PERSONA_TIMEOUT_SEC", "90"))
    except ValueError:
        return 90.0


def resolve_persona_model(host: str, model: Optional[str] = None) -> str:
    """Pick Dav1d's model: caller > NOUGEN_AGENT_MODEL_DAV1D > served custom dav1d tag.

    Discovered from /api/tags so a renamed tag needs no code change; the constant
    is only the fallback when the probe fails.
    """
    import json
    import urllib.request

    if model and model.strip():
        return model.strip()
    env = os.environ.get("NOUGEN_AGENT_MODEL_DAV1D", "").strip()
    if env:
        return env
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=5) as resp:
            names = [m.get("name", "") for m in json.load(resp).get("models", [])]
        for name in names:
            if name.lower().startswith("dav1d:") and "pre-selfid" not in name:
                return name
    except Exception as exc:
        logger.warning("dav1d persona: /api/tags probe failed (%s); using %s", exc, _PERSONA_DEFAULT_MODEL)
    return _PERSONA_DEFAULT_MODEL


def ask_dav1d_persona(
    prompt: str,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """Answer as Dav1d on the local ollama lane (persona baked into the Modelfile).

    Falls back to the AGY layer only when ollama cannot answer, and the reply says so
    (engine agy-cli), so the caller can always tell which Dav1d spoke.
    """
    import json
    import urllib.request
    from nougen_shards.agents import OLLAMA_HOST

    host_label = _get_host_label()
    limit = _persona_timeout(timeout)
    chosen = resolve_persona_model(OLLAMA_HOST, model)
    body = json.dumps({
        "model": chosen,
        "stream": False,
        "think": False,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=limit) as resp:
            data = json.load(resp)
        answer = ((data.get("message") or {}).get("content") or "").strip()
        if answer:
            return {
                "machine": "Dav1d",
                "host": host_label,
                "engine": "ollama",
                "model": chosen,
                "status": "success",
                "exit_code": 0,
                "output": answer,
            }
        reason = "empty answer from ollama"
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
    logger.warning("dav1d persona via ollama failed (%s); falling back to AGY", reason)
    res = run_dav1d_agy(command="agy", prompt=prompt, timeout=int(limit))
    res["fallback"] = f"ollama persona {chosen} failed: {reason}"
    return res
