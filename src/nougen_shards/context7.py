"""Context7 docs lookup client for the fleet MCP server.

MCP SURFACE DECISION (2026-11-22): the fleet MCP tools in
``nougen_shards.mcp`` (``context7_search`` / ``context7_resolve`` /
``context7_docs`` / ``context7_usage``) ARE the Context7 MCP surface.
The official remote Context7 MCP server (https://mcp.context7.com/mcp)
is NOT wired as a lane. Reasons, from the code as read:

* The fleet pattern for an external docs/research service is native tools
  in ``mcp.py`` delegating to a thin client module (``arxiv_radar``,
  ``cloudflare``, ``nougentube``) — one server, one auth path, one
  tenant-policy label. A remote MCP lane would be a second server with
  its own transport and its own bearer handling, bypassing the tenant
  gate in ``tenant_policy.py``.
* Auth is Keymaker-first: the key is read at call time with
  ``keymaker.get_secret("CONTEXT7_API_KEY")`` and never stored, logged,
  or hard-coded. A remote MCP lane has no Keymaker hook.
* The tools are labelled OWNER_ONLY in ``tenant_policy.py`` (shared
  service on the owner's key, same as ``arxiv_*`` / ``nougentube_*``),
  so tenants can never spend the owner's Context7 quota.

Endpoints (https://context7.com/docs/api-guide):
  GET /api/v3/search      question -> plain-text docs, no resolve needed
  GET /api/v2/libs/search libraryName (+ optional query) -> library IDs
  GET /api/v2/context     libraryId + query (+ tokens, language) -> snippets
  GET /api/v2/usage       monthly usage; free, does not count as a request

Error mapping (per the API guide and the custom.context7 connector doc):
  404 no_documentation_found -> empty result, not an error
  429 -> rate limit; honour Retry-After, back off
  503 -> search failed; retry later
  401 -> key invalid; 403 -> access denied
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from . import keymaker

BASE = "https://context7.com"
KEY_NAME = "CONTEXT7_API_KEY"

MISSING_KEY_ERROR = (
    "CONTEXT7_API_KEY is not set in the Keymaker. Ask the operator to add "
    "the Context7 API key to the Keymaker under the name CONTEXT7_API_KEY; "
    "no live Context7 lookup is possible until then."
)

_DEFAULT_TOKENS = 5000
_MAX_TOKENS = 10000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def _api_key() -> Optional[str]:
    """Read the Context7 key from the Keymaker at call time, never cached."""
    try:
        val = keymaker.get_secret(KEY_NAME)
    except Exception:
        return None
    if val:
        val = val.strip()
    return val or None


def _missing_key() -> Dict[str, Any]:
    return {"status": "error", "available": False, "error": MISSING_KEY_ERROR}


def _http_get(path: str, params: Optional[Dict[str, Any]], api_key: str):
    """One GET against context7.com. Returns (status, headers, raw_text).

    Separated from _call so tests can stub the transport without touching
    the key or the network.
    """
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "NouGen-Context7/1.0",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=60) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        headers = dict(e.headers) if e.headers else {}
        return e.code, headers, e.read().decode("utf-8", errors="replace")


def _call(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    api_key = _api_key()
    if not api_key:
        return _missing_key()
    try:
        status, headers, raw = _http_get(path, params, api_key)
    except Exception as exc:  # network failure, refused redirect, timeout
        return {"status": "error", "available": False, "error": f"Context7 request failed: {exc}"}
    if status == 404:
        try:
            body = json.loads(raw)
        except Exception:
            body = {}
        if isinstance(body, dict) and body.get("error") == "no_documentation_found":
            return {"status": "ok", "available": True, "empty": True,
                    "error": "no_documentation_found",
                    "message": "No documentation matched; treat as an empty result."}
        return {"status": "error", "available": False,
                "error": f"Context7 returned HTTP 404: {raw[:300]}"}
    if status == 429:
        retry_after = headers.get("Retry-After") or headers.get("retry-after") or ""
        hint = f" Retry after {retry_after}s." if retry_after else ""
        return {"status": "error", "available": False, "error": "rate_limited",
                "message": f"Context7 rate limit hit (HTTP 429). Back off and retry.{hint}"}
    if status == 503:
        return {"status": "error", "available": False, "error": "service_unavailable",
                "message": "Context7 search failed (HTTP 503). Retry later."}
    if status == 401:
        return {"status": "error", "available": False, "error": "unauthorized",
                "message": "Context7 key rejected (HTTP 401). Check the CONTEXT7_API_KEY value in the Keymaker."}
    if status == 403:
        return {"status": "error", "available": False, "error": "forbidden",
                "message": "Context7 access denied (HTTP 403). Check library access permissions or the plan."}
    if status >= 400:
        return {"status": "error", "available": False,
                "error": f"Context7 returned HTTP {status}: {raw[:300]}"}
    try:
        body = json.loads(raw)
        return {"status": "ok", "available": True, "result": body}
    except json.JSONDecodeError:
        # v3 search returns plain text docs, not JSON.
        return {"status": "ok", "available": True, "result": {"text": raw}}


def search_docs(query: str, libraries: Optional[List[str]] = None) -> Dict[str, Any]:
    """Search docs by question; Context7 picks the libraries.

    Args:
        query: The question to answer from current library docs.
        libraries: Optional name/ID hints, at most 4.
    """
    if not query or not query.strip():
        return {"status": "error", "available": False, "error": "query is required"}
    params: Dict[str, Any] = {"query": query.strip()}
    if libraries:
        # v3 search takes repeated `library` hints; `libraryName` belongs
        # to the v2 library-resolution endpoint and is ignored here.
        params["library"] = [str(l) for l in libraries[:4]]
    res = _call("/api/v3/search", params)
    res["query"] = query.strip()
    return res


def resolve_library(library_name: str, query: str = "") -> Dict[str, Any]:
    """Resolve a library name to its Context7 library ID.

    Args:
        library_name: Library name, e.g. 'next.js'.
        query: Optional topic to rank the matches by.
    """
    if not library_name or not library_name.strip():
        return {"status": "error", "available": False, "error": "library_name is required"}
    params: Dict[str, Any] = {"libraryName": library_name.strip()}
    if query:
        params["query"] = query
    res = _call("/api/v2/libs/search", params)
    res["library_name"] = library_name.strip()
    return res


def fetch_docs(library_id: str, query: str, tokens: int = _DEFAULT_TOKENS,
               language: str = "") -> Dict[str, Any]:
    """Fetch docs snippets for one library ID.

    Args:
        library_id: Context7 library ID, e.g. '/vercel/next.js'.
        query: Topic to fetch docs for.
        tokens: Snippet budget (default 5000, ceiling 10000).
        language: Optional language to rank examples by.
    """
    if not library_id or not library_id.strip():
        return {"status": "error", "available": False, "error": "library_id is required"}
    if not query or not query.strip():
        return {"status": "error", "available": False, "error": "query is required"}
    if isinstance(tokens, bool) or not isinstance(tokens, int) or not 1 <= tokens <= _MAX_TOKENS:
        return {"status": "error", "available": False,
                "error": f"tokens must be an integer 1-{_MAX_TOKENS}"}
    params: Dict[str, Any] = {"libraryId": library_id.strip(),
                              "query": query.strip(), "tokens": tokens}
    if language:
        params["language"] = language
    res = _call("/api/v2/context", params)
    res["library_id"] = library_id.strip()
    return res


def usage() -> Dict[str, Any]:
    """Monthly usage for this key. Free; does not count as a request."""
    return _call("/api/v2/usage")
