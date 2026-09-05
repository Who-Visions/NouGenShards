#!/usr/bin/env python3
"""
Antigravity Unix Domain Socket Server (UDS IPC for Antigravity on macOS/Linux).

Binds: /tmp/agy-socks/agy-msg-antigravity.sock
Listens for incoming plain-text and JSON messages from:
- Claude Code sessions
- Python scripts / CLI tools
- Other fleet nodes

On incoming message:
1. Validates payload
2. Ingests into active Antigravity session inboxes:
   - ~/.gemini/config/inbox/ping_<timestamp>.json
   - ~/.nougen/agy_inbox/ping_<timestamp>.json
3. Replies over socket with JSON acknowledgment.
"""
from __future__ import annotations

import os
import sys
import json
import time
import socket
from pathlib import Path
from typing import Dict, Any

SOCKET_DIR = Path("/tmp/agy-socks")
SOCKET_PATH = SOCKET_DIR / "agy-msg-antigravity.sock"
INBOX_DIRS = [
    Path.home() / ".gemini" / "config" / "inbox",
    Path.home() / ".nougen" / "agy_inbox",
]

BUFSIZE = 65536


def drop_to_inboxes(payload: Dict[str, Any]) -> list[str]:
    """Drops the received message into Antigravity inbox paths for hook ingestion."""
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
            sys.stderr.write(f"[agy_sock] Error writing to {inbox}: {e}\n")

    return written


def run_server():
    SOCKET_DIR.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        try:
            SOCKET_PATH.unlink()
        except OSError:
            pass

    for d in INBOX_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    os.chmod(str(SOCKET_PATH), 0o777)
    server.listen(16)

    print(f"🛰️ Antigravity Unix Socket Server listening on: {SOCKET_PATH}", flush=True)

    while True:
        try:
            conn, _ = server.accept()
            with conn:
                raw_data = conn.recv(BUFSIZE).decode("utf-8", errors="replace").strip()
                if not raw_data:
                    continue

                try:
                    msg_obj = json.loads(raw_data)
                    if not isinstance(msg_obj, dict):
                        msg_obj = {"text": str(msg_obj)}
                except json.JSONDecodeError:
                    msg_obj = {"text": raw_data}

                msg_obj.setdefault("source", "socket_client")
                msg_obj.setdefault("target", "antigravity")
                msg_obj.setdefault("timestamp", time.time())

                written = drop_to_inboxes(msg_obj)
                print(f"[agy_sock] Received message: '{msg_obj.get('text', '')[:60]}...' -> Dropped to {len(written)} inboxes", flush=True)

                ack = json.dumps({
                    "status": "delivered",
                    "socket": str(SOCKET_PATH),
                    "target": "antigravity",
                    "inbox_files": written,
                    "timestamp": time.time()
                }) + "\n"

                conn.sendall(ack.encode("utf-8"))
        except Exception as e:
            sys.stderr.write(f"[agy_sock] Connection error: {e}\n")


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("[agy_sock] Stopping socket server.", flush=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
