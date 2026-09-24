#!/usr/bin/env python3
"""cc_msg.py - Universal 1:1 Parity Message CLI for Claude Code, Antigravity, and Codex.

Implements full parity across the NouGen fleet:
- Target resolution: @blade, @phoebus, @whoart, @codex, @antigravity, or session UUIDs
- First-line preview enforcement (self-contained summaries for toast previews)
- Dual transport dispatch:
    1. Local HTTP Ingest (http://127.0.0.1:8766/msg)
    2. Windows Named Pipes (\\\\.\\pipe\\LOCAL\\agy-msg)
    3. Direct Claude Code Live Sockets (\\\\.\\pipe\\LOCAL\\cc-msg-* with auth framing)
    4. Remote Node LAN Transport (http://<ip>:8766/msg)
- Zero console flash / creationflags=_NO_WINDOW compliance.
"""
from __future__ import annotations

import argparse
import datetime
import json
import socket
import sys
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_PORT = 8766
DEFAULT_LOCAL_HOST = "127.0.0.1"

def _known_nodes() -> dict:
    """Node name -> LAN address, from ~/.nougen/fleet_hosts.json ("ip" per node).
    Public code ships no addresses; unknown targets fall back to localhost."""
    try:
        cfg = json.loads((Path.home() / ".nougen" / "fleet_hosts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    nodes = cfg.get("nodes") if isinstance(cfg, dict) else None
    return {str(k).lower(): str(v["ip"]) for k, v in (nodes or {}).items() if isinstance(v, dict) and v.get("ip")}


KNOWN_NODES = _known_nodes()


def send_http(host: str, port: int, payload: dict) -> dict:
    url = f"http://{host}:{port}/msg"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "cc_msg_parity/1.0"})
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_pipe(pipe_name: str, payload: dict) -> bool:
    if sys.platform != "win32":
        return False
    try:
        pipe_path = f"\\\\.\\pipe\\{pipe_name}" if not pipe_name.startswith("\\\\") else pipe_name
        with open(pipe_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        return True
    except Exception:
        return False


def send_claude_live_socket(content: str) -> bool:
    """Delivers directly into Claude Code active sessions on Windows via live named pipes."""
    if sys.platform != "win32":
        return False
    reg_path = Path.home() / ".nougen" / "state" / "claude_sessions.json"
    if not reg_path.exists():
        return False
    try:
        sessions = json.loads(reg_path.read_text(encoding="utf-8"))
        if not isinstance(sessions, dict) or not sessions:
            return False
        delivered_any = False
        for s_id, s_info in sessions.items():
            sock = s_info.get("socket") or s_info.get("sock_path")
            token = s_info.get("token", "")
            if not sock or not token:
                continue
            auth_line = json.dumps({"type": "auth", "token": token})
            user_line = json.dumps({"type": "user", "message": {"role": "user", "content": content}})
            raw = (auth_line + "\n" + user_line + "\n").encode("utf-8")
            try:
                with open(sock, "w+b", buffering=0) as f:
                    f.write(raw)
                delivered_any = True
            except Exception:
                pass
        return delivered_any
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Universal 1:1 cc-msg / nougenmsg parity dispatcher.")
    parser.add_argument("args", nargs="*", help="Target (@node/session) and message text, or bare message text")
    parser.add_argument("--to", help="Explicit target node or session")
    parser.add_argument("--sender", "-s", default="Apollo-AGY", help="Sender signature")
    parser.add_argument("--summary", "-m", help="Explicit first-line summary preview")
    parser.add_argument("--priority", "-p", choices=["low", "normal", "high"], default="normal", help="Message priority")
    parser.add_argument("--type", "-t", default="live_message", help="Message classification type")
    parser.add_argument("--inbox", action="store_true", help="Read local inbox directly")
    parser.add_argument("--drain", action="store_true", help="Pop and drain pending messages")
    parsed = parser.parse_args()

    if parsed.inbox or parsed.drain:
        endpoint = "/pop" if parsed.drain else "/"
        url = f"http://127.0.0.1:{DEFAULT_PORT}{endpoint}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cc_msg_parity/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(json.dumps(data, indent=2))
                return 0
        except Exception as e:
            print(f"Error checking inbox: {e}", file=sys.stderr)
            return 1

    pos_args = list(parsed.args)
    target_raw = "broadcast"
    if parsed.to:
        target_raw = parsed.to.lstrip("@").lower()
    elif pos_args and (pos_args[0].startswith("@") or len(pos_args[0]) == 36):
        target_raw = pos_args.pop(0).lstrip("@").lower()

    text_body = " ".join(pos_args).strip()
    if not text_body and not parsed.summary:
        print("Error: No message content provided.", file=sys.stderr)
        return 1

    summary = parsed.summary if parsed.summary else text_body.splitlines()[0]
    full_text = text_body if text_body else summary

    host = KNOWN_NODES.get(target_raw, DEFAULT_LOCAL_HOST)

    payload = {
        "text": full_text,
        "summary": summary,
        "sender": parsed.sender,
        "target": target_raw,
        "priority": parsed.priority,
        "type": parsed.type,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).timestamp(),
        "origin_host": socket.gethostname().lower(),
    }

    # 1. Attempt HTTP Transport
    delivered = False
    result = {}
    try:
        result = send_http(host, DEFAULT_PORT, payload)
        delivered = result.get("delivered", False) or result.get("ok", False)
    except Exception:
        # 2. Fallback to Named Pipe on Windows
        if sys.platform == "win32" and host == DEFAULT_LOCAL_HOST:
            delivered = send_pipe("LOCAL\\agy-msg", payload)
            result = {"delivered": delivered, "transport": "named_pipe"}

    # 3. Direct Live Claude Session Ingestion if on Blade
    if target_raw in ("blade", "claude", "all", "broadcast"):
        claude_live = send_claude_live_socket(f"[{parsed.sender}] {summary}\n\n{full_text}")
        if claude_live:
            result["claude_live"] = True

    if delivered:
        print(f"Delivered to {target_raw} [{host}] -> {result.get('file', result.get('transport', 'ok'))}")
        return 0
    else:
        print(f"Failed to deliver message to {target_raw} [{host}]", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
