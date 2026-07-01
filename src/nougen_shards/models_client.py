"""Modular LLM client interface for NouGenShards with embedding support."""
from abc import ABC, abstractmethod
import json
import urllib.request
import urllib.error
import sys
import os
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict

from . import keymaker
from . import router
from . import structured

# Hardening: bound every network lane call so a hung or unreachable upstream
# fails over instead of blocking the router indefinitely (Opposing Defense:
# 502/503/stalled sockets). Values are socket read timeouts in seconds.
DEFAULT_HTTP_TIMEOUT = 120
MODEL_PULL_TIMEOUT = 600  # model pulls stream progress; generous but finite bound


@dataclass
class ModelBudgetConfig:
    """Configuration budget for a model matching physical VRAM parameters."""
    model_name: str
    n_ctx: int = 4096
    max_tokens: Optional[int] = None
    temperature: float = 0.7

    def to_kwargs(self) -> dict:
        """Helper to unpack into Ollama or LMStudio options."""
        return {
            "model": self.model_name,
            "num_ctx": self.n_ctx,
            "temperature": self.temperature,
            "num_predict": self.max_tokens
        }


class LLMClient(ABC):
    """Abstract base class for all LLM clients."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Check if the service is reachable/configured."""

    @abstractmethod
    def list_models(self) -> list:
        """Return available model names."""

    @abstractmethod
    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        """Send chat request."""

    @abstractmethod
    def embed(self, model: str, text: str) -> list:
        """Generate vector embeddings for text."""

    @abstractmethod
    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        """Generate vector embeddings for a batch of texts."""


class LocalLLMClient(LLMClient, ABC):
    """Abstract base class for local LLM clients."""
    @abstractmethod
    def find_best_edge_model(self) -> Optional[ModelBudgetConfig]:
        """Heuristic for best local model."""


class OpenAIClient(LLMClient):
    """Client for OpenAI (ChatGPT)."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or keymaker.get_secret("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1"

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        return ["gpt-4o", "gpt-4o-mini", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: OpenAI Key missing."
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    resp_data = json.loads(res.read().decode())
                    return resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._stream_chat(res)
        except Exception as exc: # pylint: disable=broad-except
            return f"Error: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode().strip()
            if line_str.startswith("data: ") and line_str != "data: [DONE]":
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    full_content += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
                except (json.JSONDecodeError, KeyError):
                    continue
        return full_content

    def embed(self, model: str, text: str) -> list:
        if not self.api_key:
            return []
        payload = {"model": model, "input": text}
        req = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                resp_data = json.loads(res.read().decode())
                return resp_data.get("data", [{}])[0].get("embedding", [])
        except Exception: # pylint: disable=broad-except
            return []

    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        if not self.api_key or not texts:
            return [[] for _ in texts]
        payload = {"model": model, "input": texts}
        req = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                resp_data = json.loads(res.read().decode())
                data = resp_data.get("data", [])
                sorted_data = sorted(data, key=lambda x: x.get("index", 0))
                embeddings = [item.get("embedding", []) for item in sorted_data]
                if len(embeddings) == len(texts):
                    return embeddings
                result = [[] for _ in texts]
                for item in data:
                    idx = item.get("index")
                    if idx is not None and 0 <= idx < len(texts):
                        result[idx] = item.get("embedding", [])
                return result
        except Exception: # pylint: disable=broad-except
            return [[] for _ in texts]


class AnthropicClient(LLMClient):
    """Client for Anthropic (Claude)."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or keymaker.get_secret("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1"

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        return ["claude-3-5-sonnet-latest"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: Anthropic Key missing."
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        payload = {
            "model": model,
            "messages": user_msgs,
            "max_tokens": 4096,
            "system": system_msg,
            "stream": stream
        }
        req = urllib.request.Request(
            f"{self.base_url}/messages",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", self.api_key or "")
        req.add_header("anthropic-version", "2023-06-01")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    resp_data = json.loads(res.read().decode())
                    return resp_data.get("content", [{}])[0].get("text", "")
                return self._stream_chat(res)
        except Exception as exc: # pylint: disable=broad-except
            return f"Error: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode().strip()
            if line_str.startswith("data: "):
                try:
                    chunk = json.loads(line_str[6:])
                    if chunk.get("type") == "content_block_delta":
                        content = chunk.get("delta", {}).get("text", "")
                        full_content += content
                        sys.stdout.write(content)
                        sys.stdout.flush()
                except (json.JSONDecodeError, KeyError):
                    continue
        return full_content

    def embed(self, model: str, text: str) -> list:
        return []

    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        return [[] for _ in texts]


class GeminiClient(LLMClient):
    """Client for Google (Gemini)."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or keymaker.get_secret("GOOGLE_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        return ["gemini-1.5-pro", "gemini-1.5-flash"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: Google Key missing."
        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ["user", "system"] else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        endpoint = "streamGenerateContent" if stream else "generateContent"
        url = f"{self.base_url}/{model}:{endpoint}?key={self.api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps({"contents": contents}).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    resp_data = json.loads(res.read().decode())
                    return resp_data.get("candidates", [{}])[0].get(
                        "content", {}).get("parts", [{}])[0].get("text", "")
                return self._stream_chat(res)
        except Exception as exc: # pylint: disable=broad-except
            return f"Error: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode().strip()
            if not line_str:
                continue
            if line_str.startswith("["):
                line_str = line_str[1:]
            if line_str.endswith("]"):
                line_str = line_str[:-1]
            if line_str.endswith(","):
                line_str = line_str[:-1]
            try:
                chunk = json.loads(line_str)
                content = chunk.get("candidates", [{}])[0].get(
                    "content", {}).get("parts", [{}])[0].get("text", "")
                full_content += content
                sys.stdout.write(content)
                sys.stdout.flush()
            except (json.JSONDecodeError, KeyError):
                continue
        return full_content

    def embed(self, model: str, text: str) -> list:
        if not self.api_key:
            return []
        url = f"{self.base_url}/{model}:embedContent?key={self.api_key}"
        payload = {"content": {"parts": [{"text": text}]}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                resp_data = json.loads(res.read().decode())
                return resp_data.get("embedding", {}).get("values", [])
        except Exception: # pylint: disable=broad-except
            return []

    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        if not self.api_key or not texts:
            return [[] for _ in texts]
        url = f"{self.base_url}/{model}:batchEmbedContents?key={self.api_key}"
        model_ref = model if model.startswith("models/") else f"models/{model}"
        requests_list = [{"model": model_ref, "content": {"parts": [{"text": t}]}} for t in texts]
        payload = {"requests": requests_list}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                resp_data = json.loads(res.read().decode())
                embeddings_data = resp_data.get("embeddings", [])
                embeddings = [emb.get("values", []) for emb in embeddings_data]
                if len(embeddings) == len(texts):
                    return embeddings
                result = [[] for _ in texts]
                for idx, emb in enumerate(embeddings):
                    if idx < len(texts):
                        result[idx] = emb
                return result
        except Exception: # pylint: disable=broad-except
            return [self.embed(model, text) for text in texts]


class HuggingFaceClient(LLMClient):
    """Client for Hugging Face Inference API."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or keymaker.get_secret("HUGGINGFACE_API_KEY")
        self.base_url = "https://api-inference.huggingface.co/models"

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        return ["meta-llama/Llama-3.2-3B-Instruct"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: HF Key missing."
        prompt = ""
        for msg in messages:
            prompt += f"{msg['role'].upper()}: {msg['content']}\n"
        prompt += "ASSISTANT: "
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 1024}, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/{model}",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    result = json.loads(res.read().decode())
                    if isinstance(result, list):
                        return result[0].get("generated_text", "")
                    return str(result)
                return self._stream_chat(res)
        except Exception as exc: # pylint: disable=broad-except
            return f"Error: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode().strip()
            if line_str.startswith("data: "):
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("token", {}).get("text", "")
                    full_content += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
                except (json.JSONDecodeError, KeyError):
                    continue
        return full_content

    def embed(self, model: str, text: str) -> list:
        return []

    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        return [[] for _ in texts]


class OpenRouterClient(OpenAIClient):
    """Client for OpenRouter (Unified API)."""
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key=api_key or keymaker.get_secret("OPENROUTER_API_KEY"))
        self.base_url = "https://openrouter.ai/api/v1"

    def list_models(self) -> list:
        return [
            "google/gemma-3-27b-it:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-5.6-sol",
            "openai/gpt-5.6-terra",
            "openai/gpt-5.6-luna"
        ]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: OR Key missing."
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        req.add_header("HTTP-Referer", "https://whovisions.com")
        req.add_header("X-OpenRouter-Title", "NouGenShards")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    resp_data = json.loads(res.read().decode())
                    return resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._stream_chat(res)
        except Exception as exc: # pylint: disable=broad-except
            return f"Error: {exc}"

    def chat_with_fallback(self, model: str, messages: list,
                           fallback_models: Optional[list] = None, session_id: Optional[str] = None,
                           stream: bool = False, **kwargs) -> dict:
        """
        Executes a chat request with OpenRouter model fallback.
        """
        if not self.api_key:
            return {"content": "Error: OR Key missing.", "model": "unknown"}

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "models": fallback_models or [
                "anthropic/claude-3.5-sonnet",
                "google/gemini-2.0-flash-001",
                "deepseek/deepseek-chat"
            ]
        }

        if session_id:
            payload["session_id"] = session_id

        # Add optional params
        for key in ["temperature", "max_tokens"]:
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        req.add_header("HTTP-Referer", "https://whovisions.com")
        req.add_header("X-OpenRouter-Title", "NouGenShards")

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    resp_data = json.loads(res.read().decode())
                    choice = resp_data.get("choices", [{}])[0]
                    return {
                        "content": choice.get("message", {}).get("content", ""),
                        "model": resp_data.get("model", model),
                        "usage": self._extract_usage_metadata(resp_data),
                        "finish_reason": choice.get("finish_reason")
                    }
                return {"content": self._stream_chat(res), "model": model}
        except Exception as exc:
            return {"content": f"Error: {exc}", "model": "error"}

    def structured_chat(self, model: str, messages: list, schema: dict,
                        fallback_models: Optional[list] = None, session_id: Optional[str] = None,
                        healing: bool = True, strict: bool = True) -> dict:
        """
        Executes a request for structured JSON output with response healing.
        """
        if not self.api_key:
            return {"error": "OR Key missing."}

        payload = {
            "model": model,
            "messages": messages,
            "models": fallback_models or [],
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "nougen_schema",
                    "strict": strict,
                    "schema": schema
                }
            }
        }

        if session_id:
            payload["session_id"] = session_id

        if healing:
            payload["plugins"] = [{"id": "response-healing"}]

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key or ''}")
        req.add_header("HTTP-Referer", "https://whovisions.com")
        req.add_header("X-OpenRouter-Title", "NouGenShards")

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                resp_data = json.loads(res.read().decode())
                content = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")

                try:
                    data = structured.parse_json_content(content)
                except ValueError as e:
                    return {"error": f"JSON Parse Failed: {e}", "raw": content}

                valid, errors = structured.validate_against_schema(data, schema)

                return {
                    "data": data,
                    "valid": valid,
                    "errors": errors,
                    "model": resp_data.get("model"),
                    "usage": self._extract_usage_metadata(resp_data)
                }
        except Exception as exc:
            return {"error": f"Request Failed: {exc}"}

    def _extract_usage_metadata(self, response_json: dict) -> dict:
        """Normalizes OpenRouter usage data including cached tokens."""
        usage = response_json.get("usage", {})
        details = usage.get("prompt_tokens_details", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cached_tokens": details.get("cached_tokens", 0),
            "cache_write_tokens": details.get("cache_write_tokens", 0)
        }


class WhoVisionsCloudClient(LLMClient):
    """
    Client for Who Visions Hosted Cloud Brain.
    Securely bridges local CLI to remote node for metered inference.
    """
    def __init__(self, node_url: Optional[str] = None, user_token: Optional[str] = None):
        self.node_url = node_url or os.environ.get("NGS_CLOUD_URL")
        self.user_token = user_token or os.environ.get("NGS_CLOUD_TOKEN")

    def is_alive(self) -> bool:
        return bool(self.node_url and self.user_token)

    def list_models(self) -> list:
        # Return canonical cloud models
        return ["whovisions/brain-v1", "openrouter/auto"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.is_alive():
            return "Error: Who Visions Cloud not configured. Use: nougen auth set-key cloud <url>,<token>"
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        req = urllib.request.Request(
            f"{self.node_url.rstrip('/') if self.node_url else ''}/cloud/chat",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("X-NGS-Token", self.user_token or "")
        
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                resp_data = json.loads(res.read().decode())
                return resp_data.get("content", "")
        except Exception as exc:
            return f"Error: {exc}"

    def embed(self, model: str, text: str) -> list:
        # Future: implement remote embedding gateway
        return []

    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        return [[] for _ in texts]


def find_best_model_from_list(models: List[str]) -> Optional[ModelBudgetConfig]:
    """Helper to select the best available model, preferring custom models over defaults."""
    if not models:
        return None

    # 1. First tier: Known custom system models (tight context, low temp)
    custom_system_tags = [
        "dav1d:e2b", "rhea-noir:e2b", "sol-ai:e2b", "griot:e2b",
        "gemma4-aggressive:e2b", "gemma4-aggressive:e4b", "rhea-noir:e4b",
        "kaedra:e4b", "iris-ai:e4b", "sol-ai:e4b", "davos:latest", "janitor:latest"
    ]
    for tag in custom_system_tags:
        for model in models:
            model_lower = model.lower()
            if model_lower.startswith(tag) or f"/{tag}" in model_lower or f"\\{tag}" in model_lower:
                return ModelBudgetConfig(
                    model_name=model,
                    n_ctx=2048,
                    temperature=0.2
                )
                
    # 2. Second tier: Any other user-created custom/finetuned models (not starting with official vendor prefixes)
    official_prefixes = (
        "gemma", "llama", "qwen", "mistral", "phi", "deepseek", "codellama", "mixtral"
    )
    for model in models:
        base_name = os.path.basename(model.replace("\\", "/")).lower()
        if not any(base_name.startswith(p) for p in official_prefixes):
            # Dynamic context detection for user finetunes (capped at 8K for safety)
            n_ctx = 4096
            if "-8k" in base_name or "8k" in base_name:
                n_ctx = 8192
            elif "-16k" in base_name or "16k" in base_name:
                n_ctx = 8192
            elif "-2k" in base_name or "2k" in base_name:
                n_ctx = 2048
            return ModelBudgetConfig(
                model_name=model,
                n_ctx=n_ctx,
                temperature=0.7
            )
            
    # 3. Third tier: Official Gemma 4 QAT/edge/workstation defaults
    gemma4_tags = [
        "gemma4:e4b", "gemma4:e4b-it-qat",
        "gemma4:12b", "gemma4:12b-it-qat",
        "gemma4:e2b", "gemma4:e2b-it-qat",
        "gemma4:latest"
    ]
    for tag in gemma4_tags:
        for model in models:
            model_lower = model.lower()
            if model_lower.startswith(tag) or f"/{tag}" in model_lower or f"\\{tag}" in model_lower:
                return ModelBudgetConfig(
                    model_name=model,
                    n_ctx=4096,
                    temperature=0.7
                )
                
    # 4. Fourth tier: Generic fallback to any Gemma family
    for prefix in ["gemma4:", "gemma:"]:
        for model in models:
            model_lower = model.lower()
            if model_lower.startswith(prefix) or prefix in model_lower:
                return ModelBudgetConfig(
                    model_name=model,
                    n_ctx=4096,
                    temperature=0.7
                )
                
    # Default fallback to first available model
    model = models[0]
    base_name = os.path.basename(model.replace("\\", "/")).lower()
    n_ctx = 4096
    if "-8k" in base_name or "8k" in base_name:
        n_ctx = 8192
    elif "-16k" in base_name or "16k" in base_name:
        n_ctx = 8192
    elif "-2k" in base_name or "2k" in base_name:
        n_ctx = 2048
    return ModelBudgetConfig(
        model_name=model,
        n_ctx=n_ctx,
        temperature=0.7
    )


class OllamaClient(LocalLLMClient):
    """Client for local Ollama instance."""
    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        self.base_url = base_url

    def is_alive(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/version", timeout=1.0) as res:
                return res.getcode() == 200
        except Exception: # pylint: disable=broad-except
            return False

    def list_models(self) -> list:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=3.0) as res:
                data = json.loads(res.read().decode())
                return [m["name"] for m in data.get("models", [])]
        except Exception: # pylint: disable=broad-except
            return []

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    resp_data = json.loads(res.read().decode())
                    return resp_data.get("message", {}).get("content", "")
                full = ""
                for line in res:
                    chunk = json.loads(line.decode())
                    content = chunk.get("message", {}).get("content", "")
                    full += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
                return full
        except Exception as exc: # pylint: disable=broad-except
            return f"Error: {exc}"

    def embed(self, model: str, text: str) -> list:
        payload = {"model": model, "prompt": text}
        req = urllib.request.Request(
            f"{self.base_url}/api/embeddings",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                return json.loads(res.read().decode()).get("embedding", [])
        except Exception: # pylint: disable=broad-except
            return []

    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        if not texts:
            return []
        payload = {"model": model, "input": texts}
        req = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                resp_data = json.loads(res.read().decode())
                embeddings = resp_data.get("embeddings", [])
                if len(embeddings) == len(texts):
                    return embeddings
                result = [[] for _ in texts]
                for idx, emb in enumerate(embeddings):
                    if idx < len(texts):
                        result[idx] = emb
                return result
        except Exception: # pylint: disable=broad-except
            return [self.embed(model, text) for text in texts]

    def find_best_edge_model(self) -> str:
        return find_best_model_from_list(self.list_models())

    def pull_model(self, model_name: str):
        """Ollama-specific: pull model."""
        url = f"{self.base_url}/api/pull"
        payload = json.dumps({"model": model_name, "stream": True}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=MODEL_PULL_TIMEOUT) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        status = chunk.get("status", "")
                        completed = chunk.get("completed")
                        total = chunk.get("total")
                        if total and completed:
                            pct = (completed / total) * 100
                            sys.stdout.write(f"\r[*] Pulling {model_name}: {pct:.1f}% ({status})")
                        elif status:
                            sys.stdout.write(f"\r[*] {status}...")
                        sys.stdout.flush()
                print("\n✅ Model pull complete.")
                return True
        except Exception as exc: # pylint: disable=broad-except
            print(f"\n[ERR] Failed to pull model: {exc}")
            return False


class LMStudioClient(LocalLLMClient):
    """Client for local LM Studio."""
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1"):
        self.base_url = base_url

    def is_alive(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=1.0) as res:
                return res.getcode() == 200
        except Exception: # pylint: disable=broad-except
            return False

    def list_models(self) -> list:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=3.0) as res:
                data = json.loads(res.read().decode())
                return [m["id"] for m in data.get("data", [])]
        except Exception: # pylint: disable=broad-except
            return []

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_HTTP_TIMEOUT) as res:
                if not stream:
                    resp_data = json.loads(res.read().decode())
                    return resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._stream_chat(res)
        except Exception as exc: # pylint: disable=broad-except
            return f"Error: {exc}"

    def _stream_chat(self, response) -> str:
        full = ""
        for line in response:
            line_str = line.decode().strip()
            if line_str.startswith("data: ") and line_str != "data: [DONE]":
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    full += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
                except (json.JSONDecodeError, KeyError):
                    continue
        return full

    def embed(self, model: str, text: str) -> list:
        return []

    def batch_embed(self, model: str, texts: List[str]) -> List[list]:
        return [[] for _ in texts]

    def find_best_edge_model(self) -> str:
        return find_best_model_from_list(self.list_models())


def get_best_available_client() -> LocalLLMClient:
    """Detects and returns the best available local LLM provider."""
    ollama = OllamaClient()
    if ollama.is_alive():
        return ollama
    lm_client = LMStudioClient()
    if lm_client.is_alive():
        return lm_client
    return ollama
