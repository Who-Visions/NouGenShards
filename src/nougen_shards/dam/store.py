"""Dam storage: immutable per-event objects.

Two backends behind one interface:

* `LocalDamStore`  -- a directory. Used by tests and by a node with no HF
  credential, so the dam degrades to local-durable rather than to nothing.
* `HFDamStore`     -- a private Hugging Face dataset repo.

Both write ONE immutable object per event at
`pending/YYYY/MM/DD/<event_id>.json`, and record completion as a separate
`acked/...` object rather than by mutating or deleting the pending one. A
shared mutable `queue.json` would let concurrent callers stomp each other and
would destroy the audit trail; the leg calls this out and it is the reason
nothing here ever rewrites an existing object.

Space filesystems are ephemeral, so `LocalDamStore` is explicitly NOT the
backing for a deployed Space -- it is for trusted nodes and tests.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_SAFE = re.compile(r"[^A-Za-z0-9._:-]")


def object_path(prefix: str, event_id: str, created_utc: str) -> str:
    """`pending/2026/09/04/sha256:abcd....json` — date-partitioned, immutable."""
    date = (created_utc or "")[:10].replace("-", "/") or "0000/00/00"
    safe = _SAFE.sub("_", event_id)
    return f"{prefix}/{date}/{safe}.json"


class DamStore:
    """Interface. Implementations must never mutate an existing object."""

    def put_pending(self, env: Dict[str, Any]) -> str: ...
    def put_acked(self, event_id: str, created_utc: str,
                  receipt: Dict[str, Any]) -> str: ...
    def put_quarantine(self, event_id: str, created_utc: str,
                       reason: Dict[str, Any]) -> str: ...
    def list_pending(self) -> List[Dict[str, Any]]: ...
    def is_acked(self, event_id: str, created_utc: str) -> bool: ...
    def is_quarantined(self, event_id: str, created_utc: str) -> bool: ...


class LocalDamStore(DamStore):
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _write_once(self, rel: str, obj: Dict[str, Any]) -> str:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            # Immutable: re-sealing the same event is a no-op, not a rewrite.
            return rel
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)  # atomic; a torn read must never be possible
        return rel

    def put_pending(self, env: Dict[str, Any]) -> str:
        return self._write_once(
            object_path("pending", env["event_id"], env.get("created_utc", "")), env)

    def put_acked(self, event_id: str, created_utc: str,
                  receipt: Dict[str, Any]) -> str:
        return self._write_once(object_path("acked", event_id, created_utc), receipt)

    def put_quarantine(self, event_id: str, created_utc: str,
                       reason: Dict[str, Any]) -> str:
        return self._write_once(object_path("silt", event_id, created_utc), reason)

    def _iter(self, prefix: str) -> Iterator[Path]:
        base = self.root / prefix
        if base.exists():
            yield from sorted(base.rglob("*.json"))

    def list_pending(self) -> List[Dict[str, Any]]:
        out = []
        for p in self._iter("pending"):
            try:
                env = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            eid, created = env.get("event_id", ""), env.get("created_utc", "")
            if self.is_acked(eid, created) or self.is_quarantined(eid, created):
                continue
            out.append(env)
        # Oldest first: the dam drains in the order it filled.
        out.sort(key=lambda e: (e.get("created_utc") or "", e.get("event_id") or ""))
        return out

    def is_acked(self, event_id: str, created_utc: str) -> bool:
        return (self.root / object_path("acked", event_id, created_utc)).exists()

    def is_quarantined(self, event_id: str, created_utc: str) -> bool:
        return (self.root / object_path("silt", event_id, created_utc)).exists()


class HFDamStore(DamStore):
    """Private HF dataset repo. Durable across Space restarts.

    Space local disk is ephemeral, which is precisely why the queue lives in a
    Hub repo rather than on the Space filesystem -- acceptance test H ("Space
    restart does not lose queued writes") is a property of this choice.
    """

    def __init__(self, repo_id: str, token: Optional[str] = None,
                 repo_type: str = "dataset"):
        from huggingface_hub import HfApi  # imported lazily: tests need no HF
        self.repo_id = repo_id
        self.repo_type = repo_type
        self.api = HfApi(token=token)

    def _upload(self, rel: str, obj: Dict[str, Any]) -> str:
        import io
        data = json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")
        self.api.upload_file(
            path_or_fileobj=io.BytesIO(data), path_in_repo=rel,
            repo_id=self.repo_id, repo_type=self.repo_type,
            commit_message=f"dam: {rel}",
        )
        return rel

    def put_pending(self, env: Dict[str, Any]) -> str:
        return self._upload(
            object_path("pending", env["event_id"], env.get("created_utc", "")), env)

    def put_acked(self, event_id: str, created_utc: str,
                  receipt: Dict[str, Any]) -> str:
        return self._upload(object_path("acked", event_id, created_utc), receipt)

    def put_quarantine(self, event_id: str, created_utc: str,
                       reason: Dict[str, Any]) -> str:
        return self._upload(object_path("silt", event_id, created_utc), reason)

    def _listing(self) -> List[str]:
        return list(self.api.list_repo_files(self.repo_id, repo_type=self.repo_type))

    def list_pending(self) -> List[Dict[str, Any]]:
        files = self._listing()
        done = {f.rsplit("/", 1)[-1] for f in files
                if f.startswith(("acked/", "silt/"))}
        out = []
        for f in sorted(files):
            if not f.startswith("pending/"):
                continue
            if f.rsplit("/", 1)[-1] in done:
                continue
            local = self.api.hf_hub_download(
                self.repo_id, f, repo_type=self.repo_type)
            try:
                out.append(json.loads(Path(local).read_text(encoding="utf-8")))
            except Exception:
                continue
        out.sort(key=lambda e: (e.get("created_utc") or "", e.get("event_id") or ""))
        return out

    def _exists(self, prefix: str, event_id: str, created_utc: str) -> bool:
        return object_path(prefix, event_id, created_utc) in set(self._listing())

    def is_acked(self, event_id: str, created_utc: str) -> bool:
        return self._exists("acked", event_id, created_utc)

    def is_quarantined(self, event_id: str, created_utc: str) -> bool:
        return self._exists("silt", event_id, created_utc)
