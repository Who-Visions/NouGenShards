"""HF Space write-ahead buffer API (private Space).

POST /v1/shards/capture  bearer-auth; accept a shard, durable before 200.
GET  /v1/shards/pending  ?node=<name>&limit=200 ; unacked shards for a node.
POST /v1/shards/ack      {node, shas}; record a node's durable receipt.

Persistence is the local WriteAheadBuffer (SQLite + append-only JSONL). The
HF dataset mirror is attached in the Space's runtime, not here.
"""
import os
import secrets
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from nougen_shards.wal_buffer import WriteAheadBuffer

DB_PATH = os.environ.get("WAL_DB_PATH", "/data/pending_shards.db")
MIRROR_PATH = os.environ.get("WAL_MIRROR_PATH", "/data/wal.jsonl")
TOKEN = os.environ.get("WAL_BEARER_TOKEN", "")

app = FastAPI(title="NouGen shard WAL", version="0.1.0")
_buf: Optional[WriteAheadBuffer] = None


def buffer() -> WriteAheadBuffer:
    global _buf
    if _buf is None:
        _buf = WriteAheadBuffer(DB_PATH, mirror_path=MIRROR_PATH)
    return _buf


def require_bearer(authorization: Optional[str] = Header(default=None)) -> None:
    # Fail closed: no configured token means nobody gets in.
    if not TOKEN:
        raise HTTPException(status_code=503, detail="WAL_BEARER_TOKEN not configured")
    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(presented, TOKEN):
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


@app.post("/v1/shards/capture", dependencies=[Depends(require_bearer)])
def capture(body: CaptureIn):
    try:
        res = buffer().capture(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", **res}


@app.get("/v1/shards/pending", dependencies=[Depends(require_bearer)])
def pending(node: str, limit: int = 200):
    limit = max(1, min(int(limit), 500))
    return {"node": node.lower(), "shards": buffer().pending_for(node, limit=limit)}


@app.post("/v1/shards/ack", dependencies=[Depends(require_bearer)])
def ack(body: AckIn):
    return {"node": body.node.lower(), "newly_acked": buffer().ack(body.node, body.shas)}
