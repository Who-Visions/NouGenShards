import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nougen_shards import codex_pipe


class CodexPipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, NOUGEN_CODEX_INBOX=self.temp.name)
        env.start()
        self.addCleanup(env.stop)

    def test_queue_preserves_text_and_retains_until_explicit_ack(self):
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
        self.assertEqual(Path(result['file']).parent, Path(self.temp.name))
        self.assertTrue(result['retained_until_ack'])
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

    def test_activate_is_idempotent_when_receiver_is_ready(self):
        ready = {"status": "listening", "thread": "00000000-0000-4000-8000-000000000000"}
        with patch.object(codex_pipe, "request", return_value=ready):
            result = codex_pipe.activate(ready["thread"])
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["started"])

    def test_activate_retargets_live_receiver(self):
        ready = {"status": "listening", "thread": "00000000-0000-4000-8000-000000000000"}
        switched = {"status": "ready", "thread": "11111111-1111-4111-8111-111111111111"}
        with patch.object(codex_pipe, "request", side_effect=[ready, switched]):
            result = codex_pipe.activate("11111111-1111-4111-8111-111111111111")
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["retargeted"])

    def test_retarget_persists_new_thread(self):
        thread = "11111111-1111-4111-8111-111111111111"
        target = Path(self.temp.name) / "relay_target.json"
        with patch.object(codex_pipe, "_target_file", return_value=target):
            result = codex_pipe.handle({"op": "retarget", "thread": thread},
                                       "00000000-0000-4000-8000-000000000000", "codex.exe")
        self.assertEqual(result["thread"], thread)
        self.assertEqual(json.loads(target.read_text())["thread_id"], thread)

    def test_exact_ack_archives_one_message_and_writes_receipt(self):
        message_id = "11111111-1111-4111-8111-111111111111"
        path = codex_pipe.save({"message_id": message_id, "thread": "thread-1", "text": "one"})
        other = codex_pipe.save({"message_id": "22222222-2222-4222-8222-222222222222",
                                 "thread": "thread-1", "text": "two"})
        receipt = codex_pipe.acknowledge(message_id, consumer="codex", thread="thread-1",
                                         inbox=self.temp.name, work="Verified patch and green CI", sha="abcdef1")
        self.assertTrue(receipt["acknowledged"])
        self.assertEqual(receipt["work"], "Verified patch and green CI")
        self.assertEqual(receipt["sha"], "abcdef1")
        self.assertFalse(Path(path).exists())
        self.assertTrue(Path(receipt["file"]).exists())
        self.assertTrue(Path(other).exists())
        again = codex_pipe.acknowledge(message_id, consumer="codex", thread="thread-1",
                                       inbox=self.temp.name, work="Again")
        self.assertTrue(again["idempotent"])

    def test_ack_requires_work_unless_allowed(self):
        message_id = "44444444-4444-4444-8444-444444444444"
        path = codex_pipe.save({"message_id": message_id, "thread": "thread-1", "text": "test"})
        rejected = codex_pipe.acknowledge(message_id, consumer="codex", thread="thread-1",
                                          inbox=self.temp.name)
        self.assertEqual(rejected["status"], "work_required")
        self.assertFalse(rejected["acknowledged"])
        self.assertTrue(Path(path).exists())

        forced = codex_pipe.acknowledge(message_id, consumer="codex", thread="thread-1",
                                        inbox=self.temp.name, allow_empty_work=True)
        self.assertTrue(forced["acknowledged"])

    def test_claim_message_marks_in_progress(self):
        message_id = "55555555-5555-4555-8555-555555555555"
        path = codex_pipe.save({"message_id": message_id, "thread": "thread-1", "text": "to claim"})
        claimed = codex_pipe.claim(message_id, consumer="codex", thread="thread-1", inbox=self.temp.name)
        self.assertEqual(claimed["status"], "claimed")
        self.assertTrue(claimed["claimed"])
        self.assertTrue(Path(path).exists())
        saved_data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertIn("claim", saved_data)
        self.assertEqual(saved_data["claim"]["consumer"], "codex")

    def test_ack_rejects_wrong_thread_without_moving_message(self):
        message_id = "33333333-3333-4333-8333-333333333333"
        path = codex_pipe.save({"message_id": message_id, "thread": "right", "text": "one"})
        receipt = codex_pipe.acknowledge(message_id, consumer="codex", thread="wrong",
                                         inbox=self.temp.name, work="Tried wrong thread")
        self.assertEqual(receipt["status"], "thread_mismatch")
        self.assertTrue(Path(path).exists())

    def test_multi_inbox_claim_and_ack_for_agy_and_claude(self):
        # Create simulated Antigravity inbox
        agy_inbox = Path(self.temp.name) / "agy_inbox"
        agy_inbox.mkdir()
        msg_id = "66666666-6666-4666-8666-666666666666"
        ping_file = agy_inbox / f"ping_{uuid.uuid4().hex}.json"
        ping_file.write_text(json.dumps({"message_id": msg_id, "text": "agy ping", "source": "fleet"}), encoding="utf-8")

        # Claim as antigravity agent specifying agy inbox
        claimed = codex_pipe.claim(msg_id, consumer="antigravity", inbox=str(agy_inbox))
        self.assertTrue(claimed["claimed"])
        self.assertEqual(claimed["consumer"], "antigravity")

        # Acknowledge with work
        acked = codex_pipe.acknowledge(msg_id, consumer="antigravity", inbox=str(agy_inbox), work="Ran memory sync")
        self.assertTrue(acked["acknowledged"])
        self.assertEqual(acked["work"], "Ran memory sync")
        self.assertTrue((agy_inbox / "archive" / ping_file.name).exists())
        self.assertTrue((agy_inbox / "archive" / f"{ping_file.name}.ack.json").exists())

    def _stage(self, message_id, **extra):
        codex_pipe.save({"message_id": message_id, "thread": "t", "text": "do the thing", **extra})

    def test_ack_of_actionable_message_stays_pending_execution(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000001"
        self._stage(mid)
        codex_pipe.acknowledge(mid, consumer="codex", thread="t", inbox=self.temp.name, allow_empty_work=True)
        record = codex_pipe.lifecycle(mid, self.temp.name)
        self.assertEqual(record["state"], "ACKED")
        self.assertTrue(record["pending_execution"])
        self.assertEqual([p["message_id"] for p in codex_pipe.pending_execution(self.temp.name)], [mid])

    def test_informational_message_ends_at_acked(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000002"
        self._stage(mid, origin={"kind": "status"})
        codex_pipe.acknowledge(mid, consumer="codex", thread="t", inbox=self.temp.name, allow_empty_work=True)
        self.assertFalse(codex_pipe.lifecycle(mid, self.temp.name)["pending_execution"])
        self.assertEqual(codex_pipe.pending_execution(self.temp.name), [])

    def test_take_acks_and_claims_atomically_and_is_idempotent(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000003"
        self._stage(mid)
        first = codex_pipe.take(mid, consumer="codex", thread="t", inbox=self.temp.name)
        self.assertEqual(first["lifecycle_state"], "CLAIMED")
        self.assertTrue(first["pending_execution"])
        again = codex_pipe.take(mid, consumer="codex", thread="t", inbox=self.temp.name)
        self.assertEqual(again["lifecycle_state"], "CLAIMED")
        self.assertEqual(len(codex_pipe.lifecycle(mid, self.temp.name)["history"]), 2)

    def test_complete_requires_evidence_and_legal_order(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000004"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t", inbox=self.temp.name)
        skip = codex_pipe.advance(mid, "COMPLETE", "proof", inbox=self.temp.name)
        self.assertEqual(skip["status"], "illegal_transition")
        self.assertTrue(codex_pipe.advance(mid, "EXECUTING", inbox=self.temp.name)["advanced"])
        bare = codex_pipe.advance(mid, "COMPLETE", "  ", inbox=self.temp.name)
        self.assertEqual(bare["status"], "evidence_required")
        self.assertTrue(codex_pipe.pending_execution(self.temp.name))
        done = codex_pipe.advance(mid, "COMPLETE", "PR merged: abc123", inbox=self.temp.name)
        self.assertTrue(done["advanced"])
        self.assertFalse(done["pending_execution"])
        self.assertFalse(done["evidence_verified"])
        self.assertEqual(codex_pipe.pending_execution(self.temp.name), [])
        after = codex_pipe.advance(mid, "EXECUTING", inbox=self.temp.name)
        self.assertEqual(after["status"], "illegal_transition")

    def test_advance_unknown_message_and_state(self):
        self.assertEqual(codex_pipe.advance("nope", "CLAIMED", inbox=self.temp.name)["status"], "no_lifecycle")
        mid = "aaaaaaaa-0000-4000-8000-000000000005"
        self._stage(mid)
        codex_pipe.acknowledge(mid, consumer="codex", thread="t", inbox=self.temp.name, allow_empty_work=True)
        self.assertEqual(codex_pipe.advance(mid, "DONE", "x", inbox=self.temp.name)["status"], "unknown_state")


@unittest.skipUnless(sys.platform == 'win32', 'named pipe is Windows-only')
class CodexPipeServeSurvivesBadConnectsTests(unittest.TestCase):
    """Regression for the WinError 2 fleet bug: a client that drops mid-connect must not
    take the whole receiver down with it (see relay leg 20260915T033332Z)."""

    def setUp(self):
        self.orig_pipe = codex_pipe.PIPE
        self.test_pipe = rf"\\.\pipe\LOCAL\test-nougen-msg-{uuid.uuid4().hex}"
        codex_pipe.PIPE = self.test_pipe
        self.thread_id = '00000000-0000-4000-8000-000000000000'
        # sys.executable (python.exe) only needs to satisfy serve()'s is_file()/.exe check;
        # the "queue" subprocess call is never exercised by the assertions below.
        server = threading.Thread(target=codex_pipe.serve, args=(self.thread_id, sys.executable, self.test_pipe), daemon=True)
        server.start()
        for _ in range(50):
            try:
                if codex_pipe.request({'op': 'status'}, pipe=self.test_pipe)['status'] == 'listening':
                    break
            except OSError:
                time.sleep(0.1)
        else:
            self.fail('receiver never reported listening')

    def tearDown(self):
        codex_pipe.PIPE = self.orig_pipe

    def test_dropped_connect_does_not_kill_the_receiver(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        GENERIC_READ, GENERIC_WRITE, OPEN_EXISTING = 0x80000000, 0x40000000, 3
        handle = kernel.CreateFileW(self.test_pipe, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
        self.assertNotEqual(handle, -1, 'could not open the pipe to simulate a dropped client')
        kernel.CloseHandle(handle)  # connect, then vanish with no data -- never send/receive
        time.sleep(0.3)

        result = codex_pipe.request({'op': 'status'}, pipe=self.test_pipe)
        self.assertEqual(result['status'], 'listening')
        self.assertEqual(result['thread'], self.thread_id)


if __name__ == '__main__':
    unittest.main()
