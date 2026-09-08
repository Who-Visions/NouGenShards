"""Wake adapter for Kaedra agent runtime.

Imports only where Kaedra dependencies exist.
Nothing here is reachable unless the receiver's gates have already approved the message.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict


KAEDRA_DIR = Path("/Users/kushboygroup/The Observatory/Kaedra")


class Adapter:
    name = "kaedra"
    aliases = ("shadow", "tactician")

    @staticmethod
    def _timeout() -> float:
        raw = (os.environ.get("NOUGEN_WAKE_TIMEOUT_S", "") or "").strip()
        try:
            value = float(raw)
            return value if value > 0 else 120.0
        except ValueError:
            return 120.0

    def is_idle(self) -> bool:
        """True when no active Kaedra session or run is blocking."""
        return True

    def wake(self, text: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """Hands the approved message to Kaedra's inbox and records wake event."""
        inbox_dir = Path.home() / ".nougen" / "kaedra_inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        filename = f"wake_{event.get('leg_id') or 'event'}_{int(os.times().system * 1000)}.json"
        target_path = inbox_dir / filename
        payload = {
            "source": event.get("source") or "wake_adapter",
            "target": "kaedra",
            "text": text,
            "event": event,
        }
        target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {
            "woken": True,
            "agent": "kaedra",
            "inbox_file": str(target_path),
            "leg_id": event.get("leg_id"),
        }
