import ctypes
import hashlib
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
                                         inbox=self.temp.name)
        self.assertTrue(receipt["acknowledged"])
        self.assertFalse(Path(path).exists())
        self.assertTrue(Path(receipt["file"]).exists())
        self.assertTrue(Path(other).exists())
        again = codex_pipe.acknowledge(message_id, consumer="codex", thread="thread-1",
                                       inbox=self.temp.name)
        self.assertTrue(again["idempotent"])

    def test_ack_rejects_wrong_thread_without_moving_message(self):
        message_id = "33333333-3333-4333-8333-333333333333"
        path = codex_pipe.save({"message_id": message_id, "thread": "right", "text": "one"})
        receipt = codex_pipe.acknowledge(message_id, consumer="codex", thread="wrong",
                                         inbox=self.temp.name)
        self.assertEqual(receipt["status"], "thread_mismatch")
        self.assertTrue(Path(path).exists())

    def _stage(self, message_id, **extra):
        codex_pipe.save({"message_id": message_id, "thread": "t", "text": "do the thing", **extra})

    def _evidence(self, message_id, kind, **extra):
        record = codex_pipe.lifecycle(message_id, self.temp.name)
        evidence = {
            "kind": kind,
            "message_id": message_id,
            "execution_receipt": {
                "execution_id": "run-1", "worker": "codex",
                "started_at": "2026-10-01T09:00:00+00:00",
                "finished_at": "2026-10-01T09:01:00+00:00",
            },
            "context_binding": record["context_binding"],
        }
        evidence.update(extra)
        return evidence

    def test_ack_of_actionable_message_stays_pending_execution(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000001"
        self._stage(mid)
        codex_pipe.acknowledge(mid, consumer="codex", thread="t", inbox=self.temp.name)
        record = codex_pipe.lifecycle(mid, self.temp.name)
        self.assertEqual(record["state"], "ACKED")
        self.assertTrue(record["pending_execution"])
        self.assertNotIn("context_binding", record)
        self.assertEqual([p["message_id"] for p in codex_pipe.pending_execution(self.temp.name)], [mid])

    def test_informational_message_ends_at_acked(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000002"
        self._stage(mid, origin={"kind": "status"})
        codex_pipe.acknowledge(mid, consumer="codex", thread="t", inbox=self.temp.name)
        self.assertFalse(codex_pipe.lifecycle(mid, self.temp.name)["pending_execution"])
        self.assertEqual(codex_pipe.pending_execution(self.temp.name), [])

    def test_take_acks_and_claims_atomically_and_is_idempotent(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000003"
        self._stage(mid)
        first = codex_pipe.take(mid, consumer="codex", thread="t", inbox=self.temp.name)
        self.assertEqual(first["lifecycle_state"], "CLAIMED")
        self.assertTrue(first["pending_execution"])
        self.assertIn("context_binding", codex_pipe.lifecycle(mid, self.temp.name))
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
        unverified = codex_pipe.advance(mid, "COMPLETE", "PR merged: abc123", inbox=self.temp.name)
        self.assertEqual(unverified["status"], "evidence_invalid")
        self.assertEqual(codex_pipe.lifecycle(mid, self.temp.name)["state"], "EXECUTING")
        repo = Path(__file__).resolve().parents[1]
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        proof = self._evidence(mid, "complete", poe={
            "git": {"commit_sha": commit, "files_changed": ["src/nougen_shards/codex_pipe.py"],
                    "repo_path": str(repo)},
            "test_evidence": {"runner": "pytest tests/test_codex_pipe.py", "exit_code": 0,
                              "stdout_hash": "a" * 64},
            "verifier": {"observer_node": "chatgpt-app"},
        })
        done = codex_pipe.advance(mid, "COMPLETE", proof, inbox=self.temp.name)
        self.assertTrue(done["advanced"])
        self.assertFalse(done["pending_execution"])
        self.assertTrue(done["evidence_verified"])
        self.assertTrue(codex_pipe.lifecycle(mid, self.temp.name)["history"][-1]["verifier_result"]["verified"])
        self.assertEqual(codex_pipe.pending_execution(self.temp.name), [])
        after = codex_pipe.advance(mid, "EXECUTING", inbox=self.temp.name)
        self.assertEqual(after["status"], "illegal_transition")

    def test_checkpoint_recomputes_artifact_digest_and_preserves_pending_work(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000006"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t", inbox=self.temp.name)
        codex_pipe.advance(mid, "EXECUTING", inbox=self.temp.name)
        artifact = Path(self.temp.name) / "checkpoint.txt"
        artifact.write_text("checkpoint contents", encoding="utf-8")
        proof = self._evidence(mid, "checkpoint", artifacts=[{
            "path": "checkpoint.txt",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }])
        with patch.dict(os.environ, NOUGEN_CODEX_WORKSPACE=self.temp.name):
            result = codex_pipe.advance(mid, "CHECKPOINTED", proof, inbox=self.temp.name)
            self.assertTrue(result["advanced"])
            self.assertTrue(result["evidence_verified"])
            self.assertTrue(result["pending_execution"])
            codex_pipe.advance(mid, "EXECUTING", inbox=self.temp.name)
            proof["artifacts"][0]["sha256"] = "0" * 64
            rejected = codex_pipe.advance(mid, "CHECKPOINTED", proof, inbox=self.temp.name)
        self.assertEqual(rejected["status"], "evidence_invalid")
        self.assertEqual(codex_pipe.lifecycle(mid, self.temp.name)["state"], "EXECUTING")

    def test_proof_must_match_acknowledged_context_and_worker(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000007"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t", inbox=self.temp.name)
        codex_pipe.advance(mid, "EXECUTING", inbox=self.temp.name)
        repo = Path(__file__).resolve().parents[1]
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        proof = self._evidence(mid, "complete", poe={
            "git": {"commit_sha": commit, "files_changed": ["src/nougen_shards/codex_pipe.py"],
                    "repo_path": str(repo)},
            "test_evidence": {"runner": "pytest", "exit_code": 0, "stdout_hash": "b" * 64},
            "verifier": {"observer_node": "chatgpt-app"},
        })
        proof["context_binding"]["workflow_version"] = "changed-version"
        rejected_context = codex_pipe.advance(mid, "COMPLETE", proof, inbox=self.temp.name)
        self.assertEqual(rejected_context["status"], "evidence_invalid")
        proof = self._evidence(mid, "complete", poe={
            "git": {"commit_sha": commit, "files_changed": ["src/nougen_shards/codex_pipe.py"],
                    "repo_path": str(repo)},
            "test_evidence": {"runner": "pytest", "exit_code": 0, "stdout_hash": "b" * 64},
            "verifier": {"observer_node": "chatgpt-app"},
        })
        proof["execution_receipt"]["worker"] = "other-agent"
        rejected_worker = codex_pipe.advance(mid, "COMPLETE", proof, inbox=self.temp.name)
        self.assertEqual(rejected_worker["status"], "evidence_invalid")
        self.assertEqual(codex_pipe.lifecycle(mid, self.temp.name)["state"], "EXECUTING")

    def test_context_configuration_drift_requires_replanning(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000008"
        with patch.dict(os.environ, NOUGEN_POLICY_SHA256="policy-a"):
            self._stage(mid)
            codex_pipe.take(mid, consumer="codex", thread="t", inbox=self.temp.name)
            codex_pipe.advance(mid, "EXECUTING", inbox=self.temp.name)
            proof = self._evidence(mid, "checkpoint", artifacts=[])
        with patch.dict(os.environ, NOUGEN_POLICY_SHA256="policy-b"):
            result = codex_pipe.advance(mid, "CHECKPOINTED", proof, inbox=self.temp.name)
        self.assertEqual(result["status"], "evidence_invalid")
        self.assertIn("execution context changed after claim", result["verifier_result"]["errors"][0])
        self.assertEqual(codex_pipe.lifecycle(mid, self.temp.name)["state"], "EXECUTING")

    def test_advance_unknown_message_and_state(self):
        self.assertEqual(codex_pipe.advance("nope", "CLAIMED", inbox=self.temp.name)["status"], "no_lifecycle")
        mid = "aaaaaaaa-0000-4000-8000-000000000005"
        self._stage(mid)
        codex_pipe.acknowledge(mid, consumer="codex", thread="t", inbox=self.temp.name)
        self.assertEqual(codex_pipe.advance(mid, "DONE", "x", inbox=self.temp.name)["status"], "unknown_state")


@unittest.skipUnless(sys.platform == 'win32', 'named pipe is Windows-only')
class CodexPipeServeSurvivesBadConnectsTests(unittest.TestCase):
    """Regression for the WinError 2 fleet bug: a client that drops mid-connect must not
    take the whole receiver down with it (see relay leg 20260915T033332Z)."""

    def setUp(self):
        self.thread_id = '00000000-0000-4000-8000-000000000000'
        # sys.executable (python.exe) only needs to satisfy serve()'s is_file()/.exe check;
        # the "queue" subprocess call is never exercised by the assertions below.
        server = threading.Thread(target=codex_pipe.serve, args=(self.thread_id, sys.executable), daemon=True)
        server.start()
        for _ in range(50):
            try:
                if codex_pipe.request({'op': 'status'})['status'] == 'listening':
                    break
            except OSError:
                time.sleep(0.1)
        else:
            self.fail('receiver never reported listening')

    def test_dropped_connect_does_not_kill_the_receiver(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        GENERIC_READ, GENERIC_WRITE, OPEN_EXISTING = 0x80000000, 0x40000000, 3
        handle = kernel.CreateFileW(codex_pipe.PIPE, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
        self.assertNotEqual(handle, -1, 'could not open the pipe to simulate a dropped client')
        kernel.CloseHandle(handle)  # connect, then vanish with no data -- never send/receive
        time.sleep(0.3)

        result = codex_pipe.request({'op': 'status'})
        self.assertEqual(result['status'], 'listening')
        self.assertEqual(result['thread'], self.thread_id)


if __name__ == '__main__':
    unittest.main()
