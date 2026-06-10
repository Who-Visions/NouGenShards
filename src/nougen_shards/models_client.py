"""Modular local LLM client interface for NouGenShards."""
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

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: OpenAI API Key not configured. Run `nougen auth set-key openai`."
        
        payload = {"model": model, "messages": messages, "stream": stream}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=120.0) as response:
                if not stream:
                    result = json.loads(response.read().decode("utf-8"))
                    return result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                return self._stream_chat(response)
        except Exception as exc:
            return f"Error: OpenAI execution failed: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data: "):
                if line_str == "data: [DONE]":
                    break
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    full_content += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
                except json.JSONDecodeError:
                    continue
        return full_content

class AnthropicClient(LLMClient):
    """Client for Anthropic (Claude)."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or keymaker.get_secret("ANTHROPIC_API_KEY")
        self.base_url = "https://api.anthropic.com/v1"

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        return ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest", "claude-3-opus-latest"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: Anthropic API Key not configured. Run `nougen auth set-key anthropic`."
        
        # Anthropic uses 'system' role at top level, not in messages list for some versions
        # but the Messages API accepts system property.
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_messages = [m for m in messages if m["role"] != "system"]

        payload = {
            "model": model,
            "messages": user_messages,
            "max_tokens": 4096,
            "system": system_msg,
            "stream": stream
        }
        req = urllib.request.Request(
            f"{self.base_url}/messages",
            data=json.dumps(payload).encode("utf-8"),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", self.api_key)
        req.add_header("anthropic-version", "2023-06-01")

        try:
            with urllib.request.urlopen(req, timeout=120.0) as response:
                if not stream:
                    result = json.loads(response.read().decode("utf-8"))
                    return result.get("content", [{}])[0].get("text", "")
                
                return self._stream_chat(response)
        except Exception as exc:
            return f"Error: Anthropic execution failed: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data: "):
                try:
                    chunk = json.loads(line_str[6:])
                    if chunk.get("type") == "content_block_delta":
                        content = chunk.get("delta", {}).get("text", "")
                        full_content += content
                        sys.stdout.write(content)
                        sys.stdout.flush()
                except json.JSONDecodeError:
                    continue
        return full_content

class GeminiClient(LLMClient):
    """Client for Google (Gemini)."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or keymaker.get_secret("GOOGLE_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        return ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: Google API Key not configured. Run `nougen auth set-key google`."
        
        # Convert messages to Gemini format
        contents = []
        for m in messages:
            role = "user" if m["role"] in ["user", "system"] else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        endpoint = "streamGenerateContent" if stream else "generateContent"
        url = f"{self.base_url}/{model}:{endpoint}?key={self.api_key}"
        
        req = urllib.request.Request(
            url,
            data=json.dumps({"contents": contents}).encode("utf-8"),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=120.0) as response:
                if not stream:
                    result = json.loads(response.read().decode("utf-8"))
                    return result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                
                return self._stream_chat(response)
        except Exception as exc:
            return f"Error: Gemini execution failed: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        # Gemini streaming returns a JSON array of objects or individual objects per line
        # but the REST API for streaming can be tricky with raw urllib.
        # We'll handle the common NDJSON pattern if it occurs.
        for line in response:
            line_str = line.decode("utf-8").strip()
            if not line_str: continue
            try:
                # Handle possible array wrapper [{}, {}]
                if line_str.startswith("["): line_str = line_str[1:]
                if line_str.endswith("]"): line_str = line_str[:-1]
                if line_str.endswith(","): line_str = line_str[:-1]
                
                chunk = json.loads(line_str)
                content = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                full_content += content
                sys.stdout.write(content)
                sys.stdout.flush()
            except json.JSONDecodeError:
                continue
        return full_content

class HuggingFaceClient(LLMClient):
    """Client for Hugging Face Inference API."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or keymaker.get_secret("HUGGINGFACE_API_KEY")
        self.base_url = "https://api-inference.huggingface.co/models"

    def is_alive(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list:
        # Hugging Face doesn't have a simple 'list all' for the inference API in this context
        # We'll return a few popular defaults
        return [
            "meta-llama/Llama-3.2-3B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "google/gemma-2-2b-it"
        ]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: Hugging Face API Key not configured. Run `nougen auth set-key huggingface`."
        
        # Prepare inputs (simple concatenation for non-chat specific models or standard format)
        # Most modern models on HF support the chat template if using specific endpoints
        # but here we'll use the standard Inference API pattern.
        prompt = ""
        for m in messages:
            role = m["role"].upper()
            prompt += f"{role}: {m['content']}\n"
        prompt += "ASSISTANT: "

        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 1024, "return_full_text": False},
            "stream": stream
        }
        
        url = f"{self.base_url}/{model}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=120.0) as response:
                if not stream:
                    result = json.loads(response.read().decode("utf-8"))
                    # Result is often a list of objects
                    if isinstance(result, list) and len(result) > 0:
                        return result[0].get("generated_text", "")
                    return str(result)
                
                return self._stream_chat(response)
        except Exception as exc:
            return f"Error: Hugging Face execution failed: {exc}"

    def _stream_chat(self, response) -> str:
        full_content = ""
        for line in response:
            line_str = line.decode("utf-8").strip()
            if not line_str: continue
            if line_str.startswith("data: "):
                try:
                    chunk = json.loads(line_str[6:])
                    content = chunk.get("token", {}).get("text", "")
                    full_content += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
                except json.JSONDecodeError:
                    continue
        return full_content

class OpenRouterClient(OpenAIClient):
    """Client for OpenRouter (OpenAI-compatible)."""
    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key or keymaker.get_secret("OPENROUTER_API_KEY"))
        self.base_url = "https://openrouter.ai/api/v1"

    def list_models(self) -> list:
        # OpenRouter has too many models to list statically
        return [
            "google/gemma-2-9b-it:free",
            "google/gemma-3-27b-it:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o"
        ]

    def chat(self, model: str, messages: list, stream: bool = False) -> str:
        if not self.api_key:
            return "Error: OpenRouter API Key not configured. Run `nougen auth set-key openrouter`."
        return super().chat(model, messages, stream=stream)

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
