"""Host-scoped MCP: one node, a narrower tool set per public hostname.

The node's full MCP server carries every tool (vault writes, shard deletion,
remote exec). Some public hostnames front that same server for one purpose:
a messages hostname is the NouGenMsg connector, so a client that adds it
should see messaging tools, not the whole vault. This ASGI wrapper sits inside
the token gate and, only for a scoped host:

- filters ``tools/list`` results down to the host's allowlist,
- refuses ``tools/call`` for any other tool with a JSON-RPC error (the call
  never reaches the server),
- renames ``serverInfo.name`` in ``initialize`` so the client shows the
  connector's own name.

Every other host passes through byte for byte. The MCP app runs in stateless
JSON mode (one JSON body per request), which is what makes buffering safe here.
Which hosts are scoped is deployment config, never code (operator hostnames
stay out of the public runtime): ``NOUGEN_MCP_MSG_HOSTS`` is a comma list of
hosts that get the messaging profile below, and ``NOUGEN_MCP_HOST_SCOPES``
(JSON ``{host: {"name":.., "tools": [..]}}``) adds or overrides any host.
With neither set, no host is scoped and every request passes through.

``NOUGEN_MCP_OPEN_HOSTS`` (comma list) turns on fail-closed: once it and a
scope are set, a request whose Host and X-Forwarded-Host name neither a scoped
host nor an open (full-surface) host is refused with 403 instead of passing
through. That covers a proxy that rewrites Host to an internal value while the
client supplies its own X-Forwarded-Host. Loopback callers that reach the node
directly need their host (for example ``127.0.0.1``) listed as open.
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

MESSAGING_PROFILE: Dict[str, Any] = {"name": "NouGenMsg", "tools": list(MSGS_TOOLS)}


def load_scopes(env: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    """Scopes keyed by lower-case host, built from the environment only.
    A malformed JSON override is ignored (the messaging hosts still apply), so a
    typo never widens a scoped host back to every tool."""
    env = os.environ if env is None else env
    scopes: Dict[str, Dict[str, Any]] = {}
    for host in (env.get("NOUGEN_MCP_MSG_HOSTS") or "").split(","):
        if host.strip():
            scopes[_bare(host)] = MESSAGING_PROFILE
    raw = (env.get("NOUGEN_MCP_HOST_SCOPES") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        # Entry by entry: a bad host entry is skipped, never fatal. Scopes load
        # when app.py mounts /mcp, so raising here would keep the node from booting.
        if isinstance(parsed, dict):
            for host, v in parsed.items():
                if isinstance(host, str) and isinstance(v, dict) and isinstance(v.get("tools"), list):
                    name = v.get("name") if isinstance(v.get("name"), str) else None
                    scopes[_bare(host)] = {"name": name, "tools": [t for t in v["tools"] if isinstance(t, str)]}
    return {h: {"name": v.get("name"), "tools": frozenset(v["tools"])} for h, v in scopes.items()}


def load_open_hosts(env: Optional[Dict[str, str]] = None) -> frozenset:
    """Hosts allowed the full tool surface once fail-closed is on."""
    env = os.environ if env is None else env
    return frozenset(h for h in (_bare(x) for x in (env.get("NOUGEN_MCP_OPEN_HOSTS") or "").split(",")) if h)


def _bare(host: str) -> str:
    """Hostname only: lower case, no port, no brackets, no trailing root dot,
    so "MSGS.example.test.:443" and "msgs.example.test" are the same host."""
    h = host.strip().lower()
    if h.startswith("["):
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:
        h = h.split(":", 1)[0]
    return h.rstrip(".")


def _hosts(scope: dict) -> list:
    """Every hostname the request could be judged by: the Host header and each
    X-Forwarded-Host entry. A client controls X-Forwarded-Host, so it must
    never be able to talk a scoped host out of its scope."""
    out = []
    for k, v in scope.get("headers") or []:
        name = k.decode("latin-1").lower()
        if name in ("host", "x-forwarded-host"):
            out.extend(h for h in (_bare(x) for x in v.decode("latin-1").split(",")) if h)
    return out


def _resolve(scopes: Dict[str, Dict[str, Any]], scope: dict) -> Optional[Dict[str, Any]]:
    """Narrowest scope wins: if any candidate host is scoped, the request is
    scoped, and when several are, only tools allowed by all of them pass."""
    confs = [scopes[h] for h in _hosts(scope) if h in scopes]
    if not confs:
        return None
    tools = frozenset.intersection(*(c["tools"] for c in confs))
    return {"name": confs[0].get("name"), "tools": tools}


def _error(req_id: Any, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": message}}


def _blocked(msg: Any, allowed: frozenset) -> Optional[dict]:
    if isinstance(msg, dict) and msg.get("method") == "tools/call":
        params = msg.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        # A missing, non-string or unhashable name is refused, not passed
        # through: membership on a dict/list would raise and turn into a 500.
        if not isinstance(name, str) or name not in allowed:
            shown = name if isinstance(name, str) else type(name).__name__
            return _error(msg.get("id"), f"tool '{shown}' is not available on this connector")
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

    def __init__(self, app: Callable[..., Awaitable[None]], scopes: Optional[Dict[str, Dict[str, Any]]] = None,
                 open_hosts: Optional[Iterable[str]] = None):
        self.app = app
        self.scopes = load_scopes() if scopes is None else scopes
        self.open_hosts = load_open_hosts() if open_hosts is None else frozenset(_bare(h) for h in open_hosts)

    async def __call__(self, scope, receive, send):
        conf = _resolve(self.scopes, scope) if scope.get("type") == "http" else None
        if conf is None and scope.get("type") == "http" and self.scopes and self.open_hosts \
                and not any(h in self.open_hosts for h in _hosts(scope)):
            out = json.dumps({"error": "host not recognised"}).encode()
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(out)).encode())]})
            await send({"type": "http.response.body", "body": out})
            return
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
            # First call: the buffered body. After that, defer to the real
            # receive so a framework watching for disconnect waits for an actual
            # client disconnect instead of seeing a synthetic one at once.
            nonlocal sent
            if sent:
                return await receive()
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
