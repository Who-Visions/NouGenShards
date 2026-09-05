#!/usr/bin/env python3
"""
Deliver NouGenMsg and AgyMsg inbox files into Antigravity hook context (PreInvocation).

Drains unread messages from:
- ~/.nougen/agy_inbox/
- ~/.gemini/config/inbox/

Emits Antigravity PreInvocation contract output:
{
  "injectSteps": [
    {
      "ephemeralMessage": "⚡ [LIVE NOUGENMSG] ..."
    }
  ]
}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

INBOX_DIRS = [
    Path(os.environ.get("NOUGEN_AGY_INBOX", Path.home() / ".nougen" / "agy_inbox")),
    Path.home() / ".gemini" / "config" / "inbox",
]
STATE_PATH = Path(os.environ.get("NOUGEN_AGY_INBOX_STATE", Path.home() / ".nougen" / ".agy_inbox_seen.json"))
MAX_MESSAGE_CHARS = int(os.environ.get("NOUGEN_AGY_INBOX_MESSAGE_CHARS", "2000"))
MAX_BATCH_CHARS = int(os.environ.get("NOUGEN_AGY_INBOX_BATCH_CHARS", "6000"))
TARGETS = {t.strip().lower() for t in os.environ.get("NOUGEN_AGY_INBOX_TARGETS", "antigravity,gemini,all,local").split(",") if t.strip()}


def _cursor() -> tuple[int, str] | None:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return int(data["mtime_ns"]), str(data["name"])
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _save_cursor(value: tuple[int, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps({"mtime_ns": value[0], "name": value[1]}), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def _entries() -> list[tuple[tuple[int, str], Path]]:
    out = []
    for inbox in INBOX_DIRS:
        if not inbox.is_dir():
            continue
        for path in inbox.glob("*.json"):
            if path.name.startswith("."):
                continue
            try:
                out.append(((path.stat().st_mtime_ns, path.name), path))
            except OSError:
                continue
    return sorted(out, key=lambda x: x[0])


def read_new_messages(*, replay_existing: bool = False) -> list[str]:
    entries = _entries()
    if not entries:
        return []
    cursor = _cursor()
    if cursor is None and not replay_existing:
        _save_cursor(entries[-1][0])
        return []
    selected = entries if cursor is None else [e for e in entries if e[0] > cursor]
    messages: list[str] = []
    used = 0
    for key, path in selected:
        try:
            env: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            target = str(env.get("target", "antigravity")).lower()
            if target not in TARGETS:
                continue
            source = str(env.get("sender") or env.get("source") or "unknown")[:160]
            text = env.get("text") or env.get("content") or env.get("message")
            if not isinstance(text, str) or not text.strip():
                continue
            domain = str(env.get("domain") or "").lower()
            goal = str(env.get("goal") or "")

            # Smart Emoji selection based on source & content
            src_lower = source.lower()
            txt_lower = text.lower()
            if "blade" in src_lower or "apollo" in src_lower:
                emoji = "🚀 [Apollo/Blade]"
            elif "phoebus" in src_lower or "macmini" in src_lower or "keadra" in src_lower:
                emoji = "🍏 [Phoebus/MacMini]"
            elif "whoart" in src_lower or "hyperion" in src_lower:
                emoji = "⚡ [Hyperion/PX13]"
            elif "claude" in src_lower:
                emoji = "🤖 [Claude Code]"
            elif "codex" in src_lower:
                emoji = "🔮 [Codex]"
            else:
                emoji = "🛰️ [Fleet Relay]"

            # Category badges
            if any(k in txt_lower for k in ["error", "fail", "broken", "critical"]):
                badge = "🚨 CRITICAL"
            elif any(k in txt_lower for k in ["warn", "alert", "drift"]):
                badge = "⚠️ ALERT"
            elif any(k in txt_lower for k in ["verified", "complete", "online", "success", "live"]):
                badge = "✅ ONLINE"
            else:
                badge = "📡 NOTICE"

            header = f"{emoji} {badge} from @{source}"
            if goal:
                header += f" | Goal: {goal}"
            if domain:
                header += f" [{domain}]"

            rendered = f"{header}\n  └─ {text.strip()[:MAX_MESSAGE_CHARS]}"
            if messages and used + len(rendered) > MAX_BATCH_CHARS:
                break
            messages.append(rendered)
            used += len(rendered)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        finally:
            _save_cursor(key)
    return messages


def register_agy_session(event: dict) -> None:
    """Registers active Antigravity session into ~/.nougen/agy_sessions.json mirroring cc-msg."""
    try:
        import platform
        reg_path = Path.home() / ".nougen" / "agy_sessions.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if reg_path.exists():
            try:
                data = json.loads(reg_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        sessions = data.get("sessions") if isinstance(data.get("sessions"), dict) else {}
        pipe_name = r"\\.\pipe\LOCAL\agy-msg-antigravity"
        conv_id = str(event.get("conversationId") or "")
        ws = event.get("workspacePaths") or [os.getcwd()]
        cwd = str(ws[0]) if ws else os.getcwd()
        sessions[pipe_name] = {
            "socket": pipe_name,
            "session_id": conv_id,
            "cwd": cwd,
            "machine": platform.node(),
            "pid": os.getppid(),
            "agent": "antigravity",
            "registered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        tmp = reg_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sessions": sessions, "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1), encoding="utf-8")
        os.replace(tmp, reg_path)
    except Exception:
        pass


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    event = {}
    if not sys.stdin.isatty():
        try:
            event = json.load(sys.stdin)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    register_agy_session(event)

    messages = read_new_messages(replay_existing=os.environ.get("NOUGEN_AGY_INBOX_REPLAY") == "1")
    if not messages:
        print(json.dumps({"injectSteps": []}))
        return 0

    banner_lines = [
        "═══════════════════════════════════════════════════════════════════",
        "🛰️  INCOMING FLEET TELEMETRY & CROSS-SESSION DISPATCH",
        "═══════════════════════════════════════════════════════════════════",
    ]
    for msg in messages:
        banner_lines.append(msg)
    banner_lines.append("═══════════════════════════════════════════════════════════════════")

    context = "\n".join(banner_lines)
    print(json.dumps({
        "injectSteps": [
            {
                "ephemeralMessage": context
            }
        ],
        "terminationBehavior": "force_continue"
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
