---
name: nougen-git
description: Use whenever a change is about to be committed to any Who-Visions repo, when a PR needs opening or merging, when a push is refused by a protected branch, or when deciding where a commit should land. Covers the one flow the GM allows — branch, PR, clean merge to main, in the same session — the per-repo merge rules, the protected-branch and auto-merge traps, and how to move a commit onto a branch without wiping the working tree. Does not cover commit-message wording (structured-git-commit-messages) or handoff legs (relay).
---

# NouGen git — branch, PR, merge clean, same session

GM directive, 2026-09-25 (Dave): **"always up a branch to PR and merge cleanly to main."**
Merging is part of the job. A PR left open is a baton lying on the track; a push straight
to main leaves no trail and gets refused on protected repos anyway.

Nothing here is specific to one machine or one person. Every value is derived from the
repo you are standing in, so any lane on any box runs the same flow.

## The flow

```bash
git checkout -b <type>/<slug>            # BEFORE the first edit, never after
# ... edit, test ...
git add <specific paths>                  # never -A into a repo with stray files
git commit                                # message per structured-git-commit-messages
git push -u origin <type>/<slug>
gh pr create -R "$(gh repo view --json nameWithOwner -q .nameWithOwner)" --base main --head <type>/<slug> --title "..." --body "..."
gh pr merge <n> -R <owner/repo> --squash --delete-branch      # see per-repo rule below
git checkout main && git pull --ff-only origin main
git branch -D <type>/<slug>
```

Pin `-R <owner/repo>` on every `gh` write. Shell cwd persists across tool calls and a
`gh pr merge` from the wrong directory has hit the wrong repo before.

## Per-repo merge rule

Read it from the repo, never from memory:

```bash
gh api repos/<owner>/<repo> -q '{squash:.allow_squash_merge, merge:.allow_merge_commit, rebase:.allow_rebase_merge, auto:.allow_auto_merge, delete:.delete_branch_on_merge}'
gh api repos/<owner>/<repo>/branches/main/protection -q '{checks:.required_status_checks.contexts, admins:.enforce_admins.enabled}'
```

- If only `squash` is allowed, `--squash`. If `auto` is false, `gh pr merge --auto` fails
  with `enablePullRequestAutoMerge` — you wait for the checks and merge by hand.
- If `enforce_admins` is true, `--admin` does nothing; green checks are the only door.
- Required checks are named in `contexts`. A PR with `mergeStateStatus: BLOCKED` and
  `pending > 0` is waiting on them, not broken. Do not poll in a loop; check once when
  you come back to it, or let the app's PR monitor tell you.

## Moving a commit that landed on main by mistake

Protected `main` refuses the push, so the commit has to move to a branch. Do it without
touching the working tree:

```bash
git branch <type>/<slug> HEAD             # new branch at the commit
git checkout <type>/<slug>                # stay on it -- the fix stays on disk
git branch -f main origin/main            # main back to remote, working tree untouched
```

**Never `git reset --hard origin/main` for this.** It rewinds the files on disk too, so the
box runs the old code until the PR merges. That happened once with `tools/fleet.py`
(2026-09-25) and the lane was running the unfixed dispatcher for the gap.

## What "clean" means

- One branch, one PR, one concern. Unrelated fixes discovered on the way get their own branch.
- Tests run before the push, on the branch, and their result goes in the PR body.
- The PR body says what changed and why, not how; the shard id if there is one.
- Merge, sync main, delete the branch. Local and remote end the session on `main`, ahead 0.
- No `--no-verify`, no force-push, no amend of anything already pushed.

## Before opening a PR

Check what already landed — a PR for something already merged is noise:

```bash
gh pr list -R <owner/repo> --state all --search "<slug or keyword>" --limit 5
git log --oneline -S "<distinctive string>" origin/main | head
```

## Related skills

- `structured-git-commit-messages` — the message itself.
- `relay` — claim the scope before editing, leg it when the session ends.
