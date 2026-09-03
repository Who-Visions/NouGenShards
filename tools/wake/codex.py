"""Wake adapter for a Codex CLI runtime. Same contract as the antigravity one.

Import fails where the runtime is absent, which is how a node declares it
cannot be woken this way.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Dict


def _binary() -> str:
    raw = os.environ.get("NOUGEN_WAKE_CODEX_BIN", "").strip()
    if raw:
        return raw
    found = shutil.which("codex") or shutil.which("codex.exe")
    if not found:
        raise ImportError("codex runtime not on PATH; set NOUGEN_WAKE_CODEX_BIN "
                          "to enable this adapter")
    return found


BINARY = _binary()


class Adapter:
    name = "codex"
    aliases = ("gpt", "openai")

    @staticmethod
    def _timeout() -> float:
        raw = (os.environ.get("NOUGEN_WAKE_TIMEOUT_S", "") or "").strip()
        try:
            value = float(raw)
            return value if value > 0 else 120.0
        except ValueError:
            return 120.0

    def is_idle(self) -> bool:
        """No reliable idle probe for this runtime, so assume BUSY.

        Returning False here means this adapter never wakes on its own. That
        is the honest state until a probe exists: claiming idle without a way
        to check it would interrupt live turns, and the failure would be
        blamed on the bus rather than on this guess.
        """
        return False

    def wake(self, text: str, event: Dict[str, Any]) -> Dict[str, Any]:
        args = [BINARY, "exec", text]
        extra = (os.environ.get("NOUGEN_WAKE_CODEX_ARGS", "") or "").split()
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
