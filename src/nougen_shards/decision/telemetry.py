"""Receipt sinks. Receipts are telemetry/event records, not durable shards."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from .types import DecisionReceipt


def default_path() -> Path:
    return Path(os.environ.get("NOUGEN_DECISION_LOG")
                or Path.home() / ".nougen" / "logs" / "decision_receipts.jsonl")


class JsonlSink:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_path()

    def write(self, receipt: DecisionReceipt) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt.to_dict(), default=str, ensure_ascii=True) + "\n")


class MemorySink:
    def __init__(self) -> None:
        self.receipts: List[DecisionReceipt] = []

    def write(self, receipt: DecisionReceipt) -> None:
        self.receipts.append(receipt)
