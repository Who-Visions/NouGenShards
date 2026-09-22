"""Audit observable stages of a Codex <-> Antigravity message round trip.

This is a read-only evidence checker. It never sends a message, edits a shard,
or starts a daemon.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def _contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(_contains(key, needle) or _contains(item, needle)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


def _transcript_evidence(path: Path, marker: str, thread: str) -> tuple[bool, bool, bool]:
    model_consumed = False
    adapter_invoked = False
    queue_receipt = False

    for row in _read_jsonl(path):
        source, kind = row.get("source"), row.get("type")
        if source == "MODEL" and kind in {"PLANNER_RESPONSE", "GENERIC"}:
            if (_contains(row.get("content"), marker)
                    or _contains(row.get("tool_calls"), marker)):
                model_consumed = True

        calls = row.get("tool_calls", [])
        for call in calls if isinstance(calls, list) else []:
            if not isinstance(call, dict):
                continue
            args = call.get("args", {})
            command = args.get("CommandLine", "") if isinstance(args, dict) else ""
            if ("codex_pipe" in command and "deliver" in command
                    and marker in command and thread in command):
                adapter_invoked = True

        content = row.get("content", "")
        if source == "MODEL" and kind == "GENERIC" and isinstance(content, str):
            accepted = bool(re.search(r'"queue_accepted"\s*:\s*true', content))
            addressed = bool(re.search(r'"thread"\s*:\s*"' + re.escape(thread) + r'"', content))
            if accepted and addressed:
                queue_receipt = True

    return model_consumed, adapter_invoked, queue_receipt


def _archived_payload(archive_dir: Path, marker: str, thread: str) -> bool:
    try:
        for path in archive_dir.glob("ping_*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            addressed_threads = (
                payload.get("thread_id"),
                payload.get("target_session_id"),
                payload.get("thread"),
            )
            if (payload.get("target") == "codex"
                    and any(isinstance(value, str) and value == thread
                            for value in addressed_threads)
                    and _contains(payload, marker)):
                return True
    except OSError:
        pass
    return False


def _receiver_envelope(path: Path | None, marker: str, thread: str) -> bool:
    if path is None:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return False
    addressed_thread = payload.get("thread_id") or payload.get("target_session_id")
    source = payload.get("sender") or payload.get("source")
    marker_present = any(_contains(payload.get(key), marker)
                         for key in ("text", "message", "content", "correlation_marker"))
    return (addressed_thread == thread and source == "phoebus/antigravity"
            and payload.get("target") == "codex" and marker_present)


def audit_roundtrip(marker: str, thread: str, transcript: Path,
                    archive_dir: Path, receiver_envelope: Path | None = None) -> dict[str, Any]:
    consumed, invoked, accepted = _transcript_evidence(transcript, marker, thread)
    archived = _archived_payload(archive_dir, marker, thread)
    received = _receiver_envelope(receiver_envelope, marker, thread)
    queued = consumed and invoked and accepted and archived

    if queued and received:
        status = "end_to_end_confirmed"
    elif queued:
        status = "queued_waiting_for_active_codex_receipt"
    else:
        status = "incomplete"
    return {
        "marker": marker,
        "thread": thread,
        "status": status,
        "antigravity_model_consumed": consumed,
        "native_adapter_invoked": invoked,
        "queue_accepted": accepted,
        "archived_codex_payload": archived,
        "active_codex_receipt": received,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--agy-transcript", type=Path, required=True)
    parser.add_argument("--codex-archive", type=Path,
                        default=Path.home() / ".codex/inbox/archive")
    parser.add_argument("--codex-received", type=Path,
                        help="Correlated receiver envelope from the active Codex thread, if exported")
    args = parser.parse_args()

    result = audit_roundtrip(args.marker, args.thread, args.agy_transcript,
                             args.codex_archive, args.codex_received)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "end_to_end_confirmed" else 2


if __name__ == "__main__":
    sys.exit(main())
