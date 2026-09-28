"""
Unit tests for AutonomousWatchdog and ShardCompactor elevated maintenance modules.
"""

import sqlite3
from unittest.mock import patch

from nougen_shards.maintenance_elevated import ShardCompactor
from nougen_shards.watchdog_elevated import AutonomousWatchdog, ServiceProbeResult


def test_watchdog_probe_healthy():
    watchdog = AutonomousWatchdog()
    with patch.object(
        watchdog,
        "probe_http_service",
        side_effect=lambda name, url, port: ServiceProbeResult(name, port, True, 12.5),
    ):
        report = watchdog.run_supervision_cycle(auto_heal=False)
        assert report["healthy"] is True
        assert report["probes"]["msgnode"]["alive"] is True
        assert report["probes"]["ollama"]["alive"] is True
        assert len(report["healed_actions"]) == 0


def test_watchdog_auto_heal_trigger():
    watchdog = AutonomousWatchdog()
    # Mock msgnode down and ollama down
    with patch.object(
        watchdog,
        "probe_http_service",
        side_effect=lambda name, url, port: ServiceProbeResult(name, port, False, 100.0, "Connection refused"),
    ), patch.object(watchdog, "heal_ollama", return_value={"success": True, "action": "test_ollama"}), \
       patch.object(watchdog, "heal_msgnode", return_value={"success": True, "action": "test_msgnode"}):

        report = watchdog.run_supervision_cycle(auto_heal=True)
        assert report["healthy"] is False
        assert "ollama" in report["healed_actions"]
        assert "msgnode" in report["healed_actions"]
        assert report["healed_actions"]["ollama"]["success"] is True
        assert report["healed_actions"]["msgnode"]["success"] is True


def test_shard_compactor_inspection_and_vacuum(tmp_path):
    db_file = tmp_path / "test_shard.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, content TEXT);")
    for i in range(500):
        cur.execute("INSERT INTO test_data (content) VALUES (?);", (f"data_{i}" * 50,))
    conn.commit()

    # Delete 80% to create fragmentation/freelist pages
    cur.execute("DELETE FROM test_data WHERE id > 100;")
    conn.commit()
    conn.close()

    compactor = ShardCompactor(db_paths=[db_file])
    info = compactor.inspect_fragmentation(db_file)
    assert info["exists"] is True
    assert info["page_count"] > 0

    # Test compaction run with force=True
    res = compactor.compact_database(db_file, force=True)
    assert res["optimized"] is True
    assert "duration_s" in res

    # Fleet compaction sweep
    fleet_res = compactor.run_fleet_compaction(force=True)
    assert fleet_res["databases_processed"] == 1
    assert len(fleet_res["details"]) == 1
