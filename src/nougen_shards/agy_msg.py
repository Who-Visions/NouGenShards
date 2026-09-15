"""
Antigravity Live Pipe and IPC Bus Adapter (AgyMsgBus).

Provides synchronous Win32 named pipe transport for:
\\.\pipe\LOCAL\agy-msg-antigravity

Connects, sends structured event payloads, and reads JSON ACK responses from
the running Antigravity pipe server.
"""
from __future__ import annotations

import os
import json
import logging
import time
import ctypes
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)

PIPE_NAME = r"\\.\pipe\LOCAL\agy-msg-antigravity"
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = -1

# Fallbacks only; NOUGEN_AGY_MSG_URL / NOUGEN_AGY_MSG_TIMEOUT_S win when set.
DEFAULT_HTTP_URL = "http://127.0.0.1:8766/msg"
DEFAULT_HTTP_TIMEOUT_S = 1.5


def get_inbox_dir() -> Path:
    """Antigravity inbox dir: NOUGEN_AGY_INBOX_DIR, else ~/.nougen/agy_inbox. Never created here."""
    env_val = os.environ.get("NOUGEN_AGY_INBOX_DIR")
    if env_val:
        return Path(env_val).expanduser()
    return Path.home() / ".nougen" / "agy_inbox"


def _http_url() -> str:
    return os.environ.get("NOUGEN_AGY_MSG_URL") or DEFAULT_HTTP_URL


def _http_timeout() -> float:
    raw = os.environ.get("NOUGEN_AGY_MSG_TIMEOUT_S")
    if raw is None:
        return DEFAULT_HTTP_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if value <= 0:
        log.warning("NOUGEN_AGY_MSG_TIMEOUT_S=%r is not a positive number; using %s", raw, DEFAULT_HTTP_TIMEOUT_S)
        return DEFAULT_HTTP_TIMEOUT_S
    return value


class AgyMsgBus:
    """Live IPC transport for local Antigravity pipe and fleet dispatch."""

    @staticmethod
    def send_pipe_windows(payload: Dict[str, Any], pipe_name: str = PIPE_NAME) -> Dict[str, Any]:
        """Sends payload to Windows named pipe and reads response."""
        if os.name != "nt":
            return {"delivered": False, "error": "not_windows"}

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateFileW(
            pipe_name,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )

        if handle == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            return {"delivered": False, "error": f"WinError {err}", "pipe": pipe_name}

        try:
            raw_bytes = (json.dumps(payload) + "\n").encode("utf-8")
            written = wintypes.DWORD(0)
            res_write = kernel32.WriteFile(
                handle, raw_bytes, len(raw_bytes), ctypes.byref(written), None
            )
            if not res_write or written.value == 0:
                err = ctypes.get_last_error()
                return {"delivered": False, "error": f"write_failed_err_{err}", "pipe": pipe_name}

            # Read response from pipe
            buf = ctypes.create_string_buffer(65536)
            read_bytes = wintypes.DWORD(0)
            res_read = kernel32.ReadFile(handle, buf, 65536, ctypes.byref(read_bytes), None)
            response_data = None
            if res_read and read_bytes.value > 0:
                raw_resp = buf.raw[:read_bytes.value].decode("utf-8", errors="replace").strip()
                try:
                    response_data = json.loads(raw_resp)
                except Exception:
                    response_data = {"raw": raw_resp}

            return {
                "delivered": True,
                "pipe": pipe_name,
                "bytes_written": int(written.value),
                "bytes_read": int(read_bytes.value),
                "response": response_data,
            }
        finally:
            kernel32.CloseHandle(handle)

    @classmethod
    def send_local(
        cls,
        text: str,
        sender: str = "unknown",
        priority: str = "normal",
        leg_id: Optional[str] = None,
        goal: Optional[str] = None,
        target: str = "antigravity",
        action: str = "wake",
    ) -> Dict[str, Any]:
        """Dispatches message into local pipe listener and captures response."""
        payload = {
            "type": "live_message",
            "action": action,
            "target": target,
            "sender": sender,
            "text": text,
            "priority": priority,
            "leg_id": leg_id,
            "goal": goal,
            "timestamp": time.time(),
        }

        pipe_res: Dict[str, Any] = {}

        # 1. Try Windows named pipe if on Windows
        if os.name == "nt":
            pipe_res = cls.send_pipe_windows(payload)
            if pipe_res.get("delivered"):
                return pipe_res

        # 2. Try HTTP loopback (NOUGEN_AGY_MSG_URL, fallback DEFAULT_HTTP_URL)
        try:
            req = urllib.request.Request(
                _http_url(),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_http_timeout()) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"delivered": True, "transport": "http", "response": data}
        except Exception as e:
            return {
                "delivered": False,
                "error": f"pipe_and_http_failed: {e}",
                "pipe_error": pipe_res.get("error"),
            }

    @classmethod
    def broadcast_fleet(
        cls,
        text: str,
        sender: str = "unknown",
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """Fleet broadcast helper routing through NouGenMsgBus."""
        try:
            from .nougenmsg import NouGenMsgBus
            return NouGenMsgBus.emit_fleet(text=text, target="all")
        except Exception as exc:
            return {"error": str(exc)}
