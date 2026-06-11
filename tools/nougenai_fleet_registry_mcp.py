"""Workspace-safe launcher for the NouGenAi fleet-registry MCP server.

The upstream Watchtower server defaults its lock file to
``%USERPROFILE%\\.codex\\memories``, which is not writable from this Codex
sandbox. This wrapper keeps the lock in the current repo and then executes the
real server unchanged.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHTOWER_ROOT = Path(os.environ.get("WATCHTOWER_ROOT", r"%USERPROFILE%\Watchtower"))
SERVER_PATH = WATCHTOWER_ROOT / "local_search_mcp.py"


def main() -> None:
    """Launch the fleet-registry MCP server with sandbox-safe defaults."""
    if not SERVER_PATH.exists():
        raise FileNotFoundError(f"Fleet registry MCP server not found: {SERVER_PATH}")

    lock_dir = Path(
        os.environ.get(
            "NOUGENAI_MCP_LOCK_DIR",
            str(REPO_ROOT / ".mcp-locks" / str(os.getpid())),
        )
    )
    lock_dir.mkdir(parents=True, exist_ok=True)
    os.environ["NOUGENAI_MCP_LOCK_DIR"] = str(lock_dir)
    os.environ.setdefault("WATCHTOWER_ROOT", str(WATCHTOWER_ROOT))

    sys.path.insert(0, str(WATCHTOWER_ROOT))
    sys.argv[0] = str(SERVER_PATH)
    runpy.run_path(str(SERVER_PATH), run_name="__main__")


if __name__ == "__main__":
    main()
