"""Regression tests for brain_scan scanner hardening (audit HIGH findings).

Covers: symlinks are not followed (could escape the scanned tree into ~/.ssh),
known credential files are skipped, and an unreadable file does not abort the
scan (stat() is guarded).
"""
import os
from pathlib import Path

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


# --------------------------------------------------------------------------
# The five tests above exercise the predicate in ISOLATION. None of them fail
# if scan_environment stops calling _is_safe_file altogether -- testing that a
# guard exists is not testing that it is invoked. The tests below drive the
# real scan and assert the guard is applied at BOTH call sites (project scan
# and global scan).
# --------------------------------------------------------------------------

def _seed_dangerous(root):
    """Seed a scannable tree with credential stores that must never be ingested.

    `memory/` is a high-signal directory name, so anything with a supported
    extension inside it is a genuine ingest candidate -- only _is_safe_file
    stands between credentials.json and the candidate list.
    """
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    (root / ".ssh").mkdir(exist_ok=True)
    # Canary: a legitimate high-signal file, so a scan that returns nothing at
    # all cannot satisfy these assertions vacuously.
    (mem / "session.md").write_text("notes", encoding="utf-8")
    (mem / "credentials.json").write_text("{}", encoding="utf-8")
    (mem / ".env").write_text("TOKEN=redacted", encoding="utf-8")
    (mem / ".pgpass").write_text("x", encoding="utf-8")
    (mem / "id_rsa").write_text("x", encoding="utf-8")
    (mem / ".git-credentials").write_text("x", encoding="utf-8")
    (root / ".ssh" / "history.json").write_text("{}", encoding="utf-8")
    (root / ".ssh" / "id_rsa").write_text("x", encoding="utf-8")


FORBIDDEN_NAMES = {"credentials.json", ".env", ".pgpass", "id_rsa", ".git-credentials"}


def _assert_no_credentials_ingested(found):
    names = {c.path.name for c in found}
    assert "session.md" in names, "canary missing: the scan ingested nothing at all"
    leaked = names & FORBIDDEN_NAMES
    assert not leaked, f"scan ingested credential files: {sorted(leaked)}"
    assert not any(".ssh" in c.path.parts for c in found), \
        "scan ingested a file from a .ssh danger zone"


def test_project_scan_refuses_credential_files(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    _seed_dangerous(proj)
    # Single-element GLOBAL_ROOTS -> GLOBAL_ROOTS[1:] is empty, so only the
    # project branch runs and the real user home is never touched.
    monkeypatch.setattr(scanner, "GLOBAL_ROOTS", [tmp_path / "nohome"])
    found = scanner.scan_environment(project_path=str(proj), include_unknown=True)
    _assert_no_credentials_ingested(found)


def test_global_scan_refuses_credential_files(tmp_path, monkeypatch):
    fake_global = tmp_path / "fakeglobal"
    _seed_dangerous(fake_global)
    monkeypatch.setattr(scanner, "GLOBAL_ROOTS", [tmp_path / "nohome", fake_global])
    found = scanner.scan_environment(include_unknown=True)
    _assert_no_credentials_ingested(found)


def test_scan_does_not_follow_symlinks_out_of_the_tree(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "session.md"
    secret.write_text("private", encoding="utf-8")

    proj = tmp_path / "proj" / "memory"
    proj.mkdir(parents=True)
    (proj / "session.md").write_text("notes", encoding="utf-8")
    link = proj / "linked_session.md"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    monkeypatch.setattr(scanner, "GLOBAL_ROOTS", [tmp_path / "nohome"])
    found = scanner.scan_environment(project_path=str(tmp_path / "proj"),
                                     include_unknown=True)
    names = {c.path.name for c in found}
    assert "session.md" in names           # canary
    assert "linked_session.md" not in names
