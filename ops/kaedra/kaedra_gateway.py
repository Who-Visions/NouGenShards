#!/usr/bin/env python3
"""Token-gated gateway putting phoebus's local Ollama models on the fleet.

Why this exists
---------------
Coach mode says route bulk generation to a local model before a cloud call,
but no lane could reach one: Ollama binds loopback on phoebus, and the fleet
Worker runs at Cloudflare's edge. This is the same shape as the shard
gateway - Worker -> named tunnel -> local service - so the fleet gets a
`kaedra_ask` tool that costs nothing per token.

Ollama has NO authentication of its own. Exposing 11434 through a tunnel
would hand the internet a free GPU, so this process is the fence:

  * every generate call requires X-Kaedra-Token (constant-time compared)
  * only allow-listed models can be named - no pulling or running arbitrary
    weights through the public hostname
  * /health is unauthenticated but returns booleans only, matching the NGS
    node's convention, so the Worker can probe reachability without a secret
  * bound to loopback; the tunnel ingress is the only path in

keep_alive
----------
A cold model load measured 38s on this box, which blows past MCP client
timeouts (agy's default is 30s). Every request pins the model resident with
keep_alive=-1, so the first call after a reboot is slow and every later one
is inference-speed.
"""

import hmac
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
TOKEN = os.environ.get("KAEDRA_GATEWAY_TOKEN", "")
PORT = int(os.environ.get("KAEDRA_GATEWAY_PORT", "4455"))
# Allow-list: the Kaedra personas plus their base models. Anything else is a
# 403 - this hostname is not a general-purpose Ollama proxy.
ALLOWED = set(filter(None, os.environ.get(
    "KAEDRA_MODELS",
    "kaedracode:e2b,kaedracode:e4b,kaedracode:latest,gemma4:e2b,gemma4:e4b",
).split(",")))
DEFAULT_MODEL = os.environ.get("KAEDRA_DEFAULT_MODEL", "kaedracode:e2b")
# Ollama can take minutes on a cold load; the tunnel and Worker both cap
# earlier, so this only needs to be generous enough not to be the first cap.
TIMEOUT = int(os.environ.get("KAEDRA_TIMEOUT", "180"))


def _ollama(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        OLLAMA + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _models() -> list:
    try:
        req = urllib.request.Request(OLLAMA + "/api/tags")
        with urllib.request.urlopen(req, timeout=10) as r:
            return [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
    except Exception:
        return []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003 - quieter launchd logs
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, code: int, body: dict):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authed(self) -> bool:
        if not TOKEN:
            self._send(503, {"error": "gateway token not configured"})
            return False
        supplied = self.headers.get("X-Kaedra-Token", "")
        if not supplied:
            auth = self.headers.get("Authorization", "")
            if auth[:7].lower() == "bearer ":
                supplied = auth[7:].strip()
        if not supplied or not hmac.compare_digest(str(supplied), str(TOKEN)):
            self._send(401, {"error": "invalid gateway token"})
            return False
        return True

    def do_GET(self):
        if self.path.split("?")[0] != "/health":
            self._send(404, {"error": "not found"})
            return
        available = _models()
        # Booleans and model NAMES only - never the token, never a path.
        self._send(200, {
            "status": "ready" if available else "ollama_unreachable",
            "ollama_up": bool(available),
            "token_configured": bool(TOKEN),
            "allowed_models": sorted(ALLOWED),
            "loaded_models": sorted(set(available) & ALLOWED),
            "default_model": DEFAULT_MODEL,
        })

    def do_POST(self):
        if self.path.split("?")[0] != "/generate":
            self._send(404, {"error": "not found"})
            return
        if not self._authed():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception:
            self._send(400, {"error": "invalid JSON body"})
            return

        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            self._send(400, {"error": "prompt is required"})
            return
        model = body.get("model") or DEFAULT_MODEL
        if model not in ALLOWED:
            self._send(403, {"error": "model not allowed", "allowed": sorted(ALLOWED)})
            return

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            # Pin the model in memory: the 38s cold load is a one-time cost,
            # not a per-call one.
            "keep_alive": -1,
        }
        if body.get("system"):
            payload["system"] = body["system"]
        options = {}
        if isinstance(body.get("temperature"), (int, float)):
            options["temperature"] = body["temperature"]
        if isinstance(body.get("num_predict"), int):
            options["num_predict"] = body["num_predict"]
        if options:
            payload["options"] = options

        try:
            out = _ollama("/api/generate", payload)
        except urllib.error.URLError as e:
            self._send(502, {"error": "ollama unreachable", "detail": str(e)[:200]})
            return
        except Exception as e:
            self._send(500, {"error": "generate failed", "detail": str(e)[:200]})
            return

        self._send(200, {
            "model": model,
            "response": out.get("response", ""),
            "eval_count": out.get("eval_count"),
            "total_ms": round(out.get("total_duration", 0) / 1e6),
        })


if __name__ == "__main__":
    print(f"kaedra gateway on 127.0.0.1:{PORT} -> {OLLAMA} "
          f"(token={'set' if TOKEN else 'MISSING'}, models={sorted(ALLOWED)})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
