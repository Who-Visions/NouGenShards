"""UserPromptSubmit hook: flag oversized pasted prompts (token discipline).

Rule 0.0 / token discipline: every char pasted inline is cached once at write
rate and re-read at cache rate on every later turn (cost = context size x turn
count). Bulk material belongs in a file that a worker inspects, not in the
Coach prompt.

Advisory by default: it never blocks, it appends a short reminder to the turn.
Set NOUGEN_PASTE_HARD_CHARS > 0 to make truly enormous pastes block instead.

Dynamic-state doctrine (Rule 0.2): every threshold resolves from env first,
constants are logged fallbacks only.

    NOUGEN_PASTE_WARN_CHARS   advisory threshold   (default 12000)
    NOUGEN_PASTE_WARN_LINES   advisory threshold   (default 250)
    NOUGEN_PASTE_HARD_CHARS   blocking threshold   (default 0 = never block)

Fails open on any parse or runtime error - a guard must never wedge a session.
"""
import json
import os
import sys

DEFAULT_WARN_CHARS = 12000
DEFAULT_WARN_LINES = 250
DEFAULT_HARD_CHARS = 0  # 0 disables blocking


def _limit(name, fallback):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return fallback, "default"
    try:
        value = int(raw.strip())
    except ValueError:
        return fallback, "default (unparseable %s=%r)" % (name, raw)
    if value < 0:
        return fallback, "default (negative %s)" % name
    return value, "env %s" % name


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = data.get("prompt") or ""
    if not isinstance(prompt, str) or not prompt:
        return 0

    chars = len(prompt)
    lines = prompt.count("\n") + 1
    warn_chars, chars_src = _limit("NOUGEN_PASTE_WARN_CHARS", DEFAULT_WARN_CHARS)
    warn_lines, lines_src = _limit("NOUGEN_PASTE_WARN_LINES", DEFAULT_WARN_LINES)
    hard_chars, _ = _limit("NOUGEN_PASTE_HARD_CHARS", DEFAULT_HARD_CHARS)

    if hard_chars and chars >= hard_chars:
        sys.stderr.write(
            "Paste guard: prompt is %d chars (hard limit %d, NOUGEN_PASTE_HARD_CHARS). "
            "Write the bulk to a file and reference the path, or hand it to a worker "
            "and keep only the compressed return.\n" % (chars, hard_chars)
        )
        return 2

    over_chars = warn_chars and chars >= warn_chars
    over_lines = warn_lines and lines >= warn_lines
    if not (over_chars or over_lines):
        return 0

    note = (
        "[Paste guard] This prompt is %d chars / %d lines (thresholds: %d chars via %s, "
        "%d lines via %s). Inline bulk is cached at write rate and re-read every later "
        "turn. Before working it inline: write it to a file and reference the path, or "
        "delegate the inspection to a worker/subagent and keep only the compressed "
        "return. Advisory only - proceed if the bulk genuinely belongs in Coach context."
        % (chars, lines, warn_chars, chars_src, warn_lines, lines_src)
    )
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": note,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
