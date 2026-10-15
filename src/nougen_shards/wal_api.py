"""Write-ahead buffer API: the HF hallway, mounted in the node app.

Front door -> this hallway -> node rooms.

POST /v1/shards/capture  token-auth; durable (SQLite + JSONL) before 200.
GET  /v1/shards/pending  ?node=<name>&limit=200 ; unacked shards for a node.
POST /v1/shards/ack      {node, shas}; a node's durable receipt.
GET  /v1/shards/health   liveness and whether dataset commits are on.

Auth: X-NGS-Token or X-WAL-Token must equal WAL_BEARER_TOKEN (fallback
NGS_NODE_TOKEN). Fails closed with 503 when neither is configured.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import urllib.request
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from nougen_shards.wal_buffer import WriteAheadBuffer

DB_PATH = os.environ.get("WAL_DB_PATH", "/data/pending_shards.db")
MIRROR_PATH = os.environ.get("WAL_MIRROR_PATH", "/data/wal/wal.jsonl")
TOKEN = os.environ.get("WAL_BEARER_TOKEN") or os.environ.get("NGS_NODE_TOKEN", "")
# name=url pairs: "blade=https://.../v1/shards/capture,whoart=https://..."
NODE_URLS = dict(p.split("=", 1) for p in os.environ.get("WAL_NODE_URLS", "").split(",") if "=" in p)
NODE_TOKEN = os.environ.get("WAL_NODE_TOKEN", "")

router = APIRouter(prefix="/v1/shards", tags=["wal"])
_buf: Optional[WriteAheadBuffer] = None
_scheduler = None


def buffer() -> WriteAheadBuffer:
    global _buf
    if _buf is None:
        _buf = WriteAheadBuffer(DB_PATH, mirror_path=MIRROR_PATH)
    return _buf


def start_dataset_commits() -> bool:
    """Spec: append-only JSONL committed to the private dataset via CommitScheduler."""
    global _scheduler
    repo = os.environ.get("WAL_DATASET_REPO", "")
    hf_token = os.environ.get("HF_TOKEN", "")
    if _scheduler is not None or not repo or not hf_token:
        return _scheduler is not None
    from huggingface_hub import CommitScheduler
    folder = os.path.dirname(os.path.abspath(MIRROR_PATH))
    os.makedirs(folder, exist_ok=True)
    _scheduler = CommitScheduler(repo_id=repo, repo_type="dataset", folder_path=folder,
                                 path_in_repo="wal", every=5, private=True, token=hf_token)
    return True


def require_token(x_ngs_token: Optional[str] = Header(default=None),
                  x_wal_token: Optional[str] = Header(default=None)) -> None:
    if not TOKEN:
        raise HTTPException(status_code=503, detail="WAL token not configured")
    presented = x_wal_token or x_ngs_token or ""
    if not presented or not secrets.compare_digest(presented, TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


class CaptureIn(BaseModel):
    title: str
    content: str
    event_type: str = "KNOWLEDGE"
    tags: Optional[List[str]] = None
    event_time: Optional[str] = None
    capture_time: Optional[str] = None
    via: Optional[str] = None


class AckIn(BaseModel):
    node: str
    shas: List[str]


def _post_to_node(url: str, record: dict) -> bool:
    req = urllib.request.Request(
        url, data=json.dumps(record).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-NGS-Token": NODE_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except OSError:
        return False


def _fanout(record: dict) -> None:
    targets = {name: (lambda rec, u=url: _post_to_node(u, rec)) for name, url in NODE_URLS.items()}
    buffer().fanout(record, targets)


@router.post("/capture", dependencies=[Depends(require_token)])
def capture(body: CaptureIn):
    try:
        record = body.model_dump()
        res = buffer().capture(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if NODE_URLS:
        # Spec step 2: fan out in the background; the 200 does not wait on nodes.
        threading.Thread(target=_fanout, args=(record,), daemon=True).start()
    return {"status": "ok", **res}


@router.get("/pending", dependencies=[Depends(require_token)])
def pending(node: str, limit: int = 200):
    limit = max(1, min(int(limit), 500))
    return {"node": node.lower(), "shards": buffer().pending_for(node, limit=limit)}


@router.post("/ack", dependencies=[Depends(require_token)])
def ack(body: AckIn):
    return {"node": body.node.lower(), "newly_acked": buffer().ack(body.node, body.shas)}


@router.get("/health")
def health():
    return {"ok": True, "dataset_commits": _scheduler is not None}
