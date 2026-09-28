"""
Unit tests for NouGen Deep Auto Discovery service, EvidenceLedger, and CapabilityGraph.
"""

from pathlib import Path
import tempfile
import unittest

from nougen_shards.auto_discovery import (
    ActionRisk,
    CapabilityDomain,
    CapabilityGraph,
    DeepAutoDiscoveryService,
    DiscoveryBudget,
    EvidenceLedger,
    RiskClassifier,
)


class TestDeepAutoDiscovery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_risk_classifier_boundaries(self):
        # Safe read / explore
        self.assertEqual(RiskClassifier.classify_action("probe_disk", "/tmp"), ActionRisk.SAFE_REVERSIBLE)
        self.assertEqual(RiskClassifier.classify_action("read_file", "AGENTS.md"), ActionRisk.SAFE_REVERSIBLE)

        # Trust boundary mutations
        self.assertEqual(RiskClassifier.classify_action("write_credential", "api_token"), ActionRisk.TRUST_BOUNDARY_GATED)
        self.assertEqual(RiskClassifier.classify_action("delete_record", "shards.db"), ActionRisk.TRUST_BOUNDARY_GATED)

    def test_evidence_ledger_scrubbing_and_checkpoint(self):
        ckpt_file = self.root / "ckpt.json"
        ledger = EvidenceLedger(checkpoint_path=ckpt_file)

        # Record sensitive dict
        payload = {"username": "dav3", "token": "secret_abc123", "sub": {"api_key": "xyz"}}
        entry = ledger.record(
            domain=CapabilityDomain.RUNTIME,
            key="auth_state",
            value=payload,
            confidence=0.9,
            source="test",
            ttl_seconds=3600,
        )

        self.assertEqual(entry.value["token"], "[REDACTED]")
        self.assertEqual(entry.value["sub"]["api_key"], "[REDACTED]")
        self.assertEqual(entry.value["username"], "dav3")

        # Save and reload checkpoint
        self.assertTrue(ledger.save_checkpoint())
        self.assertTrue(ckpt_file.exists())

        ledger2 = EvidenceLedger(checkpoint_path=ckpt_file)
        loaded_count = ledger2.load_checkpoint()
        self.assertEqual(loaded_count, 1)
        loaded_entry = ledger2.get("runtime:auth_state")
        self.assertIsNotNone(loaded_entry)
        self.assertEqual(loaded_entry.value["username"], "dav3")

    def test_fast_probe_and_incremental_discovery(self):
        # Setup mock structure
        repo_dir = self.root / "mock_repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / "AGENTS.md").write_text("# Agents")

        service = DeepAutoDiscoveryService(
            workspace_root=self.root,
            checkpoint_dir=self.root / ".nougen",
            budget=DiscoveryBudget(max_duration_seconds=2.0, max_files_scanned=50),
        )

        # 1. Fast probe
        graph = service.probe_initial_fast()
        self.assertIsNotNone(graph.get_capability(CapabilityDomain.PLATFORM, "os_system"))
        self.assertIsNotNone(graph.get_capability(CapabilityDomain.PLATFORM, "workspace_free_gb"))

        # 2. Incremental workspace walk
        res = service.discover_workspace_repositories_and_agents()
        self.assertGreaterEqual(res["repos_found"], 1)
        self.assertGreaterEqual(res["surfaces_found"], 1)

        repos = service.graph.get_capability(CapabilityDomain.REPOSITORIES, "workspace_git_repos")
        self.assertIn("mock_repo", repos)


if __name__ == "__main__":
    unittest.main()
