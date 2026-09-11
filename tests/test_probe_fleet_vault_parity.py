"""Tests for fleet vault parity and multi-tenant lane verification."""
import pytest
from fastapi.testclient import TestClient

import app as node
from nougen_shards import core, tenants
from tools.probe_fleet_vault_parity import evaluate_fleet_parity


def test_fleet_parity_all_three_green():
    probes = [
        {"name": "blade", "ok": True, "status": 200, "latency_ms": 120.0, "error": None, "payload": {"total_shards": 50000, "db_grid": {"databases_mounted": 9, "databases_expected": 9}}},
        {"name": "phoebus", "ok": True, "status": 200, "latency_ms": 150.0, "error": None, "payload": {"total_shards": 50000, "db_grid": {"databases_mounted": 9, "databases_expected": 9}}},
        {"name": "whoart", "ok": True, "status": 200, "latency_ms": 180.0, "error": None, "payload": {"total_shards": 50000, "db_grid": {"databases_mounted": 9, "databases_expected": 9}}},
    ]
    res = evaluate_fleet_parity(probes)
    assert res["fleet_green"] is True
    assert res["status"] == "GREEN"
    assert res["cannot_determine"] is False
    assert res["vaults_responding"] == 3
    assert res["vaults_expected"] == 3


def test_fleet_parity_one_timeout_reports_degraded_no_false_green():
    probes = [
        {"name": "blade", "ok": True, "status": 200, "latency_ms": 110.0, "error": None, "payload": {"total_shards": 50000, "db_grid": {"databases_mounted": 9, "databases_expected": 9, "coverage_scope": "LOCAL_VAULT_COVERAGE"}}},
        {"name": "phoebus", "ok": False, "status": None, "latency_ms": 8000.0, "error": "TimeoutError: timed out", "payload": {}},
        {"name": "whoart", "ok": False, "status": 502, "latency_ms": 400.0, "error": "HTTP 502", "payload": {}},
    ]
    res = evaluate_fleet_parity(probes)
    # Even though blade holds a full 9/9 local grid, fleet MUST NOT be reported as green!
    assert res["fleet_green"] is False
    assert res["status"] == "DEGRADED"
    assert res["cannot_determine"] is True
    assert res["vaults_responding"] == 1
    assert res["vaults_expected"] == 3
    assert res["vaults"]["blade"]["coverage_scope"] == "LOCAL_VAULT_COVERAGE"


def test_multi_tenant_lane_reflected_in_health(tmp_path, monkeypatch):
    owner = tmp_path / "owner-vault"
    tenant_root = tmp_path / "tenant-vaults"
    registry = tmp_path / "tenants.json"
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(registry))
    monkeypatch.setenv("NOUGEN_TENANT_VAULT_ROOT", str(tenant_root))
    monkeypatch.setattr(node, "NODE_TOKEN", "test-token")
    monkeypatch.setattr(core, "GLOBAL_DIR", owner)
    core._INITIALIZED_DBS.clear()

    tok = tenants.mint_tenant("blade-client", "Blade Client", lane="blade-lane")
    client = TestClient(node.app)

    # Calling health with tenant token and custom lane header
    resp = client.get("/health", headers={
        "X-NGS-Token": tok,
        "X-NouGen-Lane": "custom-tenant-lane"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "blade-client"
    assert data["tenant_lane"] == "custom-tenant-lane"
    assert data["coverage_scope"] == "LOCAL_VAULT_COVERAGE"
    assert data["vault_grid"]["vaults_expected"] == 3
    assert "blade" in data["vault_grid"]["peer_vaults"]
    assert "phoebus" in data["vault_grid"]["peer_vaults"]
    assert "whoart" in data["vault_grid"]["peer_vaults"]
