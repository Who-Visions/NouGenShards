"""Tests for the NouGenShards CLI."""
import unittest
from unittest.mock import patch, MagicMock, mock_open
import io
import json
import numpy as np
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

    @patch('nougen_shards.cli.federation.federated_retrieve')
    def test_cmd_search_json_serializes_float32_blob(self, mock_retrieve):
        args = MagicMock()
        args.query = "test"
        args.semantic = False
        args.dual = False
        args.json = True
        args.domain = None
        vector = np.array([0.25, -1.5, 3.0], dtype=np.float32)
        mock_retrieve.return_value = [{"id": 1, "embedding": vector.tobytes()}]

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_search(args)

        payload = json.loads(fake_out.getvalue())
        self.assertEqual(payload[0]["embedding"], vector.tolist())

    @patch('nougen_shards.cli.federation.federated_retrieve')
    def test_cmd_search_json_supports_legacy_embedding(self, mock_retrieve):
        args = MagicMock()
        args.query = "test"
        args.semantic = False
        args.dual = False
        args.json = True
        args.domain = None
        mock_retrieve.return_value = [{"id": 1, "embedding": b"[0.5, -0.5]"}]

        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_search(args)

        payload = json.loads(fake_out.getvalue())
        self.assertEqual(payload[0]["embedding"], [0.5, -0.5])

    @patch('nougen_shards.cli.shards.mark_shard')
    def test_cmd_mark(self, mock_mark):
        """Test the mark command with an explicit db index."""
        args = MagicMock()
        args.id = 1
        args.worked = True
        args.db = 3
        mock_mark.return_value = True
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_mark(args)
            out = fake_out.getvalue()
            self.assertIn("Shard #1", out)
            self.assertIn("updated", out)
        # The resolved db must reach core, or the wrong shard gets the credit.
        mock_mark.assert_called_once_with(1, worked=True, db_index=3)

    @patch('nougen_shards.cli.shards.get_shard_title', return_value="a title")
    @patch('nougen_shards.cli.shards.locate_shard', return_value=[2, 7])
    @patch('nougen_shards.cli.shards.mark_shard')
    def test_cmd_mark_ambiguous_id_refuses(self, mock_mark, mock_locate, mock_title):
        """An id living in several DBs must not be resolved by guessing.

        Ids are per-DB AUTOINCREMENT. Silently taking the first match trains the
        usefulness prior on an unrelated shard and still reports success, which
        corrupts the signal this command exists to build.
        """
        args = MagicMock()
        args.id = 10032
        args.worked = True
        args.db = None
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_mark(args)
            out = fake_out.getvalue()
        mock_mark.assert_not_called()
        self.assertIn("ambiguous", out)
        self.assertIn("--db 2", out)
        self.assertIn("--db 7", out)

    @patch('nougen_shards.cli.shards.locate_shard', return_value=[5])
    @patch('nougen_shards.cli.shards.mark_shard')
    def test_cmd_mark_unique_id_resolves(self, mock_mark, mock_locate):
        """A globally unique id needs no --db: resolve it rather than refuse."""
        args = MagicMock()
        args.id = 10150
        args.worked = True
        args.db = None
        mock_mark.return_value = True
        with patch('sys.stdout', new=io.StringIO()):
            cli.cmd_mark(args)
        mock_mark.assert_called_once_with(10150, worked=True, db_index=5)

    @patch('nougen_shards.cli.shards.locate_shard', return_value=[])
    @patch('nougen_shards.cli.shards.mark_shard')
    def test_cmd_mark_missing_id(self, mock_mark, mock_locate):
        """An id in no database reports not-found instead of writing."""
        args = MagicMock()
        args.id = 999999
        args.worked = True
        args.db = None
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            cli.cmd_mark(args)
            self.assertIn("Error finding shard", fake_out.getvalue())
        mock_mark.assert_not_called()

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
