"""Journal mirror stores ISO timestamps even when a journal line carries epoch numbers (2026-10-04)."""
import json
import sqlite3

from nougen_shards import journal_mirror as jm


def test_shard_timestamp_normalizes_epochs():
    assert jm.shard_timestamp("1789583693") == "2026-09-16T18:34:53.000Z"
    assert jm.shard_timestamp("1775114335940") == "2026-04-02T07:18:55.940Z"
    assert jm.shard_timestamp(1789583693.5).endswith(".500Z")


def test_shard_timestamp_passes_through_iso_and_garbage():
    assert jm.shard_timestamp("2026-10-04T23:09:26.876Z") == "2026-10-04T23:09:26.876Z"
    assert jm.shard_timestamp("not a time") == "not a time"
    assert jm.shard_timestamp("42") == "42"  # out of plausible range: not guessed


def test_mirror_writes_iso_for_epoch_journal_line_and_stays_idempotent(tmp_path):
    journal = tmp_path / "journal.jsonl"
    journal.write_text(json.dumps({"created_utc": 1789583693, "title": "fleet ack",
                                   "content": "touchdown", "tags": ["fleet/touchdown"]}) + "\n",
                       encoding="utf-8")
    cfg = jm.MirrorConfig.resolve(watchtower_root=tmp_path, vault_dir=tmp_path,
                                  journal_path=journal, mirror_db=tmp_path / "m.db",
                                  fleet_map=tmp_path / "fleet.json", lock_file=tmp_path / "m.lock",
                                  node_name="test")
    jm.mirror_journal(cfg, dry_run=False)
    jm.mirror_journal(cfg, dry_run=False)
    rows = sqlite3.connect(cfg.mirror_db).execute("select timestamp from shards").fetchall()
    assert rows == [("2026-09-16T18:34:53.000Z",)]
