"""Unit tests for NouGen Dynamic Process Supervisor & Zombie Killer."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from nougen_shards.zombie_killer import ZombieHunter, ZombieProcess


class TestZombieKiller(unittest.TestCase):
    def setUp(self):
        self.hunter = ZombieHunter()

    def test_compute_ancestor_pids(self):
        procs_table = {
            100: {"ProcessId": 100, "ParentProcessId": 50, "Name": "child.exe"},
            50: {"ProcessId": 50, "ParentProcessId": 20, "Name": "parent.exe"},
            20: {"ProcessId": 20, "ParentProcessId": 4, "Name": "grandparent.exe"},
            4: {"ProcessId": 4, "ParentProcessId": 0, "Name": "system"},
        }
        self.hunter.my_pid = 100
        ancestors = self.hunter._compute_ancestor_pids(procs_table)
        self.assertIn(100, ancestors)
        self.assertIn(50, ancestors)
        self.assertIn(20, ancestors)
        self.assertNotIn(4, ancestors)  # Stops at PID <= 4

    def test_scan_classification_dead_parent(self):
        mock_table = [
            {
                "ProcessId": 12345,
                "ParentProcessId": 99999,  # Non-existent parent
                "Name": "python.exe",
                "CommandLine": "python.exe stuck_script.py",
                "WorkingSetSize": 50 * 1024 * 1024,
            },
            {
                "ProcessId": 54321,
                "ParentProcessId": 99999,
                "Name": "AsusOSD.exe",  # Vendor tray
                "CommandLine": "AsusOSD.exe",
                "WorkingSetSize": 20 * 1024 * 1024,
            },
            {
                "ProcessId": 22222,
                "ParentProcessId": 11111,
                "Name": "python.exe",
                "CommandLine": "python.exe active_worker.py",
                "WorkingSetSize": 30 * 1024 * 1024,
            },
            {
                "ProcessId": 11111,
                "ParentProcessId": 4,
                "Name": "code.exe",
                "CommandLine": "code.exe",
                "WorkingSetSize": 100 * 1024 * 1024,
            }
        ]

        with patch.object(self.hunter, "get_process_table", return_value=mock_table):
            procs = self.hunter.scan()
            by_pid = {p.pid: p for p in procs}

            # 12345 should be classified as SAFE_TO_KILL orphan
            p_zombie = by_pid[12345]
            self.assertTrue(p_zombie.is_orphan)
            self.assertEqual(p_zombie.risk_level, "SAFE_TO_KILL")
            self.assertFalse(p_zombie.parent_alive)

            # 54321 is not in dev target set -> SUSPICIOUS, not SAFE_TO_KILL
            p_tray = by_pid[54321]
            self.assertTrue(p_tray.is_orphan)
            self.assertEqual(p_tray.risk_level, "SUSPICIOUS")

            # 22222 parent is alive (11111) -> PROTECTED
            p_live = by_pid[22222]
            self.assertFalse(p_live.is_orphan)
            self.assertEqual(p_live.risk_level, "PROTECTED")

    def test_sweep_dry_run(self):
        mock_table = [
            {
                "ProcessId": 9911,
                "ParentProcessId": 8888,
                "Name": "node.exe",
                "CommandLine": "node.exe orphaned_server.js",
                "WorkingSetSize": 40 * 1024 * 1024,
            }
        ]

        with patch.object(self.hunter, "get_process_table", return_value=mock_table):
            res = self.hunter.sweep(kill=False)
            self.assertEqual(res["mode"], "INSPECT")
            self.assertEqual(res["zombies_found"], 1)
            self.assertEqual(res["killed_count"], 0)
            self.assertEqual(res["total_reclaimable_mb"], 40.0)

            report = ZombieHunter.render_report(res)
            self.assertIn("DETECTED 1 ORPHANED ZOMBIE", report)
            self.assertIn("9911", report)


if __name__ == "__main__":
    unittest.main()
