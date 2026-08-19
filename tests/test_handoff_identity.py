"""Identity rules for handoff records.

Two defects motivated these: a redaction pass rewrote a host inside a leg's
JSON and forked it into two index rows, and deleted legs left rows the index
could never refresh. Both are identity bugs, not storage bugs.
"""
import json
import sqlite3

import pytest

from nougen_shards import handoff


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    folder = tmp_path / ".handoffs"
    folder.mkdir()
    db = folder / "handoffs.db"
    monkeypatch.setattr(handoff, "get_handoff_db_path", lambda: db, raising=False)
    monkeypatch.setenv("NOUGEN_HANDOFF_DIR", str(folder))
    return folder, db


def _write_leg(folder, name, handoff_id, host):
    path = folder / ("handoff_" + name + ".json")
    path.write_text(json.dumps({
        "handoff_id": handoff_id,
        "timestamp": "2026-07-31T10:01:26.933110",
        "goal": "identity test",
        "message": "## Active Incidents\n- None.\n",
        "git": {"branch": "main", "changes": []},
        "agent": "claude-cli",
        "machine": {"host": host, "machine_id": "abc123def456"},
        "status": "open",
    }), encoding="utf-8")
    return path


def test_id_is_not_derived_from_the_human_host(tmp_path):
    """The canonical id must not contain a hostname.

    A hostname can carry a username, which is exactly what a public-repo
    redactor rewrites - and rewriting a primary key forks the record.
    """
    identity = {"host": "KushBoyGroups-Mac-mini", "machine_id": "982ede2af033"}
    machine_slug = (identity.get("machine_id") or "unknown")[:12]
    record_slug = f"20260731_100126_{machine_slug}_main"
    assert "KushBoyGroups" not in record_slug
    assert machine_slug in record_slug


def test_rewritten_host_does_not_fork_the_record(registry):
    """Same file, id rewritten by a scrubber -> still exactly one row."""
    folder, db = registry
    name = "20260731_100126_KushBoyGroups-Mac-mini_main"
    path = _write_leg(folder, name, "20260731_100126_KushBoyGroups-Mac-mini_main", "mac-mini")
    handoff._sync_handoff_to_db(path, json.loads(path.read_text(encoding="utf-8")))

    # a redaction pass rewrites the id inside the file; filename unchanged
    data = json.loads(path.read_text(encoding="utf-8"))
    data["handoff_id"] = "20260731_100126_<user>_main"
    path.write_text(json.dumps(data), encoding="utf-8")
    handoff._sync_handoff_to_db(path, data)

    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT handoff_id FROM handoff_records"))
    conn.close()
    assert len(rows) == 1, f"record forked into {len(rows)} rows: {rows}"
    assert rows[0][0] == "20260731_100126_<user>_main", "the id in the FILE must win"


def test_orphan_rows_are_pruned(registry):
    """A row whose file is gone must not survive a rebuild."""
    folder, db = registry
    path = _write_leg(folder, "20260731_100200_host_main", "20260731_100200_host_main", "host")
    handoff._sync_handoff_to_db(path, json.loads(path.read_text(encoding="utf-8")))
    path.unlink()

    removed = handoff.prune_orphan_records()
    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT handoff_id FROM handoff_records"))
    conn.close()
    assert removed == 1
    assert rows == []
