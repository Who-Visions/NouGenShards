"""Local classifier arm: ollama with ``format`` = the request's JSON schema."""
from __future__ import annotations

import os
import time
import urllib.request

from ..types import DecisionReceipt, DecisionRequest
from . import _http
from .base import json_schema, parse_values, prompt, receipt


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str = "", host: str = "", timeout: float = 30.0, glosses=None):
        self.model = model or os.environ.get("NOUGEN_DECISION_OLLAMA_MODEL", "gemma4:e2b")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout
        self.glosses = glosses
        self.version = f"ollama:{self.model}"

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=2):
                return True
        except Exception:
            return False

    def decide(self, request: DecisionRequest) -> DecisionReceipt:
        t0 = time.monotonic()
        out = _http.post(f"{self.host}/api/chat", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt(request, self.glosses)}],
            "format": json_schema(request), "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": 64},
        }, {}, self.timeout)
        values = parse_values(request, (out.get("message") or {}).get("content", ""))
        return receipt(request, self.name, self.model, self.version, values,
                       (time.monotonic() - t0) * 1000)
