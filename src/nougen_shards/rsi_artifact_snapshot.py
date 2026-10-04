"""Immutable, read-only filesystem snapshotting for RSI artifact evaluation.

Mitigates TOCTOU (CWE-367) attacks where candidate workspaces alter code
between reservation and scoring. Creates an evaluator-owned directory copy,
computes deterministic SHA-256 tree hashes post-copy, strips write permissions
before handing the root to the evaluator, and re-hashes the snapshot afterwards.

Symlinks, hardlinked files and special files (FIFO, device, socket) are refused, never
followed (CWE-59). Read-only permissions only stop accidents: code running as the same uid
can chmod and write. The post-evaluation re-hash detects an unrestored mutation; a
mutate-and-restore by same-uid code is NOT detected (needs a separate uid or a read-only
mount), and a directory swapped for a symlink between scan and descent is a residual race.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Tuple


class SnapshotRefused(ValueError):
    """The source tree holds a symlink, hardlinked file or special file."""


class SnapshotMutated(RuntimeError):
    """The snapshot changed while the evaluator held it."""


# O_NONBLOCK keeps a FIFO swapped in after the scan from hanging open(); O_NOFOLLOW is POSIX-only.
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


def _copy_tree_strict(src: Path, dst: Path) -> None:
    dst.mkdir(mode=0o700)
    for entry in sorted(os.scandir(src), key=lambda e: e.name):
        st = entry.stat(follow_symlinks=False)
        target = dst / entry.name
        if stat.S_ISDIR(st.st_mode):
            _copy_tree_strict(Path(entry.path), target)
        elif stat.S_ISREG(st.st_mode):
            try:
                fd = os.open(entry.path, _OPEN_FLAGS)
            except OSError as exc:  # ELOOP: swapped for a symlink after the scan
                raise SnapshotRefused(f"{entry.path}: {exc.strerror}") from exc
            try:
                fst = os.fstat(fd)
                if not stat.S_ISREG(fst.st_mode) or fst.st_nlink > 1:
                    raise SnapshotRefused(f"{entry.path}: not a plain single-link file")
                with os.fdopen(fd, "rb", closefd=False) as fh:
                    data = fh.read()
            finally:
                os.close(fd)
            target.write_bytes(data)
            target.chmod(stat.S_IMODE(fst.st_mode))
        else:
            raise SnapshotRefused(f"{entry.path}: symlink or special file")


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
        _copy_tree_strict(src, snap_path)
        digest = compute_tree_digest(snap_path)
        make_tree_readonly(snap_path)
        yield snap_path, digest
        if compute_tree_digest(snap_path) != digest:
            raise SnapshotMutated("snapshot changed during evaluation")
    finally:
        restore_tree_writable(snap_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
