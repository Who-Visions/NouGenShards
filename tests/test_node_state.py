"""Regression tests for relay directive 20260913T162818Z."""
import errno
import socket

import pytest

from nougen_shards import node_state as ns


def p(port, ok, code=None):
    return {"port": port, "reachable": ok,
            "reason_code": "SOCKET_CONNECTED" if ok else code}


TIMEOUTS = [p(22, False, "CONNECT_TIMEOUT"), p(8765, False, "CONNECT_TIMEOUT")]


def test_single_observer_timeout_is_unknown_not_offline():
    r = ns.classify("blade", TIMEOUTS, observer="phoebus")
    assert r["state"] == "UNKNOWN"
    assert "one observer cannot prove offline" in r["reason"]
    assert r["online"] is False


def test_powered_off_by_owner_is_offline_expected():
    r = ns.classify("blade", TIMEOUTS, declaration={"state": "offline", "note": "powered off"})
    assert r["state"] == "OFFLINE_EXPECTED"
    assert "powered off" in r["reason"]


def test_refused_means_host_up_service_down():
    r = ns.classify("blade", [p(22, False, "CONNECTION_REFUSED"), p(8765, False, "CONNECT_TIMEOUT")])
    assert r["state"] == "ONLINE_SERVICE_DOWN"
    assert r["online"] is True


def test_partial_ports_is_degraded_and_names_them():
    r = ns.classify("blade", [p(22, True), p(8765, False, "CONNECT_TIMEOUT")])
    assert r["state"] == "ONLINE_DEGRADED"
    assert "8765 (CONNECT_TIMEOUT)" in r["reason"]


def test_witness_that_can_see_it_makes_a_partition():
    r = ns.classify("blade", TIMEOUTS, observer="phoebus",
                    witnesses=[{"observer": "whoart", "reachable": True}])
    assert r["state"] == "NETWORK_PARTITION"
    assert "whoart" in r["reason"]


def test_independent_observers_agreeing_is_offline_unexpected():
    r = ns.classify("blade", TIMEOUTS, observer="phoebus",
                    witnesses=[{"observer": "whoart", "reachable": False}])
    assert r["state"] == "OFFLINE_UNEXPECTED"


def test_answering_while_declared_offline_is_booting_and_flags_stale_declaration():
    r = ns.classify("blade", [p(22, True)], declaration={"state": "offline"})
    assert r["state"] == "BOOTING"
    assert "stale" in r["reason"]


def test_dns_failure_alone_is_unknown():
    assert ns.classify("blade", [p(22, False, "DNS_FAILURE")])["state"] == "UNKNOWN"


def test_all_ports_up_is_healthy():
    assert ns.classify("phoebus", [p(22, True), p(8766, True)])["state"] == "ONLINE_HEALTHY"


@pytest.mark.parametrize("exc,expected", [
    (socket.gaierror(8, "nodename nor servname provided"), "DNS_FAILURE"),
    (socket.timeout(), "CONNECT_TIMEOUT"),
    (ConnectionRefusedError(errno.ECONNREFUSED, "refused"), "CONNECTION_REFUSED"),
    (OSError(errno.EHOSTUNREACH, "No route to host"), "HOST_UNREACHABLE"),
    (OSError(errno.EPERM, "nope"), "SOCKET_ERROR"),
])
def test_failure_class_names_the_real_error(exc, expected):
    assert ns.failure_class(exc) == expected


def test_declare_round_trip_and_clear(tmp_path):
    ns.declare("blade", "offline", "powered off", home_dir=tmp_path)
    assert ns.load_declarations(tmp_path)["blade"]["state"] == "offline"
    ns.declare("blade", "online", home_dir=tmp_path)
    assert "blade" not in ns.load_declarations(tmp_path)
    with pytest.raises(ValueError):
        ns.declare("blade", "dead", home_dir=tmp_path)


def test_missing_or_corrupt_declaration_file_is_empty(tmp_path):
    assert ns.load_declarations(tmp_path) == {}
    (tmp_path / "node_power.json").write_text("{not json", encoding="utf-8")
    assert ns.load_declarations(tmp_path) == {}
