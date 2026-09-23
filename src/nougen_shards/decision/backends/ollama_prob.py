"""Calibrated local arm: option probabilities read from token logprobs, not from a JSON reply.

``OllamaBackend`` returns a bare choice with confidence 0.0. This arm asks for ONE letter per
question and reads the logprobs of the option letters at that position, so every answer carries a
full probability distribution (the property that makes a system-one decider usable behind a
threshold). Temperature scaling (``fit_temperature``) turns the raw softmax into calibrated
confidence. Choice and noul questions are supported; a score question voids the reply, as any
unanswerable field does in ``parse_values``.
"""
from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import urllib.request

from ..types import ChoiceSpec, DecisionReceipt, DecisionRequest, DecisionValue, ScoreSpec
from . import _http
from .base import STATE_CHARS, receipt

_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_NOUL_OPTIONS: Tuple[Any, ...] = (True, False, None)
_NOUL_TEXT = ("yes", "no", "unknown")


def normalize_host(raw: str) -> str:
    """OLLAMA_HOST is often a bare bind address ("0.0.0.0", "host:port"): make it a dialable URL."""
    h = (raw or "").strip().rstrip("/") or "127.0.0.1"
    scheme = "http://"
    if "://" in h:
        scheme, h = h.split("://", 1)
        scheme += "://"
    host, _, port = h.partition(":")
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    return f"{scheme}{host}:{port or '11434'}"


def softmax(logits: Sequence[float], temperature: float = 1.0) -> List[float]:
    t = temperature if temperature > 0 else 1.0
    m = max(logits)
    exps = [math.exp((x - m) / t) for x in logits]
    total = sum(exps)
    return [e / total for e in exps]


def fit_temperature(examples: Iterable[Tuple[Sequence[float], int]], lo: float = 0.25,
                    hi: float = 8.0, steps: int = 200) -> float:
    """Grid-search the temperature minimising negative log-likelihood on (logits, true_index)."""
    data = list(examples)
    if not data:
        return 1.0
    best_t, best_nll = 1.0, float("inf")
    for i in range(steps + 1):
        t = lo * (hi / lo) ** (i / steps)
        nll = -sum(math.log(max(softmax(lg, t)[y], 1e-12)) for lg, y in data) / len(data)
        if nll < best_nll:
            best_t, best_nll = t, nll
    return best_t


def _load_temperature(path: str, model: str, namespace: str) -> Optional[float]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            table = json.load(f)
        t = table.get(f"{model}|{namespace}") or table.get(model)
        return float(t) if t else None
    except (OSError, ValueError, TypeError):
        return None


class OllamaProbBackend:
    name = "ollama_prob"

    def __init__(self, model: str = "", host: str = "", timeout: float = 30.0,
                 temperature: Optional[float] = None, calibration_path: str = "",
                 workers: int = 0, rotations: int = 0):
        self.model = model or os.environ.get("NOUGEN_DECISION_OLLAMA_MODEL", "gemma4:e2b")
        self.host = normalize_host(host or os.environ.get("OLLAMA_HOST", ""))
        self.timeout = timeout
        self.calibration_path = calibration_path or os.environ.get("NOUGEN_DECISION_CALIBRATION", "")
        self._fixed_t = temperature
        self.workers = workers or int(os.environ.get("NOUGEN_DECISION_WORKERS", "8"))
        # cyclic option rotations averaged to cancel letter/position bias (0 = env, default 1)
        self.rotations = max(1, rotations or int(os.environ.get("NOUGEN_DECISION_ROTATIONS", "1")))
        self.version = f"ollama_prob:{self.model}:r{self.rotations}"

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=2):
                return True
        except Exception:
            return False

    def _temperature(self, namespace: str) -> float:
        if self._fixed_t:
            return self._fixed_t
        if self.calibration_path:
            t = _load_temperature(self.calibration_path, self.model, namespace)
            if t:
                return t
        return 1.0

    def _prompt(self, request: DecisionRequest, q, shift: int = 0) -> Tuple[str, Tuple[Any, ...]]:
        if isinstance(q, ChoiceSpec):
            options: Tuple[Any, ...] = tuple(q.options)
            labels = [str(o) for o in options]
            ask = q.description
        else:
            options, labels, ask = _NOUL_OPTIONS, list(_NOUL_TEXT), q.description
        options, labels = options[shift:] + options[:shift], labels[shift:] + labels[:shift]
        menu = "\n".join(f"{_LETTERS[i]}. {lab}" for i, lab in enumerate(labels))
        state = json.dumps(dict(request.state), default=str, ensure_ascii=False)[:STATE_CHARS]
        text = (f"Decision namespace: {request.namespace}.\nState:\n{state}\n\n"
                f"Question ({q.key}): {ask}\n{menu}\n\nAnswer with the single letter only.")
        return text, options

    def _logits(self, request: DecisionRequest, q, shift: int) -> Tuple[Tuple[Any, ...], List[float]]:
        text, options = self._prompt(request, q, shift)
        out = _http.post(f"{self.host}/api/chat", {
            "model": self.model, "messages": [{"role": "user", "content": text}],
            "stream": False, "think": False, "logprobs": True,
            "top_logprobs": min(20, max(len(options) * 3, 10)),
            "options": {"temperature": 0, "num_predict": 1},
        }, {}, self.timeout)
        tops = _first_token_top(out)
        letters = _LETTERS[: len(options)]
        floor = min(tops.values()) - 5.0 if tops else -30.0
        logits = [_best(tops, ch, floor) for ch in letters]
        if all(v == floor for v in logits):
            raise ValueError(f"no option letter in top logprobs for {q.key}")
        return options, logits

    def _one(self, request: DecisionRequest, q) -> DecisionValue:
        base = tuple(q.options) if isinstance(q, ChoiceSpec) else _NOUL_OPTIONS
        n = len(base)
        agg = [0.0] * n
        t = self._temperature(request.namespace)
        shifts = [(i * n) // self.rotations % n for i in range(self.rotations)]
        for sh in shifts:
            options, logits = self._logits(request, q, sh)
            probs = softmax(logits, t)
            for j, opt in enumerate(options):
                agg[base.index(opt)] += math.log(max(probs[j], 1e-9)) / len(shifts)
        probs = softmax(agg)  # geometric mean of per-rotation probabilities, renormalised
        i = max(range(n), key=probs.__getitem__)
        dist = {str(base[j]) if base[j] is not None else "null": round(probs[j], 6) for j in range(n)}
        return DecisionValue(q.key, base[i], confidence=round(probs[i], 6), probabilities=dist)

    def decide(self, request: DecisionRequest) -> DecisionReceipt:
        t0 = time.monotonic()
        if any(isinstance(q, ScoreSpec) for q in request.questions):
            values: Tuple[DecisionValue, ...] = ()
        else:
            try:
                with ThreadPoolExecutor(max_workers=max(1, min(self.workers, len(request.questions)))) as ex:
                    values = tuple(ex.map(lambda q: self._one(request, q), request.questions))
            except (ValueError, OSError, KeyError):
                values = ()  # a partial answer is not a decision
        return receipt(request, self.name, self.model, self.version, values,
                       (time.monotonic() - t0) * 1000)


def _first_token_top(resp: Mapping[str, Any]) -> Dict[str, float]:
    lp = resp.get("logprobs") or (resp.get("message") or {}).get("logprobs") or []
    if not lp:
        return {}
    first = lp[0]
    tops = first.get("top_logprobs") or [{"token": first.get("token", ""), "logprob": first.get("logprob", -30.0)}]
    return {str(t.get("token", "")).strip().upper(): float(t.get("logprob", -30.0)) for t in tops}


def _best(tops: Mapping[str, float], letter: str, floor: float) -> float:
    return tops.get(letter, floor)
