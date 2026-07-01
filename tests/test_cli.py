"""Tests for the NouGenShards CLI."""
import unittest
from unittest.mock import patch, MagicMock, mock_open
import io
import sqlite3
import sys
import tempfile
from pathlib import Path
import nougen_shards.cli as cli

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
        """Test the config command."""
        args = MagicMock()
        args.action = "set"
        args.key = "test_key"
        args.value = "test_value"
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_config(args)
            self.assertIn("✅ Configuration updated", fake_out.getvalue())

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
