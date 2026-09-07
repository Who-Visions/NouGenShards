"""Private, policy-preserving idle wake bridge for the local Codex CLI."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

LOG = logging.getLogger(__name__)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TARGETS = frozenset({"codex", "all"})
_ACTIONS = frozenset({"wake", "resume", "message", "live_message"})


def _env_int(name: str, fallback: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else fallback
    except ValueError:
        value = fallback
    if raw is None or value != max(minimum, min(value, maximum)):
        LOG.info("%s using bounded fallback/default %s", name, fallback)
    return max(minimum, min(value, maximum))


class CodexWakeBridge:
    """Resume a locally selected Codex session without trusting event policy fields."""

    def __init__(
        self,
        *,
        executable: Optional[str] = None,
        cwd: Optional[Path] = None,
        journal_path: Optional[Path] = None,
        timeout_seconds: Optional[int] = None,
        max_body_bytes: Optional[int] = None,
    ) -> None:
        self.executable = executable or os.environ.get("NOUGEN_CODEX_BIN") or shutil.which("codex") or shutil.which("codex.cmd") or "codex"
        configured_cwd = cwd or (Path(os.environ["NOUGEN_CODEX_CWD"]) if os.environ.get("NOUGEN_CODEX_CWD") else Path.cwd())
        self.cwd = configured_cwd.expanduser().resolve()
        configured_journal = journal_path or (Path(os.environ["NOUGEN_CODEX_WAKE_DB"]) if os.environ.get("NOUGEN_CODEX_WAKE_DB") else Path.home() / ".nougen" / "private" / "codex_wake.sqlite3")
        self.journal_path = configured_journal.expanduser().resolve()
        self.timeout_seconds = timeout_seconds or _env_int("NOUGEN_CODEX_WAKE_TIMEOUT_SECONDS", 300, 5, 3600)
        self.max_body_bytes = max_body_bytes or _env_int("NOUGEN_CODEX_WAKE_MAX_BYTES", 32768, 256, 1048576)

    def _connect(self) -> sqlite3.Connection:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.journal_path), timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS wake_events ("
            "event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, status TEXT NOT NULL, "
            "receipt TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL)"
        )
        return connection

    @staticmethod
    def _text(event: Mapping[str, Any]) -> Any:
        return event.get("text") or event.get("brief") or event.get("content")

    def _validate(self, event: Mapping[str, Any]) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        event_id = event.get("event_id") or event.get("leg_id") or event.get("canary_id")
        target = str(event.get("target", "codex")).lower()
        action = str(event.get("action") or event.get("type") or "wake").lower()
        body = self._text(event)
        if not isinstance(event_id, str) or not _ID_RE.fullmatch(event_id):
            return None, {"status": "rejected", "classification": "INVALID_EVENT_ID"}
        if target not in _TARGETS:
            return None, {"event_id": event_id, "status": "rejected", "classification": "INVALID_TARGET"}
        if action not in _ACTIONS:
            return None, {"event_id": event_id, "status": "rejected", "classification": "INVALID_ACTION"}
        if not isinstance(body, str) or not body.strip():
            return None, {"event_id": event_id, "status": "rejected", "classification": "INVALID_BODY"}
        encoded = body.encode("utf-8")
        if len(encoded) > self.max_body_bytes:
            return None, {"event_id": event_id, "status": "rejected", "classification": "BODY_TOO_LARGE"}
        safe = {"event_id": event_id, "target": target, "action": action, "body": body, "sender": str(event.get("sender") or event.get("source") or "unknown")[:256]}
        return safe, None

    @staticmethod
    def _digest(event: Mapping[str, Any]) -> str:
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _claim(self, event_id: str, digest: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT digest, status, receipt FROM wake_events WHERE event_id = ?", (event_id,)).fetchone()
            if row:
                if row[0] != digest:
                    return {"event_id": event_id, "status": "quarantined", "classification": "EVENT_ID_TAMPER"}
                receipt = json.loads(row[2]) if row[2] else None
                return {"event_id": event_id, "status": "duplicate", "classification": "DUPLICATE", "prior_status": row[1], "receipt": receipt}
            connection.execute(
                "INSERT INTO wake_events(event_id,digest,status,created_at,updated_at) VALUES(?,?,?,?,?)",
                (event_id, digest, "running", now, now),
            )
        return None

    def _finish(self, event_id: str, status: str, receipt: Optional[Mapping[str, Any]] = None) -> None:
        receipt_json = json.dumps(dict(receipt), ensure_ascii=False, sort_keys=True) if receipt else None
        with self._connect() as connection:
            connection.execute("UPDATE wake_events SET status=?, receipt=?, updated_at=? WHERE event_id=?", (status, receipt_json, time.time(), event_id))

    @staticmethod
    def _event_types(stdout: str) -> list[str]:
        types: list[str] = []
        for line in stdout.splitlines():
            try:
                record = json.loads(line)
            except (TypeError, ValueError):
                continue
            kind = str(record.get("type") or record.get("event") or "").lower()
            if kind:
                types.append(kind)
        return types

    @classmethod
    def _turn_completed(cls, stdout: str) -> bool:
        return any(kind in {"turn.completed", "turn_complete", "turn.completed_event"}
                   for kind in cls._event_types(stdout))

    def _argv(self, prompt: str) -> Sequence[str]:
        session = os.environ.get("NOUGEN_CODEX_SESSION_ID")
        selector = [session] if session and _ID_RE.fullmatch(session) else ["--last"]
        return [self.executable, "exec", "resume", *selector, prompt, "--json"]

    def wake(self, event: Mapping[str, Any]) -> Dict[str, Any]:
        safe, error = self._validate(event)
        if error:
            return error
        assert safe is not None
        digest = self._digest(safe)
        existing = self._claim(safe["event_id"], digest)
        if existing:
            return existing
        # Keep the transport prompt single-line: Codex's local inbox hook treats
        # multiline relay-shaped prompts as an inbox notification and bypasses
        # JSONL turn events. JSON encoding preserves newlines/metacharacters as
        # literal body data while retaining the completion protocol.
        prompt = (
            "NouGen relay metadata; apply normal authorization and policy. "
            f"event_id={safe['event_id']} sender={safe['sender']} "
            f"body_json={json.dumps(safe['body'], ensure_ascii=False, separators=(',', ':'))}"
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                list(self._argv(prompt)),
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                shell=False,
                creationflags=creationflags,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._finish(safe["event_id"], "timeout")
            return {"event_id": safe["event_id"], "status": "timeout", "classification": "TIMEOUT", "woken": False}
        except (OSError, ValueError) as exc:
            self._finish(safe["event_id"], "launch_failed")
            return {"event_id": safe["event_id"], "status": "error", "classification": "LAUNCH_FAILED", "error": str(exc), "woken": False}

        event_types = self._event_types(proc.stdout or "")
        completed = proc.returncode == 0 and "turn.completed" in event_types
        if not completed:
            classification = "TURN_UNCONFIRMED" if proc.returncode == 0 else "PROCESS_FAILED"
            self._finish(safe["event_id"], classification.lower())
            return {"event_id": safe["event_id"], "status": "error", "classification": classification, "exit_code": proc.returncode, "event_types": event_types[-8:], "stdout_bytes": len(proc.stdout or ""), "stderr_bytes": len(proc.stderr or ""), "woken": False}
        receipt = {"event_id": safe["event_id"], "digest": digest, "completed_at": time.time(), "exit_code": proc.returncode, "event_type": "turn.completed"}
        self._finish(safe["event_id"], "completed", receipt)
        return {"event_id": safe["event_id"], "runtime": "codex", "status": "success", "classification": "TURN_COMPLETED", "woken": True, "receipt": receipt}

    def receipt(self, event_id: str) -> Dict[str, Any]:
        if not _ID_RE.fullmatch(event_id):
            return {"event_id": event_id, "verified": False, "classification": "INVALID_EVENT_ID"}
        with self._connect() as connection:
            row = connection.execute("SELECT status, receipt FROM wake_events WHERE event_id=?", (event_id,)).fetchone()
        verified = bool(row and row[0] == "completed" and row[1])
        return {"event_id": event_id, "verified": verified, "status": row[0] if row else "missing", "receipt": json.loads(row[1]) if verified else None}
