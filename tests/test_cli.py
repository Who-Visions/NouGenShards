"""Tests for the NouGenShards CLI."""
import unittest
from unittest.mock import patch, MagicMock, mock_open
import io
import sqlite3
from nougen_shards import cli

class TestCLI(unittest.TestCase):
    """Test suite for CLI commands."""

    @patch('nougen_shards.cli.shards.init_db')
    def test_cmd_init(self, mock_init):
        """Test the init command."""
        args = MagicMock()
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_init(args)
            self.assertIn("Bootstraping NouGenShards local layer...", fake_out.getvalue())
            mock_init.assert_called_once()

    @patch('nougen_shards.cli.shards.capture')
    def test_cmd_add(self, mock_capture):
        """Test the add command with content."""
        args = MagicMock()
        args.stdin = False
        args.content = "Test content"
        args.tags = "tag1,tag2"
        mock_capture.return_value = True

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_add(args)
            self.assertIn("✅ Shard captured!", fake_out.getvalue())
            mock_capture.assert_called_once_with(
                "KNOWLEDGE", "Test content", "Test content", ["tag1", "tag2"]
            )

    @patch('nougen_shards.cli.shards.capture')
    @patch('sys.stdin', new_callable=io.StringIO)
    def test_cmd_add_stdin(self, mock_stdin, mock_capture):
        """Test the add command using stdin."""
        mock_stdin.write("Stdin content")
        mock_stdin.seek(0)
        args = MagicMock()
        args.stdin = True
        args.tags = None
        mock_capture.return_value = True

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_add(args)
            self.assertIn("✅ Shard captured!", fake_out.getvalue())
            mock_capture.assert_called_once_with(
                "KNOWLEDGE", "Stdin content", "Stdin content", []
            )

    @patch('nougen_shards.cli.shards.retrieve')
    def test_cmd_search(self, mock_retrieve):
        """Test the search command."""
        args = MagicMock()
        args.query = "test"
        mock_retrieve.return_value = [
            {
                'id': 1,
                'utility_score': 1.0,
                'access_count': 5,
                'tags': '["tag1"]',
                'title': 'Test Title',
                'content': 'Test Content'
            }
        ]

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_search(args)
            self.assertIn("🔍 Found 1 shards:", fake_out.getvalue())
            self.assertIn("Test Title", fake_out.getvalue())

    @patch('builtins.input', return_value='y')
    def test_cmd_connect(self, _mock_input):
        """Test the connect command."""
        args = MagicMock()
        args.mcp = True
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_connect(args)
            self.assertIn("✅ Wires connected.", fake_out.getvalue())

    def test_cmd_config(self):
        """Test the config command."""
        args = MagicMock()
        args.action = "set"
        args.key = "test_key"
        args.value = "test_value"
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_config(args)
            self.assertIn("✅ Configuration updated: test_key = test_value", fake_out.getvalue())

    @patch('nougen_shards.cli.shards.capture')
    @patch('pathlib.Path.exists', return_value=True)
    def test_cmd_ingest(self, _mock_exists, mock_capture):
        """Test the ingest command."""
        args = MagicMock()
        args.file = "test.md"
        mock_capture.return_value = True

        m_open = mock_open(read_data="File content")
        with patch('builtins.open', m_open):
            with patch('sys.stdout', new=io.StringIO()) as fake_out:
                cli.cmd_ingest(args)
                self.assertIn("Ingesting test.md...", fake_out.getvalue())
                self.assertIn("✅ Ingestion complete.", fake_out.getvalue())
                mock_capture.assert_called_once_with(
                    "INGEST", "test.md", "File content", ["ingested", "docs"]
                )

    @patch('nougen_shards.cli.shards.mark_shard')
    def test_cmd_mark_worked(self, mock_mark):
        """Test the mark command with --worked."""
        args = MagicMock()
        args.id = 1
        args.worked = True
        args.failed = False
        mock_mark.return_value = True

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_mark(args)
            self.assertIn("marked as 'worked'", fake_out.getvalue())
            mock_mark.assert_called_once_with(1, True)

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
        
        # Mock first DB as existing
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = 1024 * 1024
        
        # Side effect to handle multiple DB calls in loop
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

    @patch('nougen_shards.cli.shards.get_connection')
    def test_cmd_status_error(self, mock_get_conn):
        """Test the status command when database is not initialized."""
        args = MagicMock()
        mock_get_conn.side_effect = sqlite3.Error("Test Error")

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_status(args)
            self.assertIn("Database not initialized.", fake_out.getvalue())

    def test_cmd_hook(self):
        """Test the hook command."""
        args = MagicMock()
        args.action = "install"
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_hook(args)
            self.assertIn("✅ Auto-capture hook installed", fake_out.getvalue())

    @patch('sys.argv', ['nougen', '--version'])
    def test_main_version(self):
        """Test main entry point with --version."""
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with self.assertRaises(SystemExit) as exc:
                cli.main()
            self.assertEqual(exc.exception.code, 0)
            self.assertIn(f"NouGenShards v{cli.VERSION}", fake_out.getvalue())

    @patch('sys.argv', ['nougen'])
    def test_main_no_args(self):
        """Test main entry point with no arguments."""
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with self.assertRaises(SystemExit) as exc:
                cli.main()
            self.assertEqual(exc.exception.code, 0)
            self.assertIn("🪩 NouGenShards CLI", fake_out.getvalue())

    @patch('sys.argv', ['nougen', 'init'])
    @patch('nougen_shards.cli.get_parser')
    @patch('nougen_shards.cli.cmd_init')
    def test_main_command(self, mock_cmd_init, mock_get_parser):
        """Test main entry point calls specific command."""
        mock_parser = MagicMock()
        mock_get_parser.return_value = mock_parser
        args = MagicMock()
        args.command = "init"
        mock_parser.parse_args.return_value = args

        cli.main()
        mock_cmd_init.assert_called_once_with(args)

if __name__ == '__main__':
    unittest.main()
