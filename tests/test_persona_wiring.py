"""persona wiring into coach.py and NouGenMsgBus: opt-in, no-op when unset."""
import os, sys, sqlite3, json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import coach  # noqa: E402
from nougen_shards import nougenmsg as NM  # noqa: E402
from nougen_shards import persona as P  # noqa: E402


@pytest.fixture
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"; v.mkdir()
    con = sqlite3.connect(v / "nougen_shards_1.db")
    con.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, title TEXT, content TEXT, tags TEXT)")
    for txt in ("leg it on the relay", "fleet probe then shard it", "so i ask again"):
        con.execute("INSERT INTO shards (timestamp,event_type,title,content,tags) VALUES (?,?,?,?,?)",
                    ("2026-09-14T04:00:00Z", "KNOWLEDGE", "t", txt, json.dumps(["via:test-app/u"])))
    con.commit(); con.close()
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(v))
    return v


def test_coach_contract_noop_when_unset(monkeypatch):
    monkeypatch.delenv("COACH_AUDIENCE_SCOPE", raising=False)
    assert coach.persona_contract() == ""


def test_coach_contract_resolves(vault):
    c = coach.persona_contract("via:test-app/u")
    assert c.startswith("[persona ") and "fleet-operator" in c and "Answer first" in c


def test_coach_local_sends_system_message(vault, monkeypatch):
    seen = {}
    class R:
        def __init__(self, req, timeout=0): seen["body"] = json.loads(req.data)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b""
    monkeypatch.setattr(coach.urllib.request, "urlopen",
                        lambda req, timeout=0: R(req) if hasattr(req, "data") else _tags())
    monkeypatch.setattr(coach.json, "load", lambda r: {"models": [{"name": "gemma4:e2b-qat"}]} if not seen.get("body")
                        else {"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr(coach, "_ledger", lambda *a, **k: None)
    out = coach.local("hello", audience="via:test-app/u")
    msgs = seen["body"]["messages"]
    assert out == "ok" and msgs[0]["role"] == "system" and msgs[0]["content"].startswith("[persona ")


class _tags:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_msg_header_noop_and_resolves(vault, monkeypatch):
    monkeypatch.delenv("NOUGEN_MSG_AUDIENCE", raising=False)
    assert NM.NouGenMsgBus.persona_header() == ""
    h = NM.NouGenMsgBus.persona_header("via:test-app/u")
    assert h.startswith("[persona ") and "fleet-operator@agent-fleet-operators" in h


def test_msg_emit_node_prefixes_once(vault, monkeypatch):
    captured = {}
    monkeypatch.setattr(NM, "get_current_node", lambda: "local")
    monkeypatch.setattr(NM.NouGenMsgBus, "live_ping", classmethod(lambda cls, target, text, origin=None, **k: captured.setdefault("text", text)))
    NM.NouGenMsgBus.emit_node("local", "claude", "body", audience="via:test-app/u")
    assert captured["text"].startswith("[persona ") and captured["text"].endswith("\nbody")
    captured.clear()
    NM.NouGenMsgBus.emit_node("local", "claude", captured.get("text") or "[persona x] already", audience="via:test-app/u")
    assert captured["text"].count("[persona ") == 1
