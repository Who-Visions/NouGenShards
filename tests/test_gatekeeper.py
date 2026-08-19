"""Tests for the DavOs Gatekeeper middleware and its integrations."""
import os
import unittest
from unittest.mock import patch, MagicMock
import io

from nougen_shards.gatekeeper import check_mutation_gate, gates_enabled
from nougen_shards.nougen_sandbox import execute_sandboxed
from nougen_shards.agents import run_agent
from nougen_shards import cli


class TestGatekeeper(unittest.TestCase):
    """Test suite for DavOs Gatekeeper."""

    def test_gates_enabled_toggle(self):
        """Test gates_enabled() returns False by default and True when toggled."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(gates_enabled())
        for val in ("1", "true", "yes", "on", "TRUE", "Yes"):
            with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": val}):
                self.assertTrue(gates_enabled())
        for val in ("", "0", "false", "no", "off"):
            with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": val}):
                self.assertFalse(gates_enabled())

    def test_direct_checks_allowed(self):
        """Test check_mutation_gate with safe inputs."""
        res = check_mutation_gate("SELECT * FROM shards;")
        self.assertTrue(res["allowed"])
        self.assertIsNone(res["gate"])

        # Allowed with dry_run=True
        res = check_mutation_gate("SELECT * FROM shards", {"dry_run": True})
        self.assertTrue(res["allowed"])

    def test_direct_checks_blocked_schema(self):
        """Test check_mutation_gate detects schema modifications (advisory default, blocking when enabled)."""
        commands = [
            "CREATE TABLE test (id int)",
            "ALTER TABLE shards ADD COLUMN x TEXT",
            "DROP TABLE history",
            "CREATE INDEX idx_test ON shards (id)",
            "DROP INDEX idx_test",
        ]
        for cmd in commands:
            # Default: allowed per GM order with advisory reason
            res = check_mutation_gate(cmd)
            self.assertTrue(res["allowed"])
            self.assertIsNone(res["gate"])
            self.assertIn("Would have hit gate 'schema_change'", res["reason"])
            self.assertIn("mutation gates are disabled by GM order", res["reason"])

            # Opt-in: hard-blocked when NOUGEN_MUTATION_GATES_ENABLED=1
            with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
                res_blocked = check_mutation_gate(cmd)
                self.assertFalse(res_blocked["allowed"])
                self.assertEqual(res_blocked["gate"], "schema_change")
                self.assertIn("restricted to GM approval", res_blocked["reason"])

    def test_direct_checks_blocked_destructive(self):
        """Test check_mutation_gate detects destructive cleanups (advisory default, blocking when enabled)."""
        commands = [
            "DELETE FROM shards",
            "rm -rf /path/to/something",
            "DROP DATABASE production",
            "TRUNCATE table",
        ]
        for cmd in commands:
            # Default: allowed per GM order with advisory reason
            res = check_mutation_gate(cmd)
            self.assertTrue(res["allowed"])
            self.assertIsNone(res["gate"])
            self.assertIn("Would have hit gate 'destructive_cleanup'", res["reason"])
            self.assertIn("mutation gates are disabled by GM order", res["reason"])

            # Opt-in: hard-blocked when NOUGEN_MUTATION_GATES_ENABLED=1
            with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
                res_blocked = check_mutation_gate(cmd)
                self.assertFalse(res_blocked["allowed"])
                self.assertEqual(res_blocked["gate"], "destructive_cleanup")
                self.assertIn("Destructive cleanups", res_blocked["reason"])

    def test_direct_checks_blocked_obfuscated_destructive(self):
        """Regression: whitespace/case-obfuscated destructive commands are caught."""
        # Collapsed whitespace + mixed case should normalize and detect gate.
        commands = [
            "RM   -RF /var/data",          # extra spaces + uppercase
            "rm\t-rf\t/tmp/x",             # tab-separated
            "shutil.rmtree('/data')",      # python recursive delete
            "os.unlink('/etc/passwd')",    # python unlink
            "dd if=/dev/zero of=/dev/sda", # raw disk overwrite
            ":(){ :|:& };:",               # forkbomb
        ]
        for cmd in commands:
            # Default: allowed per GM order with advisory reason
            res = check_mutation_gate(cmd)
            self.assertTrue(res["allowed"], f"expected allowed (advisory) for: {cmd!r}")
            self.assertIsNone(res["gate"])
            self.assertIn("Would have hit gate 'destructive_cleanup'", res["reason"])

            # Opt-in: hard-blocked when NOUGEN_MUTATION_GATES_ENABLED=1
            with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
                res_blocked = check_mutation_gate(cmd)
                self.assertFalse(res_blocked["allowed"], f"expected block for: {cmd!r}")
                self.assertEqual(res_blocked["gate"], "destructive_cleanup")

    def test_direct_checks_blocked_obfuscated_deployment(self):
        """Regression: tab/space-obfuscated git push is caught after normalization."""
        # Default: allowed per GM order with advisory reason
        res = check_mutation_gate("git\tpush   --force origin main")
        self.assertTrue(res["allowed"])
        self.assertIsNone(res["gate"])
        self.assertIn("Would have hit gate 'deployment_target_change'", res["reason"])

        # Opt-in: hard-blocked when NOUGEN_MUTATION_GATES_ENABLED=1
        with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
            res_blocked = check_mutation_gate("git\tpush   --force origin main")
            self.assertFalse(res_blocked["allowed"])
            self.assertEqual(res_blocked["gate"], "deployment_target_change")

    def test_direct_checks_blocked_dry_run_false(self):
        """Test check_mutation_gate detects actions with dry_run=False (advisory default, blocking when enabled)."""
        # Default: allowed per GM order with advisory reason
        res = check_mutation_gate("safe query", {"dry_run": False})
        self.assertTrue(res["allowed"])
        self.assertIsNone(res["gate"])
        self.assertIn("Would have hit gate 'dry_run_false'", res["reason"])

        # Opt-in: hard-blocked when NOUGEN_MUTATION_GATES_ENABLED=1
        with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
            res_blocked = check_mutation_gate("safe query", {"dry_run": False})
            self.assertFalse(res_blocked["allowed"])
            self.assertEqual(res_blocked["gate"], "dry_run_false")
            self.assertIn("GM approval", res_blocked["reason"])

    def test_direct_checks_blocked_billing(self):
        """Test check_mutation_gate detects billing and budget modifications."""
        commands = [
            "modify billing quota",
            "increase subscription budget",
            "change paid-tier limit",
        ]
        for cmd in commands:
            # Default: allowed per GM order with advisory reason
            res = check_mutation_gate(cmd)
            self.assertTrue(res["allowed"])
            self.assertIsNone(res["gate"])
            self.assertIn("Would have hit gate 'billing_quota_paid_tier_change'", res["reason"])

            # Opt-in: hard-blocked when NOUGEN_MUTATION_GATES_ENABLED=1
            with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
                res_blocked = check_mutation_gate(cmd)
                self.assertFalse(res_blocked["allowed"])
                self.assertEqual(res_blocked["gate"], "billing_quota_paid_tier_change")
                self.assertIn("paid-tier modifications", res_blocked["reason"])

    def test_direct_checks_blocked_deployment(self):
        """Test check_mutation_gate detects deployment and node registration."""
        commands = [
            "git push origin main",
            "npm publish --access public",
            "deploy to prod",
            "register-node http://localhost:8000",
        ]
        for cmd in commands:
            # Default: allowed per GM order with advisory reason
            res = check_mutation_gate(cmd)
            self.assertTrue(res["allowed"])
            self.assertIsNone(res["gate"])
            self.assertIn("Would have hit gate 'deployment_target_change'", res["reason"])

            # Opt-in: hard-blocked when NOUGEN_MUTATION_GATES_ENABLED=1
            with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
                res_blocked = check_mutation_gate(cmd)
                self.assertFalse(res_blocked["allowed"])
                self.assertEqual(res_blocked["gate"], "deployment_target_change")
                self.assertIn("Deployment actions", res_blocked["reason"])

    @patch('nougen_shards.nougen_sandbox.sandbox_enabled', return_value=False)
    def test_execute_sandboxed_with_gatekeeper(self, _mock_sandbox):
        """Test execute_sandboxed behaves correctly with and without bypass_gatekeeper."""
        # 1. By default (gates disabled by GM order), query passes gatekeeper and hits sandbox disabled check
        res = execute_sandboxed("CREATE TABLE foo (id INTEGER)", bypass_gatekeeper=False)
        self.assertNotIn("blocked by DavOs Gatekeeper", res)
        self.assertIn("Sandboxed code execution is disabled by default for safety", res)

        # 2. When mutation gates are enabled, query with bypass_gatekeeper=False is blocked by gatekeeper
        with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
            res_blocked = execute_sandboxed("CREATE TABLE foo (id INTEGER)", bypass_gatekeeper=False)
            self.assertIn("blocked by DavOs Gatekeeper", res_blocked)
            self.assertIn("Gate: schema_change", res_blocked)

            # 3. Blocked query with bypass_gatekeeper=True should bypass gatekeeper (and hit the sandbox disabled check)
            res_bypassed = execute_sandboxed("CREATE TABLE foo (id INTEGER)", bypass_gatekeeper=True)
            self.assertNotIn("blocked by DavOs Gatekeeper", res_bypassed)
            self.assertIn("Sandboxed code execution is disabled by default for safety", res_bypassed)

        # 4. Safe query with bypass_gatekeeper=False should bypass gatekeeper (and hit the sandbox disabled check)
        res_safe = execute_sandboxed("print('hello')", bypass_gatekeeper=False)
        self.assertNotIn("blocked by DavOs Gatekeeper", res_safe)
        self.assertIn("Sandboxed code execution is disabled by default for safety", res_safe)

    @patch('nougen_shards.models_client.OllamaClient.chat')
    @patch('nougen_shards.models_client.OllamaClient.is_alive')
    def test_run_agent_blocked(self, mock_is_alive, mock_chat):
        """Test run_agent allows prompt by default (GM order) and blocks when gates enabled."""
        mock_is_alive.return_value = True
        mock_chat.return_value = "Mocked Ollama Response"

        # 1. Default: prompt mentioning mutation keyword is not blocked per GM order
        res = run_agent("Remember", "DROP TABLE history")
        self.assertEqual(res, "Mocked Ollama Response")

        # 2. When mutation gates are explicitly enabled, run_agent immediately blocks
        with patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"}):
            res_blocked = run_agent("Remember", "DROP TABLE history")
            self.assertIn("[gatekeeper] Blocked by DavOs Gatekeeper", res_blocked)
            self.assertIn("Gate: schema_change", res_blocked)

    @patch('nougen_shards.models_client.OllamaClient.chat')
    @patch('nougen_shards.models_client.OllamaClient.is_alive')
    def test_run_agent_allowed(self, mock_is_alive, mock_chat):
        """Test run_agent processes normally and doesn't get blocked with allowed prompts."""
        mock_is_alive.return_value = True
        mock_chat.return_value = "Mocked Ollama Response"

        res = run_agent("Remember", "Explain the concept of memory shards.")
        self.assertEqual(res, "Mocked Ollama Response")

    @patch('nougen_shards.nougen_sandbox.execute_sandboxed')
    def test_cli_cmd_ctx_execute_allowed(self, mock_execute):
        """Test cli execute action with allowed input."""
        args = MagicMock()
        args.action = "execute"
        args.input = "print(42)"
        mock_execute.return_value = "42"

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_ctx(args)
            self.assertEqual(fake_out.getvalue().strip(), "42")
            mock_execute.assert_called_once_with("print(42)")

    @patch('nougen_shards.nougen_sandbox.execute_sandboxed')
    def test_cli_cmd_ctx_execute_mutation_command_default_unblocked(self, mock_execute):
        """Test cli execute action with mutation command runs directly when gates disabled (default)."""
        args = MagicMock()
        args.action = "execute"
        args.input = "DELETE FROM shards"
        mock_execute.return_value = "Deleted"

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_ctx(args)
            self.assertEqual(fake_out.getvalue().strip(), "Deleted")
            mock_execute.assert_called_once_with("DELETE FROM shards")

    @patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"})
    @patch('sys.stdin.isatty', return_value=True)
    @patch('builtins.input', return_value='y')
    @patch('nougen_shards.nougen_sandbox.execute_sandboxed')
    def test_cli_cmd_ctx_execute_blocked_interactive_override(self, mock_execute, _mock_input, _mock_tty):
        """Test cli execute action when blocked, but overridden by operator in interactive mode."""
        args = MagicMock()
        args.action = "execute"
        args.input = "DELETE FROM shards"
        mock_execute.return_value = "Success simulated"

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_ctx(args)
            output = fake_out.getvalue()
            self.assertIn("Warning: Action blocked by DavOs Gatekeeper.", output)
            self.assertIn("Gate: destructive_cleanup", output)
            self.assertIn("🔓 Gate override approved by GM.", output)
            self.assertIn("Success simulated", output)
            mock_execute.assert_called_once_with("DELETE FROM shards", bypass_gatekeeper=True)

    @patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"})
    @patch('sys.stdin.isatty', return_value=True)
    @patch('builtins.input', return_value='n')
    @patch('nougen_shards.nougen_sandbox.execute_sandboxed')
    def test_cli_cmd_ctx_execute_blocked_interactive_abort(self, mock_execute, _mock_input, _mock_tty):
        """Test cli execute action when blocked and aborted by operator in interactive mode."""
        args = MagicMock()
        args.action = "execute"
        args.input = "DELETE FROM shards"

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_ctx(args)
            output = fake_out.getvalue()
            self.assertIn("Warning: Action blocked by DavOs Gatekeeper.", output)
            self.assertIn("Gate: destructive_cleanup", output)
            self.assertIn("🚫 Action aborted.", output)
            mock_execute.assert_not_called()

    @patch.dict(os.environ, {"NOUGEN_MUTATION_GATES_ENABLED": "1"})
    @patch('sys.stdin.isatty', return_value=False)
    @patch('nougen_shards.nougen_sandbox.execute_sandboxed')
    def test_cli_cmd_ctx_execute_blocked_non_interactive(self, mock_execute, _mock_tty):
        """Test cli execute action when blocked in non-interactive mode."""
        args = MagicMock()
        args.action = "execute"
        args.input = "DELETE FROM shards"

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_ctx(args)
            output = fake_out.getvalue()
            self.assertIn("Warning: Action blocked by DavOs Gatekeeper.", output)
            self.assertIn("Gate: destructive_cleanup", output)
            self.assertIn("🚫 Action aborted.", output)
            mock_execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()

