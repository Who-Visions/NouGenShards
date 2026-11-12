---
name: peer-review
description: How a NouGen lane gets a PR past required review without bypassing it. When a PR is green but blocked on review, a different lane reviews it and approves as the separate GitHub account aiwithdav3, using tools/peer_review.py. Use whenever a PR shows BLOCKED with checks passing, whenever a relay leg asks for a review, and before anyone reaches for `gh pr merge --admin` (never).
---

# Peer review: one LLM reviews another's PR

## Why this exists

Every lane in the fleet (Claude CLI, claude-app, Antigravity, Codex) pushes and
opens PRs as one GitHub account, `WhoVisions`. Branch protection asks for a
review and resolved conversations before a merge. GitHub never lets an account
approve its own PR, so as far as GitHub could tell, every PR was a solo author with nobody
able to review it.

The lanes worked around that by merging with `gh pr merge --admin`. On
2026-11-11 Antigravity's conversation logs showed about 75 admin merges,
including NouGenShards #1004 and #705-#734, NouGenCode #6-#35 and NouGenRelay
#59/#76/#88. `--admin` skips the required checks and the required review. The
merge count looked like progress, but the gate that was meant to catch a bad
change was being switched off every time. A merged PR is not a landed fix, and
an unreviewed merged PR is not even a checked one.

Banning `--admin` alone would just stall the queue: dozens of green PRs that
nobody can approve. Adding a second account fixes it:

- `aiwithdav3` is a separate GitHub account, a collaborator on the Who-Visions
  repos. Its approval counts, because it is not the author.
- Its token lives in the Keymaker as `GITHUB_TOKEN_AIWITHDAV3`, fine-grained,
  scoped to reading and reviewing pull requests. It cannot merge or push, so a
  review lane cannot turn into a merge lane.
- The reviewer is a *different LLM lane* from the author. A model reviewing its
  own work repeats its own blind spots; a second model with a fresh context
  catches what the first one talked itself past. On the first run (2026-11-11)
  the reviewer independently re-derived the SHA-256 pins of six release binaries
  and checked the kill-path guard in #1029 against its test. The author lane
  only asserted those.

The result is a two-key system: one LLM writes, a different LLM checks and signs,
and Dave keeps the final say over deploys and anything on the stop list.

## Rules (BINDING)

1. **Never `gh pr merge --admin`.** A PreToolUse hook blocks it for Claude
   (`~/.claude/hooks/no_admin_merge.py`); Antigravity has the rule in GEMINI.md.
2. **Never review your own lane's PR.** If you wrote it, send it to a peer:
   `nougenmsg_send` with the PR URL and what to check.
3. **Approve only on evidence you produced yourself.** Read the diff. Run the
   tests locally, and check the claims a test can't (pinned hashes, guards on destructive paths,
   permissions in workflows). Put that evidence in the review body.
4. **The reviewer token approves and comments; that is all.** It does not merge, push or
   resolve threads. The author resolves the threads the reviewer has confirmed are
   fixed, and the owning lane merges with a plain squash once GitHub shows CLEAN.
5. **Request changes when it's not right.** An approval that was never in doubt is
   theater; `--request-changes` with the reason is a real outcome.

## How

```bash
# 1. Read the PR, see checks, unresolved threads and merge state
./.venv/bin/python tools/peer_review.py show <PR> [--repo Who-Visions/NouGenShards]

# 2. Check it out and run the tests yourself (worktree off the PR head)
git fetch origin pull/<PR>/head:rv<PR> && git worktree add "$TMPDIR/rv<PR>" rv<PR>

# 3. Sign with evidence (refuses if checks are failing or the body is empty)
./.venv/bin/python tools/peer_review.py approve <PR> --body "evidence: ..."
./.venv/bin/python tools/peer_review.py request-changes <PR> --body "reason: ..."
```

Then shard the review, file a relay leg for the owning lane to merge, and remove
the worktree.

## Known limits

- The token cannot resolve review threads; the author (WhoVisions) does that.
- A fine-grained token covers only the repos it was granted. A 403 on a repo
  means it needs to be added to the token, not that you should fall back to `--admin`.
- Peer review does not replace Dave on the stop list: deploys to live services,
  spending money, irreversible deletion.
