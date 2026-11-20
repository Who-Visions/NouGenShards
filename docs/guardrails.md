# Guardrails

Hard stops for the mistakes that cannot be taken back. The test for whether
something belongs here: if a lane gets it wrong once and it cannot be undone,
it is a deny rule or an exit-2 gate. Everything else stays a prompt rule.

## What is enforced

| Gate | Where | On failure |
|---|---|---|
| Deny rules: no reading `.env*`, `*.pem`, SSH keys, secret stores; no force push; no push to `main` | `.claude/settings.json` `permissions.deny` | The tool call is refused |
| Shell guard: the same push rules inside compound commands, recursive deletes that leave the worktree, printing secret files | `tools/guardrails/bash_guard.py` (PreToolUse) | exit 2, call blocked |
| Staged secret scan | `tools/guardrails/secret_scan.py` from `hooks/pre-commit` | commit refused |
| Verification | `tools/guardrails/verify.py` (Stop hook, or by hand) | exit 2, turn handed back |
| No receipt, no done | `tools/guardrails/stop_receipt.py` (Stop hook) | exit 2, turn handed back |

`.claude/settings.json` is committed so every session that opens the repo,
local or cloud, starts with the same rules. `.claude/settings.local.json`
stays ignored and is where personal additions go.

## Why exit 2

A hook that exits 1 is recorded as a non-blocking error and the turn is
marked complete anyway. Exit 2 hands the message on stderr back to the model
and the session keeps working. Both Stop gates block once per stop and then
let the session end, so a lane that cannot fix the problem is not trapped.

## Receipts

A turn that used tools and ends by saying the work is done, fixed, merged,
shipped or passing must show one of: a commit hash, a PR link or number,
test output, an exit code, or a shard id. Saying plainly that something is
not done always passes.

## Verification checks

`verify.py` resolves its checks from `NOUGEN_VERIFY_CMDS` (commands joined
by `;;`), then `tools/guardrails/verify.json`, then a fallback that
byte-compiles the changed Python files. Add a linter or type checker by
adding its command to the `fast` list in `verify.json`; a program that is
not installed is skipped and reported.

    python tools/guardrails/verify.py                 # fast profile
    python tools/guardrails/verify.py --profile full  # whole test suite

## Secret scan

Runs on staged added lines only, offline, using the shared pattern set in
`nougen_shards.credential_patterns`. Install the tracked hooks once per
clone:

    git config core.hooksPath hooks

A false positive is fixed by adding the path to
`tools/guardrails/secret_scan_allow.txt`, not by `--no-verify`.

## Review

A PR is reviewed by a session that did not write it: the reviewer account or
another lane, starting from the diff with no shared context. The author
session never approves or merges its own PR.

## Switches

Each gate has an off switch for the rare case it is wrong:
`NOUGEN_BASH_GUARD=off`, `NOUGEN_SECRET_SCAN=off`, `NOUGEN_VERIFY=off`,
`NOUGEN_STOP_RECEIPT=off`. Protected branches come from
`NOUGEN_PROTECTED_BRANCHES` (default `main,master`).

## Upgrading an existing clone

If a clone already has an untracked `.claude/settings.json`, git will refuse
to pull this file over it. Move the local file to
`.claude/settings.local.json` first, then pull.
