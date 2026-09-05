"""Wake adapter for an Antigravity agent runtime.

Imports only where the runtime is actually installed. On a node without it the
import fails, `tools.wake` records why, and waking reports unavailable rather
than pretending. Nothing here is reachable unless the receiver's gates have
already approved the message.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict


def _binary() -> str:
    """The runtime executable, resolved rather than assumed."""
    raw = os.environ.get("NOUGEN_WAKE_ANTIGRAVITY_BIN", "").strip()
    if raw:
        return raw
    found = shutil.which("agy") or shutil.which("agy.exe")
    if not found:
        raise ImportError("antigravity runtime not on PATH; set "
                          "NOUGEN_WAKE_ANTIGRAVITY_BIN to enable this adapter")
    return found


BINARY = _binary()  # import-time, so an absent runtime means an absent adapter


class Adapter:
    name = "antigravity"
    aliases = ("agy", "apollo")

    @staticmethod
    def _timeout() -> float:
        raw = (os.environ.get("NOUGEN_WAKE_TIMEOUT_S", "") or "").strip()
        try:
            value = float(raw)
            return value if value > 0 else 120.0
        except ValueError:
            return 120.0

    def is_idle(self) -> bool:
        """True when no turn is in flight, so a wake would not interrupt one.

        Conservative: anything it cannot determine counts as BUSY. Waking a
        running agent mid-turn is the worse error, and a missed wake is
        retried by the next poll while an interrupted turn is not recoverable.
        """
        try:
            probe = subprocess.run([BINARY, "status", "--json"], capture_output=True,
                                   text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return False
        if probe.returncode != 0:
            return False
        try:
            return bool(json.loads(probe.stdout or "{}").get("idle"))
        except ValueError:
            return False

    def wake(self, text: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """Hand the approved message to a fresh turn as its opening context.

        The message is passed as an ARGUMENT, never interpolated into a shell
        string: it is attacker-influenced content that has passed a content
        gate, not a trusted command, and a gate is not a shell escape.
        """
        args = [BINARY, "-p", text]
        extra = (os.environ.get("NOUGEN_WAKE_ANTIGRAVITY_ARGS", "") or "").split()
        try:
            proc = subprocess.run(args + extra, capture_output=True, text=True,
                                  timeout=self._timeout())
        except subprocess.TimeoutExpired:
            return {"woken": True, "completed": False, "reason": "still running at timeout"}
        except OSError as exc:
            return {"woken": False, "error": str(exc)[:120]}
        return {"woken": proc.returncode == 0, "exit": proc.returncode,
                "leg_id": event.get("leg_id"),
                "output_head": (proc.stdout or "")[:200]}
