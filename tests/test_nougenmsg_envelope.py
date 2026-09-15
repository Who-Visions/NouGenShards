"""Message envelope (from WhoArt's unshipped node patch, shipped 2026-09-14).

The origin envelope carries id / trigger_source / correlation_id /
idempotency_key / reply_to, and live_ping appends each delivery to
~/.nougen/messages.db when that ledger exists (it is created out of band).
"""
import sqlite3
from pathlib import Path

import nougen_shards.nougenmsg as m

SCHEMA = ("CREATE TABLE messages (id TEXT, timestamp REAL, source_node TEXT, source_agent TEXT,"
          " target_node TEXT, target_agent TEXT, trigger_source TEXT, correlation_id TEXT,"
          " idempotency_key TEXT, text TEXT, provenance JSON)")


def _quiet_lanes(monkeypatch):
    for name in ("ping_claude", "ping_codex"):
        monkeypatch.setattr(m.AgentPinger, name, staticmethod(lambda *a, **k: "ok"))
    monkeypatch.setattr(m.AgentPinger, "ping_antigravity", staticmethod(lambda *a, **k: "ok"))


def test_envelope_carries_supplied_fields(monkeypatch):
    monkeypatch.delenv("NOUGEN_TRIGGER_SOURCE", raising=False)
    env = m.NouGenMsgBus._origin_envelope({"id": "m1", "correlation_id": "c1",
                                           "idempotency_key": "k1", "reply_to": "@blade"})
    assert (env["id"], env["correlation_id"], env["idempotency_key"], env["reply_to"]) == ("m1", "c1", "k1", "@blade")
    assert env["trigger_source"] == "direct_dispatch"


def test_trigger_source_env_default(monkeypatch):
    monkeypatch.setenv("NOUGEN_TRIGGER_SOURCE", "cron")
    assert m.NouGenMsgBus._origin_envelope({})["trigger_source"] == "cron"


def test_live_ping_appends_to_ledger_when_present(monkeypatch, isolated_msg_home):
    _quiet_lanes(monkeypatch)
    db = Path(isolated_msg_home) / ".nougen" / "messages.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as c:
        c.execute(SCHEMA)
    m.NouGenMsgBus.live_ping(target="claude", text="hello ledger", origin={"correlation_id": "c9"})
    with sqlite3.connect(db) as c:
        rows = c.execute("select text, correlation_id, target_agent from messages").fetchall()
    assert rows == [("hello ledger", "c9", "claude")]


def test_no_ledger_no_file(monkeypatch, isolated_msg_home):
    _quiet_lanes(monkeypatch)
    m.NouGenMsgBus.live_ping(target="claude", text="hi")
    assert not (Path(isolated_msg_home) / ".nougen" / "messages.db").exists()


def test_cli_exposes_envelope_flags():
    src = (Path(__file__).resolve().parents[1] / "tools" / "nougenmsg.py").read_text(encoding="utf-8")
    for flag in ("--trigger-source", "--correlation-id", "--idempotency-key", "--reply-to"):
        assert f'"{flag}"' in src, flag
