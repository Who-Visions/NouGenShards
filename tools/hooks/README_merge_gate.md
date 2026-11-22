# Merge gate hook

`pr_merge_gate.py` reads a PR's live review state and refuses a merge while any
reviewer's latest word is CHANGES_REQUESTED, a thread is unresolved, a check is red,
or no non-author approval stands. `pr_merge_gate_hook.py` runs it as a PreToolUse
hook so a merge cannot skip it.

Install on a node: add a PreToolUse hook whose command runs
`python <path>/tools/hooks/pr_merge_gate_hook.py` with matcher
`Bash|mcp__.*merge_pull_request.*`. The hook denies on gate exit 1 (blocked) or 2
(state unreadable) and always denies `--admin`. Repo, PR and identity are resolved at
run time from the command, a PR URL, or the working directory's gh context.

Checks that are red for a non-code reason (billing on a private repo) are named in
`NOUGEN_MERGE_GATE_ALLOW_RED` (comma separated). Free tools only; no Actions needed.
