import json
import sqlite3
from pathlib import Path

from nougen_shards import machine_backfill as mb


def _vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    for i in (1, 2):
        c = sqlite3.connect(v / f"nougen_shards_{i}.db")
        c.execute("create table shards (id integer primary key, title text, content text, tags text)")
        c.executemany("insert into shards(title, content, tags) values (?,?,?)", [
            ("a", "x", json.dumps(["k1"])),
            ("b", "y", json.dumps(["k2", "machine:otherhost"])),
            ("c", "z", None),
            ("d", "w", "not json"),
            ("e", "v", json.dumps(["machine:thishost"])),
        ])
        c.commit()
        c.close()
    return v


def test_machine_id_env_first(monkeypatch):
    monkeypatch.setenv("NOUGEN_MACHINE_ID", "NodeX")
    assert mb.machine_id() == "nodex"
    monkeypatch.delenv("NOUGEN_MACHINE_ID")
    assert mb.machine_id() and mb.machine_id() == mb.machine_id().lower()


def test_dry_run_writes_nothing(tmp_path: Path):
    v = _vault(tmp_path)
    r = mb.run(str(v), execute=False, tag="machine:thishost")
    assert r["written"] == 0 and r["untagged"] == 6 and r["mine"] == 2 and r["total"] == 10
    c = sqlite3.connect(v / "nougen_shards_1.db")
    assert c.execute("select tags from shards where id=1").fetchone()[0] == json.dumps(["k1"])


def test_execute_is_idempotent_and_keeps_other_hosts(tmp_path: Path):
    v = _vault(tmp_path)
    r1 = mb.run(str(v), execute=True, tag="machine:thishost")
    assert r1["written"] == 6 and r1["untagged"] == 0
    c = sqlite3.connect(v / "nougen_shards_1.db")
    rows = {i: json.loads(t) for i, t in c.execute("select id, tags from shards")}
    assert rows[1] == ["k1", "machine:thishost"]
    assert rows[2] == ["k2", "machine:otherhost"]          # another host's tag untouched
    assert rows[3] == ["machine:thishost"] and rows[4] == ["machine:thishost"]
    assert rows[5] == ["machine:thishost"]
    r2 = mb.run(str(v), execute=True, tag="machine:thishost")
    assert r2["written"] == 0                               # second run is a no-op


def test_force_rewrites_other_host(tmp_path: Path):
    v = _vault(tmp_path)
    r = mb.run(str(v), execute=True, force=True, tag="machine:thishost")
    c = sqlite3.connect(v / "nougen_shards_1.db")
    assert json.loads(c.execute("select tags from shards where id=2").fetchone()[0]) == ["k2", "machine:thishost"]
    assert r["dbs"][0]["other_host"] == 0
