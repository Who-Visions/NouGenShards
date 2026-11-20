#!/usr/bin/env python3
"""Stop hook: no receipt, no done. Exit 2 sends the session back to work.

When a turn that used tools ends by claiming the work is finished, the turn
must also carry proof: a commit hash, a PR link or number, test output, an
exit code, or a shard id. A claim with none of those is refused once, with
the reason on stderr, so the lane either produces the receipt or rewords the
claim to what is actually true.

Exit 1 would let the harness mark the turn complete. Exit 2 does not.

It blocks at most once per stop (`stop_hook_active`), so it cannot loop
forever, and it fails open on any error: a guard that wedges a session gets
removed, and a removed guard protects nothing.

Config (env, optional):
  NOUGEN_STOP_RECEIPT  "off" disables the hook
"""
from __future__ import annotations

import json
import os
import re
import sys

_CLAIM = re.compile(
    r"\b(done|finished|fixed|shipped|merged|deployed|landed|complete|completed|"
    r"all green|tests? pass(es|ing|ed)?|is live|now live|resolved|verified)\b",
    re.IGNORECASE,
)
_NEGATED = re.compile(
    r"\b(not|n't|isn't|never|no longer|un|yet to be|still not|nothing)\s+(\w+\s+){0,2}"
    r"(done|finished|fixed|shipped|merged|deployed|landed|complete|completed|verified|resolved)\b",
    re.IGNORECASE,
)
_RECEIPTS = [re.compile(p, re.IGNORECASE) for p in (
    r"\b(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b",   # commit hash
    r"/pull/\d+|\bPR\s*#?\d+|\b[\w.-]+/[\w.-]+#\d+",              # pull request
    r"\b\d+\s+(passed|failed|tests? ran|errors?)\b",               # test output
    r"\bexit(ed)?( with)?( code)?[ =:]+\d+\b",                     # exit code
    r"\b\d+@db\d+\b|\bshard(\s+id)?[ #:]+\d+\b",                   # shard id
)]


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            out.append(block.get("text") or "")
        elif block.get("type") == "tool_result":
            out.append(_text_of(block.get("content")))
    return "\n".join(out)


def _is_user_prompt(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    return any(isinstance(b, dict) and b.get("type") == "text" for b in content or [])


def read_turn(transcript_path: str):
    """(last assistant text, all text this turn, whether a tool ran)."""
    entries = []
    with open(transcript_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    start = 0
    for i, entry in enumerate(entries):
        if _is_user_prompt(entry):
            start = i
    last, everything, used_tool = "", [], False
    for entry in entries[start + 1:]:
        content = (entry.get("message") or {}).get("content")
        text = _text_of(content)
        everything.append(text)
        if entry.get("type") == "assistant":
            if text.strip():
                last = text
            if any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content or []):
                used_tool = True
    return last, "\n".join(everything), used_tool


def claims_done(text: str) -> bool:
    return bool(_CLAIM.search(_NEGATED.sub(" ", text)))


def has_receipt(text: str) -> bool:
    return any(p.search(text) for p in _RECEIPTS)


def verdict(last: str, turn_text: str, used_tool: bool) -> str | None:
    """Reason to refuse the stop, or None."""
    if not used_tool or not claims_done(last):
        return None
    if has_receipt(turn_text):
        return None
    return ("This turn says the work is finished but shows no receipt. Add the commit "
            "hash, PR link, test output, exit code or shard id that proves it, or say "
            "plainly what is not done yet.")


def main() -> int:
    if (os.environ.get("NOUGEN_STOP_RECEIPT") or "").lower() == "off":
        return 0
    try:
        event = json.load(sys.stdin)
        if event.get("stop_hook_active"):
            return 0
        path = event.get("transcript_path")
        if not path or not os.path.isfile(path):
            return 0
        why = verdict(*read_turn(path))
    except Exception:  # noqa: BLE001 - fail open, see module docstring
        return 0
    if why:
        sys.stderr.write(f"[guardrails] NO RECEIPT: {why}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
