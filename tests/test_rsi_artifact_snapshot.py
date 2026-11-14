from __future__ import annotations

import os
import stat
import subprocess
from contextlib import contextmanager

import pytest
from pathlib import Path
import nougen_shards.rsi_artifact_snapshot as snapshot_module
from nougen_shards.rsi_artifact_snapshot import (
    SnapshotMutated,
    SnapshotRefused,
    evaluator_readonly_snapshot,
    compute_tree_digest,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="symlink/FIFO semantics tested on POSIX")


def test_evaluator_readonly_snapshot_locks_permissions(tmp_path: Path):
    src = tmp_path / "candidate_src"
    src.mkdir()
    f1 = src / "solver.py"
    f1.write_text("def solve(): return 42")

    orig_digest = compute_tree_digest(src)

    with evaluator_readonly_snapshot(src) as (snap, snap_digest):
        assert snap_digest == orig_digest
        snap_file = snap / "solver.py"
        assert snap_file.read_text() == "def solve(): return 42"

        # Verify read-only enforcement: attempting to overwrite must raise PermissionError
        with pytest.raises(PermissionError):
            snap_file.write_text("def solve(): return 0")


def test_evaluator_snapshot_prevents_toctou_mutation(tmp_path: Path):
    src = tmp_path / "candidate_src"
    src.mkdir()
    f1 = src / "solver.py"
    f1.write_text("def solve(): return 100")

    with evaluator_readonly_snapshot(src) as (snap, snap_digest):
        # Even if candidate alters original source directory after copy:
        f1.write_text("def solve(): return 666")

        # Snapshot remains untampered and matches post-copy digest
        snap_file = snap / "solver.py"
        assert snap_file.read_text() == "def solve(): return 100"
        assert compute_tree_digest(snap) == snap_digest


@posix_only
def test_symlink_is_refused_and_outside_bytes_never_enter_the_snapshot(tmp_path: Path):
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / "secret.txt").write_text("SECRET")
    cand = tmp_path / "cand"; cand.mkdir()
    (cand / "innocent.py").symlink_to(outside / "secret.txt")
    with pytest.raises(SnapshotRefused):
        with evaluator_readonly_snapshot(cand):
            pytest.fail("snapshot must not be handed to the evaluator")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_junction_is_refused_and_outside_bytes_never_enter_snapshot(tmp_path: Path):
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / "secret.txt").write_text("SECRET")
    cand = tmp_path / "cand"; cand.mkdir()
    junction = cand / "linked-dir"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with pytest.raises(SnapshotRefused):
        with evaluator_readonly_snapshot(cand):
            pytest.fail("snapshot must not traverse a junction outside the candidate")


@pytest.mark.skipif(os.name != "nt", reason="Windows directory-handle sharing semantics")
def test_windows_child_directory_cannot_be_replaced_during_scan(tmp_path: Path, monkeypatch):
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / "secret.txt").write_text("SECRET")
    cand = tmp_path / "cand"; cand.mkdir()
    child = cand / "child"; child.mkdir()
    original_scandir = os.scandir
    state = {"attempted": False, "blocked": False, "swapped": False}

    def racing_scandir(path):
        if Path(path) == child and not state["attempted"]:
            state["attempted"] = True
            try:
                child.rmdir()
            except OSError as exc:
                state["blocked"] = getattr(exc, "winerror", None) == 32
            else:
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(child), str(outside)],
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, result.stderr
                state["swapped"] = True
        return original_scandir(path)

    monkeypatch.setattr(snapshot_module.os, "scandir", racing_scandir)
    with evaluator_readonly_snapshot(cand) as (snap, _):
        assert state["attempted"]
        assert state["blocked"]
        assert not state["swapped"]
        assert not (snap / "child" / "secret.txt").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows directory-handle and junction semantics")
def test_windows_child_directory_swap_before_handle_open_is_refused(tmp_path: Path, monkeypatch):
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / "secret.txt").write_text("SECRET")
    cand = tmp_path / "cand"; cand.mkdir()
    child = cand / "child"; child.mkdir()
    displaced = cand / "displaced"
    state = {"attempted": False, "blocked": False, "swapped": False}
    original_hold = snapshot_module._hold_windows_directory
    original_write_bytes = Path.write_bytes
    copied_secrets = []

    def record_secret_copy(path, data):
        if path.name == "secret.txt":
            copied_secrets.append(path)
        return original_write_bytes(path, data)

    @contextmanager
    def racing_hold(path, expected_stat):
        if Path(path) == child and not state["attempted"]:
            state["attempted"] = True
            try:
                child.rename(displaced)
            except OSError as exc:
                state["blocked"] = getattr(exc, "winerror", None) == 32
            else:
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(child), str(outside)],
                    capture_output=True,
                    text=True,
                )
                assert result.returncode == 0, result.stderr
                state["swapped"] = True
        with original_hold(path, expected_stat):
            yield

    monkeypatch.setattr(snapshot_module, "_hold_windows_directory", racing_hold)
    monkeypatch.setattr(Path, "write_bytes", record_secret_copy)
    try:
        try:
            with evaluator_readonly_snapshot(cand):
                assert state["attempted"]
        except SnapshotRefused:
            assert state["swapped"]
        else:
            assert state["blocked"]
        assert copied_secrets == []
    finally:
        if state["swapped"]:
            child.rmdir()
            displaced.rmdir()


def test_hardlinked_file_is_refused(tmp_path: Path):
    outside = tmp_path / "shared.txt"; outside.write_text("SHARED")
    cand = tmp_path / "cand"; cand.mkdir()
    os.link(outside, cand / "linked.py")
    with pytest.raises(SnapshotRefused):
        with evaluator_readonly_snapshot(cand):
            pytest.fail("snapshot must not be handed to the evaluator")


@posix_only
def test_fifo_is_refused_without_hanging(tmp_path: Path):
    cand = tmp_path / "cand"; cand.mkdir()
    os.mkfifo(cand / "pipe")
    with pytest.raises(SnapshotRefused):
        with evaluator_readonly_snapshot(cand):
            pytest.fail("snapshot must not be handed to the evaluator")


@posix_only
def test_unrestored_mutation_during_evaluation_is_detected(tmp_path: Path):
    cand = tmp_path / "cand"; cand.mkdir()
    (cand / "a.py").write_text("GOOD")
    with pytest.raises(SnapshotMutated):
        with evaluator_readonly_snapshot(cand) as (snap, _digest):
            f = snap / "a.py"
            f.chmod(stat.S_IRUSR | stat.S_IWUSR)    # read-only is advisory for the same uid
            f.write_text("EVIL")


@posix_only
@pytest.mark.xfail(strict=True, reason="residual: same-uid mutate-and-restore inside the snapshot is not detected")
def test_mutate_and_restore_is_detected(tmp_path: Path):
    cand = tmp_path / "cand"; cand.mkdir()
    (cand / "a.py").write_text("GOOD")
    with pytest.raises(SnapshotMutated):
        with evaluator_readonly_snapshot(cand) as (snap, _digest):
            f = snap / "a.py"
            f.chmod(stat.S_IRUSR | stat.S_IWUSR)
            f.write_text("EVIL")                     # evaluator-side reader sees EVIL here
            f.write_text("GOOD")                     # restored before the final hash
