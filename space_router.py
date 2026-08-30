"""Space-side model inference router - the underground tunnel.

Exposes POST /v1/chat/completions (OpenAI shape) on the NouGenShards Space so
fleet clients route inference THROUGH the Space instead of hitting metered
provider surfaces directly (GM doctrine, shard #22353). The Space holds the
provider credentials; callers hold only the node token.

Self-contained on purpose: no imports from app.py (avoids a circular import),
auth re-reads the same env contract the node uses, and every knob resolves
from env with the constant as a logged fallback only.
"""

import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter()

_DEFAULT_MODEL = os.environ.get("NGS_ROUTER_DEFAULT_MODEL", "moonshotai/Kimi-K3")
_MAX_TOKENS_CAP = int(os.environ.get("NGS_ROUTER_MAX_TOKENS_CAP", "8192"))


def _node_token() -> Optional[str]:
    # Same contract as app.py: NGS_NODE_TOKEN primary, SHARD_GATEWAY_TOKEN legacy.
    return os.environ.get("NGS_NODE_TOKEN") or os.environ.get("SHARD_GATEWAY_TOKEN")


def _provider_token() -> Optional[str]:
    # Space secrets: standard HF names first, NouGen names as fallback.
    for key in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "AGY_HF_API", "HUGGINGFACE_API_KEY"):
        val = os.environ.get(key)
        if val and val.strip():
            return val.strip()
    return None


def _verify(authorization: Optional[str], x_ngs_token: Optional[str]) -> None:
    expected = _node_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Node token not configured; router is deny-by-default.")
    supplied = x_ngs_token
    if not supplied and authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid node token. Send X-NGS-Token or Authorization: Bearer <token>.")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


@router.get("/v1/models")
def list_models(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_ngs_token: Optional[str] = Header(None, alias="X-NGS-Token"),
) -> Dict[str, Any]:
    _verify(authorization, x_ngs_token)
    return {
        "object": "list",
        "data": [{"id": _DEFAULT_MODEL, "object": "model", "owned_by": "nougen-space-router"}],
        "note": "Router proxies arbitrary provider model ids; this lists only the default.",
    }


@router.post("/v1/chat/completions")
def chat_completions(
    body: ChatRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_ngs_token: Optional[str] = Header(None, alias="X-NGS-Token"),
) -> Dict[str, Any]:
    _verify(authorization, x_ngs_token)
    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must be non-empty")

    token = _provider_token()
    if not token:
        raise HTTPException(status_code=503, detail="No provider token configured on the Space (HF_TOKEN et al absent).")

    model = (body.model or _DEFAULT_MODEL).strip()
    max_tokens = min(body.max_tokens or 2048, _MAX_TOKENS_CAP)
    temperature = body.temperature if body.temperature is not None else 0.5

    try:
        from huggingface_hub import InferenceClient
    except ImportError as ie:
        raise HTTPException(status_code=503, detail=f"huggingface_hub unavailable on this node: {ie}")

    started = time.time()
    try:
        client = InferenceClient(token=token)
        res = client.chat.completions.create(
            model=model,
            messages=[m.model_dump() for m in body.messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        # Surface the provider failure honestly; the caller owns its fallback chain.
        raise HTTPException(status_code=502, detail=f"Provider inference failed for '{model}': {e}")

    if not res.choices:
        raise HTTPException(status_code=502, detail=f"Provider returned no choices for '{model}'.")

    content = res.choices[0].message.content or ""
    usage = getattr(res, "usage", None)
    return {
        "id": f"ngsr-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(started),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": getattr(res.choices[0], "finish_reason", None) or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        },
        "router": {"node": "nougen-space-router", "elapsed_ms": int((time.time() - started) * 1000)},
    }
