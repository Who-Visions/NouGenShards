"""Route a tool's chat call to local Ollama or to NVIDIA NIM by model name.

Ollama's cloud models (``gemma4:31b-cloud``) stopped being free on 2026-11-18,
so the tools that used one as their big-model choice now use NVIDIA through the
Keymaker's ``NVIDIA_API_KEY`` instead. A model name starting with ``nvidia:``
goes to NVIDIA (``nvidia:auto`` lets the client walk its verified list; any
other suffix is an NVIDIA model id, tried first). Every other name goes to the
local Ollama server exactly as before.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

NVIDIA_PREFIX = "nvidia:"
NVIDIA_DEFAULT = os.environ.get("NOUGEN_NVIDIA_MODEL", "nvidia:auto")


def is_nvidia(model: str) -> bool:
    return bool(model) and model.startswith(NVIDIA_PREFIX)


def nvidia_available() -> bool:
    """True when this machine has an NVIDIA key. Never raises."""
    try:
        return _client().is_alive()
    except Exception:  # pylint: disable=broad-except
        return False


def _client():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "src")
    if root not in sys.path:
        sys.path.insert(0, root)
    from nougen_shards.nvidia_nim import NvidiaNimClient  # noqa: E402
    return NvidiaNimClient()


def pick(prefs, local_models):
    """First preference that can run here: a local Ollama model that is
    installed, or an ``nvidia:`` entry when the NVIDIA key is present."""
    for pref in prefs:
        if is_nvidia(pref):
            if nvidia_available():
                return pref
        elif pref in local_models:
            return pref
    return None


def chat(model: str, prompt: str, ollama_url: str, timeout: float = 600,
         max_tokens: int = 4096) -> str:
    """One user turn. Raises RuntimeError when NVIDIA gives no answer, so callers
    keep their existing error handling for a failed model call."""
    if is_nvidia(model):
        name = model[len(NVIDIA_PREFIX):]
        detail = _client().chat_detail(None if name in ("", "auto") else name,
                                       [{"role": "user", "content": prompt}],
                                       max_tokens=max_tokens, timeout=timeout)
        if not detail["content"]:
            raise RuntimeError(f"no NVIDIA model answered: {detail['errors']}")
        return detail["content"]
    payload = json.dumps({
        "model": model, "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{ollama_url}/api/chat", data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]
