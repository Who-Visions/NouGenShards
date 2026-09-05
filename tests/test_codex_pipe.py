import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nougen_shards import codex_pipe


class CodexPipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, NOUGEN_CODEX_INBOX=self.temp.name)
        env.start()
        self.addCleanup(env.stop)

    def test_queue_preserves_text_as_one_argument_and_archives(self):
        text = 'Unicode: hello \U0001f30d "quotes" $(whoami) `literal`\nsecond line'
        done = subprocess.CompletedProcess([], 0, 'Queued message test-id', '')
        with patch.object(codex_pipe.subprocess, 'run', return_value=done) as run:
            result = codex_pipe.handle({'text': text}, 'test-thread', 'codex.exe')
        self.assertEqual(result['status'], 'queued')
        self.assertFalse(result['delivery_verified'])
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[:5], ['codex.exe', 'queue', '--thread', 'test-thread', '--message'])
        self.assertEqual(json.loads(arguments[5].split('\n', 1)[1])['text'], text)
        self.assertFalse(run.call_args.kwargs.get('shell', False))
        self.assertEqual(Path(result['file']).parent.name, 'archive')
        self.assertEqual(json.loads(Path(result['file']).read_text(encoding='utf-8'))['text'], text)

    def test_queue_failure_retains_unread_message(self):
        done = subprocess.CompletedProcess([], 1, '', 'thread unavailable')
        with patch.object(codex_pipe.subprocess, 'run', return_value=done):
            result = codex_pipe.handle({'text': 'keep me'}, 'test-thread', 'codex.exe')
        self.assertEqual(result['status'], 'saved')
        self.assertEqual(Path(result['file']).parent, Path(self.temp.name))

    def test_offline_fallback_uses_unique_files(self):
        with patch.object(codex_pipe, 'request', side_effect=OSError('offline')):
            first = codex_pipe.deliver('first')
            second = codex_pipe.deliver('second')
        self.assertNotEqual(first['file'], second['file'])
        self.assertFalse(first['pipe_delivered'])
        self.assertEqual(len(list(Path(self.temp.name).glob('*.json'))), 2)

    def test_invalid_payload_does_not_queue(self):
        with patch.object(codex_pipe.subprocess, 'run') as run:
            for payload in ([], {}, {'text': ''}, {'text': 42}):
                with self.assertRaises(ValueError):
                    codex_pipe.handle(payload, 'thread', 'codex.exe')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
