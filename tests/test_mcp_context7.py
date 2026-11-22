"""Tests for Context7 docs lookup: client (nougen_shards.context7) and the
fleet MCP tools (nougen_shards.mcp context7_*). The Keymaker entry
CONTEXT7_API_KEY does not exist yet, so the missing-key degradation path
is a first-class case here, not an afterthought.
"""

import json
from unittest.mock import MagicMock

import pytest

from nougen_shards import context7, mcp
from nougen_shards.tenant_policy import OWNER_ONLY

FAKE_KEY = "ctx7sk-TEST"


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr("nougen_shards.keymaker.get_secret",
                        lambda name: FAKE_KEY if name == "CONTEXT7_API_KEY" else None)
    return FAKE_KEY


@pytest.fixture
def without_key(monkeypatch):
    monkeypatch.setattr("nougen_shards.keymaker.get_secret", lambda name: None)


def _stub_http(monkeypatch, status, raw, headers=None):
    def _fake(path, params, api_key):
        assert api_key == FAKE_KEY
        return status, dict(headers or {}), raw
    monkeypatch.setattr("nougen_shards.context7._http_get", _fake)


# --- Missing key: clean degradation, no crash, no internals leaked ---

def test_missing_key_search(without_key):
    res = context7.search_docs("How do I cache in Next.js 15?")
    assert res["status"] == "error"
    assert "CONTEXT7_API_KEY" in res["error"]
    assert "Keymaker" in res["error"]


def test_missing_key_resolve_docs_usage(without_key):
    for res in (context7.resolve_library("next.js"),
                context7.fetch_docs("/vercel/next.js", "caching"),
                context7.usage()):
        assert res["status"] == "error"
        assert res["available"] is False
        assert "CONTEXT7_API_KEY" in res["error"]


def test_missing_key_mcp_tools(without_key):
    for raw in (mcp.context7_search("How do I cache in Next.js 15?"),
                mcp.context7_resolve("next.js"),
                mcp.context7_docs("/vercel/next.js", "caching"),
                mcp.context7_usage()):
        res = json.loads(raw)
        assert res["status"] == "error"
        assert "CONTEXT7_API_KEY" in res["error"]
        assert "Keymaker" in res["error"]


# --- Happy paths (transport stubbed; no network, no real key) ---

def test_search_plain_text(with_key, monkeypatch):
    _stub_http(monkeypatch, 200, "Next.js 15 caching docs...\nSource: /vercel/next.js")
    res = context7.search_docs("How do I cache in Next.js 15?", libraries=["next.js"])
    assert res["status"] == "ok"
    assert res["result"]["text"].startswith("Next.js 15 caching docs")


def test_resolve_json(with_key, monkeypatch):
    _stub_http(monkeypatch, 200, json.dumps({"results": [
        {"id": "/vercel/next.js", "title": "Next.js",
         "description": "The React Framework"}]}))
    res = context7.resolve_library("next.js", query="caching")
    assert res["status"] == "ok"
    assert res["result"]["results"][0]["id"] == "/vercel/next.js"


def test_docs_json(with_key, monkeypatch):
    _stub_http(monkeypatch, 200, json.dumps(
        {"snippets": [{"title": "Caching", "content": "use cache: ..."}]}))
    res = context7.fetch_docs("/vercel/next.js", "caching", tokens=5000)
    assert res["status"] == "ok"
    assert res["result"]["snippets"][0]["title"] == "Caching"


def test_usage_json(with_key, monkeypatch):
    _stub_http(monkeypatch, 200, json.dumps(
        {"plan": "free", "usageResetsAt": "2026-12-01",
         "member": {"requests": 0, "includedInPlan": 1000}}))
    res = context7.usage()
    assert res["status"] == "ok"
    assert res["result"]["plan"] == "free"
    assert res["result"]["member"]["includedInPlan"] == 1000


def test_docs_tokens_validation(with_key):
    res = context7.fetch_docs("/vercel/next.js", "caching", tokens=99999)
    assert res["status"] == "error"
    assert "tokens" in res["error"]


def test_empty_query_validation(with_key):
    assert context7.search_docs("  ")["status"] == "error"
    assert context7.resolve_library("  ")["status"] == "error"
    assert context7.fetch_docs("/vercel/next.js", "  ")["status"] == "error"


# --- API error mapping ---

def test_404_no_documentation_is_empty_not_error(with_key, monkeypatch):
    _stub_http(monkeypatch, 404, json.dumps({"error": "no_documentation_found"}))
    res = context7.search_docs("obscure lib nobody documented")
    assert res["status"] == "ok"
    assert res["empty"] is True


def test_429_rate_limit(with_key, monkeypatch):
    _stub_http(monkeypatch, 429, json.dumps({"error": "rate_limited"}),
               headers={"Retry-After": "30"})
    res = context7.search_docs("x")
    assert res["status"] == "error"
    assert res["error"] == "rate_limited"
    assert "30" in res["message"]


def test_503_retry_later(with_key, monkeypatch):
    _stub_http(monkeypatch, 503, "Service Unavailable")
    res = context7.search_docs("x")
    assert res["status"] == "error"
    assert res["error"] == "service_unavailable"


def test_401_key_rejected(with_key, monkeypatch):
    _stub_http(monkeypatch, 401, json.dumps({"error": "unauthorized"}))
    res = context7.usage()
    assert res["status"] == "error"
    assert res["error"] == "unauthorized"


# --- MCP tools delegate to the client, like the arxiv_* tools ---

def test_mcp_search_delegates(monkeypatch):
    mock = MagicMock(return_value={"status": "ok", "available": True,
                                   "result": {"text": "docs..."}, "query": "caching"})
    monkeypatch.setattr("nougen_shards.context7.search_docs", mock)
    res = json.loads(mcp.context7_search("caching", libraries=["next.js"]))
    assert res["status"] == "ok"
    assert res["result"]["text"] == "docs..."
    mock.assert_called_once_with(query="caching", libraries=["next.js"])


def test_mcp_resolve_docs_usage_delegate(monkeypatch):
    monkeypatch.setattr("nougen_shards.context7.resolve_library",
                        MagicMock(return_value={"status": "ok", "available": True,
                                                "result": {"results": []}}))
    monkeypatch.setattr("nougen_shards.context7.fetch_docs",
                        MagicMock(return_value={"status": "ok", "available": True,
                                                "result": {"snippets": []}}))
    monkeypatch.setattr("nougen_shards.context7.usage",
                        MagicMock(return_value={"status": "ok", "available": True,
                                                "result": {"plan": "free"}}))
    assert json.loads(mcp.context7_resolve("next.js"))["status"] == "ok"
    assert json.loads(mcp.context7_docs("/vercel/next.js", "caching"))["status"] == "ok"
    assert json.loads(mcp.context7_usage())["result"]["plan"] == "free"


# --- Tenant policy: owner-only, like the other shared-service tools ---

def test_context7_tools_labelled_owner_only():
    for name in ("context7_search", "context7_resolve", "context7_docs", "context7_usage"):
        assert name in OWNER_ONLY, f"{name} must be labelled OWNER_ONLY in tenant_policy.py"
