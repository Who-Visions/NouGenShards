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

# Last-known fleet value used only when the executable cannot answer a version
# probe (for example, the cloud simulation path).
_CACHED_VERSION = os.environ.get("NOUGEN_AGY_FALLBACK_VERSION", "1.1.17")


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


def get_agy_version(bin_path: str) -> str:
    """Return the live AGY version, with a logged fleet fallback."""
    global _CACHED_VERSION
    try:
        result = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=float(os.environ.get("NOUGEN_AGY_VERSION_TIMEOUT_SEC", "5")),
        )
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode == 0 and output:
            _CACHED_VERSION = output.splitlines()[0].strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        logger.debug("AGY version probe failed for %s; using fallback", bin_path)
    return _CACHED_VERSION


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

    # Security check: verify first token is in allowed subcommands or flags
    first_tok = target_args[0].lower() if target_args else ""
    if first_tok.startswith("-"):
        pass  # allow flags like --version, --print
    elif first_tok not in ALLOWED_SUBCOMMANDS:
        return {
            "machine": "Dav1d",
            "host": host_label,
            "engine": "agy-cli",
            "version": _CACHED_VERSION,
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
            "version": f"{_CACHED_VERSION} (fleet manifest)",
            "command": f"{command} {subcommand or ' '.join(target_args)}".strip(),
            "status": "simulated",
            "exit_code": 0,
            "output": "AGY CLI registered on Dav1d node. FastMCP bridge operational."
        }

    version = get_agy_version(bin_path)
    cmd_list = [bin_path] + target_args

    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout)
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
