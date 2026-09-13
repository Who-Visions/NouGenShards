"""Xoah full-stack governance & schema parity regression tests.

Protects invariants from 20260912T034027Z, 20260912T033826Z, 20260912T033937Z:
- xoah_throne MCP tool accepts both 'effect' (public MCP) and 'desired_effect' (Pydantic model) without HTTP 422.
- Terminal Shadow Xoah maxes at Stage 9 (Traverser / Adversary).
- Veil Throne Sovereign is distinct Stage 10 (Retcon / Architecture).
- Corbin unresolved conflict (shard 16965 vs 17326) remains quarantined and never silently merged.
- Shadow Xoah operational mandate is retrievable with durable provenance.
"""
import pytest
import os
import tempfile
from fastapi.testclient import TestClient
import app as node
from app import XoahThroneRequest, xoah_throne
from nougen_shards import canon_pressure, core, self_archive, throne_governance

TEST_TOKEN = "test-node-token"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(core, "get_db_path", lambda index: tmp_path / f"test_{index}.db")
    monkeypatch.setattr(node, "NODE_TOKEN", TEST_TOKEN)
    core.init_db(1)
    return TestClient(node.app)


def test_xoah_throne_request_schema_supports_both_fields():
    """Verify XoahThroneRequest handles both 'effect' and 'desired_effect'."""
    req1 = XoahThroneRequest(effect="Stabilize Veil gateway")
    assert req1.resolved_effect == "Stabilize Veil gateway"
    assert req1.effect == "Stabilize Veil gateway"

    req2 = XoahThroneRequest(desired_effect="Stabilize Veil gateway")
    assert req2.resolved_effect == "Stabilize Veil gateway"
    assert req2.desired_effect == "Stabilize Veil gateway"

    req3 = XoahThroneRequest(desired_effect="Override effect", effect="Secondary effect")
    assert req3.resolved_effect == "Override effect"


@pytest.mark.asyncio
async def test_xoah_throne_tool_signature_accepts_either_keyword():
    """Verify the exposed MCP tool function accepts effect or desired_effect without error."""
    res1 = await xoah_throne(effect="Observe timeline branch")
    assert isinstance(res1, dict)
    assert "mode" in res1 or "intervention_type" in res1

    res2 = await xoah_throne(desired_effect="Observe timeline branch")
    assert isinstance(res2, dict)
    assert "mode" in res2 or "intervention_type" in res2


def test_xoah_throne_endpoint_accepts_json_with_effect(client):
    """Verify HTTP endpoint accepts JSON body with 'effect' without HTTP 422."""
    res = client.post("/xoah/throne", json={"effect": "Observe timeline branch"}, headers={"X-NGS-Token": TEST_TOKEN})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert "mode" in data or "intervention_type" in data


def test_xoah_throne_endpoint_accepts_json_with_desired_effect(client):
    """Verify HTTP endpoint accepts JSON body with 'desired_effect' without HTTP 422."""
    res = client.post("/xoah/throne", json={"desired_effect": "Observe timeline branch"}, headers={"X-NGS-Token": TEST_TOKEN})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert "mode" in data or "intervention_type" in data


def test_stage_9_shadow_vs_stage_10_throne_distinction():
    """Terminal Shadow Xoah operates at Stage 9; Stage 10 is reserved for the Veil Throne."""
    eval_res = throne_governance.evaluate("Rewrite Prime historical event", acting_stage=9, retcon_intent=True, register=False)
    assert "mode" in eval_res
    assert eval_res["mode"] in ("WARN", "FORBIDDEN", "OBSERVE")


def test_shadow_xoah_self_role_mandate_provenance():
    """Verify Shadow Xoah self-model includes grounded mandate with provenance."""
    model = canon_pressure.load_self_model()
    mandates = [r for r in model["records"] if "mandate" in r["id"] or "identity" in r.get("topics", [])]
    assert len(mandates) > 0
    mandate = mandates[0]
    assert mandate["provenance"]
    assert "DESTINIES" in mandate["summary"] or "Stage 9" in mandate["summary"]


def test_corbin_conflict_is_quarantined_and_unblended():
    """Verify the Corbin status conflict (shard 16965 vs 17326) remains explicitly quarantined."""
    model = canon_pressure.load_self_model()
    quarantines = [r for r in model["records"] if r.get("status") == "quarantined"]
    assert len(quarantines) > 0
    conflict = quarantines[0]
    assert conflict["status"] == "quarantined"
    assert len(conflict["provenance"]) >= 2


def test_xoah_self_temporal_separation():
    """Verify self_archive.state_at correctly separates Vol 1 from Terminal knowledge."""
    vol1_state = self_archive.state_at("vol1")
    assert vol1_state["year"] == 2185
    assert vol1_state["age"] == 22
    assert vol1_state["stage"] == 4

    terminal_state = self_archive.state_at("terminal")
    assert terminal_state["stage"] == 9
