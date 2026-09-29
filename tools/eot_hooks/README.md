# End-of-turn inbox-continue hooks (Codex + Antigravity)

An agent that stops while its NouGenMsg inbox holds unread work leaves that work
waiting. These hooks make the stop conditional on the inbox:

| Agent | Hook | Behaviour |
|---|---|---|
| Codex | `codex_nougen_lifecycle.py` (Stop) | Blocks the stop and injects unread items from `~/.codex/inbox` and `~/.nougen/codex/inbox` that are newer than `~/.nougen/state/codex_eot_cursor.json`. The cursor is seeded at first run, so an existing backlog never fires. |
| Antigravity | `agy_check_inbox_and_continue.py` (PostInvocation, Stop) | Same idea against `~/.nougen/agy_inbox`; an unreadable claims directory (WinError 448) is skipped, never a crash. |

When the inbox is clear both hooks announce completion through `NouGen/speak.py`
if present. The announcement names the operator only when
`NOUGEN_OPERATOR_NAME` is set.

## Install

    python tools/eot_hooks/install.py     # backs up existing hook config, then writes
    python tools/eot_hooks/selftest.py    # seed / idle / new-ping / after / agy

`selftest.py` passes when steps 1, 2 and 4 print `{"continue": true}`, step 3
prints `"decision": "block"`, and step 5 has no traceback.

## Configuration (no hardcoded hosts)

- `NOUGEN_OBSERVATORY` - project root (default `~/The Observatory`).
- `NOUGEN_OPERATOR_NAME` - optional name for the spoken completion line.
- `NOUGEN_PIPE_FORWARD_SSH` / `NOUGEN_PIPE_FORWARD_KEY`, or an untracked
  `~/.nougen/pipe_forward.json` (`{"ssh": "user@host", "key": "~/.ssh/..."}`) -
  where the Antigravity hook forwards a wake to a peer's named pipe. Unset means
  no forward.
