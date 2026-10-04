"""Immutable, read-only filesystem snapshotting for RSI artifact evaluation.

Mitigates TOCTOU (CWE-367) attacks where candidate workspaces alter code
between reservation and scoring. Creates an evaluator-owned directory copy,
computes deterministic SHA-256 tree hashes post-copy, and strips write permissions
before handing the root to the evaluator.
"""

from __future__ import annotations

import hashlib
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Tuple


def compute_tree_digest(root_path: Path) -> str:
    """Computes a deterministic digest of all files and relative paths in root."""
    entries = []
    for p in sorted(root_path.rglob("*")):
        if p.is_file() and not p.is_symlink():
            rel = p.relative_to(root_path).as_posix()
            data = p.read_bytes()
            fhash = hashlib.sha256(data).hexdigest()
            entries.append(f"{rel}:{len(data)}:{fhash}")
    blob = "\n".join(entries).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_tree_readonly(root_path: Path) -> None:
    """Recursively removes write permissions from files and directories."""
    for p in root_path.rglob("*"):
        mode = p.stat().st_mode
        if p.is_file():
            p.chmod(mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
        elif p.is_dir():
            p.chmod(mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def restore_tree_writable(root_path: Path) -> None:
    """Restores user write permissions to allow cleanup."""
    for p in root_path.rglob("*"):
        mode = p.stat().st_mode
        p.chmod(mode | stat.S_IWUSR)


@contextmanager
def evaluator_readonly_snapshot(source_root: str | Path) -> Iterator[Tuple[Path, str]]:
    """Copies source_root into an isolated evaluator-owned directory, locks permissions,
    and yields (snapshot_path, post_copy_digest). Cleans up safely on exit.
    """
    src = Path(source_root).resolve()
    if not src.exists() or not src.is_dir():
        raise ValueError(f"Source directory does not exist: {src}")

    tmp_dir = tempfile.mkdtemp(prefix="rsi_snapshot_")
    snap_path = Path(tmp_dir) / "eval_root"

    try:
        shutil.copytree(src, snap_path, symlinks=False)
        digest = compute_tree_digest(snap_path)
        make_tree_readonly(snap_path)
        yield snap_path, digest
    finally:
        restore_tree_writable(snap_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
