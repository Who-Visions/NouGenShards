"""
Unit tests for FleetSyncManager auto-sync and rebase dynamics.
Tests target repo validation, branch tracking discovery, and divergence reconciliation.
"""

import subprocess
import pytest
from pathlib import Path
from nougen_shards.fleet_sync import FleetSyncManager, SyncResult


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
