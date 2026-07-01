"""Regression tests for brain_scan scanner hardening (audit HIGH findings).

Covers: symlinks are not followed (could escape the scanned tree into ~/.ssh),
known credential files are skipped, and an unreadable file does not abort the
scan (stat() is guarded).
"""
import os

import pytest

from nougen_shards.brain_scan import scanner


def test_symlink_is_not_safe(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}")
    link = tmp_path / "link.json"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    assert scanner._is_safe_file(real) is True
    assert scanner._is_safe_file(link) is False  # symlinks skipped outright


@pytest.mark.parametrize("name", [".netrc", ".git-credentials", ".pgpass", ".env", "credentials.json"])
def test_credential_files_are_skipped(tmp_path, name):
    f = tmp_path / name
    f.write_text("secret")
    assert scanner._is_safe_file(f) is False


def test_safe_size_handles_unreadable(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    # No exception; returns None so the caller skips rather than crashing.
    assert scanner._safe_size_mb(missing) is None


def test_safe_size_returns_mb(tmp_path):
    f = tmp_path / "f.json"
    f.write_bytes(b"x" * (1024 * 1024))  # 1 MB
    size = scanner._safe_size_mb(f)
    assert size is not None and abs(size - 1.0) < 0.01


def test_danger_dir_still_blocked(tmp_path):
    # _is_safe_file also rejects files under danger dirs (.ssh/.aws).
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    key = ssh / "config.json"
    key.write_text("{}")
    assert scanner._is_safe_file(key) is False
