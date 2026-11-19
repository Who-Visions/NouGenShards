"""Schema guard: numeric epoch timestamps written by ANY writer are normalized to ISO (2026-10-04)."""
import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture
def db(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path", lambda index: temp_path / f"t_{index}.db")
        shards.init_db(1)
        conn = sqlite3.connect(temp_path / "t_1.db")
        yield conn
        conn.close()


def _raw_insert(conn, ts):
    # Bypasses capture() on purpose, like the unidentified Antigravity writer on phoebus.
    cur = conn.execute("INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash) "
                       "VALUES (?, 'touchdown_proof', 't', 'c', '[]', ?)", (ts, uuid.uuid4().hex))
    conn.commit()
    return conn.execute("SELECT timestamp FROM shards WHERE id=?", (cur.lastrowid,)).fetchone()[0]


def test_epoch_seconds_normalized(db):
    assert _raw_insert(db, "1789583693") == "2026-09-16T18:34:53.000Z"


def test_epoch_millis_normalized(db):
    assert _raw_insert(db, "1775114335940") == "2026-04-02T07:18:55.940Z"


def test_float_epoch_and_integer_affinity(db):
    assert _raw_insert(db, 1789583693.25).startswith("2026-09-16T18:34:53.2")


def test_iso_and_out_of_range_untouched(db):
    assert _raw_insert(db, "2026-10-04T23:09:26.876Z") == "2026-10-04T23:09:26.876Z"
    assert _raw_insert(db, "42") == "42"


def test_update_to_epoch_is_normalized(db):
    cur = db.execute("INSERT INTO shards (timestamp, event_type, title, content, tags, file_hash) "
                     "VALUES ('2026-01-01T00:00:00Z', 'x', 't', 'c', '[]', ?)", (uuid.uuid4().hex,))
    db.execute("UPDATE shards SET timestamp='1789583693' WHERE id=?", (cur.lastrowid,))
    db.commit()
    assert db.execute("SELECT timestamp FROM shards WHERE id=?", (cur.lastrowid,)).fetchone()[0] \
        == "2026-09-16T18:34:53.000Z"


def test_capture_still_works(db):
    sid = shards.capture("KNOWLEDGE", "trigger smoke", "capture path unaffected by the timestamp guard")
    assert sid
