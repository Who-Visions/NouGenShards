#!/usr/bin/env python
"""Paste-size tripwire (UserPromptSubmit hook).

Flags oversized pasted prompts so bulk source material gets sharded/delegated
instead of riding in agent context for the rest of the session. Advisory only —
never blocks the prompt.

Threshold resolves from env NOUGEN_PASTE_TRIPWIRE_CHARS (constant fallback
logged in output per dynamic-state doctrine).
"""
import json
import os
import sys

DEFAULT_THRESHOLD = 8000  # chars, ~2k tokens; fallback only — env wins


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # malformed input: stay silent, never break prompt submission

    prompt = payload.get("prompt") or ""
    threshold_src = os.environ.get("NOUGEN_PASTE_TRIPWIRE_CHARS")
    try:
        threshold = int(threshold_src) if threshold_src else DEFAULT_THRESHOLD
    except ValueError:
        threshold = DEFAULT_THRESHOLD
    if len(prompt) <= threshold:
        return

    src = "env" if threshold_src else f"fallback:{DEFAULT_THRESHOLD}"
    print(json.dumps({
        "systemMessage": (
            f"Paste tripwire: prompt is {len(prompt):,} chars "
            f"(threshold {threshold:,}, {src}). Big pastes pay context rent "
            "every turn — next time drop a URL/path and let a worker fetch it."
        ),
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"[paste-tripwire] This prompt is {len(prompt):,} chars — over the "
                f"{threshold:,}-char discipline threshold. Handle per token doctrine: "
                "(1) distill and shard it to the vault NOW, in this turn; "
                "(2) keep your reply short and do not re-quote the pasted body; "
                "(3) if more source material is coming, ask the GM for URLs/paths "
                "so workers can fetch instead of pasting; "
                "(4) if this session is already heavy, recommend handoff-and-reset."
            ),
        },
    }))


if __name__ == "__main__":
    main()
