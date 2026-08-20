"""Offline vault union preserves durable rows and global deduplication."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sqlite3


SPEC = spec_from_file_location(
    "union_vaults", Path(__file__).parents[1] / "tools" / "union_vaults.py")
union_vaults = module_from_spec(SPEC)
SPEC.loader.exec_module(union_vaults)


def _make_db(vault: Path, rows):
    vault.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(vault / "nougen_shards_1.db")
    try:
        conn.execute("""
            CREATE TABLE shards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, content TEXT, file_hash TEXT UNIQUE,
                embedding BLOB, sensitivity TEXT DEFAULT 'normal', enc INTEGER DEFAULT 0
            )
        """)
        conn.executemany(
            "INSERT INTO shards(title,content,file_hash,embedding,sensitivity,enc) "
            "VALUES(?,?,?,?,?,?)", rows)
        conn.commit()
    finally:
        conn.close()


def test_union_vaults_adds_only_globally_new_hashes(tmp_path):
    target, source = tmp_path / "target", tmp_path / "source"
    _make_db(target, [("existing", "a", "h1", b"vec1", "normal", 0)])
    _make_db(source, [
        ("duplicate", "a", "h1", b"vec1", "normal", 0),
        ("new", "b", "h2", b"vec2", "private", 1),
    ])

    report = union_vaults.union_vaults(source, target, apply=True)

    assert report["inserted"] == 1
    assert report["duplicates"] == 1
    conn = sqlite3.connect(target / "nougen_shards_1.db")
    try:
        rows = conn.execute(
            "SELECT file_hash,embedding,sensitivity,enc FROM shards ORDER BY file_hash").fetchall()
    finally:
        conn.close()
    assert rows == [("h1", b"vec1", "normal", 0), ("h2", b"vec2", "private", 1)]
    assert report["dedup_index"] == 2
