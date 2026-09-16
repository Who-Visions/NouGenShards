"""
NouGen Cloudflare Edge Substrate — Native Management & Zero-Downtime Engine.
Integrates Cloudflare Workers, Storage (D1/KV/R2), Secrets, and Workers AI with Keymaker DPAPI authentication.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore

from . import keymaker

logger = logging.getLogger(__name__)

CF_API = "https://api.cloudflare.com/client/v4"
DEFAULT_TOKEN_KEYS = ("CLOUDFLARE_API_TOKEN_NOUGEN_FULL", "CLOUDFLARE_API_TOKEN", "NOUGEN_CF_AI_TOKEN")
DEFAULT_ACCOUNT_KEYS = ("CLOUDFLARE_ACCOUNT_ID", "NOUGEN_CF_ACCOUNT_ID")
FLEET_GATEWAY_URL = "https://nougen-fleet-mcp.whoentertains.workers.dev"


@dataclass
class WorkerInfo:
    id: str
    created_on: str
    modified_on: str
    usage_model: str
    routes: List[str]


@dataclass
class SecretInfo:
    name: str
    type: str


def strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments from JSONC text, and trailing commas."""
    # Remove block comments
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)
    # Remove single-line comments
    text = re.sub(r'//.*', '', text)
    # Remove trailing commas before } or ]
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


class CloudflareClient:
    """First-class native Cloudflare client with auto-discovery, intelligent context detection,
    and Keymaker authentication."""

    def __init__(self, token: Optional[str] = None, account_id: Optional[str] = None):
        self.token = token or self._resolve_token()
        if not self.token:
            raise RuntimeError("Cloudflare API token not found in environment or Keymaker vault.")
        self.account_id, self.account_name = self._resolve_account(account_id)

    @staticmethod
    def _resolve_token() -> Optional[str]:
        for k in ("CLOUDFLARE_API_TOKEN", "NOUGEN_CF_AI_TOKEN"):
            val = os.environ.get(k)
            if val:
                return val.strip()
        if keymaker:
            for k in DEFAULT_TOKEN_KEYS:
                try:
                    val = keymaker.get_secret(k)
                    if val:
                        return val.strip()
                except Exception:
                    pass
        return None

    def _resolve_account(self, explicit_id: Optional[str] = None) -> Tuple[str, str]:
        if explicit_id:
            return explicit_id, "explicit"
        for k in DEFAULT_ACCOUNT_KEYS:
            val = os.environ.get(k)
            if val:
                return val.strip(), "env"

        # Discover accounts from Cloudflare API
        res = self.request("/accounts")
        if res.get("success") and res.get("result"):
            acc = res["result"][0]
            return acc["id"], acc.get("name", "unnamed")
        raise RuntimeError(f"Could not resolve Cloudflare account ID: {res.get('errors')}")

    def request(self, endpoint: str, method: str = "GET", data: Optional[Union[Dict, List, bytes]] = None,
                content_type: str = "application/json") -> Dict[str, Any]:
        url = f"{CF_API}{endpoint}" if endpoint.startswith("/") else endpoint
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "NouGen-Native-Cloudflare/2.0"
        }
        if content_type:
            headers["Content-Type"] = content_type

        body = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body = json.dumps(data).encode("utf-8")
            elif isinstance(data, (bytes, bytearray)):
                body = bytes(data)
            elif isinstance(data, str):
                body = data.encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except Exception:
                    return {"success": True, "raw": raw}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            try:
                return json.loads(err)
            except Exception:
                return {"success": False, "error": f"HTTP {e.code}: {err}", "code": e.code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Telemetry & Health ---

    def ping(self) -> Dict[str, Any]:
        """Probes API connectivity, token validity, account ID, and fleet MCP gateway status."""
        t0 = time.perf_counter()
        workers = self.list_workers()
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        token_ok = len(workers) > 0 or self.request(f"/accounts/{self.account_id}").get("success") is True

        # Check fleet gateway
        gw_status = "UNKNOWN"
        gw_latency_ms = None
        try:
            t_gw = time.perf_counter()
            req_gw = urllib.request.Request(f"{FLEET_GATEWAY_URL}/", headers={"User-Agent": "NouGen-Probe/1.0"})
            with urllib.request.urlopen(req_gw, timeout=5) as r:
                gw_latency_ms = round((time.perf_counter() - t_gw) * 1000, 1)
                gw_status = "ONLINE" if r.status in (200, 404, 405) else f"HTTP_{r.status}"
        except Exception as e:
            gw_status = f"OFFLINE ({type(e).__name__})"

        return {
            "account_id": self.account_id,
            "account_name": self.account_name,
            "token_valid": token_ok,
            "api_latency_ms": latency_ms,
            "active_workers": len(workers),
            "gateway_url": FLEET_GATEWAY_URL,
            "gateway_status": gw_status,
            "gateway_latency_ms": gw_latency_ms
        }

    # --- Workers Management ---

    def list_workers(self) -> List[WorkerInfo]:
        res = self.request(f"/accounts/{self.account_id}/workers/scripts")
        if not res.get("success"):
            logger.error("Failed to list workers: %s", res.get("errors"))
            return []
        out = []
        for s in res.get("result", []):
            out.append(WorkerInfo(
                id=s.get("id", ""),
                created_on=(s.get("created_on") or "")[:19].replace("T", " "),
                modified_on=(s.get("modified_on") or "")[:19].replace("T", " "),
                usage_model=s.get("usage_model", "standard"),
                routes=s.get("routes", [])
            ))
        return out

    def get_worker(self, worker_name: str) -> Optional[WorkerInfo]:
        for w in self.list_workers():
            if w.id == worker_name:
                return w
        return None

    def delete_worker(self, worker_name: str) -> bool:
        res = self.request(f"/accounts/{self.account_id}/workers/scripts/{worker_name}", method="DELETE")
        return bool(res.get("success"))

    # --- Secrets Management ---

    def list_secrets(self, worker_name: str) -> List[SecretInfo]:
        res = self.request(f"/accounts/{self.account_id}/workers/scripts/{worker_name}/secrets")
        if not res.get("success"):
            return []
        return [SecretInfo(name=s.get("name", ""), type=s.get("type", "")) for s in res.get("result", [])]

    def put_secret(self, worker_name: str, name: str, value: str) -> bool:
        payload = {"name": name, "text": value, "type": "secret_text"}
        res = self.request(f"/accounts/{self.account_id}/workers/scripts/{worker_name}/secrets", method="PUT", data=payload)
        return bool(res.get("success"))

    def delete_secret(self, worker_name: str, name: str) -> bool:
        res = self.request(f"/accounts/{self.account_id}/workers/scripts/{worker_name}/secrets/{name}", method="DELETE")
        return bool(res.get("success"))

    def sync_secrets(self, worker_name: str, keys: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """Intelligently pulls secrets from Keymaker and puts them into the worker secrets store."""
        target_keys = keys or [
            "NOUGEN_RELAY_KEY", "GOOGLE_CLIENT_SECRET", "GOOGLE_CLIENT_ID",
            "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"
        ]
        synced, missing = [], []
        for k in target_keys:
            val = keymaker.get_secret(k)
            if val:
                if self.put_secret(worker_name, k, val.strip()):
                    synced.append(k)
            else:
                missing.append(k)
        return {"synced": synced, "missing": missing}

    # --- Storage Substrates: D1, KV, R2 ---

    def list_d1(self) -> List[Dict[str, Any]]:
        res = self.request(f"/accounts/{self.account_id}/d1/database")
        return res.get("result", []) if res.get("success") else []

    def query_d1(self, db_id_or_name: str, sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Runs a SQL statement on a Cloudflare D1 database."""
        # Resolve DB ID if name was passed
        db_id = db_id_or_name
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', db_id_or_name):
            for d in self.list_d1():
                if d.get("name") == db_id_or_name:
                    db_id = d.get("uuid", "")
                    break

        payload: Dict[str, Any] = {"sql": sql}
        if params:
            payload["params"] = params
        return self.request(f"/accounts/{self.account_id}/d1/database/{db_id}/query", method="POST", data=payload)

    def list_kv(self) -> List[Dict[str, Any]]:
        res = self.request(f"/accounts/{self.account_id}/storage/kv/namespaces")
        return res.get("result", []) if res.get("success") else []

    def get_kv(self, namespace_id: str, key: str) -> Optional[str]:
        res = self.request(f"/accounts/{self.account_id}/storage/kv/namespaces/{namespace_id}/values/{urllib.parse.quote(key)}")
        return res.get("raw") if isinstance(res, dict) and "raw" in res else None

    def put_kv(self, namespace_id: str, key: str, value: str) -> bool:
        url = f"{CF_API}/accounts/{self.account_id}/storage/kv/namespaces/{namespace_id}/values/{urllib.parse.quote(key)}"
        req = urllib.request.Request(
            url,
            data=value.encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "text/plain"},
            method="PUT"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status in (200, 201)
        except Exception:
            return False

    def list_r2(self) -> List[Dict[str, Any]]:
        res = self.request(f"/accounts/{self.account_id}/r2/buckets")
        return res.get("result", {}).get("buckets", []) if res.get("success") else []

    # --- Workers AI Native Edge Inference ---

    def run_ai(self, prompt: str, model: str = "@cf/meta/llama-3.1-8b-instruct", system_prompt: Optional[str] = None) -> str:
        """Executes zero-VRAM Cloudflare Workers AI edge model inference."""
        if system_prompt:
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            }
        else:
            payload = {"prompt": prompt}

        res = self.request(f"/accounts/{self.account_id}/ai/run/{model}", method="POST", data=payload)
        if res.get("success"):
            result = res.get("result", {})
            return result.get("response", "") or result.get("description", "") or str(result)
        raise RuntimeError(f"Workers AI error: {res.get('errors')}")

    def embed_ai(self, text: Union[str, List[str]], model: str = "@cf/baai/bge-small-en-v1.5") -> List[List[float]]:
        """Generates zero-VRAM text embeddings using Workers AI."""
        texts = [text] if isinstance(text, str) else text
        payload = {"text": texts}
        res = self.request(f"/accounts/{self.account_id}/ai/run/{model}", method="POST", data=payload)
        if res.get("success"):
            data = res.get("result", {}).get("data", [])
            return data
        raise RuntimeError(f"Workers AI embedding error: {res.get('errors')}")

    def list_ai_models(self) -> List[Dict[str, Any]]:
        """Returns recommended Workers AI model catalogue with categories."""
        return [
            {"id": "@cf/meta/llama-3.1-8b-instruct", "task": "Text Generation", "speed": "Ultra-Fast", "neurons_per_m": 2727},
            {"id": "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "task": "Heavy Reasoning", "speed": "Fast", "neurons_per_m": 22727},
            {"id": "@cf/google/gemma-4-26b-a4b-it", "task": "Balanced Tool-Calling", "speed": "Medium", "neurons_per_m": 9091},
            {"id": "@cf/qwen/qwen3-30b-a3b-fp8", "task": "Coding & Architecture", "speed": "Fast", "neurons_per_m": 9091},
            {"id": "@cf/baai/bge-small-en-v1.5", "task": "Text Embeddings (384d)", "speed": "Real-Time", "neurons_per_m": 909},
            {"id": "@cf/baai/bge-large-en-v1.5", "task": "Text Embeddings (1024d)", "speed": "Real-Time", "neurons_per_m": 1818},
        ]

    # --- Intelligent Directory Inspection & Auto-Deploy ---

    def inspect_directory(self, start_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Intelligently inspects a directory for Cloudflare Worker configurations, entrypoints,
        and bindings."""
        directory = (start_dir or Path.cwd()).resolve()
        config_path = None
        config_type = None

        for cand in ("wrangler.jsonc", "wrangler.json", "wrangler.toml"):
            p = directory / cand
            if p.is_file():
                config_path = p
                config_type = p.suffix.lstrip(".")
                break

        if not config_path:
            # Check package.json
            pkg = directory / "package.json"
            if pkg.is_file():
                config_path = pkg
                config_type = "package.json"

        is_worker = config_path is not None
        worker_name = directory.name
        main_entry = "src/worker.js"
        compat_date = "2024-04-05"
        bindings = {"vars": [], "kv": [], "d1": [], "r2": [], "ai": False}

        if config_path and config_path.is_file():
            raw_text = config_path.read_text(encoding="utf-8")
            if config_type in ("jsonc", "json"):
                clean_json = strip_jsonc_comments(raw_text)
                try:
                    data = json.loads(clean_json)
                    worker_name = data.get("name", worker_name)
                    main_entry = data.get("main", main_entry)
                    compat_date = data.get("compatibility_date", compat_date)
                    if "vars" in data:
                        bindings["vars"] = list(data["vars"].keys())
                    if "kv_namespaces" in data:
                        bindings["kv"] = [kv.get("binding") for kv in data["kv_namespaces"] if "binding" in kv]
                    if "d1_databases" in data:
                        bindings["d1"] = [d.get("binding") for d in data["d1_databases"] if "binding" in d]
                    if "r2_buckets" in data:
                        bindings["r2"] = [b.get("binding") for b in data["r2_buckets"] if "binding" in b]
                    if "ai" in data:
                        bindings["ai"] = True
                except Exception as e:
                    logger.debug("Failed parsing JSONC %s: %s", config_path, e)
            elif config_type == "toml" and tomllib:
                try:
                    data = tomllib.loads(raw_text)
                    worker_name = data.get("name", worker_name)
                    main_entry = data.get("main", main_entry)
                    compat_date = data.get("compatibility_date", compat_date)
                except Exception as e:
                    logger.debug("Failed parsing TOML %s: %s", config_path, e)

        # Resolve entry file
        entry_file = (directory / main_entry).resolve()
        if not entry_file.is_file():
            for alt_name in ("src/index.js", "worker.js", "index.js", "src/worker.ts"):
                alt = directory / alt_name
                if alt.is_file():
                    entry_file = alt
                    main_entry = alt_name
                    break

        # Check live state in Cloudflare
        live_worker = None
        try:
            live_worker = self.get_worker(worker_name)
        except Exception:
            pass

        return {
            "directory": str(directory),
            "is_worker": is_worker,
            "config_file": config_path.name if config_path else None,
            "worker_name": worker_name,
            "entry_file": str(entry_file),
            "entry_exists": entry_file.is_file(),
            "compatibility_date": compat_date,
            "bindings": bindings,
            "live_deployed": live_worker is not None,
            "live_info": live_worker
        }

    def deploy(self, script_name: str, script_path: Path, metadata_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Deploys an ES module worker bundle directly to the Cloudflare API."""
        if not script_path.is_file():
            raise FileNotFoundError(f"Worker code not found at: {script_path}")

        code = script_path.read_bytes()
        boundary = f"----WebKitFormBoundaryNouGenNativeDeploy{int(time.time())}"
        
        meta = {"main_module": "worker.js", "compatibility_date": "2024-04-05"}
        if metadata_overrides:
            meta.update(metadata_overrides)
        metadata_bytes = json.dumps(meta).encode("utf-8")

        body = bytearray()
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n".encode())
        body.extend(metadata_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"worker.js\"; filename=\"worker.js\"\r\nContent-Type: application/javascript+module\r\n\r\n".encode())
        body.extend(code)
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        url = f"{CF_API}/accounts/{self.account_id}/workers/scripts/{script_name}/content"
        req_put = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req_put, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def auto_deploy(self, start_dir: Optional[Path] = None, worker_name_override: Optional[str] = None) -> Dict[str, Any]:
        """Intelligently detects configuration, verifies syntax, and deploys the worker."""
        info = self.inspect_directory(start_dir)
        if not info["entry_exists"]:
            raise FileNotFoundError(f"Cannot auto-deploy: Entry point '{info['entry_file']}' does not exist.")

        worker_name = worker_name_override or info["worker_name"]
        entry_file = Path(info["entry_file"])

        # Node syntax check if .js
        if entry_file.suffix.lower() == ".js":
            chk = subprocess.run(["node", "--check", str(entry_file)], capture_output=True, text=True)
            if chk.returncode != 0:
                raise SyntaxError(f"Node syntax check failed on {entry_file.name}:\n{chk.stderr[:400]}")

        meta = {"compatibility_date": info.get("compatibility_date", "2024-04-05")}
        res = self.deploy(worker_name, entry_file, metadata_overrides=meta)
        res["worker_name"] = worker_name
        res["entry_point"] = str(entry_file)
        res["directory"] = info["directory"]
        return res
