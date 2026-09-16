import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import codex_roundtrip_audit as audit  # noqa: E402


MARKER = "TEST-ROUNDTRIP-7Q2"
THREAD = "00000000-0000-4000-8000-000000000001"


def seed_native_queue(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    archive = tmp_path / "archive"
    archive.mkdir()
    rows = [
        {"source": "SYSTEM_SDK", "type": "EPHEMERAL_MESSAGE", "content": MARKER},
        {"source": "MODEL", "type": "PLANNER_RESPONSE", "tool_calls": [{
            "name": "run_command", "args": {"CommandLine":
                f"NOUGEN_CODEX_THREAD={THREAD} codex_pipe.deliver('{MARKER}')"}}]},
        {"source": "MODEL", "type": "GENERIC", "content":
            f'{{"queue_accepted": true, "thread": "{THREAD}", "delivery_verified": false}}'},
    ]
    transcript.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    (archive / "ping_test.json").write_text(json.dumps({
        "source": "phoebus/antigravity", "target": "codex", "text": MARKER}), encoding="utf-8")
    return transcript, archive


def test_end_to_end_requires_receiver_envelope(tmp_path):
    transcript, archive = seed_native_queue(tmp_path)
    queued = audit.audit_roundtrip(MARKER, THREAD, transcript, archive)
    assert queued["status"] == "queued_waiting_for_active_codex_receipt"
    assert not queued["active_codex_receipt"]

    receiver = tmp_path / "receiver.json"
    receiver.write_text(json.dumps({
        "sender": "phoebus/antigravity", "target": "codex",
        "thread_id": THREAD, "correlation_marker": MARKER}), encoding="utf-8")
    complete = audit.audit_roundtrip(MARKER, THREAD, transcript, archive, receiver)
    assert complete["status"] == "end_to_end_confirmed"


def test_handwritten_ack_does_not_prove_native_queue(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    archive = tmp_path / "archive"
    archive.mkdir()
    transcript.write_text(json.dumps({"source": "MODEL", "type": "GENERIC",
                                      "content": f"ACK {MARKER}"}), encoding="utf-8")
    (archive / "ack.json").write_text(json.dumps({
        "sender": "phoebus/antigravity", "target": "codex", "text": MARKER}), encoding="utf-8")
    result = audit.audit_roundtrip(MARKER, THREAD, transcript, archive)
    assert result["status"] == "incomplete"
    assert not result["queue_accepted"]


def test_wrong_thread_receipt_is_not_accepted(tmp_path):
    transcript, archive = seed_native_queue(tmp_path)
    transcript.write_text(transcript.read_text(encoding="utf-8").replace(
        THREAD, "wrong-thread"), encoding="utf-8")
    result = audit.audit_roundtrip(MARKER, THREAD, transcript, archive)
    assert not result["native_adapter_invoked"]
    assert not result["queue_accepted"]


def test_malformed_transcript_is_incomplete(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    archive = tmp_path / "archive"
    archive.mkdir()
    transcript.write_text("not-json\n{}\n", encoding="utf-8")
    result = audit.audit_roundtrip(MARKER, THREAD, transcript, archive)
    assert result["status"] == "incomplete"


def test_receiver_envelope_must_match_target_thread_and_marker(tmp_path):
    transcript, archive = seed_native_queue(tmp_path)
    receiver = tmp_path / "receiver.json"
    receiver.write_text(json.dumps({
        "sender": "phoebus/antigravity", "target": "codex",
        "thread_id": "wrong-thread", "correlation_marker": MARKER}), encoding="utf-8")
    result = audit.audit_roundtrip(MARKER, THREAD, transcript, archive, receiver)
    assert not result["active_codex_receipt"]
