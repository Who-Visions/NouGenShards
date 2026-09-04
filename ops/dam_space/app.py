"""HF Space front for the shard capture dam.

This Space is dumb cargo storage on purpose. It holds the AES key for
NOTHING -- it receives ciphertext plus routing metadata, checks that the
request came from a NouGen front door, and writes one immutable object to a
private dataset repo. It cannot read a shard body, and a full compromise of
this Space yields encrypted blobs and timing metadata, nothing more.

Space local disk is ephemeral, so nothing durable is kept here: the queue
lives in the Hub repo, which is what makes a Space restart survivable.

Env (Space secrets):
  NOUGEN_DAM_REPO        private dataset repo id, e.g. nougenai/NouGenShardSpool-private
  NOUGEN_DAM_HF_TOKEN    fine-grained token, write-scoped to that repo ONLY
  NOUGEN_DAM_HMAC_KEY    hex; shared with the front door, gates ingress
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import time
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, Response
from huggingface_hub import HfApi

REPO = os.environ.get("NOUGEN_DAM_REPO", "")
TOKEN = os.environ.get("NOUGEN_DAM_HF_TOKEN", "")
HMAC_KEY = bytes.fromhex(os.environ.get("NOUGEN_DAM_HMAC_KEY", "") or "")

SCHEMA = "nougen.shard-spool.v1"
SPOOLABLE = {"shards_capture", "shards_amend"}
NEVER = {"shards_forget", "vault_put", "vault_list", "keymaker_ingest"}
_SAFE = re.compile(r"[^A-Za-z0-9._:-]")
MAX_BODY = 1_000_000  # one shard, not a bulk upload channel

app = FastAPI(title="NouGen Shard Capture Dam")
api = HfApi(token=TOKEN) if TOKEN else None


def _signing_basis(env: Dict[str, Any]) -> bytes:
    return json.dumps({k: env.get(k) for k in (
        "schema", "event_id", "idempotency_key", "operation", "created_utc",
        "lane", "fleet_key_fingerprint", "target", "payload_ciphertext",
        "nonce", "aad_hash")}, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")


def _object_path(prefix: str, event_id: str, created_utc: str) -> str:
    date = (created_utc or "")[:10].replace("-", "/") or "0000/00/00"
    return f"{prefix}/{date}/{_SAFE.sub('_', event_id)}.json"


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "repo_configured": bool(REPO and api),
            "ingress_signed": bool(HMAC_KEY),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


@app.post("/spool")
async def spool(request: Request) -> Dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "envelope too large")
    try:
        env = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "body is not JSON")

    if env.get("schema") != SCHEMA:
        raise HTTPException(400, f"unknown schema {env.get('schema')!r}")

    op = str(env.get("operation") or "")
    if op in NEVER or op not in SPOOLABLE:
        # Refused at the door. A queue that accepts shards_forget is a queue
        # that can replay an irreversible deletion.
        raise HTTPException(403, f"operation {op!r} may not be spooled")

    # Ingress signature stops arbitrary queue injection by anyone who finds
    # the Space URL.
    if HMAC_KEY:
        sig = str(env.get("ingress_sig") or "")
        want = hmac.new(HMAC_KEY, _signing_basis(env), hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(sig, want):
            raise HTTPException(401, "ingress signature invalid")

    for field in ("event_id", "payload_ciphertext", "nonce", "aad_hash",
                  "created_utc"):
        if not env.get(field):
            raise HTTPException(400, f"missing {field}")

    if not (REPO and api):
        raise HTTPException(503, "dam repo not configured")

    path = _object_path("pending", str(env["event_id"]), str(env["created_utc"]))
    existing = set(api.list_repo_files(REPO, repo_type="dataset"))
    if path in existing:
        # Immutable: same event, same object. Not an error.
        return {"stored": True, "duplicate": True, "path": path,
                "event_id": env["event_id"], "state": "DAM_PENDING"}

    api.upload_file(
        path_or_fileobj=io.BytesIO(json.dumps(env, indent=2,
                                              sort_keys=True).encode("utf-8")),
        path_in_repo=path, repo_id=REPO, repo_type="dataset",
        commit_message=f"dam: spool {env['event_id']}",
    )
    return {"stored": True, "duplicate": False, "path": path,
            "event_id": env["event_id"], "state": "DAM_PENDING",
            "captured": False, "replay_required": True}


@app.head("/spool/{event_id}")
def probe(event_id: str) -> Response:
    if not (REPO and api):
        return Response(status_code=503)
    safe = _SAFE.sub("_", event_id)
    files = api.list_repo_files(REPO, repo_type="dataset")
    hit = any(f.endswith(f"/{safe}.json") for f in files)
    return Response(status_code=200 if hit else 404)
