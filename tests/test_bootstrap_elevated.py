from unittest.mock import patch
from nougen_shards.bootstrap_elevated import (
    RiskClassifier,
    ActionRisk,
    DiskSpaceRequirement,
    AgentSurfaceAdapter,
    ZeroBabysittingBootstrap,
)


def test_risk_classifier():
    safe = RiskClassifier.classify_action("apply_agent_hook", "/path/to/AGENTS.md")
    assert safe == ActionRisk.SAFE_REVERSIBLE

    gated = RiskClassifier.classify_action("ingest_secret_vault", "/secrets")
    assert gated == ActionRisk.TRUST_BOUNDARY_GATED

    gated_delete = RiskClassifier.classify_action("delete_database", "/shards.db")
    assert gated_delete == ActionRisk.TRUST_BOUNDARY_GATED


def test_disk_space_requirement():
    req = DiskSpaceRequirement(model_bundle_bytes=7_500_000_000, reserve_floor_bytes=10_000_000_000)
    assert req.total_required == 17_500_000_000

    # 50GB free -> Qualified
    qualified, reason = req.evaluate(50 * 1024 * 1024 * 1024)
    assert qualified is True
    assert "Qualified" in reason

    # 5GB free -> Unqualified
    qualified2, reason2 = req.evaluate(5 * 1024 * 1024 * 1024)
    assert qualified2 is False
    assert "Insufficient" in reason2


def test_agent_surface_adapter_injection_and_preservation(tmp_path):
    target = tmp_path / "AGENTS.md"
    user_header = "# User Custom Instructions\nDo not break production."
    target.write_text(user_header, encoding="utf-8")

    res = AgentSurfaceAdapter.apply_to_file(target, "codex")
    assert res["modified"] is True
    assert res["existed_prior"] is True

    content = target.read_text(encoding="utf-8")
    assert user_header in content
    assert AgentSurfaceAdapter.MANAGED_START in content
    assert AgentSurfaceAdapter.MANAGED_END in content

    # Re-apply for idempotence
    res2 = AgentSurfaceAdapter.apply_to_file(target, "codex")
    assert res2["modified"] is False
    content2 = target.read_text(encoding="utf-8")
    assert content2.count(AgentSurfaceAdapter.MANAGED_START) == 1


def test_bootstrap_probe_environment(tmp_path):
    bootstrap = ZeroBabysittingBootstrap(root_dir=tmp_path)
    probe = bootstrap.probe_environment()

    assert "free_gb" in probe
    assert "space_qualified" in probe
    assert probe["bootstrap_mode"] in ("local_hybrid", "remote_memory_only")


def test_install_agent_hooks_all_surfaces(tmp_path):
    bootstrap = ZeroBabysittingBootstrap(root_dir=tmp_path)
    results = bootstrap.install_agent_hooks(tmp_path)

    assert len(results) == 3
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "GEMINI.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_autonomous_bootstrap_with_models(tmp_path):
    # Set reserve_gb to 1.0 so test environment satisfies space check
    bootstrap = ZeroBabysittingBootstrap(root_dir=tmp_path, reserve_gb=1.0)
    # Mock space check to ensure deterministic pass across CI runners
    mock_probe = {
        "free_bytes": 100 * 1024**3,
        "free_gb": 100.0,
        "space_qualified": True,
        "space_reason": "Qualified: 100 GB free exceeds requirement.",
        "ollama_binary_found": True,
        "ollama_live": True,
        "bootstrap_mode": "local_hybrid",
    }

    with patch.object(bootstrap, "probe_environment", return_value=mock_probe), \
         patch.object(bootstrap, "is_ollama_live", return_value=True), \
         patch.object(bootstrap, "list_installed_models", return_value=["nomic-embed-text:latest", "gemma4:e2b"]):
        
        # Test individual model check
        ok1, msg1 = bootstrap.ensure_model_installed("nomic-embed-text:latest")
        assert ok1 is True
        assert "already installed" in msg1

        ok2, msg2 = bootstrap.ensure_model_installed("gemma4:e2b")
        assert ok2 is True
        assert "already installed" in msg2

        # Full bootstrap run
        report = bootstrap.autonomous_bootstrap(target_workspace=tmp_path)
        assert report["status"] == "completed"
        assert report["ollama"]["ready"] is True
        assert report["models"]["nomic-embed-text:latest"]["ready"] is True
        assert report["models"]["gemma4:e2b"]["ready"] is True
        assert len(report["agent_hooks"]) == 3
