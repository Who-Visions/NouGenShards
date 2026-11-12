"""
Unit tests for FleetSyncManager auto-sync and rebase dynamics.
Tests target repo validation, branch tracking discovery, and divergence reconciliation.
"""

import subprocess
from nougen_shards.fleet_sync import FleetSyncManager


def test_is_target_repo(tmp_path):
    manager = FleetSyncManager()

    # Create dummy git repo with non-whovisions remote
    repo_ext = tmp_path / "external_repo"
    repo_ext.mkdir()
    subprocess.run(["git", "-C", str(repo_ext), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_ext), "remote", "add", "origin", "https://github.com/foo/bar.git"], check=True, capture_output=True)

    is_target, url = manager.is_target_repo(repo_ext)
    assert is_target is False
    assert url == "https://github.com/foo/bar.git"

    # Set remote to Who-Visions
    subprocess.run(["git", "-C", str(repo_ext), "remote", "set-url", "origin", "https://github.com/Who-Visions/test.git"], check=True, capture_output=True)
    is_target_wv, url_wv = manager.is_target_repo(repo_ext)
    assert is_target_wv is True
    assert "who-visions" in url_wv.lower()


def test_discover_repositories(tmp_path):
    root_1 = tmp_path / "Observatory"
    root_1.mkdir()

    repo_a = root_1 / "RepoA"
    repo_a.mkdir()
    subprocess.run(["git", "-C", str(repo_a), "init"], check=True, capture_output=True)

    repo_b = root_1 / "RepoB"
    repo_b.mkdir()
    subprocess.run(["git", "-C", str(repo_b), "init"], check=True, capture_output=True)

    non_repo = root_1 / "NotARepo"
    non_repo.mkdir()

    manager = FleetSyncManager(target_roots=[root_1])
    discovered = manager.discover_repositories()
    discovered_names = [p.name for p in discovered]
    assert "RepoA" in discovered_names
    assert "RepoB" in discovered_names
    assert "NotARepo" not in discovered_names


def test_sync_repository_skipped_on_non_target(tmp_path):
    repo_ext = tmp_path / "foo"
    repo_ext.mkdir()
    subprocess.run(["git", "-C", str(repo_ext), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_ext), "remote", "add", "origin", "https://github.com/other/repo.git"], check=True, capture_output=True)

    manager = FleetSyncManager()
    result = manager.sync_repository(repo_ext)
    assert result.status == "skipped"
    assert "Not a WhoVisions" in result.details


def test_sync_repository_autostash_unmerged_conflict_aborts(tmp_path, monkeypatch):
    repo = tmp_path / "nougen_repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    manager = FleetSyncManager()

    def fake_run_git(path, args, timeout=30):
        cmd = tuple(args)
        if cmd == ("config", "--get", "remote.origin.url"):
            return 0, "https://github.com/Who-Visions/NouGenShards.git", ""
        if cmd == ("branch", "--show-current"):
            return 0, "main", ""
        if cmd == ("status", "--porcelain"):
            # First call (pre-pull): 1 dirty file; second call (post-pull): autostash conflict UU
            if getattr(fake_run_git, "pulled", False):
                return 0, "UU README.md", ""
            return 0, " M README.md", ""
        if cmd[0] in ("config", "fetch"):
            return 0, "", ""
        if cmd == ("rev-parse", "--abbrev-ref", "@{u}"):
            return 0, "origin/main", ""
        if cmd == ("rev-list", "--left-right", "--count", "HEAD...origin/main"):
            return 0, "0\t1", ""
        if cmd[:3] == ("pull", "--rebase", "--autostash"):
            fake_run_git.pulled = True
            return 0, "Autostash pop conflict", ""
        return 0, "", ""

    monkeypatch.setattr(manager, "_run_git", fake_run_git)
    result = manager.sync_repository(repo)
    assert result.status == "conflict_aborted"
    assert "UU README.md" in (result.error or "")
