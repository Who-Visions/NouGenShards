"""_route_node_ip failsafe ladder: env pin -> live dns/mdns -> last-known-good cache."""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


@pytest.fixture()
def msg(monkeypatch, tmp_path):
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("nougenmsg_resolve_t", TOOLS / "nougenmsg.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "NODE_IP_CACHE", str(tmp_path / "node_ips.json"))
    ssh = tmp_path / "ssh_config"
    ssh.write_text("Host blade blade1tb apollo\n    HostName blade1tb.local\n    User super\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_ssh_config_hostnames",
                        lambda node, _p=ssh: [ln.split()[1] for ln in ssh.read_text().splitlines()
                                              if ln.strip().lower().startswith("hostname")]
                        if node == "blade" else [])
    monkeypatch.delenv("NOUGEN_NODE_BLADE_IP", raising=False)
    return mod


def test_env_pin_wins(msg, monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE_BLADE_IP", "10.9.9.9")
    monkeypatch.setattr(msg, "_resolve_ipv4", lambda n: pytest.fail("must not resolve"))
    assert msg._route_node_ip("blade") == ("10.9.9.9", "NOUGEN_NODE_BLADE_IP")


def test_ssh_hostname_resolves_and_caches(msg, monkeypatch):
    monkeypatch.setattr(msg, "_resolve_ipv4", lambda n: "10.0.0.87" if n == "blade1tb.local" else "")
    ip, via = msg._route_node_ip("blade")
    assert (ip, via) == ("10.0.0.87", "resolved:blade1tb.local")
    assert msg._node_ip_cache()["blade"]["ip"] == "10.0.0.87"


def test_loopback_answer_is_rejected(msg, monkeypatch):
    monkeypatch.setattr(msg, "_resolve_ipv4", lambda n: "127.0.0.1")
    assert msg._route_node_ip("blade")[0] is None


def test_cache_is_the_failsafe_when_mdns_is_silent(msg, monkeypatch):
    msg._node_ip_cache({"blade": {"ip": "10.0.0.87", "via": "blade1tb.local", "ts": 1}})
    monkeypatch.setattr(msg, "_resolve_ipv4", lambda n: "")
    assert msg._route_node_ip("blade") == ("10.0.0.87", "cache:blade1tb.local")


def test_nothing_anywhere_returns_none_with_reason(msg, monkeypatch):
    monkeypatch.setattr(msg, "_resolve_ipv4", lambda n: "")
    ip, reason = msg._route_node_ip("blade")
    assert ip is None and "NOUGEN_NODE_BLADE_IP" in reason


def test_real_ssh_config_parser(tmp_path, monkeypatch, msg):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "config").write_text(
        "Host phoebus macmini\n  HostName Mac-mini.local\nHost other\n  HostName x.local\n", encoding="utf-8")
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    spec = importlib.util.spec_from_file_location("nougenmsg_resolve_t2", TOOLS / "nougenmsg.py")
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    assert fresh._ssh_config_hostnames("MacMini") == ["Mac-mini.local"]
    assert fresh._ssh_config_hostnames("nobody") == []
