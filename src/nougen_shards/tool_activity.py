"""Bounded session tool activity tracking and telemetry projection.

Part of NouGen information dynamics and context-bloat mitigation.
Tracks, bounds, redacts, and projects tool execution activity across agent sessions
without leaking sensitive secrets or blowing primary context tokens.
Provides both file-backed stream logging (ActivitySink) and in-memory bounded HUD projections.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --- File-backed ActivitySink (bounded, disk-capped stream) ---

class ActivitySink:
    """One session stream, with explicit loss accounting and a disk ceiling.

    Arbitrary argument/result text is never persisted: only shape and size.
    The writer stops appending at the ceiling; callers can inspect status().
    """

    def __init__(self, directory, session_id=None, capacity=256, max_bytes=1048576):
        session_id = session_id or uuid.uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session_id):
            raise ValueError("invalid activity session identifier")
        if capacity < 1 or max_bytes < 1:
            raise ValueError("activity limits must be positive")
        self.session_id = session_id
        self.path = Path(directory) / (session_id + ".jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("xb"):
            pass
        self.max_bytes = max_bytes
        self.dropped = 0
        self.errors = 0
        self.sequence = 0
        self.lock = threading.Lock()
        self.pending = queue.Queue(capacity)
        self.closed = threading.Event()
        self.worker = threading.Thread(target=self._write, daemon=True)
        self.worker.start()

    def status(self):
        with self.lock:
            return {"dropped_event_count": self.dropped, "writer_errors": self.errors}

    def emit(self, phase, tool_name, invocation_id="", **fields):
        with self.lock:
            self.sequence += 1
            event = dict(schema_version=1, event_id=uuid.uuid4().hex,
                         session_id=self.session_id, invocation_id=invocation_id,
                         sequence=self.sequence,
                         timestamp=datetime.now(timezone.utc).isoformat(),
                         phase=phase, tool_name=tool_name[:128],
                         dropped_event_count=self.dropped, **fields)
            try:
                self.pending.put_nowait(json.dumps(event).encode("utf-8") + b"\n")
            except queue.Full:
                self.dropped += 1

    def _write(self):
        while not self.closed.is_set() or not self.pending.empty():
            try:
                line = self.pending.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if self.path.is_symlink():
                    raise OSError("activity stream cannot be a symlink")
                with self.path.open("ab") as stream:
                    if stream.tell() + len(line) > self.max_bytes:
                        with self.lock:
                            self.dropped += 1
                    else:
                        stream.write(line)
            except Exception:
                with self.lock:
                    self.errors += 1
                    self.dropped += 1
            finally:
                self.pending.task_done()

    def flush(self):
        """Wait for already queued writes; intended for tests and shutdown."""
        self.pending.join()

    def close(self):
        """Drain in the background without delaying the tool's return."""
        self.closed.set()


def configured_sink():
    """Opt in with NOUGEN_TOOL_ACTIVITY_DIR; no background writer otherwise."""
    directory = os.environ.get("NOUGEN_TOOL_ACTIVITY_DIR")
    return ActivitySink(directory) if directory else None


def observe(sink, phase, name, invocation_id="", **fields):
    """An observer cannot change tool execution, including custom observers."""
    if sink is not None:
        try:
            sink.emit(phase, name, invocation_id, **fields)
        except Exception:
            pass


# --- In-Memory Bounded Session Tracker & Secret Redaction ---

DEFAULT_MAX_ACTIVITY_RECORDS = 50
DEFAULT_MAX_ARG_CHARS = 500
DEFAULT_MAX_RESULT_CHARS = 1000

SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z\-_]{30,50})"),
    re.compile(r"(ghp_[0-9A-Za-z]{36,})"),
    re.compile(r"(sk-[0-9A-Za-z]{20,})"),
    re.compile(r"(bearer\s+[A-Za-z0-9_\-\.]+)", re.IGNORECASE),
    re.compile(r"(['\"]?(?:api[_-]?key|token|secret|password)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Scrub known secret and token patterns from tool args or result payloads."""
    if not isinstance(text, str):
        return text

    scrubbed = text
    scrubbed = SECRET_PATTERNS[0].sub("[REDACTED_GOOGLE_KEY]", scrubbed)
    scrubbed = SECRET_PATTERNS[1].sub("[REDACTED_GH_TOKEN]", scrubbed)
    scrubbed = SECRET_PATTERNS[2].sub("[REDACTED_API_KEY]", scrubbed)
    scrubbed = SECRET_PATTERNS[3].sub("Bearer [REDACTED_TOKEN]", scrubbed)

    def _kv_repl(m: re.Match) -> str:
        return f"{m.group(1)}[REDACTED]{m.group(3)}"

    scrubbed = SECRET_PATTERNS[4].sub(_kv_repl, scrubbed)
    return scrubbed


@dataclass
class ToolActivityRecord:
    session_id: str
    tool_name: str
    arguments: Dict[str, Any]
    ok: bool
    result_size: int
    duration_ms: float
    timestamp: float = field(default_factory=time.time)
    digest: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if not self.digest:
            canon = f"{self.session_id}:{self.tool_name}:{json.dumps(self.arguments, sort_keys=True, default=str)}"
            self.digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


class SessionToolActivityTracker:
    """Thread-safe bounded recorder of tool invocations within a session."""

    def __init__(
        self,
        session_id: str,
        max_records: int = DEFAULT_MAX_ACTIVITY_RECORDS,
        max_arg_chars: int = DEFAULT_MAX_ARG_CHARS,
        max_result_chars: int = DEFAULT_MAX_RESULT_CHARS,
    ):
        self.session_id = session_id
        self.max_records = max_records
        self.max_arg_chars = max_arg_chars
        self.max_result_chars = max_result_chars
        self._records: List[ToolActivityRecord] = []
        self._counts: Dict[str, int] = {}

    def record_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        ok: bool,
        result_size: int,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> ToolActivityRecord:
        """Record a single tool call with bounding and secret redaction."""
        redacted_args: Dict[str, Any] = {}
        for k, v in arguments.items():
            s = json.dumps(v, default=str)
            s_clean = redact_secrets(s)
            if len(s_clean) > self.max_arg_chars:
                s_clean = s_clean[: self.max_arg_chars] + "...[truncated]"
            try:
                redacted_args[k] = json.loads(s_clean)
            except Exception:
                redacted_args[k] = s_clean

        rec = ToolActivityRecord(
            session_id=self.session_id,
            tool_name=tool_name,
            arguments=redacted_args,
            ok=ok,
            result_size=result_size,
            duration_ms=duration_ms,
            error=redact_secrets(error) if error else None,
        )

        self._records.append(rec)
        self._counts[tool_name] = self._counts.get(tool_name, 0) + 1

        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records :]

        return rec

    @property
    def total_calls(self) -> int:
        return sum(self._counts.values())

    @property
    def counts(self) -> Dict[str, int]:
        return dict(self._counts)

    def get_records(self, limit: Optional[int] = None) -> List[ToolActivityRecord]:
        if limit is None:
            return list(self._records)
        return self._records[-limit:]

    def summarize(self) -> Dict[str, Any]:
        """Compact summary HUD suitable for low-token context injection."""
        success_count = sum(1 for r in self._records if r.ok)
        failure_count = len(self._records) - success_count
        return {
            "session_id": self.session_id,
            "total_calls": self.total_calls,
            "recent_count": len(self._records),
            "success_count": success_count,
            "failure_count": failure_count,
            "tools_used": self._counts,
            "recent_tools": [r.tool_name for r in self._records[-5:]],
        }

    def project_bounded_context(self, max_tokens_approx: int = 500) -> str:
        """Render ultra-dense human-readable HUD string for context injection."""
        s = self.summarize()
        lines = [
            f"[TOOL_ACTIVITY | Session: {self.session_id}]",
            f"Total: {s['total_calls']} calls | OK: {s['success_count']} | Fail: {s['failure_count']}",
            f"Tool breakdown: {', '.join(f'{k}:{v}' for k, v in sorted(self._counts.items()))}",
        ]
        if self._records:
            lines.append("Recent executions:")
            for r in self._records[-3:]:
                status = "OK" if r.ok else f"ERR({r.error})"
                lines.append(f"  • {r.tool_name}(...) -> {status} [{r.result_size} bytes, {r.duration_ms:.1f}ms]")
        rendered = "\n".join(lines)
        max_chars = max_tokens_approx * 4
        if len(rendered) > max_chars:
            rendered = rendered[:max_chars] + "\n...[activity truncated]"
        return rendered
