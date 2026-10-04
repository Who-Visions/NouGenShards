from __future__ import annotations

import pytest
from pathlib import Path
from nougen_shards.rsi_artifact_snapshot import (
    evaluator_readonly_snapshot,
    compute_tree_digest,
)


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
