"""Scheduler: classify + score + decide with reason codes; HF as provider-of-providers;
policy_unknown never pools; HF credits unknown/spent scores the lane to zero (hermetic)."""
import json

import pytest

import nougen_shards.core as core
from nougen_shards import provider_scheduler as ps


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    for k in ("NOUGEN_PROVIDER_REGISTRY", "NOUGEN_HF_CREDIT_BUDGET_USD", "NOUGEN_HF_CREDITS_SPENT_USD", "NOUGEN_SCHEDULER_PROVENANCE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NOUGEN_ROUTING_LOG", str(tmp_path / "routing.jsonl"))  # never the real decision log
    yield


CATALOG = {"fetched_utc": "x", "source": "test", "models": [
    {"model": "zai-org/GLM-5.3", "owner": "zai-org", "input": ["text"], "output": ["text"], "providers": [
        {"provider": "novita", "status": "live", "context": 1048576, "price_in": 1.4, "price_out": 4.4, "is_free": False, "tools": True, "structured": False, "latency_ms": 900},
        {"provider": "groq", "status": "live", "context": 131072, "price_in": 0.5, "price_out": 1.5, "is_free": False, "tools": True, "structured": True, "latency_ms": 200}]},
    {"model": "openai/gpt-oss-20b", "owner": "openai", "input": ["text"], "output": ["text"], "providers": [
        {"provider": "publicai", "status": "live", "context": 131072, "price_in": 0.0, "price_out": 0.0, "is_free": True, "tools": False, "structured": False, "latency_ms": 1500},
        {"provider": "cerebras", "status": "staging", "context": 131072, "price_in": 0.1, "price_out": 0.3, "is_free": False, "tools": True, "structured": True, "latency_ms": 100}]},
]}


def test_registry_loads_and_every_provider_has_policy():
    reg = ps.load_registry()
    assert reg["providers"] and all("policy" in p for p in reg["providers"])
    assert reg["reason_codes"]["POLICY_BLOCK"]


def test_bulk_draft_routes_local_with_reason_codes_and_layers():
    d = ps.route("draft 40 captions for the reel", harness="claude-cli", toolset=[])
    assert d["role"] == "bulk_draft" and d["lane"] == "ollama-local"
    assert "PREFERENCE" in d["reason_codes"]
    for k in ("role", "harness", "inference_fabric", "model", "routing_policy", "toolset", "account", "lane", "machine"):
        assert k in d
    assert d["no_pooling"] is True
    assert all(c["lane"] != "hf-router" or not c["eligible"] for c in d["candidates"]), "HF lane must be ineligible with no credit budget"
    hf = next(c for c in d["candidates"] if c["lane"] == "hf-router")
    assert hf["reasons"] == ["CREDIT_BUDGET"]


def test_hf_lane_scores_to_zero_when_credits_spent_and_swap_is_named(monkeypatch):
    monkeypatch.setenv("NOUGEN_HF_CREDIT_BUDGET_USD", "0.10")
    monkeypatch.setenv("NOUGEN_HF_CREDITS_SPENT_USD", "0.10")
    d = ps.route("summarize this transcript", pinned_lane="hf-router", catalog=CATALOG)
    assert d["lane"] != "hf-router" and "DEGRADE_SWAP" in d["reason_codes"]
    hf = next(c for c in d["candidates"] if c["lane"] == "hf-router")
    assert hf["reasons"] == ["QUOTA_EXHAUSTED"]


def test_hf_provider_of_providers_picks_cheapest_then_fastest(monkeypatch):
    monkeypatch.setenv("NOUGEN_HF_CREDIT_BUDGET_USD", "5")
    d = ps.route("summarize this transcript", pinned_lane="hf-router", catalog=CATALOG, hf_policy="cheapest")
    assert d["lane"] == "hf-router" and d["model"] == "openai/gpt-oss-20b" and d["downstream_provider"] == "publicai"
    assert d["routing_policy"] == ":cheapest" and "PINNED" in d["reason_codes"]
    d2 = ps.route("summarize this transcript", pinned_lane="hf-router", catalog=CATALOG, hf_policy="fastest")
    assert d2["downstream_provider"] == "groq", "cerebras is staging, not live"
    d3 = ps.route("call the tool and act as an agent", role="tool_agent", pinned_lane="hf-router", catalog=CATALOG, hf_policy="cheapest")
    assert d3["downstream_provider"] == "groq" and d3["hf"]["tools"] is True if "tools" in d3["hf"] else d3["downstream_provider"] == "groq"
    d4 = ps.route("summarize", pinned_lane="hf-router", pinned_model="GLM-5.3", catalog=CATALOG)
    assert d4["model"] == "zai-org/GLM-5.3" and d4["routing_policy"] == "pinned"


def test_policy_unknown_never_pools(monkeypatch, tmp_path):
    reg = ps.load_registry()
    reg["providers"] = [{"lane": "pooled-mystery", "fabric": "x", "account": "many", "capabilities": ["text"], "cost_class": "free",
                         "quota_class": "daily-per-account", "latency_class": "fast", "reliability": 0.9, "eval_score": 0.9,
                         "policy": {"multi_account_pooling": True, "policy_verified": False}, "tags": ["cheap"], "models": ["m"]}]
    d = ps.route("draft", registry=reg)
    assert d["lane"] is None and d["reason_codes"] == ["POLICY_BLOCK"] and d["error"] == "no eligible provider"


def test_capability_miss_and_cache_affinity():
    d = ps.route("embed these 200 shards", role="embed")
    assert d["lane"] == "ollama-local"
    miss = next(c for c in d["candidates"] if c["lane"] == "openrouter-free")
    assert miss["reasons"] == ["CAP_MISS"] and "embeddings" in miss["missing"]
    d2 = ps.route("draft", last_lane="openrouter-free")
    aff = next(c for c in d2["candidates"] if c["lane"] == "openrouter-free")
    assert "CACHE_AFFINITY" in aff["reasons"]


def test_catalog_normalization_matches_live_shape():
    raw = {"object": "list", "data": [{"id": "zai-org/GLM-5.3", "owned_by": "zai-org", "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                                       "providers": [{"provider": "novita", "status": "live", "context_length": 1048576, "pricing": {"input": 1.4, "output": 4.4}, "is_free": False, "supports_tools": True, "supports_structured_output": False, "first_token_latency_ms": 900}]}]}
    cat = ps.normalize_hf_catalog(raw)
    assert cat[0]["model"] == "zai-org/GLM-5.3" and cat[0]["providers"][0]["price_out"] == 4.4 and cat[0]["providers"][0]["tools"] is True


def test_catalog_without_token_is_empty_and_honest(monkeypatch):
    monkeypatch.setattr(ps, "_hf_token", lambda: None)
    cat = ps.fetch_hf_catalog(force=True)
    assert cat["models"] == [] and cat["source"].startswith("none")


def test_provenance_shard_is_captured_when_asked(monkeypatch):
    core.init_db(1)
    d = ps.route("triage these 30 relay legs", provenance=True)
    assert d["provenance"] == "captured"
    rows = core._keyword_retrieve("dispatch triage", 5, None, "*")
    assert rows and rows[0]["title"].startswith("dispatch triage")
    body = json.loads(rows[0]["content"])
    assert body["lane"] == d["lane"] and body["reason_codes"] == d["reason_codes"]


def test_unknown_price_never_wins_cheapest(monkeypatch):
    monkeypatch.setenv("NOUGEN_HF_CREDIT_BUDGET_USD", "5")
    cat = {"models": [
        {"model": "a/mystery", "input": ["text"], "output": ["text"], "providers": [{"provider": "x", "status": "live", "price_in": None, "price_out": None, "is_free": False, "tools": True, "structured": True, "latency_ms": 10}]},
        {"model": "b/known", "input": ["text"], "output": ["text"], "providers": [{"provider": "y", "status": "live", "price_in": 2.0, "price_out": 6.0, "is_free": False, "tools": True, "structured": True, "latency_ms": 900}]},
    ]}
    assert ps.hf_pick(cat, policy="cheapest", need_tools=True)["model"] == "b/known"
    assert ps.hf_pick(cat, policy="fastest", need_tools=True)["model"] == "a/mystery"
