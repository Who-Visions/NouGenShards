"""NouGen Tunnel Connector (Ngrok Shang Tsung Assimilation).

Provides programmatic edge ingress tunnels for NouGenMsg nodes, MCP tool
servers, and local web applications (e.g. Next.js / Whovisions) using the
vaulted credentials in ~/.nougen/secrets/ngrok.env.
"""
from __future__ import annotations

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

VAULT_PATH = Path.home() / ".nougen" / "secrets" / "ngrok.env"


def get_ngrok_token() -> str:
    """Read the Ngrok authtoken from the secure vault or environment."""
    env_token = os.environ.get("NGROK_AUTHTOKEN")
    if env_token:
        return env_token.strip()

    if VAULT_PATH.exists():
        try:
            with open(VAULT_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NGROK_AUTHTOKEN="):
                        return line.split("=", 1)[1].strip().strip("\"'")
        except Exception:
            pass

    return ""


async def start_tunnel_async(
    port: int,
    service_name: Optional[str] = None,
    domain: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Start an ngrok edge tunnel programmatically using the native ngrok SDK."""
    try:
        import ngrok
    except ImportError:
        raise RuntimeError("ngrok package not installed. Run `pip install ngrok`.")

    token = auth_token or get_ngrok_token()
    if not token:
        raise ValueError("NGROK_AUTHTOKEN not found in vault (~/.nougen/secrets/ngrok.env) or environment.")

    # Configure session
    builder = ngrok.SessionBuilder().authtoken(token)
    session = await builder.connect()

    listener_builder = session.http_endpoint()
    if domain:
        listener_builder.domain(domain)
    if service_name:
        listener_builder.metadata(f"nougen:{service_name}")

    listener = await listener_builder.listen_and_forward(f"localhost:{port}")
    public_url = listener.url()

    return {
        "url": public_url,
        "port": port,
        "service": service_name or "generic",
        "domain": domain,
        "status": "online",
        "listener": listener,
        "session": session,
    }


def start_tunnel(
    port: int,
    service_name: Optional[str] = None,
    domain: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous entrypoint for starting a tunnel."""
    return asyncio.run(start_tunnel_async(port, service_name, domain, auth_token))


def get_active_tunnels(api_url: Optional[str] = None, timeout_s: Optional[float] = None) -> Dict[str, Any]:
    """Inspect live ngrok tunnels via the local agent API. Fails soft when no agent is running."""
    import json
    import urllib.request
    import urllib.error
    url = (api_url or os.environ.get("NGROK_API_URL") or f"http://127.0.0.1:{os.environ.get('NGROK_API_PORT', '4040')}").rstrip("/") + "/api/tunnels"
    timeout = float(timeout_s if timeout_s is not None else os.environ.get("NGROK_API_TIMEOUT_S", "3"))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"status": "down", "api_url": url, "tunnels": [], "error": str(exc)}
    tunnels = [
        {"name": t.get("name"), "public_url": t.get("public_url"), "proto": t.get("proto"),
         "addr": (t.get("config") or {}).get("addr")}
        for t in data.get("tunnels", [])
    ]
    return {"status": "up" if tunnels else "idle", "api_url": url, "count": len(tunnels), "tunnels": tunnels}
