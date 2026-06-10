"""Modular LLM client interface for NouGenShards with embedding support."""
from abc import ABC, abstractmethod
import json
import urllib.request
import urllib.error
import socket
import sys

from . import keymaker

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

class LocalLLMClient(LLMClient, ABC):
    """Abstract base class for local LLM clients."""
    @abstractmethod
    def find_best_edge_model(self) -> str:
        """Heuristic for best local model."""

class OpenAIClient(LLMClient):
    """Client for OpenAI (ChatGPT)."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or keymaker.get_secret("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1"

    def is_alive(self) -> bool: return bool(self.api_key)
    def list_models(self) -> list: return ["gpt-4o", "gpt-4o-mini"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key: return "Error: OpenAI Key missing."
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req) as res:
                if not stream:
                    return json.loads(res.read().decode()).get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._stream_chat(res)
        except Exception as e: return f"Error: {e}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode().strip()
            if line_str.startswith("data: ") and line_str != "data: [DONE]":
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    full_content += content
                    sys.stdout.write(content); sys.stdout.flush()
                except Exception: continue
        return full_content

    def embed(self, model: str, text: str) -> list:
        if not self.api_key: return []
        payload = {"model": model, "input": text}
        req = urllib.request.Request(f"{self.base_url}/embeddings", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req) as res:
                return json.loads(res.read().decode()).get("data", [{}])[0].get("embedding", [])
        except Exception: return []

class AnthropicClient(LLMClient):
    """Client for Anthropic (Claude)."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or keymaker.get_secret("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1"

    def is_alive(self) -> bool: return bool(self.api_key)
    def list_models(self) -> list: return ["claude-3-5-sonnet-latest"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key: return "Error: Anthropic Key missing."
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        payload = {"model": model, "messages": user_msgs, "max_tokens": 4096, "system": system_msg, "stream": stream}
        req = urllib.request.Request(f"{self.base_url}/messages", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", self.api_key); req.add_header("anthropic-version", "2023-06-01")
        try:
            with urllib.request.urlopen(req) as res:
                if not stream:
                    return json.loads(res.read().decode()).get("content", [{}])[0].get("text", "")
                return self._stream_chat(res)
        except Exception as e: return f"Error: {e}"

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
                        sys.stdout.write(content); sys.stdout.flush()
                except Exception: continue
        return full_content

    def embed(self, model: str, text: str) -> list: return []

class GeminiClient(LLMClient):
    """Client for Google (Gemini)."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or keymaker.get_secret("GOOGLE_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def is_alive(self) -> bool: return bool(self.api_key)
    def list_models(self) -> list: return ["gemini-1.5-pro", "gemini-1.5-flash"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key: return "Error: Google Key missing."
        contents = []
        for m in messages:
            role = "user" if m["role"] in ["user", "system"] else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        endpoint = "streamGenerateContent" if stream else "generateContent"
        url = f"{self.base_url}/{model}:{endpoint}?key={self.api_key}"
        req = urllib.request.Request(url, data=json.dumps({"contents": contents}).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as res:
                if not stream:
                    return json.loads(res.read().decode()).get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return self._stream_chat(res)
        except Exception as e: return f"Error: {e}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode().strip()
            if not line_str: continue
            if line_str.startswith("["): line_str = line_str[1:]
            if line_str.endswith("]"): line_str = line_str[:-1]
            if line_str.endswith(","): line_str = line_str[:-1]
            try:
                chunk = json.loads(line_str)
                content = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                full_content += content
                sys.stdout.write(content); sys.stdout.flush()
            except Exception: continue
        return full_content

    def embed(self, model: str, text: str) -> list:
        if not self.api_key: return []
        url = f"{self.base_url}/{model}:embedContent?key={self.api_key}"
        payload = {"content": {"parts": [{"text": text}]}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as res:
                return json.loads(res.read().decode()).get("embedding", {}).get("values", [])
        except Exception: return []

class HuggingFaceClient(LLMClient):
    """Client for Hugging Face Inference API."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or keymaker.get_secret("HUGGINGFACE_API_KEY")
        self.base_url = "https://api-inference.huggingface.co/models"

    def is_alive(self) -> bool: return bool(self.api_key)
    def list_models(self) -> list: return ["meta-llama/Llama-3.2-3B-Instruct"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key: return "Error: HF Key missing."
        prompt = ""
        for m in messages: prompt += f"{m['role'].upper()}: {m['content']}\n"
        prompt += "ASSISTANT: "
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 1024}, "stream": stream}
        req = urllib.request.Request(f"{self.base_url}/{model}", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json"); req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req) as res:
                if not stream:
                    result = json.loads(res.read().decode())
                    return result[0].get("generated_text", "") if isinstance(result, list) else str(result)
                return self._stream_chat(res)
        except Exception as e: return f"Error: {e}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode().strip()
            if line_str.startswith("data: "):
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("token", {}).get("text", "")
                    full_content += content
                    sys.stdout.write(content); sys.stdout.flush()
                except Exception: continue
        return full_content

    def embed(self, model: str, text: str) -> list: return []

class OpenRouterClient(OpenAIClient):
    """Client for OpenRouter (Unified API)."""
    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key or keymaker.get_secret("OPENROUTER_API_KEY"))
        self.base_url = "https://openrouter.ai/api/v1"

    def list_models(self) -> list: return ["google/gemma-3-27b-it:free", "anthropic/claude-3.5-sonnet"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key: return "Error: OR Key missing."
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json"); req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("HTTP-Referer", "https://whovisions.com"); req.add_header("X-OpenRouter-Title", "NouGenShards")
        try:
            with urllib.request.urlopen(req) as res:
                if not stream:
                    return json.loads(res.read().decode()).get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._stream_chat(res)
        except Exception as e: return f"Error: {e}"

class OllamaClient(LocalLLMClient):
    """Client for local Ollama instance."""
    def __init__(self, base_url: str = "http://127.0.0.1:11434"): self.base_url = base_url
    def is_alive(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/version", timeout=1.0) as res: return res.getcode() == 200
        except Exception: return False

    def list_models(self) -> list:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=3.0) as res:
                return [m["name"] for m in json.loads(res.read().decode()).get("models", [])]
        except Exception: return []

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(f"{self.base_url}/api/chat", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as res:
                if not stream: return json.loads(res.read().decode()).get("message", {}).get("content", "")
                full = ""
                for line in res:
                    chunk = json.loads(line.decode())
                    content = chunk.get("message", {}).get("content", "")
                    full += content; sys.stdout.write(content); sys.stdout.flush()
                return full
        except Exception as e: return f"Error: {e}"

    def embed(self, model: str, text: str) -> list:
        payload = {"model": model, "prompt": text}
        req = urllib.request.Request(f"{self.base_url}/api/embeddings", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as res: return json.loads(res.read().decode()).get("embedding", [])
        except Exception: return []

    def find_best_edge_model(self) -> str:
        models = self.list_models()
        for p in ["dav1d:e2b", "rhea-noir:e2b", "sol-ai:e2b"]:
            for m in models:
                if m.startswith(p): return m
        return models[0] if models else ""

    def pull_model(self, model_name: str):
        """Ollama-specific: pull model."""
        url = f"{self.base_url}/api/pull"
        data = json.dumps({"model": model_name, "stream": True}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as response:
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
        except Exception as exc:
            print(f"\n[ERR] Failed to pull model: {exc}")
            return False

class LMStudioClient(LocalLLMClient):
    """Client for local LM Studio."""
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1"): self.base_url = base_url
    def is_alive(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=1.0) as res: return res.getcode() == 200
        except Exception: return False

    def list_models(self) -> list:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=3.0) as res:
                return [m["id"] for m in json.loads(res.read().decode()).get("data", [])]
        except Exception: return []

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as res:
                if not stream: return json.loads(res.read().decode()).get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._stream_chat(res)
        except Exception as e: return f"Error: {e}"

    def _stream_chat(self, response) -> str:
        full = ""
        for line in response:
            line_str = line.decode().strip()
            if line_str.startswith("data: ") and line_str != "data: [DONE]":
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    full += content; sys.stdout.write(content); sys.stdout.flush()
                except Exception: continue
        return full

    def embed(self, model: str, text: str) -> list: return []
    def find_best_edge_model(self) -> str:
        models = self.list_models()
        return models[0] if models else ""

def get_best_available_client() -> LocalLLMClient:
    ollama = OllamaClient()
    if ollama.is_alive(): return ollama
    lm = LMStudioClient()
    if lm.is_alive(): return lm
    return ollama
