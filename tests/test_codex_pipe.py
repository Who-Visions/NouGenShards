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
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nougen_shards import codex_pipe


class CodexPipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, NOUGEN_CODEX_INBOX=self.temp.name, NOUGEN_HOME=self.temp.name)
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
            result = AgentPinger.ping_codex('offline')
            self.assertIn('codex_limits', result)
            result.pop('codex_limits')
            self.assertEqual(result, receipt)
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
        self.assertTrue(receipt["receipt_only"])
        self.assertNotIn("work", receipt)
        self.assertNotIn("sha", receipt)
        self.assertFalse(Path(path).exists())
        self.assertTrue(Path(receipt["file"]).exists())
        self.assertTrue(Path(other).exists())
        again = codex_pipe.acknowledge(message_id, consumer="codex", thread="thread-1",
                                       inbox=self.temp.name)
        self.assertTrue(again["idempotent"])

    def test_ack_is_receipt_only_and_leaves_actionable_work_pending(self):
        message_id = "44444444-4444-4444-8444-444444444444"
        path = codex_pipe.save({"message_id": message_id, "thread": "thread-1", "text": "test"})
        receipt = codex_pipe.acknowledge(message_id, consumer="codex", thread="thread-1",
                                         inbox=self.temp.name)
        self.assertTrue(receipt["acknowledged"])
        self.assertFalse(Path(path).exists())
        self.assertNotIn("work", receipt)
        self.assertEqual(codex_pipe.lifecycle(message_id, self.temp.name)["state"], "ACKED")
        self.assertTrue(codex_pipe.lifecycle(message_id, self.temp.name)["pending_execution"])

    def test_multi_inbox_claim_and_ack_are_receipt_only(self):
        agy_inbox = Path(self.temp.name) / ".nougen" / "agy_inbox"
        agy_inbox.mkdir(parents=True)
        msg_id = "66666666-6666-4666-8666-666666666666"
        ping_file = agy_inbox / f"ping_{uuid.uuid4().hex}.json"
        ping_file.write_text(json.dumps({"message_id": msg_id, "text": "agy ping", "source": "fleet"}), encoding="utf-8")

        claimed = codex_pipe.claim(msg_id, consumer="antigravity", inbox=str(agy_inbox))
        self.assertTrue(claimed["claimed"])
        acked = codex_pipe.acknowledge(msg_id, consumer="antigravity", inbox=str(agy_inbox))
        self.assertTrue(acked["acknowledged"])
        self.assertNotIn("work", acked)
        self.assertTrue((agy_inbox / "archive" / ping_file.name).exists())
        self.assertTrue((agy_inbox / "archive" / f"{ping_file.name}.ack.json").exists())
        state = codex_pipe.lifecycle(msg_id, str(agy_inbox))
        self.assertEqual(state["state"], "ACKED")
        self.assertTrue(state["pending_execution"])
        with patch.object(Path, "home", return_value=Path(self.temp.name)):
            self.assertIn(msg_id, [item["message_id"] for item in codex_pipe.pending_execution()])

    def test_expired_take_is_reclaimed_and_old_epoch_cannot_advance(self):
        mid = "99999999-9999-4999-8999-999999999999"
        codex_pipe.save({"message_id": mid, "thread": "old-worker", "text": "do the thing"})
        with patch.dict(os.environ, NOUGEN_LIVE_LEASE_SECONDS="1"):
            first = codex_pipe.take(mid, consumer="codex", thread="old-worker")
            time.sleep(1.05)
            second = codex_pipe.take(mid, consumer="codex", thread="new-worker")
        self.assertGreater(second["fencing_epoch"], first["fencing_epoch"])
        stale = codex_pipe.advance(mid, "EXECUTING", consumer="codex",
                                   fencing_epoch=first["fencing_epoch"], inbox=self.temp.name)
        self.assertEqual(stale["status"], "fencing_token_required")
        current = codex_pipe.advance(mid, "EXECUTING", consumer="codex",
                                     fencing_epoch=second["fencing_epoch"], inbox=self.temp.name)
        self.assertTrue(current["advanced"])

    def test_live_ack_command_is_passive_and_rejects_work_summaries(self):
        from nougen_shards.live import handle_live_command

        mid = "77777777-7777-4777-8777-777777777777"
        self._stage(mid)
        receipt = json.loads(handle_live_command(["ack-msg", mid]))
        self.assertTrue(receipt["acknowledged"])
        self.assertNotIn("work", receipt)
        self.assertTrue(codex_pipe.lifecycle(mid, self.temp.name)["pending_execution"])

        second = "88888888-8888-4888-8888-888888888888"
        path = codex_pipe.save({"message_id": second, "text": "do another thing"})
        rejected = json.loads(handle_live_command(["ack-msg", second, "--work", "done"]))
        self.assertEqual(rejected["status"], "invalid_args")
        self.assertTrue(Path(path).exists())

    def test_claim_message_marks_in_progress(self):
        message_id = "55555555-5555-4555-8555-555555555555"
        path = codex_pipe.save({"message_id": message_id, "thread": "thread-1", "text": "to claim"})
        claimed = codex_pipe.claim(message_id, consumer="codex", thread="thread-1")
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
                                         inbox=self.temp.name)
        self.assertEqual(receipt["status"], "thread_mismatch")
        self.assertTrue(Path(path).exists())

    def _stage(self, message_id, **extra):
        codex_pipe.save({"message_id": message_id, "thread": "t", "text": "do the thing", **extra})

    def _advance(self, message_id, state, evidence="", **kwargs):
        record = codex_pipe.lifecycle(message_id, self.temp.name)
        epoch = record.get("fencing_epoch") if record else None
        return codex_pipe.advance(message_id, state, evidence, consumer="codex",
                                  fencing_epoch=epoch, inbox=self.temp.name, **kwargs)

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
        codex_pipe.acknowledge(mid, consumer="codex", thread="t")
        record = codex_pipe.lifecycle(mid, self.temp.name)
        self.assertEqual(record["state"], "ACKED")
        self.assertTrue(record["pending_execution"])
        self.assertNotIn("context_binding", record)
        self.assertEqual([p["message_id"] for p in codex_pipe.pending_execution(self.temp.name)], [mid])

    def test_informational_message_ends_at_acked(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000002"
        self._stage(mid, origin={"kind": "status"})
        codex_pipe.acknowledge(mid, consumer="codex", thread="t")
        self.assertFalse(codex_pipe.lifecycle(mid, self.temp.name)["pending_execution"])
        self.assertEqual(codex_pipe.pending_execution(self.temp.name), [])

    def test_take_acks_and_claims_atomically_and_is_idempotent(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000003"
        self._stage(mid)
        first = codex_pipe.take(mid, consumer="codex", thread="t")
        no_token = codex_pipe.advance(mid, "EXECUTING", consumer="codex")
        self.assertEqual(no_token["status"], "fencing_token_required")
        self.assertEqual(first["lifecycle_state"], "CLAIMED")
        self.assertTrue(first["pending_execution"])
        self.assertIn("context_binding", codex_pipe.lifecycle(mid, self.temp.name))
        again = codex_pipe.take(mid, consumer="codex", thread="t")
        self.assertEqual(again["lifecycle_state"], "CLAIMED")
        self.assertEqual(len(codex_pipe.lifecycle(mid, self.temp.name)["history"]), 2)

    def test_complete_requires_evidence_and_legal_order(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000004"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t")
        skip = self._advance(mid, "COMPLETE", "proof")
        self.assertEqual(skip["status"], "illegal_transition")
        self.assertTrue(self._advance(mid, "EXECUTING")["advanced"])
        bare = self._advance(mid, "COMPLETE", "  ")
        self.assertEqual(bare["status"], "evidence_required")
        self.assertTrue(codex_pipe.pending_execution(self.temp.name))
        unverified = self._advance(mid, "COMPLETE", "PR merged: abc123")
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
        done = self._advance(mid, "COMPLETE", proof)
        self.assertTrue(done["advanced"], done)
        self.assertFalse(done["pending_execution"])
        self.assertTrue(done["evidence_verified"])
        self.assertTrue(codex_pipe.lifecycle(mid, self.temp.name)["history"][-1]["verifier_result"]["verified"])
        self.assertEqual(codex_pipe.pending_execution(self.temp.name), [])
        after = self._advance(mid, "EXECUTING")
        self.assertEqual(after["status"], "illegal_transition")

    def _valid_complete_proof(self, mid):
        repo = Path(__file__).resolve().parents[1]
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        return self._evidence(mid, "complete", poe={
            "git": {"commit_sha": commit, "files_changed": ["src/nougen_shards/codex_pipe.py"],
                    "repo_path": str(repo)},
            "test_evidence": {"runner": "pytest tests/test_codex_pipe.py", "exit_code": 0,
                              "stdout_hash": "a" * 64},
            "verifier": {"observer_node": "chatgpt-app"},
        })

    def test_complete_resumes_after_a_crash_between_commit_and_complete(self):
        """verify + commit succeeded, complete() died: the retry must finish, not stick.

        The manager now refuses to move a COMMITTING claim back to VERIFYING, so
        advance() has to resume at complete() with the same idempotency key.
        """
        from nougen_shards.claim_lifecycle import ClaimLifecycleManager
        mid = "aaaaaaaa-0000-4000-8000-0000000000a1"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t")
        self.assertTrue(self._advance(mid, "EXECUTING")["advanced"])
        proof = self._valid_complete_proof(mid)
        real_complete = ClaimLifecycleManager.complete
        calls = {"n": 0}

        def crash_once(self_, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("simulated crash after commit_step")
            return real_complete(self_, *a, **k)

        with patch.object(ClaimLifecycleManager, "complete", crash_once):
            first = self._advance(mid, "COMPLETE", proof)
            self.assertFalse(first["advanced"])
            claim = ClaimLifecycleManager().get_claim(mid)
            self.assertEqual(claim["state"], "COMMITTING")        # committed, not completed
            retry = self._advance(mid, "COMPLETE", proof)
        self.assertTrue(retry["advanced"], retry)
        self.assertEqual(ClaimLifecycleManager().get_claim(mid)["state"], "COMPLETE")
        self.assertEqual(codex_pipe.pending_execution(self.temp.name), [])

    def test_a_different_completion_cannot_hijack_a_committing_claim(self):
        from nougen_shards.claim_lifecycle import ClaimLifecycleManager
        mid = "aaaaaaaa-0000-4000-8000-0000000000a2"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t")
        self.assertTrue(self._advance(mid, "EXECUTING")["advanced"])
        proof = self._valid_complete_proof(mid)
        with patch.object(ClaimLifecycleManager, "complete", side_effect=ValueError("crash")):
            self._advance(mid, "COMPLETE", proof)
        other = dict(proof)
        other["execution_receipt"] = dict(proof["execution_receipt"], execution_id="run-2")
        result = self._advance(mid, "COMPLETE", other)
        self.assertFalse(result["advanced"])
        self.assertEqual(ClaimLifecycleManager().get_claim(mid)["state"], "COMMITTING")

    def test_checkpoint_recomputes_artifact_digest_and_preserves_pending_work(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000006"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t")
        self._advance(mid, "EXECUTING")
        artifact = Path(self.temp.name) / "checkpoint.txt"
        artifact.write_text("checkpoint contents", encoding="utf-8")
        proof = self._evidence(mid, "checkpoint", artifacts=[{
            "path": "checkpoint.txt",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }])
        with patch.dict(os.environ, NOUGEN_CODEX_WORKSPACE=self.temp.name):
            result = self._advance(mid, "CHECKPOINTED", proof)
            self.assertTrue(result["advanced"], result)
            self.assertTrue(result["evidence_verified"])
            self.assertTrue(result["pending_execution"])
            self._advance(mid, "EXECUTING")
            proof["artifacts"][0]["sha256"] = "0" * 64
            rejected = self._advance(mid, "CHECKPOINTED", proof)
        self.assertEqual(rejected["status"], "evidence_invalid")
        self.assertEqual(codex_pipe.lifecycle(mid, self.temp.name)["state"], "EXECUTING")

    def test_proof_must_match_acknowledged_context_and_worker(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000007"
        self._stage(mid)
        codex_pipe.take(mid, consumer="codex", thread="t")
        self._advance(mid, "EXECUTING")
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
        rejected_context = self._advance(mid, "COMPLETE", proof)
        self.assertEqual(rejected_context["status"], "evidence_invalid")
        proof = self._evidence(mid, "complete", poe={
            "git": {"commit_sha": commit, "files_changed": ["src/nougen_shards/codex_pipe.py"],
                    "repo_path": str(repo)},
            "test_evidence": {"runner": "pytest", "exit_code": 0, "stdout_hash": "b" * 64},
            "verifier": {"observer_node": "chatgpt-app"},
        })
        proof["execution_receipt"]["worker"] = "other-agent"
        rejected_worker = self._advance(mid, "COMPLETE", proof)
        self.assertEqual(rejected_worker["status"], "evidence_invalid")
        self.assertEqual(codex_pipe.lifecycle(mid, self.temp.name)["state"], "EXECUTING")

    def test_context_configuration_drift_requires_replanning(self):
        mid = "aaaaaaaa-0000-4000-8000-000000000008"
        with patch.dict(os.environ, NOUGEN_POLICY_SHA256="policy-a"):
            self._stage(mid)
            codex_pipe.take(mid, consumer="codex", thread="t")
            self._advance(mid, "EXECUTING")
            proof = self._evidence(mid, "checkpoint", artifacts=[])
        with patch.dict(os.environ, NOUGEN_POLICY_SHA256="policy-b"):
            result = self._advance(mid, "CHECKPOINTED", proof)
        self.assertEqual(result["status"], "evidence_invalid")
        self.assertIn("execution context changed after claim", result["verifier_result"]["errors"][0])
        self.assertEqual(codex_pipe.lifecycle(mid, self.temp.name)["state"], "EXECUTING")

    def test_advance_unknown_message_and_state(self):
        self.assertEqual(self._advance("nope", "CLAIMED")["status"], "no_lifecycle")
        mid = "aaaaaaaa-0000-4000-8000-000000000005"
        self._stage(mid)
        codex_pipe.acknowledge(mid, consumer="codex", thread="t")
        self.assertEqual(self._advance(mid, "DONE", "x")["status"], "unknown_state")


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
