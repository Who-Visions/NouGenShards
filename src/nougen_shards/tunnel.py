"""NouGen Tunnel Connector.

Fleet ingress runs on Cloudflare tunnels; get_active_tunnels() reports their
health. The ngrok helpers below remain only for ad-hoc local sharing.

Legacy ngrok notes:

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


# Routes are never baked in: each install names its own front door and the
# route behind it for every machine and tenant, so a tester sees their own
# fleet. Resolution order: NOUGEN_TUNNEL_TARGETS ("name=url,name=url"), then the
# endpoints file's "tunnel_routes" ({"name": "url"} or ["name=url"]), plus
# fleet_gateway_url as the front door when the routes don't already name it.
# Machines that sleep on purpose (unreachable = asleep, never an outage) come
# from NOUGEN_TUNNEL_SLEEPERS or the endpoints file's "tunnel_sleepers".
# cloudflared's metrics server picks the first free port in this range unless --metrics sets one.
DEFAULT_CLOUDFLARED_METRICS = tuple(f"127.0.0.1:{p}" for p in range(20241, 20246))


def _http_get(url: str, timeout: float):
    """GET url and return (status, body_text). HTTP errors return their status; network errors raise OSError."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "nougen-tunnel-status/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(4096).decode("utf-8", "replace")
        except Exception:
            body = ""
        return exc.code, body


def _split_env(name: str, default):
    raw = os.environ.get(name, "")
    vals = [v.strip() for v in raw.replace(";", ",").split(",") if v.strip()]
    return tuple(vals) if vals else tuple(default)


def cloudflared_local(metrics: Optional[tuple] = None, timeout_s: float = 2.0) -> Dict[str, Any]:
    """Ask this box's cloudflared connector whether it holds live edge connections (/ready on its metrics server)."""
    import json
    tried = []
    for addr in metrics or _split_env("NOUGEN_CLOUDFLARED_METRICS", DEFAULT_CLOUDFLARED_METRICS):
        base = addr if addr.startswith("http") else f"http://{addr}"
        url = base.rstrip("/") + "/ready"
        tried.append(url)
        try:
            code, body = _http_get(url, timeout_s)
        except (OSError, ValueError):
            continue
        try:
            data = json.loads(body) if body else {}
        except ValueError:
            data = {}
        conns = int(data.get("readyConnections") or 0)
        return {"status": "up" if code == 200 and conns > 0 else "down", "metrics": url,
                "ready_connections": conns, "connector_id": data.get("connectorId"), "http": code}
    return {"status": "not_running", "tried": tried,
            "fix": "no cloudflared metrics server answered on this box; start the tunnel service, or set NOUGEN_CLOUDFLARED_METRICS"}


def _configured_targets():
    from nougen_shards import endpoints
    env = _split_env("NOUGEN_TUNNEL_TARGETS", ())
    if env:
        return list(env)
    out = []
    routes = endpoints.resolve_raw("tunnel_routes")
    if isinstance(routes, dict):
        out = [(str(k), str(v)) for k, v in routes.items()]
    elif isinstance(routes, list):
        out = [str(v) for v in routes]
    front = endpoints.fleet_gateway_url()
    if front:
        door = front.rstrip("/") + "/health"
        if door not in {u for _, u in _targets(out)}:
            out.insert(0, ("front-door", door))
    return out


def _configured_sleepers():
    from nougen_shards import endpoints
    env = _split_env("NOUGEN_TUNNEL_SLEEPERS", ())
    if env:
        return set(env)
    raw = endpoints.resolve_raw("tunnel_sleepers")
    return {str(x) for x in raw} if isinstance(raw, list) else set()


def _targets(raw=None):
    """Normalise targets to (name, url): accepts name=url strings, (name, url) pairs or bare hosts."""
    out = []
    for t in raw if raw is not None else _configured_targets():
        if isinstance(t, (tuple, list)):
            name, url = t[0], t[1]
        elif "=" in t:
            name, url = t.split("=", 1)
        else:
            name, url = t, t
        name, url = name.strip(), url.strip()
        if not url.startswith("http"):
            url = f"https://{url}/health"
        out.append((name, url))
    return out


def probe_host(name: str, url: str, timeout_s: float = 5.0) -> Dict[str, Any]:
    """GET one route through Cloudflare's edge and classify what came back."""
    try:
        code, body = _http_get(url, timeout_s)
    except (OSError, ValueError) as exc:
        return {"name": name, "url": url, "status": "down", "error": str(exc)[:200]}
    if 200 <= code < 300:
        status = "up"
    elif code == 530 or "1033" in body[:2048]:
        status = "tunnel_down"  # Cloudflare edge is fine but no connector holds this tunnel
    elif code in (502, 503, 504, 521, 522, 523, 524):
        status = "origin_down"  # tunnel reached, local service behind it is not answering
    elif code < 500:
        status = "reachable"  # the origin answered (auth or a missing /health route), so the tunnel is up
    else:
        status = "error"
    return {"name": name, "url": url, "status": status, "http": code}


def get_active_tunnels(targets=None, timeout_s: Optional[float] = None,
                       metrics: Optional[tuple] = None, sleepers=None) -> Dict[str, Any]:
    """Cloudflare tunnel status: the front door, each machine's route, and this box's cloudflared."""
    from concurrent.futures import ThreadPoolExecutor
    timeout = float(timeout_s if timeout_s is not None else os.environ.get("NOUGEN_TUNNEL_TIMEOUT_S", "5"))
    pairs = _targets(targets)
    sleep = set(sleepers) if sleepers is not None else _configured_sleepers()
    if not pairs:
        return {"provider": "cloudflare", "status": "not_configured", "routes": [],
                "local_connector": cloudflared_local(metrics, min(timeout, 2.0)),
                "fix": "name this install's routes: NOUGEN_TUNNEL_TARGETS=\"front-door=https://<your front door>/health,"
                       "<machine>=https://<its route>/health\" or \"tunnel_routes\" in the endpoints file"}
    with ThreadPoolExecutor(max_workers=min(8, len(pairs) + 1)) as pool:
        local_f = pool.submit(cloudflared_local, metrics, min(timeout, 2.0))
        results = list(pool.map(lambda nu: probe_host(nu[0], nu[1], timeout), pairs))
        local = local_f.result()
    for r in results:
        if r["name"] in sleep and r["status"] not in ("up", "reachable"):
            r["status"] = "asleep"
    counted = [r for r in results if r["status"] != "asleep"]
    ok = [r for r in counted if r["status"] in ("up", "reachable")]
    if counted and len(ok) == len(counted):
        status = "up"
    elif ok:
        status = "degraded"
    else:
        status = "down"
    return {"provider": "cloudflare", "status": status, "up": len(ok), "total": len(counted),
            "routes": results, "local_connector": local}
