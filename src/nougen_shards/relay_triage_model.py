"""Model-backed arm of relay triage: the Jev pattern on local hardware.

``relay_triage.classify`` sorts a leg with ordered rules. This module asks a
model the same question with the same closed menu (``relay_triage.LABELS``):
the leg goes in, exactly one label comes out. The model cannot write prose --
the reply is constrained to a JSON object whose only field is an enum -- so a
verdict is always a member of the menu or it is ``None``.

Backends, tried in order (``NOUGEN_TRIAGE_BACKENDS``, default ``ollama,openrouter``):

  * ``ollama``     local, ``format`` = JSON schema. Model: ``NOUGEN_TRIAGE_MODEL``
                   (default ``gemma4:e2b`` -- the smallest resident model; phoebus is
                   a 16GB CPU-only box, so a bigger one stalls in swap).
  * ``openrouter`` cloud fallback, ``response_format`` = json_schema. Model:
                   ``NOUGEN_TRIAGE_OR_MODEL``. Key from the Keymaker, never logged.

A backend failure is not a verdict: ``classify_model`` returns ``None`` and the
caller keeps the rule verdict. ``shadow`` runs both arms and reports agreement;
it never changes what gets delivered.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .relay_triage import LABELS, SURFACE, Verdict, classify

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
BODY_CHARS = 1200

_GLOSS = {
    "CLOSED": "leg is finished/terminal; nothing to do",
    "ECHO_OWN": "this node wrote the leg itself; it is our own message coming back",
    "AUTO_NOTE": "automatic hook/daemon note (e.g. 'session ended with N uncommitted files')",
    "OTHER_LANE": "addressed to a different node or lane, not this one",
    "NEEDS_OWNER": "asks the owner (Dave) to decide, approve, or lock something",
    "ACTIONABLE": "asks this node or any node to do concrete work now",
    "STATUS_FYI": "reports results or status; no ask",
    "STALE": "old open leg, not addressed here, overtaken by events",
    "UNKNOWN": "cannot tell; a human should look",
}

_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": list(LABELS)}},
    "required": ["label"],
    "additionalProperties": False,
}


def _prompt(leg: Mapping[str, Any], me: str) -> str:
    menu = "\n".join(f"- {k}: {v}" for k, v in _GLOSS.items())
    body = str(leg.get("body") or leg.get("message") or "")[:BODY_CHARS]
    return (
        f"You triage relay legs for fleet node '{me or 'unknown'}'. "
        "Pick exactly one label.\n\nLabels:\n" + menu + "\n\n"
        f"Leg id: {leg.get('id', '')}\n"
        f"From: {leg.get('machine', '?')}/{leg.get('agent', '?')}\n"
        f"Status: {leg.get('status') or leg.get('state') or '?'}\n"
        f"Goal: {leg.get('goal', '')}\n"
        f"Body: {body}\n\n"
        'Answer as JSON: {"label": "<LABEL>"}'
    )


def _post(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _parse(text: str) -> Optional[str]:
    try:
        label = json.loads(text).get("label")
    except (ValueError, AttributeError):
        return None
    return label if label in LABELS else None


def _ollama(prompt: str, timeout: float) -> Optional[str]:
    out = _post(f"{OLLAMA_URL}/api/chat", {
        "model": os.environ.get("NOUGEN_TRIAGE_MODEL", "gemma4:e2b"),
        "messages": [{"role": "user", "content": prompt}],
        "format": _SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 32},
    }, {}, timeout)
    return _parse((out.get("message") or {}).get("content", ""))


def _openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    try:
        from . import keymaker
        return (keymaker.get_secret("OPENROUTER_API_KEY") or "").strip()
    except Exception:
        return ""


def _openrouter(prompt: str, timeout: float) -> Optional[str]:
    key = _openrouter_key()
    if not key:
        return None
    out = _post(OR_URL, {
        "model": os.environ.get("NOUGEN_TRIAGE_OR_MODEL", "google/gemini-2.5-flash-lite"),
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "triage", "strict": True, "schema": _SCHEMA}},
        "temperature": 0,
        "max_tokens": 32,
    }, {"Authorization": f"Bearer {key}"}, timeout)
    choices = out.get("choices") or [{}]
    return _parse((choices[0].get("message") or {}).get("content", ""))


BACKENDS = {"ollama": _ollama, "openrouter": _openrouter}


def classify_model(leg: Mapping[str, Any], me: Optional[str] = None, *,
                   backends: Optional[str] = None, timeout: float = 30.0) -> Optional[Verdict]:
    """One label from the first backend that answers inside the menu, else None."""
    node = (me or os.environ.get("NOUGEN_MACHINE") or "").strip().lower()
    prompt = _prompt(leg, node)
    order = backends or os.environ.get("NOUGEN_TRIAGE_BACKENDS", "ollama,openrouter")
    for name in (b.strip() for b in order.split(",") if b.strip()):
        fn = BACKENDS.get(name)
        if fn is None:
            continue
        t0 = time.monotonic()
        try:
            label = fn(prompt, timeout)
        except Exception:  # timeout, refused, HTTP error: try the next backend
            label = None
        if label:
            return Verdict(label, f"M-{name}", f"{time.monotonic() - t0:.1f}s")
    return None


def shadow(leg: Mapping[str, Any], me: Optional[str] = None, *,
           log: Optional[Path] = None, **kw: Any) -> Dict[str, Any]:
    """Run both arms. The rule verdict stays authoritative; this only records.

    ``agree_surface`` is the comparison that matters: two labels can differ
    (STATUS_FYI vs CLOSED) while both correctly stay silent.
    """
    rule = classify(leg, me)
    model = classify_model(leg, me, **kw)
    row = {
        "id": leg.get("id"),
        "rule": rule.label, "rule_id": rule.rule,
        "model": model.label if model else None,
        "backend": model.rule if model else None,
        "agree": bool(model) and model.label == rule.label,
        "agree_surface": bool(model) and model.surface() == rule.surface(),
        "ts": time.time(),
    }
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    return row


__all__ = ["classify_model", "shadow", "BACKENDS", "SURFACE"]
