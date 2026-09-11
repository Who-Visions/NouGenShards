import pytest
from nougen_shards.live import NouGenLive, handle_live_slash

def test_live_probe_ports():
    live = NouGenLive()
    res = live.probe_ports("127.0.0.1", [8766, 99999])
    assert 8766 in res
    assert res[99999] is False

def test_live_slash_overview():
    out = handle_live_slash([])
    assert "NOUGEN FLEET CONTROL PLANE (/live)" in out
    assert "LOCAL LISTENING PORTS" in out

def test_live_slash_ports():
    out = handle_live_slash(["ports"])
    assert "8766" in out

def test_live_targeted_send_unreachable():
    live = NouGenLive()
    res = live.send_targeted("non-existent-session-xyz", "hello")
    assert res["state"] == "unreachable"
