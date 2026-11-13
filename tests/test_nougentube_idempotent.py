"""A repeated or concurrent ingest of one video must not store it twice (eys5TpLWdgQ, 2026-11-12)."""
import os
import time

import pytest

from test_nougentube import URL, VID, _mock_pipeline, tube  # noqa: F401  (temp_vault autouse comes along)
from test_nougentube import temp_vault  # noqa: F401


@pytest.fixture(autouse=True)
def lease_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_TUBE_LEASE_DIR", str(tmp_path / "leases"))
    return tmp_path / "leases"


def test_part_key_is_content_derived():
    a, b = tube.part_key(VID, 1, "x"), tube.part_key(VID, 1, "y")
    assert a.startswith(f"tube:{VID}:part:1:") and a != b and a == tube.part_key(VID, 1, "x")


def test_live_lease_blocks_a_second_run(monkeypatch):
    _mock_pipeline(monkeypatch)
    held = tube.acquire_lease(VID)
    assert held is not None
    writes = []
    monkeypatch.setattr(tube, "grid_capture", lambda *a, **k: writes.append(a) or True)
    assert tube.process_video(URL) == "in-progress" and not writes
    tube.release_lease(held)


def test_stale_lease_is_taken_over(lease_dir):
    held = tube.acquire_lease(VID)
    old = time.time() - tube.LEASE_STALE_S - 5
    os.utime(held, (old, old))
    again = tube.acquire_lease(VID)
    assert again is not None
    tube.release_lease(again)


def test_parts_already_stored_are_not_rewritten(monkeypatch):
    _mock_pipeline(monkeypatch)
    assert tube.process_video(URL) == "captured"
    # Simulate the 524 retry: the video marker is missing but every part key is present.
    monkeypatch.setattr(tube, "dedupe_check", lambda vid: False)
    writes = []
    monkeypatch.setattr(tube, "grid_capture", lambda *a, **k: writes.append(a) or True)
    assert tube.process_video(URL) == "captured" and not writes


def test_lease_is_released_after_a_run(monkeypatch, lease_dir):
    _mock_pipeline(monkeypatch)
    tube.process_video(URL)
    assert not list(lease_dir.glob("*.lease"))
