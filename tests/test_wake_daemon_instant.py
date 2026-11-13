"""Tests for instant Win32 directory-change wake in nougen_shards.wake_daemon."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from nougen_shards import wake_daemon


def test_wait_for_change_wakes_promptly_on_new_file(tmp_path: Path) -> None:
    """Writing a file into a watched dir wakes _wait_for_change before timeout."""
    if os.name != "nt":
        return

    def _writer() -> None:
        time.sleep(0.08)
        (tmp_path / "ping.json").write_text('{"text": "hi"}', encoding="utf-8")

    t = threading.Thread(target=_writer, daemon=True)
    t.start()
    started = time.monotonic()
    wake_daemon._wait_for_change([tmp_path], 5.0)
    elapsed = time.monotonic() - started
    t.join(timeout=1.0)
    assert elapsed < 1.5


def test_wait_for_change_handles_missing_dirs(tmp_path: Path) -> None:
    """Missing directories fall back cleanly without raising."""
    missing = tmp_path / "does_not_exist"
    started = time.monotonic()
    wake_daemon._wait_for_change([missing], 0.25)
    assert time.monotonic() - started >= 0.2
