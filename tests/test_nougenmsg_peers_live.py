"""--peers lists only live endpoints: kernel pipes and nodes that answer."""
import json
import socket

from nougen_shards import nougenmsg as m


def _peers(monkeypatch, tmp_path, pipes, registry=None):
    monkeypatch.setattr(m, "_live_pipe_names", lambda: list(pipes))
    monkeypatch.setattr(m.os.path, "expanduser", lambda p: str(tmp_path / p.lstrip("~/\\")))
    if registry is not None:
        reg = tmp_path / ".nougen" / "agy_sessions.json"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(json.dumps({"sessions": {k: {} for k in registry}}), encoding="utf-8")
    monkeypatch.setattr(m.NouGenMsgBus, "_probe_nodes",
                        staticmethod(lambda curr: {"nodes_reachable": [], "nodes_unreachable": []}))
    return m.NouGenMsgBus.list_peers()


def test_registry_entry_without_live_pipe_is_stale_not_active(monkeypatch, tmp_path):
    dead = r"\.\pipe\LOCAL\agy-msg-antigravity"
    r = _peers(monkeypatch, tmp_path, pipes=[], registry=[dead])
    assert r["antigravity_active_pipes"] == []
    assert r["antigravity_stale_registry"] == [dead]


def test_no_default_pipe_is_fabricated(monkeypatch, tmp_path):
    r = _peers(monkeypatch, tmp_path, pipes=[])
    assert r["antigravity_active_pipes"] == []


def test_live_agy_pipe_is_listed(monkeypatch, tmp_path):
    live = r"\.\pipe\LOCAL\agy-msg-antigravity"
    r = _peers(monkeypatch, tmp_path, pipes=[live, r"\.\pipe\other"])
    assert r["antigravity_active_pipes"] == [live]


def test_probe_nodes_splits_on_real_connect(monkeypatch):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    monkeypatch.setenv("NOUGEN_MSG_PORT", str(srv.getsockname()[1]))
    monkeypatch.setenv("NOUGEN_MSG_PROBE_TIMEOUT_S", "0.5")
    monkeypatch.setenv("NOUGEN_NODE_GHOST_IP", "127.0.0.2")
    monkeypatch.setattr(m, "fleet_identity_maps", lambda: ({"x": "ghost"}, {}))
    try:
        r = m.NouGenMsgBus._probe_nodes("blade")
    finally:
        srv.close()
    assert r["nodes_reachable"] == ["blade"]
    assert r["nodes_unreachable"] == ["ghost"]
