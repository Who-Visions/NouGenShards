#!/usr/bin/env python3
"""Claude Code Stop hook: say, in the lane's resolved voice, what the turn that just ended did.

Reads the hook's JSON on stdin (``transcript_path``), finds the turn that just ended (everything after
the last plain-string user entry), and speaks its first sentence. Turns that used no tools are
acknowledgements and echoes of the fleet's own broadcasts, so they stay silent
(``NOUGEN_EOT_SPEAK_ALL=1`` speaks them too). The voice comes from ``whoart_voice_sync`` (explicit voice,
then this lane's entry in lane_voices.json, then WhoArt's favourites), never from this file.
Detaches before speaking so the hook returns at once.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent
LIMIT = 140
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_STOP = re.compile(r"(?<=[.!?])\s|\n")


def turn_summary(lines: Iterable[str]) -> tuple[int, str]:
    """(tool calls, final assistant text) of the turn that ends the transcript."""
    entries = []
    for raw in lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if entry.get("type") in ("assistant", "user"):
            entries.append(entry)
    tool_calls, final_text = 0, ""
    for entry in reversed(entries):
        content = (entry.get("message") or {}).get("content")
        if entry["type"] == "user":
            if isinstance(content, str):       # a real prompt (or an injected message) starts the turn
                break
            continue                            # tool results belong to the turn
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool_calls += 1
            elif block.get("type") == "text" and not final_text and block.get("text", "").strip():
                final_text = block["text"]
    return tool_calls, final_text


def sentence(text: str, limit: int = LIMIT) -> str:
    """First sentence of ``text`` with markdown stripped, at most ``limit`` characters."""
    text = _FENCE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)   # markdown headings
    text = re.sub(r"#(\d+)", r"number \1", text)                   # "#731" is spoken as "number 731"
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)                    # NOUGEN_LANE -> "NOUGEN LANE": speakable
    text = re.sub(r"[`*#>|_]", "", text)
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.MULTILINE)
    text = text.strip()
    first = _STOP.split(text, maxsplit=1)[0].strip() if text else ""
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    if first and first[-1] not in ".!?":
        first += "."
    return first


def announcement(tool_calls: int, text: str, speak_all: bool = False) -> str | None:
    if tool_calls == 0 and not speak_all:
        return None
    first = sentence(text)
    if first:
        return first
    return f"Turn complete, {tool_calls} tool call{'s' if tool_calls != 1 else ''}." if tool_calls else None


def _already_speaking() -> bool:
    return subprocess.run(["pgrep", "-f", "nougen_speak_neural"], capture_output=True).returncode == 0


def main(stdin_text: str | None = None, speak=None) -> int:
    try:
        payload = json.loads(stdin_text if stdin_text is not None else sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    path = payload.get("transcript_path")
    if not path or not Path(path).is_file():
        return 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        calls, text = turn_summary(fh.read().splitlines())
    message = announcement(calls, text, os.environ.get("NOUGEN_EOT_SPEAK_ALL") == "1")
    if not message or (speak is None and _already_speaking()):
        return 0
    if speak is None:
        if os.fork():                           # parent returns to Claude immediately
            return 0
        os.setsid()
        sys.path.insert(0, str(HERE))
        from speak import speak as speak        # noqa: PLC0415 - heavy, only needed in the child
    speak(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
