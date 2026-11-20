"""Host-scoped MCP: one node, a narrower tool set per public hostname.

The node's full MCP server carries every tool (vault writes, shard deletion,
remote exec). Some public hostnames front that same server for one purpose:
``msgs.nougenai.com`` is the NouGenMsg connector, so a client that adds it
should see messaging tools, not the whole vault. This ASGI wrapper sits inside
the token gate and, only for a scoped host:

- filters ``tools/list`` results down to the host's allowlist,
- refuses ``tools/call`` for any other tool with a JSON-RPC error (the call
  never reaches the server),
- renames ``serverInfo.name`` in ``initialize`` so the client shows the
  connector's own name.

Every other host passes through byte for byte. The MCP app runs in stateless
JSON mode (one JSON body per request), which is what makes buffering safe here.
Scopes come from ``NOUGEN_MCP_HOST_SCOPES`` (JSON ``{host: {"name":..,
"tools": [..]}}``) and default to the msgs scope below.
"""
from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional

MSGS_TOOLS = (
    "nougenmsg",
    "nougenmsg_latest",
    "nougenmsg_inbox",
    "nougenmsg_read",
    "nougenmsg_search",
    "relay_open_legs",
    "relay_claim_leg",
    "relay_create_leg",
    "relay_ack_leg",
    "node_status",
)

DEFAULT_SCOPES: Dict[str, Dict[str, Any]] = {
    "msgs.nougenai.com": {"name": "NouGenMsg", "tools": list(MSGS_TOOLS)},
}


def load_scopes(env: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    """Scopes keyed by lower-case host. A malformed override falls back to the
    defaults rather than opening every host to every tool."""
    env = os.environ if env is None else env
    raw = (env.get("NOUGEN_MCP_HOST_SCOPES") or "").strip()
    scopes = DEFAULT_SCOPES
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and all(
                isinstance(v, dict) and isinstance(v.get("tools"), list) for v in parsed.values()
            ):
                scopes = parsed
        except ValueError:
            pass
    return {h.lower(): {"name": v.get("name"), "tools": frozenset(v["tools"])} for h, v in scopes.items()}


def _host(scope: dict) -> str:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
    host = headers.get("x-forwarded-host") or headers.get("host") or ""
    return host.split(",")[0].strip().split(":")[0].lower()


def _error(req_id: Any, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": message}}


def _blocked(msg: Any, allowed: frozenset) -> Optional[dict]:
    if isinstance(msg, dict) and msg.get("method") == "tools/call":
        name = (msg.get("params") or {}).get("name")
        if name not in allowed:
            return _error(msg.get("id"), f"tool '{name}' is not available on this connector")
    return None


def _rewrite(msg: Any, allowed: frozenset, server_name: Optional[str]) -> Any:
    if not isinstance(msg, dict):
        return msg
    result = msg.get("result")
    if isinstance(result, dict):
        if isinstance(result.get("tools"), list):
            result["tools"] = [t for t in result["tools"] if isinstance(t, dict) and t.get("name") in allowed]
        info = result.get("serverInfo")
        if server_name and isinstance(info, dict):
            info["name"] = server_name
    return msg


class HostScopedMCP:
    """ASGI wrapper; see module docstring."""

    def __init__(self, app: Callable[..., Awaitable[None]], scopes: Optional[Dict[str, Dict[str, Any]]] = None):
        self.app = app
        self.scopes = load_scopes() if scopes is None else scopes

    async def __call__(self, scope, receive, send):
        conf = self.scopes.get(_host(scope)) if scope.get("type") == "http" else None
        if conf is None or scope.get("method") != "POST":
            return await self.app(scope, receive, send)

        body = b""
        while True:
            event = await receive()
            body += event.get("body", b"")
            if not event.get("more_body"):
                break
        allowed = conf["tools"]
        try:
            payload = json.loads(body or b"null")
        except ValueError:
            payload = None

        msgs: Iterable[Any] = payload if isinstance(payload, list) else [payload]
        refusals = [r for r in (_blocked(m, allowed) for m in msgs) if r]
        if refusals:
            out = json.dumps(refusals if isinstance(payload, list) else refusals[0]).encode()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(out)).encode())]})
            await send({"type": "http.response.body", "body": out})
            return

        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        start: Dict[str, Any] = {}
        chunks = []

        async def capture(event):
            if event["type"] == "http.response.start":
                start.update(event)
            elif event["type"] == "http.response.body":
                chunks.append(event.get("body", b""))
                if not event.get("more_body"):
                    await flush()

        async def flush():
            raw = b"".join(chunks)
            headers = list(start.get("headers") or [])
            ctype = next((v for k, v in headers if k.lower() == b"content-type"), b"")
            if b"json" in ctype:
                try:
                    data = json.loads(raw)
                    data = [_rewrite(m, allowed, conf.get("name")) for m in data] if isinstance(data, list) \
                        else _rewrite(data, allowed, conf.get("name"))
                    raw = json.dumps(data).encode()
                except ValueError:
                    pass
            headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
            headers.append((b"content-length", str(len(raw)).encode()))
            await send({"type": "http.response.start", "status": start.get("status", 200), "headers": headers})
            await send({"type": "http.response.body", "body": raw})

        await self.app(scope, replay, capture)
