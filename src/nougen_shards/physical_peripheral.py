"""NouGen Physical Peripheral Driver — HP ENVY Pro 6455.

Exposes physical scanning, printing, and duplicating capabilities as native Python functions
and FastMCP tools with headless Windows execution.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
CANONICAL_SCRIPT = Path(os.environ.get("USERPROFILE", "C:/Users/super")) / ".nougen" / "bin" / "hp_scan_print.py"


def scan_document(
    output_path: Optional[str] = None,
    source: str = "auto",
) -> Dict[str, Any]:
    """Acquire a scan from the physical HP ENVY Pro 6455."""
    import json
    cmd = [sys.executable, str(CANONICAL_SCRIPT), "--scan", "--source", source, "--json"]
    if output_path:
        cmd.extend(["--out", str(output_path)])

    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW, timeout=60)
    if proc.returncode != 0:
        return {"status": "error", "error": proc.stderr or proc.stdout}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"status": "success", "raw": proc.stdout}


def print_document(
    file_path: str,
    printer_name: str = "HP ENVY 6455 USB",
    copies: int = 1,
) -> Dict[str, Any]:
    """Headlessly print a document (JPG, PNG, PDF) to the physical printer."""
    import json
    cmd = [
        sys.executable,
        str(CANONICAL_SCRIPT),
        "--print",
        str(file_path),
        "--printer",
        printer_name,
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW, timeout=45)
    if proc.returncode != 0:
        return {"status": "error", "error": proc.stderr or proc.stdout}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"status": "success", "raw": proc.stdout}


def copy_document(
    copies: int = 1,
    source: str = "auto",
    printer_name: str = "HP ENVY 6455 USB",
) -> Dict[str, Any]:
    """Scan from tray/flatbed and immediately print physical copies."""
    import json
    cmd = [
        sys.executable,
        str(CANONICAL_SCRIPT),
        "--copy",
        str(copies),
        "--source",
        source,
        "--printer",
        printer_name,
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW, timeout=90)
    if proc.returncode != 0:
        return {"status": "error", "error": proc.stderr or proc.stdout}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"status": "success", "raw": proc.stdout}
