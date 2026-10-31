"""How to USE a key, stored next to the key.

The Keymaker holds the secret; this module holds the instructions for presenting it
(which header, what base URL, the MCP transport, the traps), so an agent that
fetches a key never has to ask the owner how to send it. Records contain no secret
values and are safe to print.

Built-in records match a key NAME by prefix. A per-vault override table
(`secret_usage` in the secrets DB) wins over the built-ins, so a new provider is
one `set_usage()` call, not a code change.

    nougen auth usage EXA_API_KEY
    nougen auth usage EXA_API_KEY --json
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from . import keymaker

BEARER = {"header": "Authorization", "scheme": "Bearer {key}"}

# prefixes are matched against the upper-cased key name, longest prefix first
_BUILTIN: list[dict[str, Any]] = [
    {
        "provider": "Exa",
        "example": {"path": "/search", "method": "POST", "body": '{"query": "test", "numResults": 1}'},
        "prefixes": ["EXA_", "EXA"],
        "base_url": "https://api.exa.ai",
        "auth": {"header": "x-api-key", "scheme": "{key}"},
        "mcp": {"url": "https://mcp.exa.ai/mcp", "type": "http"},
        "docs": ["https://exa.ai/docs/llms.txt", "https://exa.ai/auth.md"],
        "notes": [
            "MCP transport is streamable HTTP: type \"http\", never \"sse\" (SSE gets a 405).",
            "Send the key in the x-api-key header, not in the URL query string.",
            "An explicit ?tools= list replaces the defaults; current tools are "
            "web_search_exa, web_fetch_exa, web_search_advanced_exa, agent_run.",
            "agent_run is usage-billed: leave it out unless spending is approved.",
        ],
    },
    {
        "provider": "OpenRouter",
        "example": {"path": "/models"},
        "prefixes": ["OPENROUTER", "OPENR"],
        "base_url": "https://openrouter.ai/api/v1",
        "auth": BEARER,
        "docs": ["https://openrouter.ai/docs"],
        "notes": ["Free models end in :free and return 429 under load."],
    },
    {
        "provider": "Hugging Face",
        "prefixes": ["HF_", "HF-", "HUGGINGFACE"],
        "base_url": "https://router.huggingface.co/v1",
        "auth": BEARER,
        "docs": ["https://huggingface.co/docs/inference-providers"],
        "notes": ["Hub API is https://huggingface.co/api with the same Bearer token."],
    },
    {
        "provider": "Ollama Cloud",
        "example": {"path": "/tags"},
        "prefixes": ["OLLAMACLOUD", "OLLAMA"],
        "base_url": "https://ollama.com/api",
        "auth": BEARER,
        "docs": ["https://docs.ollama.com/cloud"],
        "notes": ["Local Ollama (http://127.0.0.1:11434) needs no key."],
    },
    {
        "provider": "Google Gemini",
        "example": {"path": "/models"},
        "prefixes": ["GEMINI", "GOOGLE_API"],
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "auth": {"header": "x-goog-api-key", "scheme": "{key}"},
        "docs": ["https://ai.google.dev/api"],
    },
    {
        "provider": "Anthropic",
        "example": {"path": "/models"},
        "prefixes": ["ANTHROPIC"],
        "base_url": "https://api.anthropic.com/v1",
        "auth": {"header": "x-api-key", "scheme": "{key}"},
        "extra_headers": {"anthropic-version": "2023-06-01"},
        "docs": ["https://docs.anthropic.com/en/api"],
    },
    {
        "provider": "OpenAI",
        "example": {"path": "/models"},
        "prefixes": ["OPENAI"],
        "base_url": "https://api.openai.com/v1",
        "auth": BEARER,
        "docs": ["https://platform.openai.com/docs/api-reference"],
    },
    {
        "provider": "Cloudflare",
        "example": {"path": "/user/tokens/verify"},
        "prefixes": ["CLOUDFLARE"],
        "base_url": "https://api.cloudflare.com/client/v4",
        "auth": BEARER,
        "docs": ["https://developers.cloudflare.com/api"],
        "notes": ["Account-scoped calls need CLOUDFLARE_ACCOUNT_ID if the token sees several accounts."],
    },
    {
        "provider": "NouGen node / gateway",
        "prefixes": ["NGS_NODE"],  # not "NGS_": NGS_CLOUD_CREDENTIALS is a "url,token" pair, not a node token
        "resolve": "fleet_gateway",  # host comes from endpoints config, never hardcoded here
        "auth": {"header": "X-NGS-Token", "scheme": "{key}"},
        "notes": [
            "/mcp/ needs the trailing slash; auth is X-NGS-Token, not Authorization.",
            "Cloudflare returns 403 to Python's default User-Agent; send a normal one.",
            "Each node has its own token; a 401 on one node says nothing about another.",
        ],
    },
    {
        "provider": "Tavily",
        "example": {"path": "/search", "method": "POST", "body": '{"query": "test", "max_results": 1}'},
        "prefixes": ["TAVILY"],
        "base_url": "https://api.tavily.com",
        "auth": BEARER,
        "docs": ["https://docs.tavily.com"],
    },
    {
        "provider": "SerpAPI",
        "prefixes": ["SERPAPI", "SERP"],
        "base_url": "https://serpapi.com/search",
        "auth": {"query": "api_key"},
        "docs": ["https://serpapi.com/search-api"],
        "notes": ["Key goes in the api_key query parameter; there is no auth header."],
    },
    {
        "provider": "TMDB",
        "example": {"path": "/configuration"},
        "prefixes": ["TMDB"],
        "base_url": "https://api.themoviedb.org/3",
        "auth": BEARER,
        "docs": ["https://developer.themoviedb.org/docs"],
        "notes": ["A v3 API key (short hex) goes in the api_key query parameter instead; "
                  "a v4 read token (long JWT) goes in the Bearer header."],
    },
    {
        "provider": "OMDb",
        "prefixes": ["OMDB"],
        "base_url": "https://www.omdbapi.com/",
        "auth": {"query": "apikey"},
        "docs": ["https://www.omdbapi.com"],
    },
    {
        "provider": "Notion",
        "example": {"path": "/users/me"},
        "prefixes": ["NOTION"],
        "base_url": "https://api.notion.com/v1",
        "auth": BEARER,
        "extra_headers": {"Notion-Version": "2022-06-28"},
        "docs": ["https://developers.notion.com/reference"],
    },
    {
        "provider": "Netlify",
        "prefixes": ["NETLIFY"],
        "base_url": "https://api.netlify.com/api/v1",
        "auth": BEARER,
        "docs": ["https://docs.netlify.com/api/get-started"],
    },
    {
        "provider": "GitHub",
        "example": {"path": "/user"},
        "prefixes": ["GITHUB"],
        "base_url": "https://api.github.com",
        "auth": BEARER,
        "extra_headers": {"Accept": "application/vnd.github+json"},
        "notes": ["Prefer the gh CLI where it is installed."],
    },
    {
        "provider": "GitLab",
        "example": {"path": "/user"},
        "prefixes": ["GITLAB"],
        "base_url": "https://gitlab.com/api/v4",
        "auth": {"header": "PRIVATE-TOKEN", "scheme": "{key}"},
        "docs": ["https://docs.gitlab.com/ee/api"],
    },
    {
        "provider": "RapidAPI",
        "prefixes": ["RAPIDAPI"],
        "auth": {"header": "X-RapidAPI-Key", "scheme": "{key}"},
        "notes": ["Every call also needs X-RapidAPI-Host set to the specific API's host."],
    },
]


def _db_path():
    # tenant-aware: a tenant session must read and write its own vault, not the owner's
    return keymaker.db_path()


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS secret_usage ("
        "secret_key TEXT PRIMARY KEY, usage_json TEXT NOT NULL, updated TEXT NOT NULL)"
    )


def set_usage(key: str, usage: dict[str, Any]) -> None:
    """Store a usage record for one key name (override). Never stores a secret."""
    if not key or not isinstance(usage, dict):
        raise ValueError("key and a usage dict are required")
    keymaker.init_vault()
    conn = sqlite3.connect(str(_db_path()))
    try:
        _ensure_table(conn)
        conn.execute(
            "INSERT OR REPLACE INTO secret_usage (secret_key, usage_json, updated) VALUES (?,?,?)",
            (key, json.dumps(usage, sort_keys=True), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def _override(key: str) -> Optional[dict[str, Any]]:
    path = _db_path()
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT usage_json FROM secret_usage WHERE secret_key = ?", (key,)).fetchone()
        finally:
            conn.close()
        return json.loads(row[0]) if row else None
    except (sqlite3.Error, OSError, ValueError):
        return None


def _builtin(key: str) -> Optional[dict[str, Any]]:
    name = key.upper()
    best: tuple[int, Optional[dict[str, Any]]] = (0, None)
    for record in _BUILTIN:
        for prefix in record["prefixes"]:
            if name.startswith(prefix) and len(prefix) > best[0]:
                best = (len(prefix), record)
    return best[1]


def usage_for(key: str) -> Optional[dict[str, Any]]:
    """The usage record for a key name, or None when nothing is known. Never invents."""
    record = _override(key) or _builtin(key)
    if record is None:
        return None
    out = {k: v for k, v in record.items() if k not in ("prefixes", "resolve")}
    if record.get("resolve") == "fleet_gateway":
        from . import endpoints  # operator hosts are configured, not hardcoded in runtime code
        gateway = endpoints.fleet_gateway_url()
        if gateway:
            out["base_url"] = gateway
            out["mcp"] = {"url": gateway + "/mcp/", "type": "http"}
    out["key_name"] = key
    out["curl"] = _curl(key, out)
    return out


def _curl(key: str, record: dict[str, Any]) -> Optional[str]:
    """A copy-paste example that references the key by $NAME, never by value.

    Providers with an `example` ({path, method, body}) get a real request. Others
    get an auth-only template (the base URL is not an API operation), flagged as such.
    """
    base = record.get("base_url")
    if not base:
        return None
    auth = record.get("auth") or {}
    example = record.get("example") or {}
    base = base.rstrip("/") + example["path"] if example.get("path") else base
    parts = ["curl -s"]
    if example.get("method") and example["method"] != "GET":
        parts.append(f"-X {example['method']}")
    if auth.get("header"):
        parts.append(f'-H "{auth["header"]}: {auth["scheme"].replace("{key}", "$" + key)}"')
    for name, value in (record.get("extra_headers") or {}).items():
        parts.append(f'-H "{name}: {value}"')
    url = base
    if auth.get("query"):
        url += ("&" if "?" in url else "?") + f"{auth['query']}=${key}"
    if example.get("body"):
        parts.append('-H "content-type: application/json"')
        parts.append(f"-d '{example['body']}'")
    parts.append(f'"{url}"')  # double quotes so the shell expands $KEY
    line = " ".join(parts)
    if example.get("path"):
        return line
    return "# auth-only template; append the provider's resource path: " + line


def describe(key: str) -> dict[str, Any]:
    """Presence + usage for a key, without the value. Safe to print or return to a model."""
    present = key in set(keymaker.list_providers())
    return {"key_name": key, "present": present, "usage": usage_for(key)}


def get_secret_with_usage(key: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """The value and how to send it, in one call."""
    return keymaker.get_secret(key), usage_for(key)


def format_usage(key: str) -> str:
    record = usage_for(key)
    if record is None:
        return (f"No usage record for {key}. Add one with key_usage.set_usage(); "
                "do not guess the header.")
    lines = [f"{key}: {record['provider']}"]
    auth = record.get("auth") or {}
    if auth.get("header"):
        lines.append(f"  header:   {auth['header']}: {auth['scheme']}")
    if auth.get("query"):
        lines.append(f"  query:    ?{auth['query']}=<key>")
    for name, value in (record.get("extra_headers") or {}).items():
        lines.append(f"  also:     {name}: {value}")
    if record.get("base_url"):
        lines.append(f"  base URL: {record['base_url']}")
    if record.get("mcp"):
        lines.append(f"  MCP:      {record['mcp']['url']}  (type {record['mcp']['type']})")
    for doc in record.get("docs", []):
        lines.append(f"  docs:     {doc}")
    for note in record.get("notes", []):
        lines.append(f"  note:     {note}")
    if record.get("curl"):
        lines.append(f"  example:  {record['curl']}")
    return "\n".join(lines)
