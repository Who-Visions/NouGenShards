import json
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


def test_agent_surface_adapter_uses_native_imports_and_codex_inline(tmp_path):
    canonical = tmp_path / "core.md"
    canonical.write_text("Shared fleet rules", encoding="utf-8")
    assert "@" + str(canonical) in AgentSurfaceAdapter.generate_instruction_block("gemini", str(canonical))
    assert "@" + str(canonical) in AgentSurfaceAdapter.generate_instruction_block("claude", str(canonical))
    codex = AgentSurfaceAdapter.generate_instruction_block("codex", str(canonical))
    assert "Preserve active ownership" in codex
    assert "@import" not in codex


def test_model_store_volume_uses_ollama_models_path(tmp_path, monkeypatch):
    model_store = tmp_path / "separate-volume" / "ollama-models"
    model_store.mkdir(parents=True)
    monkeypatch.setenv("OLLAMA_MODELS", str(model_store))
    bootstrap = ZeroBabysittingBootstrap(root_dir=tmp_path)
    with patch("nougen_shards.bootstrap_elevated.shutil.disk_usage") as disk_usage:
        disk_usage.return_value.free = 123
        probe = bootstrap.probe_environment()
    assert probe["space_probe_dir"] == str(model_store)
    disk_usage.assert_called_once_with(model_store)


def test_remote_ollama_storage_is_not_assumed_to_match_local_disk():
    bootstrap = ZeroBabysittingBootstrap(ollama_url="http://ollama.example:11434")
    with patch.object(bootstrap, "is_ollama_live", return_value=True):
        probe = bootstrap.probe_environment()
    assert probe["model_storage_local"] is False
    assert probe["space_qualified"] is False
    assert "cannot be measured" in probe["space_reason"]


def test_model_pull_skips_unmeasurable_remote_storage():
    bootstrap = ZeroBabysittingBootstrap(ollama_url="http://ollama.example:11434")
    with patch.object(bootstrap, "list_installed_models", return_value=[]):
        ok, detail = bootstrap.ensure_model_installed("gemma4:e2b")
    assert ok is False
    assert "remote Ollama storage capacity is not measurable" in detail


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
         patch.object(bootstrap, "list_installed_models", return_value=["nomic-embed-text:latest", "gemma4:e2b-it-qat"]):
        
        # Test individual model check (gemma4:e2b dynamically maps to gemma4:e2b-it-qat)
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
        assert report["models"]["gemma4:e2b-it-qat"]["ready"] is True
        assert len(report["agent_hooks"]) == 3


def test_qat_prime_directive_tag_resolution():
    # Maps unquantized to QAT
    assert ZeroBabysittingBootstrap.resolve_optimal_model_tag("gemma4:e2b") == "gemma4:e2b-it-qat"
    assert ZeroBabysittingBootstrap.resolve_optimal_model_tag("gemma4:e4b") == "gemma4:e4b-it-qat"
    assert ZeroBabysittingBootstrap.resolve_optimal_model_tag("gemma4") == "gemma4:e4b-it-qat"

    # Preserves when QAT already installed locally
    installed = ["gemma4:e2b-it-qat", "nomic-embed-text:latest"]
    assert ZeroBabysittingBootstrap.resolve_optimal_model_tag("gemma4:e2b", installed) == "gemma4:e2b-it-qat"
    assert ZeroBabysittingBootstrap.resolve_optimal_model_tag("gemma4", installed) == "gemma4:e2b-it-qat"


def test_low_space_still_installs_safe_hooks(tmp_path):
    bootstrap = ZeroBabysittingBootstrap(root_dir=tmp_path)
    probe = {
        "free_bytes": 1, "free_gb": 0.0, "space_qualified": False,
        "space_reason": "Insufficient free disk.", "ollama_binary_found": False,
        "ollama_live": False, "bootstrap_mode": "remote_memory_only",
    }
    with patch.object(bootstrap, "probe_environment", return_value=probe):
        report = bootstrap.autonomous_bootstrap(target_workspace=tmp_path)
    assert report["status"] == "partial"
    assert len(report["agent_hooks"]) == 3
    assert (tmp_path / "AGENTS.md").exists()


def test_pull_requires_model_list_verification():
    bootstrap = ZeroBabysittingBootstrap()
    response = type("Response", (), {
        "status": 200,
        "read": lambda self: json.dumps({"status": "success"}).encode(),
        "__enter__": lambda self: self,
        "__exit__": lambda self, *_args: False,
    })()
    with patch.object(bootstrap, "list_installed_models", side_effect=[[], []]), \
         patch.object(bootstrap, "is_ollama_live", return_value=True), \
         patch("nougen_shards.bootstrap_elevated.urllib.request.urlopen", return_value=response):
        ok, detail = bootstrap.ensure_model_installed("gemma4:e2b")
    assert ok is False
    assert "absent from Ollama's model list" in detail


def test_missing_ollama_does_not_suggest_unapproved_installer():
    bootstrap = ZeroBabysittingBootstrap()
    with patch.object(bootstrap, "is_ollama_live", return_value=False), \
         patch("nougen_shards.bootstrap_elevated.shutil.which", return_value=None):
        ok, detail = bootstrap.ensure_ollama_installed_and_running()
    assert ok is False
    assert "setup was skipped" in detail
    assert "curl" not in detail


def test_autostart_generators():
    plist = ZeroBabysittingBootstrap.generate_macos_launchd_plist(
        python_bin="/usr/bin/python3",
        script_path="-m nougen_shards",
        label="com.nougen.test",
        working_dir="/tmp/test",
    )
    assert "<key>Label</key>" in plist
    assert "<string>com.nougen.test</string>" in plist
    assert "<string>/usr/bin/python3</string>" in plist
    assert "<key>RunAtLoad</key>" in plist

    service = ZeroBabysittingBootstrap.generate_systemd_service(
        python_bin="/usr/bin/python3",
        script_path="-m nougen_shards",
        description="Test Service",
        working_dir="/tmp/test",
    )
    assert "[Unit]" in service
    assert "Description=Test Service" in service
    assert "ExecStart=/usr/bin/python3 -m nougen_shards" in service


def test_install_autostart_daemon_darwin(tmp_path):
    bootstrap = ZeroBabysittingBootstrap(root_dir=tmp_path)
    with patch("platform.system", return_value="Darwin"), \
         patch("pathlib.Path.home", return_value=tmp_path):
        res = bootstrap.install_autostart_daemon(
            python_bin="/usr/bin/python3",
            script_path="-m nougen_shards",
            label="com.nougen.testnode",
        )
        assert res["platform"] == "darwin"
        assert res["installed"] is True
        expected_file = tmp_path / "Library" / "LaunchAgents" / "com.nougen.testnode.plist"
        assert expected_file.exists()
        assert "com.nougen.testnode" in expected_file.read_text(encoding="utf-8")


def test_install_autostart_daemon_linux(tmp_path):
    bootstrap = ZeroBabysittingBootstrap(root_dir=tmp_path)
    with patch("platform.system", return_value="Linux"), \
         patch("pathlib.Path.home", return_value=tmp_path):
        res = bootstrap.install_autostart_daemon(
            python_bin="/usr/bin/python3",
            script_path="-m nougen_shards",
            label="com.nougen.testnode",
        )
        assert res["platform"] == "linux"
        assert res["installed"] is True
        expected_file = tmp_path / ".config" / "systemd" / "user" / "com.nougen.testnode.service"
        assert expected_file.exists()
        assert "ExecStart=/usr/bin/python3 -m nougen_shards" in expected_file.read_text(encoding="utf-8")
