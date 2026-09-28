r'''
Fleet Auto-Sync & Rebase Engine (Module: Repository Synchronizer).
Automates the safe detection, synchronization, stashing, rebasing, and fast-forwarding
of fleet git repositories across WhoVisions and Who-Visions without requiring users
to manually execute git stash -> fetch -> pull --rebase sequences.

Mathematical Foundations & State Transition Model:
1. Operational State Graph:
   Let $S \in \{\text{CLEAN}, \text{DIRTY}, \text{DETACHED}, \text{NO\_REMOTE}\}$
   - If $S = \text{DIRTY}$:
     $\mathcal{T}_{\text{autostash}}: \text{git stash create} \to \text{rebase} \to \text{git stash pop}$
   - If ahead > 0 and behind == 0:
     $\mathcal{T}_{\text{push}}: \text{git push -u origin } b$
   - If ahead == 0 and behind > 0:
     $\mathcal{T}_{\text{fast\_forward}}: \text{git rebase origin/}b$
   - If ahead > 0 and behind > 0 (diverged):
     $\mathcal{T}_{\text{rebase\_safe}}: \text{git pull --rebase --autostash origin } b$

2. Divergence Distance & Conflict Safety Metric:
   $\Delta(L, R) = |H_L \setminus H_R| + |H_R \setminus H_L|$
   If rebase encounters merge conflicts, automatic rollback $\mathcal{T}_{\text{abort}}$
   restores pristine local working directory and leaves an explicit incident log.
'''

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class SyncResult:
    repo_name: str
    path: str
    branch: str
    remote_url: str
    status: str             # "synced", "up_to_date", "pushed", "stashed_and_rebased", "conflict_aborted", "skipped"
    ahead: int = 0
    behind: int = 0
    dirty_files: int = 0
    details: str = ""
    error: Optional[str] = None


class FleetSyncManager:
    """
    Automated zero-babysitting repository synchronizer.
    Finds and updates local checkouts to the latest upstream refs.
    """

    def __init__(
        self,
        target_roots: Optional[List[Path]] = None,
        org_filter: Tuple[str, ...] = ("whovisions", "who-visions"),
        timeout_seconds: int = 30
    ):
        self.target_roots = target_roots or [
            Path.home() / "The Observatory",
            Path.home() / "The Observatory" / "NouGen",
            Path.home() / ".nougen" / "src",
            Path.home() / "Watchtower" / "NouGen"
        ]
        self.org_filter = tuple(o.lower() for o in org_filter)
        self.timeout = timeout_seconds

    def discover_repositories(self, explicit_paths: Optional[List[Path]] = None) -> List[Path]:
        """Discovers all valid git repositories under target roots."""
        if explicit_paths:
            return [p.resolve() for p in explicit_paths if p.is_dir() and (p / ".git").exists()]

        discovered: Set[Path] = set()
        for root in self.target_roots:
            if not root.exists():
                continue
            # Direct check if root itself is a repo
            if (root / ".git").exists():
                discovered.add(root.resolve())
            try:
                for child in root.iterdir():
                    if child.is_dir() and (child / ".git").exists():
                        discovered.add(child.resolve())
            except OSError:
                continue

        return sorted(list(discovered))

    def _run_git(self, repo: Path, args: List[str]) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except subprocess.TimeoutExpired:
            return 124, "", f"Timed out after {self.timeout}s"
        except Exception as e:
            return 1, "", str(e)

    def is_target_repo(self, repo: Path) -> Tuple[bool, str]:
        """Verifies if repository belongs to WhoVisions or Who-Visions."""
        code, out, _ = self._run_git(repo, ["config", "--get", "remote.origin.url"])
        if code != 0 or not out:
            return False, ""
        url_lower = out.lower()
        matches = any(org in url_lower for org in self.org_filter)
        return matches, out

    def sync_repository(
        self,
        repo: Path,
        auto_push: bool = True,
        rebase_dirty: bool = True
    ) -> SyncResult:
        """
        Synchronizes a single repository:
        1. Validates remote.origin.url
        2. Detects branch & porcelain status
        3. Fetches upstream
        4. Rebase/pulls with autostash
        5. Pushes unpushed commits if auto_push is enabled
        """
        is_target, remote_url = self.is_target_repo(repo)
        if not is_target:
            return SyncResult(
                repo_name=repo.name,
                path=str(repo),
                branch="",
                remote_url=remote_url,
                status="skipped",
                details="Not a WhoVisions/Who-Visions repository"
            )

        # 1. Identify active branch
        _, branch, _ = self._run_git(repo, ["branch", "--show-current"])
        if not branch:
            # Detached HEAD
            _, head_commit, _ = self._run_git(repo, ["rev-parse", "--short", "HEAD"])
            return SyncResult(
                repo_name=repo.name,
                path=str(repo),
                branch=f"DETACHED_{head_commit}",
                remote_url=remote_url,
                status="skipped",
                details="Repository is in detached HEAD state"
            )

        # 2. Check porcelain status
        _, status_out, _ = self._run_git(repo, ["status", "--porcelain"])
        dirty_lines = [l for l in status_out.splitlines() if l.strip()]
        dirty_count = len(dirty_lines)

        # 3. Ensure wildcard fetch refspec exists so all remote branches are tracked
        self._run_git(repo, ["config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"])

        # 4. Fetch upstream
        code, _, fetch_err = self._run_git(repo, ["fetch", "--all", "--prune"])
        if code != 0:
            return SyncResult(
                repo_name=repo.name,
                path=str(repo),
                branch=branch,
                remote_url=remote_url,
                status="error",
                error=f"Fetch failed: {fetch_err}"
            )

        # 5. Check tracking branch & ahead/behind counts
        code, tracking_branch, _ = self._run_git(repo, ["rev-parse", "--abbrev-ref", "@{u}"])
        if code != 0 or not tracking_branch:
            # Check if remote branch exists with same name on origin
            code, ls_out, _ = self._run_git(repo, ["ls-remote", "--heads", "origin", branch])
            if ls_out:
                self._run_git(repo, ["branch", "-u", f"origin/{branch}"])
                tracking_branch = f"origin/{branch}"
            else:
                # Local feature branch not yet pushed
                if auto_push and dirty_count == 0:
                    code_push, _, push_err = self._run_git(repo, ["push", "-u", "origin", branch])
                    if code_push == 0:
                        return SyncResult(
                            repo_name=repo.name,
                            path=str(repo),
                            branch=branch,
                            remote_url=remote_url,
                            status="pushed",
                            ahead=0,
                            behind=0,
                            dirty_files=0,
                            details="New feature branch pushed and upstream tracking configured"
                        )
                return SyncResult(
                    repo_name=repo.name,
                    path=str(repo),
                    branch=branch,
                    remote_url=remote_url,
                    status="up_to_date" if dirty_count == 0 else "dirty_local",
                    ahead=1 if not ls_out else 0,
                    dirty_files=dirty_count,
                    details=f"Local branch with {dirty_count} uncommitted files (no upstream tracking)"
                )

        # 6. Compute Ahead / Behind
        _, count_out, _ = self._run_git(repo, ["rev-list", "--left-right", "--count", f"HEAD...{tracking_branch}"])
        ahead, behind = 0, 0
        if count_out:
            parts = count_out.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

        # 7. Apply Rebase / Autostash
        if behind > 0:
            rebase_args = ["pull", "--rebase", "--autostash", "origin", branch]
            code_rebase, _, rebase_err = self._run_git(repo, rebase_args)
            if code_rebase != 0:
                # Abort rebase to preserve pristine working tree
                self._run_git(repo, ["rebase", "--abort"])
                return SyncResult(
                    repo_name=repo.name,
                    path=str(repo),
                    branch=branch,
                    remote_url=remote_url,
                    status="conflict_aborted",
                    ahead=ahead,
                    behind=behind,
                    dirty_files=dirty_count,
                    error=f"Rebase encountered conflict; safely aborted: {rebase_err}"
                )
            behind = 0

        # 8. Push if ahead and auto_push is enabled
        if ahead > 0 and auto_push:
            code_push, _, push_err = self._run_git(repo, ["push", "origin", branch])
            if code_push == 0:
                ahead = 0
                return SyncResult(
                    repo_name=repo.name,
                    path=str(repo),
                    branch=branch,
                    remote_url=remote_url,
                    status="synced",
                    ahead=0,
                    behind=0,
                    dirty_files=dirty_count,
                    details="Rebased and pushed ahead commits to remote"
                )
            else:
                return SyncResult(
                    repo_name=repo.name,
                    path=str(repo),
                    branch=branch,
                    remote_url=remote_url,
                    status="rebased_push_failed",
                    ahead=ahead,
                    behind=0,
                    dirty_files=dirty_count,
                    error=f"Rebased successfully but push rejected: {push_err}"
                )

        status_label = "synced" if (behind == 0 and ahead == 0) else "up_to_date"
        return SyncResult(
            repo_name=repo.name,
            path=str(repo),
            branch=branch,
            remote_url=remote_url,
            status=status_label,
            ahead=ahead,
            behind=behind,
            dirty_files=dirty_count,
            details="Aligned with remote tracking"
        )

    def sync_all(
        self,
        explicit_paths: Optional[List[Path]] = None,
        auto_push: bool = True
    ) -> List[SyncResult]:
        """Synchronizes all discovered repositories."""
        repos = self.discover_repositories(explicit_paths)
        results = []
        for r in repos:
            res = self.sync_repository(r, auto_push=auto_push)
            results.append(res)
        return results
