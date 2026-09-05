"""Dam object paths must be writable on every fleet node, not just POSIX.

`event_id` is `"sha256:<hex>"` (dam/envelope.py). object_path's sanitiser
allowed ":" through, so the store tried to write

    pending/2026/09/05/sha256:9cf9c337....json

NTFS reads a colon as the alternate-data-stream separator, so that raises
OSError WinError 87 "The parameter is incorrect". The temporal shard capture
dam could not spool a single event on whoart or blade -- a durable spool that
does not write on two of the three fleet nodes -- and 10 of its 27 tests
failed there.

It was invisible until the fd_budget collection abort was fixed, because
`pytest tests/` had been dying before it reached this file on Windows at all.
"""
from __future__ import annotations

import pytest

from nougen_shards.dam.store import (LocalDamStore, legacy_object_path,
                                     object_path)

EVENT_ID = "sha256:9cf9c3378f3d94507b7f2d69d5a714f4e1263a8f9c4067da7717668f29a6c628"
CREATED = "2026-09-05T13:00:00Z"

# Every character Windows forbids in a file name.
WINDOWS_FORBIDDEN = set('<>:"/\\|?*')


@pytest.mark.parametrize("prefix", ["pending", "acked", "silt"])
def test_no_windows_forbidden_character_in_the_file_name(prefix):
    name = object_path(prefix, EVENT_ID, CREATED).rsplit("/", 1)[1]
    bad = sorted(WINDOWS_FORBIDDEN & set(name))
    assert not bad, f"{name!r} contains {bad}, unwritable on NTFS"


def test_the_colon_specifically_is_gone():
    assert ":" not in object_path("pending", EVENT_ID, CREATED)
    assert "sha256_" in object_path("pending", EVENT_ID, CREATED)


def test_date_partitioning_is_unchanged():
    assert object_path("pending", EVENT_ID, CREATED).startswith("pending/2026/09/05/")
    assert object_path("pending", EVENT_ID, "").startswith("pending/0000/00/00/")


def test_distinct_events_still_get_distinct_paths():
    """Sanitising must not collapse two ids onto one object."""
    a = object_path("pending", "sha256:" + "a" * 64, CREATED)
    b = object_path("pending", "sha256:" + "b" * 64, CREATED)
    assert a != b


def test_a_real_write_round_trips(tmp_path):
    """The end-to-end failure: this raised WinError 87 before the fix."""
    store = LocalDamStore(tmp_path)
    rel = store.put_pending({"event_id": EVENT_ID, "created_utc": CREATED,
                             "payload": "x"})
    assert (tmp_path / rel).exists()
    assert [e["event_id"] for e in store.list_pending()] == [EVENT_ID]


def test_legacy_colon_object_is_still_seen(tmp_path):
    """Events spooled on POSIX before the fix must not be re-processed."""
    store = LocalDamStore(tmp_path)
    legacy = tmp_path / legacy_object_path("acked", EVENT_ID, CREATED)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    try:
        legacy.write_text("{}", encoding="utf-8")
    except OSError:
        pytest.skip("filesystem refuses ':' in a name, so no legacy objects exist here")
    assert store.is_acked(EVENT_ID, CREATED), "legacy object went unseen"


def test_legacy_path_keeps_the_colon(tmp_path):
    """The read-only fallback must reproduce the OLD spelling exactly."""
    assert ":" in legacy_object_path("pending", EVENT_ID, CREATED)
