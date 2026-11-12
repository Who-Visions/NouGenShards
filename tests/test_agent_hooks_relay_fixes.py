"""Baton hydration reads what the relay writer persists; only sends count as handoffs."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nougen_shards import agent_hooks


class ActiveBatonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mdir = Path(self.tmp.name) / "phoebus"
        self.mdir.mkdir()
        self.env = mock.patch.dict(os.environ, {"NOUGEN_RELAY_DIR": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _write_current(self, **fields):
        data = {"schema": 1, "machine": "phoebus", "session": "sess-abc", "mission": "m",
                "phase": "start", "active": True, "updated_utc": "2026-11-10T00:00:00Z"}
        data.update(fields)
        (self.mdir / "current.json").write_text(json.dumps(data), encoding="utf-8")

    def test_reads_session_field_and_finds_baton_file(self):
        self._write_current()
        baton = self.mdir / "baton_2026-11-10_sess-abc.json"
        baton.write_text("{}", encoding="utf-8")
        out = agent_hooks.active_relay_summary()
        self.assertIn("Session sess-abc", out)
        self.assertNotIn("Session none", out)
        self.assertIn(str(baton), out)

    def test_missing_baton_leaves_path_empty_but_still_names_session(self):
        self._write_current()
        out = agent_hooks.active_relay_summary()
        self.assertIn("Session sess-abc", out)
        self.assertTrue(out.endswith("| "))

    def test_inactive_baton_is_not_reported(self):
        self._write_current(active=False)
        self.assertEqual(agent_hooks.active_relay_summary(), "")


class RelayMatcherTests(unittest.TestCase):
    def test_sends_count_as_handoff(self):
        self.assertIsNotNone(agent_hooks._RELAY_TOOL.search("mcp__nougen-shards__nougenmsg_send"))
        self.assertIsNotNone(agent_hooks._RELAY_TOOL.search("relay_checkpoint"))

    def test_reading_messages_does_not_count(self):
        for name in ("mcp__nougen-shards__nougenmsg_inbox",
                     "mcp__nougen-shards__nougenmsg_search",
                     "mcp__nougen-shards__nougenmsg_peers"):
            self.assertIsNone(agent_hooks._RELAY_TOOL.search(name), name)


if __name__ == "__main__":
    unittest.main()
