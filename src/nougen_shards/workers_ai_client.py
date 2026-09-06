"""Cloudflare Workers AI as a FREE tool-calling lane (`workers-ai`).

Speaks the OpenAI-compatible chat endpoint Workers AI exposes under an
account's `/ai/v1` path and normalises the answer into the same dict shape
`OllamaClient.chat_raw` returns (`message.tool_calls` intact), so a tool loop
can swap lanes without reshaping anything.

Every environment-shaped value resolves env -> Keymaker -> logged fallback
(Rule 0.2). Nothing account-specific lives in this file.

A local day counter (`NeuronBudgetGuard`) refuses calls that would push the
machine past the free daily Neuron allocation, so the lane can never drift
into paid usage on its own.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import keymaker

logger = logging.getLogger(__name__)

LANE = "workers-ai"

ENV_ACCOUNT_ID = "NOUGEN_CF_ACCOUNT_ID"
ENV_TOKEN = "NOUGEN_CF_AI_TOKEN"
ENV_BASE_URL = "NOUGEN_CF_AI_BASE_URL"
ENV_MODEL = "NOUGEN_CF_AI_MODEL"
ENV_TIMEOUT_S = "NOUGEN_CF_AI_TIMEOUT_S"
ENV_DAILY_NEURONS = "NOUGEN_CF_AI_DAILY_NEURONS"
ENV_STATE_FILE = "NOUGEN_CF_AI_STATE_FILE"
ENV_STATE_DIR = "NOUGEN_STATE_DIR"
ENV_NEURONS_IN_PER_M = "NOUGEN_CF_AI_NEURONS_IN_PER_M"
ENV_NEURONS_OUT_PER_M = "NOUGEN_CF_AI_NEURONS_OUT_PER_M"
ENV_EST_OUTPUT_TOKENS = "NOUGEN_CF_AI_EST_OUTPUT_TOKENS"

# Keymaker key names tried, in order, when the env var is unset.
KEYMAKER_TOKEN_KEYS = (ENV_TOKEN, "CLOUDFLARE_API_TOKEN")
KEYMAKER_ACCOUNT_KEYS = (ENV_ACCOUNT_ID, "CLOUDFLARE_ACCOUNT_ID")

# Logged fallbacks only. Docs read 2026-09-06: free allocation is 10,000
# Neurons per day on both plans; gemma-4-26b-a4b-it bills 9,091 Neurons per M
# input tokens and 27,273 per M output tokens.
_FALLBACK_BASE_URL = "https://api.cloudflare.com/client/v4"
_FALLBACK_MODEL = "@cf/google/gemma-4-26b-a4b-it"
_FALLBACK_TIMEOUT_S = 60
_FALLBACK_DAILY_NEURONS = 10000
_FALLBACK_NEURONS_IN_PER_M = 9091
_FALLBACK_NEURONS_OUT_PER_M = 27273
_FALLBACK_EST_OUTPUT_TOKENS = 1024
_FALLBACK_CHARS_PER_TOKEN = 4
# Free-tier models that support function calling, per the docs; used only when
# the live catalogue cannot be reached.
FREE_TOOL_MODELS_SEED = [
    "@cf/google/gemma-4-26b-a4b-it",
    "@cf/qwen/qwen3-30b-a3b-fp8",
    "@cf/ibm-granite/granite-4.0-h-micro",
    "@cf/openai/gpt-oss-20b",
]


def _env_or(name: str, fallback: Any, cast=str) -> Any:
    raw = os.getenv(name)
    if raw is None or raw == "":
        logger.debug("%s unset; using logged fallback %r", name, fallback)
        return fallback
    try:
        return cast(raw)
    except (TypeError, ValueError):
        logger.warning("%s=%r is not a valid %s; using fallback %r", name, raw, cast.__name__, fallback)
        return fallback


def _secret(env_name: str, keymaker_keys) -> Optional[str]:
    """env first, then the Keymaker (DPAPI layers peeled by get_secret)."""
    value = os.getenv(env_name)
    if value:
        return value
    for key in keymaker_keys:
        try:
            found = keymaker.get_secret(key)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Keymaker lookup of %s failed: %s", key, exc)
            found = None
        if found:
            return found
    return None


def default_state_file() -> Path:
    raw = os.getenv(ENV_STATE_FILE)
    if raw:
        return Path(raw)
    state_dir = os.getenv(ENV_STATE_DIR)
    base = Path(state_dir) if state_dir else Path.home() / ".nougen" / "state"
    return base / "workers_ai_neurons.json"


class NeuronBudgetGuard:
    """Per-machine day counter of Neurons spent on the lane.

    Refuses any call whose estimated cost would push today's total past the
    limit. The counter resets when the calendar day changes.
    """

    def __init__(self, limit: Optional[int] = None, state_path: Optional[Path] = None):
        self.limit = int(limit) if limit is not None else _env_or(ENV_DAILY_NEURONS, _FALLBACK_DAILY_NEURONS, int)
        self.state_path = Path(state_path) if state_path else default_state_file()

    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if data.get("day") != self._today():
            data = {"day": self._today(), "neurons": 0.0, "calls": 0}
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(data), encoding="utf-8")
        except OSError as exc:
            logger.warning("could not persist neuron counter at %s: %s", self.state_path, exc)

    def spent_today(self) -> float:
        return float(self._load().get("neurons", 0.0))

    def remaining(self) -> float:
        return max(0.0, self.limit - self.spent_today())

    def would_exceed(self, neurons: float) -> bool:
        return self.spent_today() + float(neurons) > self.limit

    def record(self, neurons: float) -> float:
        data = self._load()
        data["neurons"] = float(data.get("neurons", 0.0)) + float(neurons)
        data["calls"] = int(data.get("calls", 0)) + 1
        self._save(data)
        return data["neurons"]


def neurons_for_tokens(prompt_tokens: float, completion_tokens: float) -> float:
    rate_in = _env_or(ENV_NEURONS_IN_PER_M, _FALLBACK_NEURONS_IN_PER_M, float)
    rate_out = _env_or(ENV_NEURONS_OUT_PER_M, _FALLBACK_NEURONS_OUT_PER_M, float)
    return (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000.0


class WorkersAIClient:
    """Chat client for Cloudflare Workers AI (OpenAI-compatible endpoint)."""

    def __init__(self, account_id: Optional[str] = None, token: Optional[str] = None,
                 base_url: Optional[str] = None, model: Optional[str] = None,
                 timeout_s: Optional[float] = None, guard: Optional[NeuronBudgetGuard] = None):
        self.account_id = account_id or _secret(ENV_ACCOUNT_ID, KEYMAKER_ACCOUNT_KEYS)
        self.token = token or _secret(ENV_TOKEN, KEYMAKER_TOKEN_KEYS)
        self.base_url = (base_url or _env_or(ENV_BASE_URL, _FALLBACK_BASE_URL)).rstrip("/")
        self.model = model or _env_or(ENV_MODEL, _FALLBACK_MODEL)
        self.timeout_s = float(timeout_s) if timeout_s is not None else _env_or(ENV_TIMEOUT_S, _FALLBACK_TIMEOUT_S, float)
        self.guard = guard or NeuronBudgetGuard()

    # ---- plumbing -------------------------------------------------------
    def is_alive(self) -> bool:
        return bool(self.account_id and self.token)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/accounts/{self.account_id}/ai/{path.lstrip('/')}"

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> Dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self._url(path), data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.token or ''}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as res:
                return json.loads(res.read().decode())
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode()[:300]
            except Exception:  # pylint: disable=broad-except
                pass
            return {"error": f"HTTP {exc.code}: {body or exc.reason}", "status": exc.code}
        except Exception as exc:  # pylint: disable=broad-except
            return {"error": str(exc)}

    # ---- catalogue ------------------------------------------------------
    def list_models(self, task: str = "Text Generation") -> List[str]:
        if not self.is_alive():
            return list(FREE_TOOL_MODELS_SEED)
        query = urllib.parse.urlencode({"task": task, "per_page": 100})
        raw = self._request("GET", f"models/search?{query}")
        names = [m.get("name") for m in raw.get("result", []) if isinstance(m, dict) and m.get("name")]
        if names:
            return names
        logger.info("workers-ai catalogue unavailable (%s); using seed list", raw.get("error", "empty"))
        return list(FREE_TOOL_MODELS_SEED)

    # ---- chat -----------------------------------------------------------
    @staticmethod
    def _estimate_prompt_tokens(messages: list, tools: Optional[list]) -> float:
        blob = json.dumps(messages) + (json.dumps(tools) if tools else "")
        return len(blob) / _FALLBACK_CHARS_PER_TOKEN

    def chat(self, model: Optional[str] = None, messages: Optional[list] = None,
             tools: Optional[list] = None, temperature: Optional[float] = None,
             max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """Returns the `OllamaClient.chat_raw` shape; `{"error": ...}` on refusal."""
        model = model or self.model
        messages = messages or []
        if not self.is_alive():
            return {"error": f"{LANE} lane not configured: set {ENV_ACCOUNT_ID} and {ENV_TOKEN} "
                             f"(or vault {KEYMAKER_ACCOUNT_KEYS[-1]} / {KEYMAKER_TOKEN_KEYS[-1]})",
                    "lane": LANE}
        est_out = float(max_tokens) if max_tokens else float(_env_or(ENV_EST_OUTPUT_TOKENS, _FALLBACK_EST_OUTPUT_TOKENS, int))
        estimate = neurons_for_tokens(self._estimate_prompt_tokens(messages, tools), est_out)
        if self.guard.would_exceed(estimate):
            return {"error": f"neuron budget guard refused: spent {self.guard.spent_today():.0f} + "
                             f"est {estimate:.0f} > {self.guard.limit} ({ENV_DAILY_NEURONS})",
                    "lane": LANE, "budget_refused": True}
        payload: Dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        started = time.monotonic()
        raw = self._request("POST", "v1/chat/completions", payload)
        latency = time.monotonic() - started
        if "error" in raw:
            raw.setdefault("lane", LANE)
            raw["latency_s"] = round(latency, 3)
            return raw
        out = self.normalise(raw, model)
        out["latency_s"] = round(latency, 3)
        usage = out.get("usage") or {}
        spent = usage.get("neurons")
        if spent is None:
            spent = neurons_for_tokens(float(usage.get("prompt_tokens", 0) or 0),
                                       float(usage.get("completion_tokens", 0) or 0))
            out["neurons_estimated"] = True
        out["neurons"] = round(float(spent), 3)
        out["neurons_today"] = round(self.guard.record(spent), 3)
        return out

    @staticmethod
    def normalise(raw: Dict[str, Any], model: str) -> Dict[str, Any]:
        """OpenAI chat.completion -> Ollama /api/chat shape (tool_calls kept)."""
        choice = (raw.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = []
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except ValueError:
                    args = {"_raw": args}
            entry: Dict[str, Any] = {"function": {"name": fn.get("name"), "arguments": args}}
            if call.get("id"):
                entry["id"] = call["id"]
            tool_calls.append(entry)
        message: Dict[str, Any] = {"role": msg.get("role", "assistant"), "content": msg.get("content") or ""}
        if tool_calls:
            message["tool_calls"] = tool_calls
        # gemma-4 on Workers AI spends completion tokens on `reasoning_content`
        # before `content`; measured 2026-09-06: max_tokens=20 gave empty content,
        # 100 gave PONG. Keep it under Ollama's `thinking` key and size max_tokens
        # to leave room for it.
        reasoning = msg.get("reasoning_content") or msg.get("reasoning")
        if reasoning:
            message["thinking"] = reasoning
        return {
            "model": raw.get("model") or model,
            "lane": LANE,
            "message": message,
            "done": True,
            "done_reason": choice.get("finish_reason"),
            "usage": raw.get("usage") or {},
        }


def kaedra_cloud_fallback(messages: list, tools: Optional[list] = None, model: Optional[str] = None,
                          temperature: Optional[float] = None, max_tokens: Optional[int] = None,
                          client: Optional[WorkersAIClient] = None) -> Dict[str, Any]:
    """Cloud fallback for the Kaedra lane: same return shape as `OllamaClient.chat_raw`.

    Never raises; a lane that is unconfigured, over budget, or failing returns
    `{"error": ...}` so the caller can fall through to the next lane.
    """
    client = client or WorkersAIClient()
    if not client.is_alive():
        return {"error": f"{LANE} lane not configured", "lane": LANE}
    return client.chat(model=model, messages=messages, tools=tools,
                       temperature=temperature, max_tokens=max_tokens)
