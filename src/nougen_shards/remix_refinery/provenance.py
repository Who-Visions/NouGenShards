"""
Immutable Provenance Ledger & Audit Trail for Remix Refinery.
"""

import json
from pathlib import Path
from typing import Optional
from .models import ProvenanceLedger

DEFAULT_LEDGER_DIR = Path.home() / ".nougen" / "provenance"


class ProvenanceManager:
    """Persists and inspects transformation ledgers."""

    def __init__(self, ledger_dir: Optional[Path] = None):
        self.ledger_dir = ledger_dir or DEFAULT_LEDGER_DIR
        self.ledger_dir.mkdir(parents=True, exist_ok=True)

    def record(self, ledger: ProvenanceLedger) -> Path:
        """Saves provenance ledger to disk as JSON."""
        out_file = self.ledger_dir / f"{ledger.ledger_id}.json"
        out_file.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")
        return out_file

    def get(self, ledger_id: str) -> Optional[ProvenanceLedger]:
        """Loads a ledger by ID."""
        target = self.ledger_dir / f"{ledger_id}.json"
        if not target.exists():
            return None
        data = json.loads(target.read_text(encoding="utf-8"))
        return ProvenanceLedger.model_validate(data)