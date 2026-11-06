---
name: github-ssh
description: Use when git push/pull/clone to GitHub fails on auth, asks for a token, or hangs on a credential helper; when setting up a fleet machine for GitHub; when adding an SSH key at github.com/settings/ssh; or when checking which repos use SSH vs HTTPS. Covers the key, the global https->ssh rewrite, the exit-code-1 trap, and the tool NouGen/tools/github_ssh.py. Does not cover gh API auth (PRs, issues) — that still uses gh's own token.
---

# GitHub over SSH

Git talks to GitHub with an SSH key, not a token. No expiry, no revocation surprises,
and no `gh auth git-credential` helper on every push. That helper once ran away on
WhoArt and grew the pagefile to 56 GB.

## The tool

```
python tools/github_ssh.py status   # keys, live auth, rewrite on/off, this repo's remotes
python tools/github_ssh.py setup    # turn on the rewrite, then test
python tools/github_ssh.py test     # ssh -T plus a real ls-remote through the rewrite
python tools/github_ssh.py undo     # turn the rewrite off
```

Exit 0 means healthy. It never prints private key material.

## How it is wired

1. **Key.** `~/.ssh/id_ed25519.pub` is registered on the WhoVisions GitHub account
   (WhoArt's key is titled `WhoArt-NGS-Git`, added 11/6/2026). The private half never leaves the machine.
2. **Global rewrite.** `git config --global url."git@github.com:".insteadOf "https://github.com/"`
   sends every `https://github.com/...` remote and clone through SSH. No per-repo edits needed.
3. **Remotes.** You can still set remotes to `git@github.com:Owner/Repo.git` explicitly.
   That works with or without the rewrite.

## New machine

1. `ssh-keygen -t ed25519` if `~/.ssh` has no `.pub`.
2. Paste the `.pub` contents at github.com/settings/ssh/new as an Authentication Key,
   titled `<Host>-NGS-Git`. Only the operator can click Add, so ask once with the key already on the clipboard
   (`Get-Content ~\.ssh\id_ed25519.pub | Set-Clipboard`).
3. `python tools/github_ssh.py setup`.

## Traps

- **`ssh -T git@github.com` exits 1 on success.** GitHub refuses a shell. Read the text
  ("successfully authenticated"), not the exit code. The tool already does this.
- **gh is separate.** `gh pr create` and other API calls use gh's token, not the key.
  A green SSH test says nothing about gh.
- **Org access.** The key carries the account's permissions. A repo in another org
  (e.g. `nougenai/nougen`) works only if WhoVisions has access. That one was verified 11/6/2026.
- **First connect.** Use `StrictHostKeyChecking=accept-new` for automated lanes, or the
  host-key prompt blocks with no TTY.
