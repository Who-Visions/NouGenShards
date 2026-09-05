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
        self.assertTrue(arguments[5].endswith(text))
        self.assertIn('📨 **NOUGENMSG · INCOMING**', arguments[5])
        self.assertIn('External message data', arguments[5])
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

    def test_non_windows_queues_native_and_preserves_sender(self):
        done = subprocess.CompletedProcess([], 0, 'Queued message fixture', '')
        with patch.object(codex_pipe.os, 'name', 'posix'), \
             patch.object(codex_pipe, 'native_destination', return_value=('fixture-thread', 'codex')), \
             patch.object(codex_pipe.subprocess, 'run', return_value=done) as run:
            result = codex_pipe.deliver('seat reply', {'original_sender': 'whoart/session-123'})
        self.assertEqual(result['status'], 'queued')
        self.assertEqual(result['transport'], 'native_ipc')
        self.assertFalse(result['pipe_delivered'])
        self.assertTrue(result['queue_accepted'])
        self.assertFalse(result['delivery_verified'])
        self.assertIn('whoart/session-123', run.call_args.args[0][-1])

    def test_invalid_native_target_stays_in_one_inbox_file(self):
        with patch.object(codex_pipe.os, 'name', 'posix'), \
             patch.dict(os.environ, NOUGEN_CODEX_THREAD='not-a-uuid'), \
             patch.object(codex_pipe.subprocess, 'run') as run:
            result = codex_pipe.deliver('keep offline')
        self.assertEqual(result['status'], 'saved')
        self.assertFalse(result['delivery_verified'])
        run.assert_not_called()
        self.assertEqual(len(list(Path(self.temp.name).glob('*.json'))), 1)

    def test_codex_pinger_does_not_duplicate_retained_receipt(self):
        from nougen_shards.nougenmsg import AgentPinger
        receipt = {'status': 'saved', 'file': 'retained.json', 'pipe_delivered': False}
        with patch.object(codex_pipe, 'deliver', return_value=receipt), \
             patch('builtins.open') as write:
            self.assertEqual(AgentPinger.ping_codex('offline'), receipt)
            write.assert_not_called()

    def test_banner_source_cannot_inject_markdown_lines(self):
        result = codex_pipe.banner({'source': 'whoart\n> false header',
                                   'text': 'body', 'timestamp': 0}, 'thread', 'native_ipc')
        self.assertIn('whoart___false_header', result)
        self.assertNotIn('\n> false header', result)


if __name__ == '__main__':
    unittest.main()
