"""Tests for the NouGenShards CLI."""
import unittest
from unittest.mock import patch, MagicMock, mock_open
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
import nougen_shards.cli as cli

# Import path of the package under test, discovered from the loaded module
# rather than hardcoded, so the subprocess lane follows the same checkout.
_SRC_DIR = str(Path(cli.__file__).resolve().parents[1])


def _cli_env(overrides=None):
    """A child-process env that can import the package under test."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _SRC_DIR + (os.pathsep + existing if existing else "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(overrides or {})
    return env


def _run_cli(argv, env=None):
    """Run the CLI as a real process so the OS-level exit code is observable."""
    return subprocess.run(
        [sys.executable, "-m", "nougen_shards.cli", *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env or _cli_env(), timeout=120,
    )


def _isolated_env(vault_dir, extra=None):
    """Env pinned to a throwaway vault so no test can read or write the real one.

    NOUGEN_VAULT_DIR drives BOTH stores the CLI touches: the shard cluster
    (core.GLOBAL_DIR) and the secrets vault (keymaker.VAULT_DIR). Pinning it is
    what makes "no database", "no OpenRouter key" reproducible failure states
    instead of whatever the developer's machine happens to have.
    """
    overrides = {"NOUGEN_VAULT_DIR": str(vault_dir)}
    overrides.update(extra or {})
    return _cli_env(overrides)


class TestCLIExitCodes(unittest.TestCase):
    """main() must propagate handler return codes to the process exit status."""

    def test_handoff_unreadable_message_file_exits_non_zero(self):
        """cmd_handoff returns 1 for an unreadable -M; the PROCESS must too.

        Hooks, CI steps and this repo's scheduled tasks branch on the exit
        status, so a handler failure that exits 0 silently disarms all of them.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "does-not-exist.md"
            result = _run_cli(
                ["handoff", "create", "-a", "test-agent", "-M", str(missing)]
            )
        self.assertNotEqual(
            result.returncode, 0,
            "unreadable --message-file reported success at the process level "
            f"(stdout={result.stdout!r} stderr={result.stderr!r})"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error reading --message-file", result.stderr)

    def test_successful_command_exits_zero(self):
        """The propagation fix must not turn ordinary successes into failures."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Path(temp_dir) / "config.json"
            env = _cli_env({"NOUGEN_CONFIG": str(cfg)})
            result = _run_cli(["config", "set", "ok_key", "ok_value"], env)
        self.assertEqual(result.returncode, 0, result.stderr)


class TestDoctorExitCode(unittest.TestCase):
    """`doctor` is a diagnostic: it MUST be able to report a bad diagnosis.

    A health check wired into a scheduled task or a pre-push hook that always
    exits 0 is worse than no health check — it actively certifies a broken
    install as healthy.
    """

    def test_doctor_exits_non_zero_when_substrate_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["doctor"], _isolated_env(vault))
        self.assertNotEqual(
            result.returncode, 0,
            "doctor diagnosed a vault with no shard database and still exited 0 "
            f"(stdout={result.stdout!r})"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("No database shards found", result.stdout)
        self.assertIn("Diagnosis", result.stderr)

    def test_doctor_exits_zero_on_a_healthy_substrate(self):
        """And it must not cry wolf: a freshly initialised vault is healthy.

        No BYOK provider keys and no secrets vault yet is the NORMAL state of a
        local-first install, so those red rows must not turn into a failure.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            env = _isolated_env(vault)
            init = _run_cli(["init"], env)
            self.assertEqual(init.returncode, 0, init.stderr)
            result = _run_cli(["doctor"], env)
        self.assertEqual(
            result.returncode, 0,
            f"doctor failed a healthy freshly-initialised vault "
            f"(stdout={result.stdout!r} stderr={result.stderr!r})"
        )

    def test_doctor_json_report_carries_the_same_verdict(self):
        """--json must not be a way to lose the verdict."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["doctor", "--json"], _isolated_env(vault))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('"healthy": false', result.stdout)


class TestRouterExitCode(unittest.TestCase):
    """`router doctor` is the same class of hole as `doctor`."""

    def test_router_doctor_exits_non_zero_without_a_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["router", "doctor"], _isolated_env(vault))
        self.assertNotEqual(
            result.returncode, 0,
            "router doctor reported a missing OpenRouter key and exited 0 "
            f"(stdout={result.stdout!r})"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("OpenRouter key not found", result.stdout)

    def test_router_doctor_exits_zero_when_routing_is_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            env = _isolated_env(vault)
            stored = _run_cli(["auth", "set-key", "openrouter", "sk-test-not-a-real-key"], env)
            self.assertEqual(stored.returncode, 0, stored.stderr)
            result = _run_cli(["router", "doctor"], env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("openrouter_key: True", result.stdout)

    def test_router_without_a_subcommand_is_a_usage_error(self):
        """The dispatcher must not silently succeed on an unrouted invocation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            env = _isolated_env(vault)
            _run_cli(["auth", "set-key", "openrouter", "sk-test-not-a-real-key"], env)
            result = _run_cli(["router"], env)
        self.assertEqual(result.returncode, 2, result.stdout)


class TestAuthExitCode(unittest.TestCase):
    """A credential write that failed must never look like it landed."""

    def test_unknown_provider_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(
                ["auth", "set-key", "not-a-provider", "sk-test-not-a-real-key"],
                _isolated_env(vault),
            )
        self.assertNotEqual(
            result.returncode, 0,
            f"auth accepted an unknown provider and exited 0 (stdout={result.stdout!r})"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown provider", result.stdout)
        self.assertNotIn("saved to vault", result.stdout)

    def test_storing_and_listing_a_key_exits_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            env = _isolated_env(vault)
            stored = _run_cli(["auth", "set-key", "openrouter", "sk-test-not-a-real-key"], env)
            listed = _run_cli(["auth", "list"], env)
        self.assertEqual(stored.returncode, 0, stored.stderr)
        self.assertIn("saved to vault", stored.stdout)
        self.assertEqual(listed.returncode, 0, listed.stderr)

    def test_listing_an_empty_vault_is_success_not_failure(self):
        """Zero connected services is a correct answer, not an error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["auth", "list"], _isolated_env(vault))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No cloud services connected", result.stdout)


class TestDbExitCode(unittest.TestCase):
    """A link that did not persist must not report success: federated search
    would then quietly query one source fewer."""

    def test_link_without_a_table_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["db", "link"], _isolated_env(vault))
        self.assertNotEqual(
            result.returncode, 0,
            f"incomplete `db link` exited 0 (stdout={result.stdout!r})"
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("✅", result.stdout)

    def test_link_and_list_exit_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            env = _isolated_env(vault)
            linked = _run_cli(
                ["db", "link", "sqlite:///" + str(Path(temp_dir) / "ext.db"),
                 "--table", "notes"],
                env,
            )
            listed = _run_cli(["db", "list"], env)
        self.assertEqual(linked.returncode, 0, linked.stderr)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("notes", listed.stdout)

    def test_listing_with_nothing_linked_is_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["db", "list"], _isolated_env(vault))
        self.assertEqual(result.returncode, 0, result.stderr)


class TestNodeExitCode(unittest.TestCase):
    """Sync is the sharp edge: a push that never left the machine used to print
    '✅ Sync result: error' and exit 0, which reads as 'backup succeeded'."""

    def test_push_to_a_rejected_url_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            # An insecure URL is refused by the cloud connector, which reports
            # the refusal in-band as {"status": "error"} — no network needed.
            result = _run_cli(
                ["node", "push", "http://insecure.invalid", "--token", "t"],
                _isolated_env(vault),
            )
        self.assertNotEqual(
            result.returncode, 0,
            f"a rejected push exited 0 (stdout={result.stdout!r})"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("push failed", result.stderr)

    def test_push_without_a_token_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["node", "push", "https://node.invalid"], _isolated_env(vault))
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_link_and_list_exit_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            env = _isolated_env(vault)
            linked = _run_cli(["node", "link", "https://node.invalid", "--name", "n1"], env)
            listed = _run_cli(["node", "list"], env)
        self.assertEqual(linked.returncode, 0, linked.stderr)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("n1", listed.stdout)


class TestIndexExitCode(unittest.TestCase):
    """Index maintenance runs unattended; a build that did not write an index
    must not tell the scheduler it did."""

    def test_ann_build_with_a_non_ok_status_exits_non_zero(self):
        """The status->exit-code rule itself.

        NOUGEN_ANN_OK_STATUSES is the documented knob for which in-band build
        statuses count as done (Rule 0.2). Narrowing it to "ok" makes the empty
        build that this vault produces a non-ok status, which is the condition
        cmd_index must turn into a failure.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(
                ["index", "ann-build"],
                _isolated_env(vault, {"NOUGEN_ANN_OK_STATUSES": "ok"}),
            )
        self.assertNotEqual(
            result.returncode, 0,
            f"a build that wrote no index exited 0 (stdout={result.stdout!r})"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("ANN index build failed", result.stderr)

    def test_schema_migrate_propagates_the_delegated_failure(self):
        """cmd_index hands schema-migrate to schema._main; its refusal to run
        without a vault must reach the process exit status."""
        env = _cli_env()
        env.pop("NOUGEN_VAULT_DIR", None)
        result = _run_cli(["index", "schema-migrate"], env)
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_ann_build_on_an_empty_vault_exits_zero(self):
        """A vault with no embeddings yet is not a failed build: recall falls
        back to the linear scan, which works."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            result = _run_cli(["index", "ann-build"], _isolated_env(vault))
        self.assertEqual(result.returncode, 0, result.stderr)


class TestRemainingHandlerExitCodes(unittest.TestCase):
    """Coverage for the non-prioritised handlers reachable without a network,
    an LLM, a TTY or a long-running server."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        self.vault.mkdir()
        self.env = _isolated_env(self.vault)
        init = _run_cli(["init"], self.env)
        self.assertEqual(init.returncode, 0, init.stderr)

    def tearDown(self):
        self._tmp.cleanup()

    def test_mark_missing_shard_exits_non_zero(self):
        result = _run_cli(["mark", "999999", "--worked"], self.env)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Error finding shard", result.stdout)

    def test_ctx_get_missing_event_exits_non_zero(self):
        result = _run_cli(["ctx", "get", "999999"], self.env)
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_ctx_search_without_a_query_is_a_usage_error(self):
        result = _run_cli(["ctx", "search"], self.env)
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_trigger_rm_of_a_missing_trigger_exits_non_zero(self):
        result = _run_cli(["trigger", "rm", "--id", "999999"], self.env)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("no such trigger", result.stdout)

    def test_trigger_status_exits_zero(self):
        result = _run_cli(["trigger", "status"], self.env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_connect_without_mcp_is_a_usage_error(self):
        result = _run_cli(["connect"], self.env)
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_hook_without_an_action_is_a_usage_error(self):
        result = _run_cli(["hook"], self.env)
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_ingest_of_an_unreadable_path_exits_non_zero(self):
        missing = Path(self._tmp.name) / "nope.md"
        result = _run_cli(["ingest", str(missing)], self.env)
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_search_with_no_matches_is_success(self):
        """The most important non-failure: an empty vault is not a broken one."""
        result = _run_cli(["search", "nothing-will-ever-match-this-xyzzy"], self.env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_status_and_stats_exit_zero(self):
        for argv in (["status"], ["stats"]):
            with self.subTest(argv=argv):
                result = _run_cli(argv, self.env)
                self.assertEqual(result.returncode, 0, result.stderr)


class TestCLI(unittest.TestCase):
    """Test suite for CLI commands."""

    @patch('nougen_shards.cli.shards.init_db')
    def test_cmd_init(self, mock_init):
        """Test the init command."""
        args = MagicMock()
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_init(args)
            self.assertIn("Initializing Valerion", fake_out.getvalue())
            self.assertIn("[IGNITION COMPLETE]", fake_out.getvalue())
            mock_init.assert_called_once()

    @patch('nougen_shards.cli.shards.capture')
    def test_cmd_add(self, mock_capture):
        """Test the add command with content."""
        args = MagicMock()
        args.stdin = False
        args.content = "Test content"
        args.tags = "tag1,tag2"
        args.embed = False
        mock_capture.return_value = True
    
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_add(args)
            self.assertIn("✅ Shard captured!", fake_out.getvalue())
            mock_capture.assert_called_once_with(
                "KNOWLEDGE", "Test content", "Test content", ["tag1", "tag2"], embedding=None, domain_key=None
            )

    @patch('nougen_shards.cli.federation.federated_retrieve')
    def test_cmd_search(self, mock_retrieve):
        """Test the search command."""
        args = MagicMock()
        args.query = "test"
        args.semantic = False
        mock_retrieve.return_value = [
            {
                'id': 1,
                'utility_score': 1.0,
                'final_score': 0.85,
                '_db_index': 1,
                'tags': '["tag1"]',
                'title': 'Test Title',
                'content': 'Test Content'
            }
        ]
    
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_search(args)
            self.assertIn("🔍 Found 1 records across the fabric", fake_out.getvalue())
            self.assertIn("Final Score: 0.85", fake_out.getvalue())

    @patch('nougen_shards.cli.shards.mark_shard')
    def test_cmd_mark(self, mock_mark):
        """Test the mark command."""
        args = MagicMock()
        args.id = 1
        args.worked = True
        mock_mark.return_value = True
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_mark(args)
            self.assertIn("Shard #1 updated", fake_out.getvalue())

    @patch('nougen_shards.cli.shards.get_connection')
    @patch('nougen_shards.cli.shards.get_db_path')
    @patch('nougen_shards.cli.shards.get_active_db_index', return_value=1)
    def test_cmd_status(self, mock_active, mock_get_path, mock_get_conn):
        """Test the status command."""
        args = MagicMock()
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cursor = mock_conn.execute.return_value
        mock_cursor.fetchone.return_value = [10]
        
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = 1024 * 1024
        
        def side_effect(idx):
            if idx == 1: return mock_path
            m = MagicMock()
            m.exists.return_value = False
            return m
        mock_get_path.side_effect = side_effect

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_status(args)
            self.assertIn("DB #1: 10 shards", fake_out.getvalue())
            self.assertIn("1.00 MB / 1024 MB", fake_out.getvalue())

    def test_cmd_config(self):
        """`config set` must report back the exact key/value it was given.

        The banner alone is worthless — a bare print of the success string
        passes it. Assert the key and the value make it into the output, so a
        handler that drops or swaps its arguments fails here.

        Persistence itself is pinned by
        test_cmd_config_set_get_round_trip_across_processes below.
        """
        args = MagicMock()
        args.action = "set"
        args.key = "test_key"
        args.value = "test_value"
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Path(temp_dir) / "config.json"
            with patch.dict(os.environ, {"NOUGEN_CONFIG": str(cfg)}):
                with patch('sys.stdout', new=io.StringIO()) as fake_out:
                    rc = cli.cmd_config(args)
                    output = fake_out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("✅ Configuration updated", output)
        self.assertIn("test_key = test_value", output)

    def test_cmd_config_reflects_distinct_values(self):
        """A different key/value must produce different output.

        Guards against a hardcoded echo: the previous assertion would still
        pass if the handler always printed the same literal pair.
        """
        args = MagicMock()
        args.action = "set"
        args.key = "embed_model"
        args.value = "nomic-embed-text"
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Path(temp_dir) / "config.json"
            with patch.dict(os.environ, {"NOUGEN_CONFIG": str(cfg)}):
                with patch('sys.stdout', new=io.StringIO()) as fake_out:
                    cli.cmd_config(args)
                    output = fake_out.getvalue()
        self.assertIn("embed_model = nomic-embed-text", output)
        self.assertNotIn("test_key", output)

    def test_cmd_config_missing_key_or_value_prints_usage(self):
        """An incomplete `config set` must NOT claim success."""
        for key, value in (("", "v"), ("k", ""), ("", "")):
            with self.subTest(key=key, value=value):
                args = MagicMock()
                args.action = "set"
                args.key = key
                args.value = value
                with patch('sys.stdout', new=io.StringIO()) as fake_out:
                    rc = cli.cmd_config(args)
                    output = fake_out.getvalue()
                self.assertIn("Usage: nougen config set", output)
                self.assertNotIn("Configuration updated", output)
                self.assertEqual(rc, 1, "an incomplete `config set` must exit non-zero")

    def test_cmd_config_set_get_round_trip_across_processes(self):
        """`config set` must actually persist — proven across process boundaries.

        Replaces test_cmd_config_persistence_is_unimplemented, which pinned the
        old defect (a success banner with no write). Same intent, stronger form:
        a banner alone can no longer pass. The write happens in one interpreter
        and the read in a second, so nothing in-memory can fake it.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Path(temp_dir) / "config.json"
            env = _cli_env({"NOUGEN_CONFIG": str(cfg)})

            setter = _run_cli(["config", "set", "embed_model", "nomic-embed-text"], env)
            self.assertEqual(setter.returncode, 0, setter.stderr)
            self.assertIn("✅ Configuration updated", setter.stdout)

            # Process 1 wrote a real file.
            self.assertTrue(cfg.exists(), "config set wrote no file")
            self.assertEqual(
                json.loads(cfg.read_text(encoding="utf-8"))["embed_model"],
                "nomic-embed-text",
            )

            # Process 2 reads it back.
            getter = _run_cli(["config", "get", "embed_model"], env)
            self.assertEqual(getter.returncode, 0, getter.stderr)
            self.assertEqual(getter.stdout.strip(), "nomic-embed-text")

    def test_cmd_config_set_merges_and_does_not_clobber(self):
        """A second `set` must preserve pre-existing keys and back the file up."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Path(temp_dir) / "config.json"
            cfg.write_text(json.dumps({"vault_dir": "/pre/existing"}), encoding="utf-8")
            env = _cli_env({"NOUGEN_CONFIG": str(cfg)})

            result = _run_cli(["config", "set", "embed_model", "mxbai"], env)
            self.assertEqual(result.returncode, 0, result.stderr)

            data = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(data["vault_dir"], "/pre/existing", "existing key clobbered")
            self.assertEqual(data["embed_model"], "mxbai")

            backup = cfg.with_suffix(cfg.suffix + ".bak")
            self.assertTrue(backup.exists(), "no backup taken before the first write")
            self.assertEqual(
                json.loads(backup.read_text(encoding="utf-8")), {"vault_dir": "/pre/existing"}
            )

    def test_cmd_config_failed_write_exits_non_zero(self):
        """A config file that cannot be parsed must NOT report success."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Path(temp_dir) / "config.json"
            cfg.write_text("{ this is not json", encoding="utf-8")
            env = _cli_env({"NOUGEN_CONFIG": str(cfg)})

            result = _run_cli(["config", "set", "k", "v"], env)
            self.assertNotEqual(result.returncode, 0, "corrupt config still reported success")
            self.assertNotIn("✅ Configuration updated", result.stdout)
            # And the unparseable file is left intact rather than silently reset.
            self.assertEqual(cfg.read_text(encoding="utf-8"), "{ this is not json")

    def test_cmd_config_get_missing_key_exits_non_zero(self):
        """`config get` on an unset key must fail, not print an empty success."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = Path(temp_dir) / "config.json"
            env = _cli_env({"NOUGEN_CONFIG": str(cfg)})
            result = _run_cli(["config", "get", "never_set"], env)
            self.assertNotEqual(result.returncode, 0)

    def test_cmd_hook_codex_anchor_reads_handoff_db(self):
        """Test Codex anchor hook emits compact state from handoffs.db."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            handoff_dir = root / ".handoffs"
            handoff_dir.mkdir()
            db_path = handoff_dir / "handoffs.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE handoff_records (
                    handoff_id TEXT PRIMARY KEY,
                    agent TEXT,
                    status TEXT,
                    goal TEXT,
                    message TEXT,
                    branch TEXT,
                    path TEXT,
                    created_at TEXT,
                    acknowledged_by TEXT,
                    acknowledged_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO handoff_records (
                    handoff_id, agent, status, goal, message, branch, path,
                    created_at, acknowledged_by, acknowledged_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "20260616_231648_main",
                    "codex",
                    "open",
                    "Standardize seamless triple-provider handoffs",
                    "Compact anchor source " + ("LONGMSG-" * 120),
                    "main",
                    "handoff.json",
                    "2026-06-16T23:16:48",
                    None,
                    None,
                    "2026-06-16T23:16:48",
                ),
            )
            conn.commit()
            conn.close()

            args = MagicMock()
            args.action = "codex-anchor"
            args.limit = 5
            args.max_chars = 4000

            with patch("nougen_shards.hooks._default_repo_root", return_value=root):
                with patch('sys.stdout', new=io.StringIO()) as fake_out:
                    cli.cmd_hook(args)
                    output = fake_out.getvalue()

            self.assertIn("[NOUGEN_CONTEXT_ANCHOR]", output)
            self.assertIn("Cache SLO: target >=90%", output)
            self.assertIn("20260616_231648_main", output)
            self.assertIn("Standardize seamless triple-provider handoffs", output)
            self.assertIn("Compact anchor source", output)
            self.assertIn("...", output)
            self.assertNotIn("LONGMSG-" * 80, output)

    def test_cmd_hook_install_writes_local_codex_artifacts(self):
        """Test local Codex hook install avoids profile/global mutation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / ".nougen-hooks"
            args = MagicMock()
            args.action = "install"
            args.agent = "codex"
            args.output_dir = str(output_dir)
            args.limit = 5
            args.max_chars = 4000

            with patch("nougen_shards.hooks._default_repo_root", return_value=root):
                with patch('sys.stdout', new=io.StringIO()) as fake_out:
                    cli.cmd_hook(args)
                    output = fake_out.getvalue()

            self.assertTrue((output_dir / "codex-preflight-anchor.md").exists())
            self.assertTrue((output_dir / "hf-space-orchestration-anchor.md").exists())
            self.assertTrue((output_dir / "codex-anchor.ps1").exists())
            self.assertTrue((output_dir / "codex-anchor.cmd").exists())
            self.assertIn("No shell profile or global runtime config was modified", output)

    @patch('nougen_shards.cli.hooks.get_space_orchestration_anchor')
    def test_cmd_hook_space_anchor(self, mock_space_anchor):
        """Test HF Space orchestration hook emits additive anchor."""
        mock_space_anchor.return_value = "[HF_SPACE_ORCHESTRATION]\nMode: additive control-plane"
        args = MagicMock()
        args.action = "space-anchor"
        args.limit = 5
        args.max_chars = 4000
        args.space = "WhoVisions/nga_hgf_Space"
        args.token_key = "Yuki_HGF_key"

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_hook(args)
            output = fake_out.getvalue()

        self.assertIn("[HF_SPACE_ORCHESTRATION]", output)
        mock_space_anchor.assert_called_once_with(
            limit=5,
            max_chars=4000,
            space_id="WhoVisions/nga_hgf_Space",
            token_key="Yuki_HGF_key",
        )

    @patch('nougen_shards.cli.shards.capture')
    @patch('pathlib.Path.exists', return_value=True)
    def test_cmd_ingest(self, _mock_exists, mock_capture):
        """Test the ingest command."""
        args = MagicMock()
        args.file = "test.md"
        mock_capture.return_value = True
        with patch('builtins.open', mock_open(read_data="content")):
            with patch('sys.stdout', new=io.StringIO()) as fake_out:
                cli.cmd_ingest(args)
                self.assertIn("✅ Ingestion complete", fake_out.getvalue())

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_main_no_args(self, mock_stdout):
        """Test main with no args."""
        with patch('sys.argv', ['nougen']):
            with self.assertRaises(SystemExit) as cm:
                cli.main()
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("🪩 NouGenShards CLI", mock_stdout.getvalue())

if __name__ == '__main__':
    unittest.main()
