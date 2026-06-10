"""Modular local LLM client interface for NouGenShards."""
from abc import ABC, abstractmethod
import json
import urllib.request
import urllib.error
import socket
import sys

class LocalLLMClient(ABC):
    """Abstract base class for local LLM clients."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Check if the server is reachable."""

    @abstractmethod
    def list_models(self) -> list:
        """Return available model names."""

    @abstractmethod
    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        """Send chat request."""

    @abstractmethod
    def find_best_edge_model(self) -> str:
        """Heuristic for best local model."""

class OllamaClient(LocalLLMClient):
    """Client for local Ollama instance."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        self.base_url = base_url

    def is_alive(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/version")
            with urllib.request.urlopen(req, timeout=1.0) as response:
                return response.getcode() == 200
        except (urllib.error.URLError, socket.timeout, ConnectionRefusedError):
            return False

    def list_models(self) -> list:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return [m["name"] for m in data.get("models", [])]
        except (urllib.error.URLError, socket.timeout):
            pass
        return []

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=120.0) as response:
                if not stream:
                    result = json.loads(response.read().decode("utf-8"))
                    return result.get("message", {}).get("content", "")

                full_content = ""
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        content = chunk.get("message", {}).get("content", "")
                        full_content += content
                        sys.stdout.write(content)
                        sys.stdout.flush()
                return full_content
        except (urllib.error.URLError, socket.timeout) as exc:
            return f"Error: Local model execution failed: {exc}"

    def find_best_edge_model(self) -> str:
        models = self.list_models()
        preferences = ["dav1d:e2b", "rhea-noir:e2b", "sol-ai:e2b", "gemma4:e2b"]
        for pref in preferences:
            for mdl in models:
                if mdl.startswith(pref):
                    return mdl
        for mdl in models:
            if "e2b" in mdl.lower():
                return mdl
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
        except (urllib.error.URLError, socket.timeout) as exc:
            print(f"\n[ERR] Failed to pull model: {exc}")
            return False

class LMStudioClient(LocalLLMClient):
    """Client for local LM Studio instance (OpenAI-compatible)."""

    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1"):
        self.base_url = base_url

    def is_alive(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/models")
            with urllib.request.urlopen(req, timeout=1.0) as response:
                return response.getcode() == 200
        except (urllib.error.URLError, socket.timeout, ConnectionRefusedError):
            return False

    def list_models(self) -> list:
        try:
            req = urllib.request.Request(f"{self.base_url}/models")
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return [m["id"] for m in data.get("data", [])]
        except (urllib.error.URLError, socket.timeout):
            pass
        return []

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=120.0) as response:
                if not stream:
                    result = json.loads(response.read().decode("utf-8"))
                    return result.get("choices", [{}])[0].get("message", {}).get("content", "")

                return self._stream_chat(response)
        except (urllib.error.URLError, socket.timeout) as exc:
            return f"Error: Local LM Studio execution failed: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data: "):
                if line_str == "data: [DONE]":
                    break
                chunk = json.loads(line_str[6:])
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                full_content += content
                sys.stdout.write(content)
                sys.stdout.flush()
        return full_content

    def find_best_edge_model(self) -> str:
        models = self.list_models()
        # LM Studio IDs often contain the full path or quantized name
        for mdl in models:
            if "e2b" in mdl.lower() or "2b" in mdl.lower():
                return mdl
        return models[0] if models else ""

def get_best_available_client() -> LocalLLMClient:
    """Detect and return the first available local LLM client."""
    ollama = OllamaClient()
    if ollama.is_alive():
        return ollama
    lm_studio = LMStudioClient()
    if lm_studio.is_alive():
        return lm_studio
    return ollama # Default fallback
