"""Mirror the write-ahead buffer's JSONL to the private HF dataset via CommitScheduler.

Spec: append-only JSONL committed to the private dataset nougenai/NouGenShards-wal.
The scheduler batches local appends into periodic commits; durability on the
Space is the local SQLite + JSONL, the commit is the off-box copy.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

DEFAULT_REPO = "nougenai/NouGenShards-wal"


class HFDatasetMirror:
    def __init__(self, folder: str, repo_id: str = DEFAULT_REPO, every_min: float = 5.0,
                 token: Optional[str] = None, scheduler_cls: Any = None) -> None:
        os.makedirs(folder, exist_ok=True)
        self.folder = folder
        self.file = os.path.join(folder, "wal.jsonl")
        if scheduler_cls is None:
            from huggingface_hub import CommitScheduler as scheduler_cls  # noqa: N813
        self.scheduler = scheduler_cls(
            repo_id=repo_id, repo_type="dataset", folder_path=folder,
            path_in_repo="wal", every=every_min, private=True, token=token,
        )

    def append(self, payload: dict) -> None:
        line = json.dumps(payload, sort_keys=True) + "\n"
        with self.scheduler.lock:  # CommitScheduler reads under this lock
            with open(self.file, "a", encoding="utf-8") as fh:
                fh.write(line)
