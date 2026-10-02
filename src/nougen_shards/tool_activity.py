"""Bounded, optional tool telemetry. Activity never constitutes execution proof."""
import json
import os
import queue
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


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
