"""Cloud arm: any OpenAI-compatible endpoint with json_schema response_format.
Default OpenRouter; key from env or the Keymaker, never logged."""
from __future__ import annotations

import os
import time

from ..types import DecisionReceipt, DecisionRequest
from . import _http
from .base import json_schema, parse_values, prompt, receipt


def _key(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        from ... import keymaker
        return (keymaker.get_secret(name) or "").strip()
    except Exception:
        return ""


class StructuredLLMBackend:
    name = "structured_llm"

    def __init__(self, model: str = "", url: str = "", key_name: str = "OPENROUTER_API_KEY",
                 timeout: float = 30.0, glosses=None):
        self.model = model or os.environ.get("NOUGEN_DECISION_LLM_MODEL", "google/gemini-2.5-flash-lite")
        self.url = url or "https://openrouter.ai/api/v1/chat/completions"
        self.key_name = key_name
        self.timeout = timeout
        self.glosses = glosses
        self.version = f"llm:{self.model}"

    def available(self) -> bool:
        return bool(_key(self.key_name))

    def decide(self, request: DecisionRequest) -> DecisionReceipt:
        t0 = time.monotonic()
        out = _http.post(self.url, {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt(request, self.glosses)}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": request.namespace.replace(".", "_"), "strict": True,
                "schema": json_schema(request)}},
            "temperature": 0, "max_tokens": 64,
        }, {"Authorization": f"Bearer {_key(self.key_name)}"}, self.timeout)
        choices = out.get("choices") or [{}]
        values = parse_values(request, (choices[0].get("message") or {}).get("content", ""))
        return receipt(request, self.name, self.model, self.version, values,
                       (time.monotonic() - t0) * 1000)
