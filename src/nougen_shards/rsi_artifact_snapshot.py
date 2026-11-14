"""Immutable, read-only filesystem snapshotting for RSI artifact evaluation.

Mitigates TOCTOU (CWE-367) attacks where candidate workspaces alter code
between reservation and scoring. Creates an evaluator-owned directory copy,
computes deterministic SHA-256 tree hashes post-copy, strips write permissions
before handing the root to the evaluator, and re-hashes the snapshot afterwards.

Symlinks, hardlinked files and special files (FIFO, device, socket) are refused, never
followed (CWE-59). Read-only permissions only stop accidents: code running as the same uid
can chmod and write. The post-evaluation re-hash detects an unrestored mutation; a
mutate-and-restore by same-uid code is NOT detected (needs a separate uid or a read-only
mount). Windows descendant directories are pinned while scanned to block replacement races;
source-root ancestors and POSIX path-based directory descent remain residual race surfaces.
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


@contextmanager
def _hold_windows_directory(path: Path, expected_stat: os.stat_result) -> Iterator[None]:
    """Pin a Windows directory against replacement while its children are scanned."""
    if os.name != "nt":
        yield
        return

    import ctypes
    from ctypes import wintypes

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_low", wintypes.DWORD),
            ("creation_high", wintypes.DWORD),
            ("access_low", wintypes.DWORD),
            ("access_high", wintypes.DWORD),
            ("write_low", wintypes.DWORD),
            ("write_high", wintypes.DWORD),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("link_count", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_ByHandleFileInformation),
    ]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    # FILE_LIST_DIRECTORY, FILE_SHARE_READ, OPEN_EXISTING,
    # FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT.
    handle = kernel32.CreateFileW(
        str(path), 0x0001, 0x0001, None, 3, 0x02000000 | 0x00200000, None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise SnapshotRefused(f"{path}: cannot pin directory ({ctypes.get_last_error()})")

    try:
        info = _ByHandleFileInformation()
        if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise SnapshotRefused(f"{path}: cannot inspect pinned directory ({ctypes.get_last_error()})")
        if info.attributes & 0x00000400:
            raise SnapshotRefused(f"{path}: reparse point")
        if not info.attributes & 0x00000010:
            raise SnapshotRefused(f"{path}: not a directory")
        file_id = (info.file_index_high << 32) | info.file_index_low
        if (expected_stat.st_dev, expected_stat.st_ino) != (info.volume_serial, file_id):
            raise SnapshotRefused(f"{path}: directory changed after scan")
        yield
    finally:
        kernel32.CloseHandle(handle)


def _copy_tree_strict(
    src: Path, dst: Path, expected_stat: os.stat_result | None = None,
) -> None:
    dst.mkdir(mode=0o700)
    expected = expected_stat or src.lstat()
    with _hold_windows_directory(src, expected):
        for entry in sorted(os.scandir(src), key=lambda e: e.name):
            st = entry.stat(follow_symlinks=False)
            if os.name == "nt":
                # Windows DirEntry metadata may omit the file ID (st_dev/st_ino = 0).
                # The parent handle is held without share-delete/write while this stat runs.
                st = os.stat(entry.path, follow_symlinks=False)
            reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & reparse:
                raise SnapshotRefused(f"{entry.path}: symlink or reparse point")
            target = dst / entry.name
            if stat.S_ISDIR(st.st_mode):
                _copy_tree_strict(Path(entry.path), target, st)
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
