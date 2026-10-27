"""A node whose accept loop died must exit so the supervisor can rebind
(whoart 2026-10-26: uvicorn alive for hours with a dead :4444 socket)."""
import time

import app as node_app


def _reset(monkeypatch):
    monkeypatch.setattr(node_app, "_LISTENER_STATE",
                        {"status": "pending", "port": None, "consecutive_failures": 0, "checks": 0})


def test_disabled_without_port_or_with_zero_interval(monkeypatch):
    _reset(monkeypatch)
    for name in ("NGS_PORT", "NOUGEN_NODE_PORT", "PORT"):
        monkeypatch.delenv(name, raising=False)
    node_app._start_listener_selfcheck(exit_fn=lambda c: None)
    assert node_app.listener_selfcheck_status()["status"] == "disabled"
    _reset(monkeypatch)
    monkeypatch.setenv("NGS_PORT", "4444")
    monkeypatch.setenv("NOUGEN_LISTENER_SELFCHECK_S", "0")
    node_app._start_listener_selfcheck(exit_fn=lambda c: None)
    assert node_app.listener_selfcheck_status()["status"] == "disabled"


def test_exits_after_consecutive_refused_probes(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("NGS_PORT", "4444")
    monkeypatch.setenv("NOUGEN_LISTENER_SELFCHECK_S", "0.02")
    monkeypatch.setenv("NOUGEN_LISTENER_SELFCHECK_FAILS", "3")
    monkeypatch.setattr(node_app, "_probe_listener", lambda port, timeout_s=2.0: False)
    exits = []
    node_app._start_listener_selfcheck(exit_fn=exits.append)
    t0 = time.monotonic()
    while not exits and time.monotonic() - t0 < 3:
        time.sleep(0.01)
    assert exits == [3]
    st = node_app.listener_selfcheck_status()
    assert st["status"] == "dead" and st["consecutive_failures"] == 3 and st["port"] == 4444


def test_one_refused_probe_between_successes_does_not_exit(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("NGS_PORT", "4444")
    monkeypatch.setenv("NOUGEN_LISTENER_SELFCHECK_S", "0.02")
    monkeypatch.setenv("NOUGEN_LISTENER_SELFCHECK_FAILS", "2")
    results = iter([True, False, True, False, True] + [True] * 50)
    monkeypatch.setattr(node_app, "_probe_listener", lambda port, timeout_s=2.0: next(results, True))
    exits = []
    node_app._start_listener_selfcheck(exit_fn=exits.append)
    time.sleep(0.4)
    assert exits == [] and node_app.listener_selfcheck_status()["consecutive_failures"] == 0


def test_probe_listener_real_socket():
    import socket
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert node_app._probe_listener(port) is True
    finally:
        srv.close()
    assert node_app._probe_listener(port) is False
