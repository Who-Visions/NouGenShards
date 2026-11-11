"""NVIDIA NIM lane (build.nvidia.com), OpenAI-compatible.

The key comes from the Keymaker (NVIDIA_API_KEY) and the base URL from its usage
record, so nothing here holds a secret or a second copy of the endpoint.

The catalog lists many models this account cannot call: /models returns them, but
a call gets 404 (not deployed for the account), 410 (retired) or hangs with no
first token. So `chat` walks a verified list and moves to the next model on any of
those, instead of returning a failure from the first one it tried. `probe` re-checks
which models answer, so the list can be refreshed from evidence.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import urllib.error
import urllib.request
from typing import Dict, Iterable, List, Optional, Tuple

from . import key_usage, keymaker
from .lane_header import LaneTools
from .models_client import LLMClient

KEY_NAME = "NVIDIA_API_KEY"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Answered 200 for this account on 2026-11-10 (phoebus), most reliable first.
# Availability moves: gemma-4-31b hung for 280s and then answered in 0.4s the
# same morning, and gpt-oss-20b answered once and timed out the next time.
# Treat this as an ordering, not a guarantee; chat() falls through on failure.
VERIFIED_CHAT_MODELS: Tuple[str, ...] = (
    "nvidia/nemotron-3.5-bolt-e4b",
    "google/gemma-4-31b-it",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "openai/gpt-oss-20b",
)
VERIFIED_EMBED_MODELS: Tuple[str, ...] = (
    "nvidia/nemotron-3.5-embed-1b",
    "nvidia/nemotron-3.5-embed-8b",
    "nvidia/nemotron-3-embed-1b",
)

# Statuses that mean "this model, not the request": try the next model.
_SKIP_STATUSES = {404, 410, 429, 500, 502, 503, 504}
# Reasoning models spend tokens before answering; fewer leaves content empty.
_MIN_MAX_TOKENS = 256


def _timeout() -> float:
    try:
        return max(5.0, float(os.getenv("NOUGEN_NVIDIA_TIMEOUT", "60")))
    except ValueError:
        return 60.0


class NvidiaNimClient(LLMClient):
    """Chat and embeddings on NVIDIA NIM with per-model fallback."""

    lane_tools = LaneTools("nvidia")

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or keymaker.get_secret(KEY_NAME)
        usage = key_usage.usage_for(KEY_NAME) or {}
        self.base_url = (base_url or usage.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.last_model: Optional[str] = None
        self.pinned_embed_model: Optional[str] = None
        self.last_errors: Dict[str, str] = {}

    # --------------------------------------------------------------- transport
    def _request(self, path: str, body: Optional[dict] = None,
                 timeout: Optional[float] = None) -> Tuple[object, Optional[dict]]:
        """(status, json) for one call. Status is an int, or an exception name when
        there was no HTTP answer (timeout, DNS). Never raises."""
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            method="POST" if body is not None else "GET",
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        try:
            with urllib.request.urlopen(req, timeout=timeout or _timeout()) as res:
                return res.status, json.loads(res.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            return exc.code, None
        except (urllib.error.URLError, http.client.HTTPException, socket.timeout,
                TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
            return type(exc).__name__, None

    # --------------------------------------------------------------- LLMClient
    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        """Every model the catalog lists, callable or not. Use probe() to know which answer."""
        status, data = self._request("/models", timeout=30)
        if status != 200 or not data:
            return []
        return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))

    def chat(self, model: Optional[str], messages: list, stream: bool = False,
             max_tokens: int = 1024, fallbacks: Optional[Iterable[str]] = None) -> str:
        """Answer from ``model``, or the first verified model that answers.

        ``model`` of None or "auto" uses the verified list. A named model is tried
        first, then the verified list, unless ``fallbacks`` is given (pass () to
        disable fallback). Returns "Error: ..." when no model answers, like the
        other clients. ``stream`` is accepted for interface parity and ignored.
        """
        if not self.api_key:
            return f"Error: {KEY_NAME} missing from the Keymaker."
        chain = self._chain(model, fallbacks)
        messages = self._with_lane_header(messages)
        self.last_errors = {}
        for name in chain:
            body = {"model": name, "messages": messages,
                    "max_tokens": max(max_tokens, _MIN_MAX_TOKENS)}
            status, data = self._request("/chat/completions", body)
            if status == 200 and data:
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                content = (msg.get("content") or "").strip()
                if content:
                    self.last_model = name
                    return content
                self.last_errors[name] = "empty content"
                continue
            self.last_errors[name] = str(status)
            if isinstance(status, int) and status not in _SKIP_STATUSES:
                break  # 400/401/403: the request or key is wrong, another model won't help
        self.last_model = None
        detail = ", ".join(f"{m}={e}" for m, e in self.last_errors.items())
        return f"Error: no NVIDIA model answered ({detail})"

    def reset_embed_model(self) -> None:
        """Clear any pinned auto-selected embedding model before re-indexing."""
        self.pinned_embed_model = None

    def embed(self, model: Optional[str], text: str, input_type: str = "passage") -> list:
        vectors = self.batch_embed(model, [text], input_type=input_type)
        return vectors[0] if vectors else []

    def batch_embed(self, model: Optional[str], texts: List[str],
                    input_type: str = "passage") -> List[list]:
        """Vectors for ``texts`` pinned to a single embedding space.

        Unlike chat, embeddings cannot silently switch models mid-index:
        - Explicit ``model`` never falls back to another model.
        - ``None`` / ``"auto"`` probes ``VERIFIED_EMBED_MODELS`` until one
          succeeds, then pins ``self.pinned_embed_model`` so subsequent
          batches/queries fail instead of mixing incompatible vector spaces.
        """
        if not texts or not self.api_key:
            return [[] for _ in texts]
        explicit = bool(model and model != "auto")
        if explicit:
            chain = [model]
        elif self.pinned_embed_model:
            chain = [self.pinned_embed_model]
        else:
            chain = list(VERIFIED_EMBED_MODELS)
        self.last_errors = {}
        for name in chain:
            status, data = self._request("/embeddings", {
                "model": name, "input": list(texts), "input_type": input_type,
                "encoding_format": "float"})
            if status == 200 and data and data.get("data"):
                self.last_model = name
                if self.pinned_embed_model is None or explicit:
                    self.pinned_embed_model = name
                rows = sorted(data["data"], key=lambda r: r.get("index", 0))
                return [r.get("embedding", []) for r in rows]
            self.last_errors[name] = "empty data" if status == 200 else str(status)
            if isinstance(status, int) and status not in _SKIP_STATUSES:
                break
        self.last_model = None
        return [[] for _ in texts]

    # --------------------------------------------------------------- evidence
    def probe(self, models: Optional[Iterable[str]] = None,
              timeout: float = 90) -> Dict[str, object]:
        """Status per model for a one-word chat. 200 means it answers this account."""
        out: Dict[str, object] = {}
        for name in models or VERIFIED_CHAT_MODELS:
            status, data = self._request("/chat/completions", {
                "model": name, "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": _MIN_MAX_TOKENS}, timeout=timeout)
            out[name] = status
        return out

    @staticmethod
    def _chain(model: Optional[str], fallbacks: Optional[Iterable[str]],
               verified: Tuple[str, ...] = VERIFIED_CHAT_MODELS) -> List[str]:
        rest = list(verified if fallbacks is None else fallbacks)
        if not model or model == "auto":
            return rest or list(verified)
        return [model] + [m for m in rest if m != model]
