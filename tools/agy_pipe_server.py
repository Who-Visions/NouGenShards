#!/usr/bin/env python3
"""
Antigravity Named Pipe Server (Win32 Named Pipe IPC for Antigravity & Fleet).

Binds: \\\\.\\pipe\\LOCAL\\agy-msg-antigravity
Listens for incoming plain-text and JSON messages from:
- Claude Code sessions
- Python scripts / CLI tools
- Other fleet nodes

On incoming message:
1. Validates payload
2. Ingests into active Antigravity session inboxes:
   - ~/.gemini/config/inbox/ping_<timestamp>.json
   - ~/.nougen/agy_inbox/ping_<timestamp>.json
3. Replies over pipe with JSON acknowledgment.
"""
from __future__ import annotations

import os
import sys
import json
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PIPE_NAME = r"\\.\pipe\LOCAL\agy-msg-antigravity"
INBOX_DIRS = [
    Path.home() / ".gemini" / "config" / "inbox",
    Path.home() / ".nougen" / "agy_inbox",
]

# Win32 Pipe Constants
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255
BUFSIZE = 65536
INVALID_HANDLE_VALUE = -1

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.CreateNamedPipeW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID
]
kernel32.CreateNamedPipeW.restype = wintypes.HANDLE

kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
kernel32.ConnectNamedPipe.restype = wintypes.BOOL

kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
kernel32.DisconnectNamedPipe.restype = wintypes.BOOL

kernel32.ReadFile.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID
]
kernel32.ReadFile.restype = wintypes.BOOL

kernel32.WriteFile.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID
]
kernel32.WriteFile.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.AttachConsole.argtypes = [wintypes.DWORD]
kernel32.AttachConsole.restype = wintypes.BOOL
kernel32.FreeConsole.argtypes = []
kernel32.FreeConsole.restype = wintypes.BOOL
kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
kernel32.GetStdHandle.restype = wintypes.HANDLE
kernel32.WriteConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.WriteConsoleInputW.restype = wintypes.BOOL


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("uChar", wintypes.WCHAR),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class INPUT_RECORD_UNION(ctypes.Union):
    _fields_ = [("KeyEvent", KEY_EVENT_RECORD)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [
        ("EventType", wintypes.WORD),
        ("Event", INPUT_RECORD_UNION),
    ]


def wake_idle_consoles() -> int:
    """Finds active agy CLI processes and pulses VK_RETURN into console input buffer."""
    import subprocess
    woken = 0
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "Get-Process -Name agy -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
            text=True,
            errors="replace",
            timeout=2,
        )
        pids = [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]
    except Exception:
        pids = []

    for pid in pids:
        try:
            kernel32.FreeConsole()
            if kernel32.AttachConsole(pid):
                hStdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
                rec_down = INPUT_RECORD()
                rec_down.EventType = 1  # KEY_EVENT
                rec_down.Event.KeyEvent.bKeyDown = True
                rec_down.Event.KeyEvent.wRepeatCount = 1
                rec_down.Event.KeyEvent.wVirtualKeyCode = 0x0D  # VK_RETURN
                rec_down.Event.KeyEvent.wVirtualScanCode = 0x1C
                rec_down.Event.KeyEvent.uChar = "\r"

                rec_up = INPUT_RECORD()
                rec_up.EventType = 1
                rec_up.Event.KeyEvent.bKeyDown = False
                rec_up.Event.KeyEvent.wRepeatCount = 1
                rec_up.Event.KeyEvent.wVirtualKeyCode = 0x0D
                rec_up.Event.KeyEvent.wVirtualScanCode = 0x1C
                rec_up.Event.KeyEvent.uChar = "\r"

                records = (INPUT_RECORD * 2)(rec_down, rec_up)
                written = wintypes.DWORD(0)
                if kernel32.WriteConsoleInputW(hStdin, ctypes.byref(records), 2, ctypes.byref(written)):
                    woken += 1
                kernel32.FreeConsole()
        except Exception:
            pass

    return woken


def drop_to_inboxes(payload: Dict[str, Any]) -> list[str]:
    """Drops the received message into Antigravity inbox paths for hook ingestion and pulses idle sessions."""
    timestamp_ms = int(time.time() * 1000)
    filename = f"ping_{timestamp_ms}.json"
    written = []

    for inbox in INBOX_DIRS:
        try:
            inbox.mkdir(parents=True, exist_ok=True)
            target_file = inbox / filename
            target_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            written.append(str(target_file))
        except Exception as e:
            sys.stderr.write(f"[agy_pipe] Error writing to {inbox}: {e}\n")

    woken = wake_idle_consoles()
    if woken > 0:
        print(f"[agy_pipe] Pulsed {woken} idle agy CLI session(s) via Win32 console buffer", flush=True)

    return written


def run_server():
    print(f"🛰️ Antigravity Named Pipe Server listening on: {PIPE_NAME}", flush=True)
    for d in INBOX_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    while True:
        handle = kernel32.CreateNamedPipeW(
            PIPE_NAME,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            BUFSIZE,
            BUFSIZE,
            0,
            None
        )

        if handle == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            sys.stderr.write(f"[agy_pipe] CreateNamedPipe error: {err}\n")
            time.sleep(1)
            continue

        connected = kernel32.ConnectNamedPipe(handle, None)
        if not connected:
            err = ctypes.get_last_error()
            # 535 = ERROR_PIPE_CONNECTED (client connected between Create and Connect)
            if err != 535:
                kernel32.CloseHandle(handle)
                continue

        try:
            read_buf = ctypes.create_string_buffer(BUFSIZE)
            bytes_read = wintypes.DWORD(0)

            success = kernel32.ReadFile(handle, read_buf, BUFSIZE, ctypes.byref(bytes_read), None)
            if success and bytes_read.value > 0:
                raw_data = read_buf.raw[:bytes_read.value].decode("utf-8", errors="replace").strip()
                lines = [line.strip() for line in raw_data.splitlines() if line.strip()]
                msg_obj: Dict[str, Any] = {}
                for line in lines:
                    try:
                        parsed = json.loads(line)
                        if isinstance(parsed, dict):
                            if parsed.get("type") == "auth":
                                continue
                            if parsed.get("type") == "user" and isinstance(parsed.get("message"), dict):
                                msg_obj["text"] = parsed["message"].get("content", "")
                                msg_obj["source"] = parsed.get("sender") or "claude-code"
                            elif "text" in parsed or "content" in parsed:
                                msg_obj.update(parsed)
                            elif not msg_obj:
                                msg_obj = parsed
                    except json.JSONDecodeError:
                        if not msg_obj.get("text"):
                            msg_obj["text"] = line

                if not msg_obj:
                    msg_obj = {"text": raw_data}

                msg_obj.setdefault("source", "pipe_client")
                msg_obj.setdefault("target", "antigravity")
                msg_obj.setdefault("timestamp", time.time())

                written = drop_to_inboxes(msg_obj)
                print(f"[agy_pipe] Received message: '{msg_obj.get('text', '')[:60]}...' -> Dropped to {len(written)} inboxes", flush=True)

                ack = json.dumps({
                    "status": "delivered",
                    "pipe": PIPE_NAME,
                    "target": "antigravity",
                    "inbox_files": written,
                    "timestamp": time.time()
                }) + "\n"

                ack_bytes = ack.encode("utf-8")
                bytes_written = wintypes.DWORD(0)
                kernel32.WriteFile(handle, ack_bytes, len(ack_bytes), ctypes.byref(bytes_written), None)
        finally:
            kernel32.DisconnectNamedPipe(handle)
            kernel32.CloseHandle(handle)


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("[agy_pipe] Stopping named pipe server.", flush=True)
