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
