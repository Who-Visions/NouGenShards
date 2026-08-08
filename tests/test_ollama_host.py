"""Rule 0.2 regression: OLLAMA_HOST is a bind address, not a client target."""

import pytest

from nougen_shards import ollama_host
from nougen_shards.ollama_host import (
    DEFAULT_OLLAMA_PORT,
    api,
    autostart_enabled,
    candidate_ports,
    discover_ollama_url,
    ensure_ollama_url,
    resolve_ollama_url,
    sanitize_ollama_url,
)


@pytest.mark.parametrize("raw", ["0.0.0.0", "http://0.0.0.0", "0.0.0.0:11434", "::", "[::]", "*"])
def test_wildcard_binds_become_dialable(raw):
    """The exact class of value that raised WinError 10049 on 2026-08-05/06."""
    assert sanitize_ollama_url(raw) == f"http://127.0.0.1:{DEFAULT_OLLAMA_PORT}"


def test_empty_and_none_fall_back():
    assert sanitize_ollama_url(None) == f"http://127.0.0.1:{DEFAULT_OLLAMA_PORT}"
    assert sanitize_ollama_url("   ") == f"http://127.0.0.1:{DEFAULT_OLLAMA_PORT}"


def test_bind_shorthand_port_only():
    assert sanitize_ollama_url(":11500") == "http://127.0.0.1:11500"


def test_schemeless_host_gets_scheme_and_port():
    assert sanitize_ollama_url("localhost") == f"http://localhost:{DEFAULT_OLLAMA_PORT}"
    assert sanitize_ollama_url("192.168.1.16") == f"http://192.168.1.16:{DEFAULT_OLLAMA_PORT}"


def test_explicit_port_preserved():
    assert sanitize_ollama_url("http://192.168.1.16:9999") == "http://192.168.1.16:9999"


def test_cloud_url_passes_through_untouched():
    """The opposite case: https://ollama.com is a real client URL, don't force :11434."""
    assert sanitize_ollama_url("https://ollama.com") == "https://ollama.com"
    assert sanitize_ollama_url("https://ollama.com/") == "https://ollama.com"


def test_real_ipv6_literal_is_kept_bracketed():
    assert sanitize_ollama_url("http://[::1]:11434") == "http://[::1]:11434"


def test_no_naive_substring_replacement():
    """A path containing the wildcard text must not be rewritten (old bug)."""
    assert sanitize_ollama_url("http://10.0.0.0:11434") == "http://10.0.0.0:11434"


def test_resolution_order_prefers_explicit_override():
    env = {"NOUGEN_OLLAMA_URL": "http://10.0.0.5:1234", "OLLAMA_HOST": "0.0.0.0"}
    assert resolve_ollama_url(env=env) == "http://10.0.0.5:1234"


def test_resolution_sanitizes_inherited_bind_address():
    assert resolve_ollama_url(env={"OLLAMA_HOST": "0.0.0.0"}) == \
        f"http://127.0.0.1:{DEFAULT_OLLAMA_PORT}"


def test_resolution_falls_back_when_env_empty():
    assert resolve_ollama_url(env={}) == f"http://127.0.0.1:{DEFAULT_OLLAMA_PORT}"


def test_api_join_is_single_slashed():
    base = "http://127.0.0.1:11434"
    assert api("/api/tags", base=base) == f"{base}/api/tags"
    assert api("api/tags", base=base) == f"{base}/api/tags"


# --- live-port discovery + cold-start (dream lane, 2026-08-07) -------------------

def test_candidate_ports_are_env_resolvable(monkeypatch):
    monkeypatch.setenv("NOUGEN_OLLAMA_PORTS", "11500, 11501 ;11500")
    assert candidate_ports() == (11500, 11501)


def test_candidate_ports_lead_with_env_port_then_constants(monkeypatch):
    monkeypatch.delenv("NOUGEN_OLLAMA_PORTS", raising=False)
    monkeypatch.setenv("NOUGEN_OLLAMA_PORT", "11436")
    ports = candidate_ports()
    assert ports[0] == 11436
    assert DEFAULT_OLLAMA_PORT in ports


def test_discovery_finds_the_live_port_when_default_is_dead(monkeypatch):
    """The 2026-08-07 case: 11434 answered nothing, the daemon was on 11436."""
    monkeypatch.delenv("NOUGEN_OLLAMA_PORTS", raising=False)
    monkeypatch.delenv("NOUGEN_OLLAMA_PORT", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0")  # portless bind -> pins 11434 without probing
    monkeypatch.setattr(ollama_host, "probe_url",
                        lambda url, timeout=None: url == "http://127.0.0.1:11436")
    assert discover_ollama_url() == "http://127.0.0.1:11436"


def test_discovery_returns_none_when_nothing_answers(monkeypatch):
    monkeypatch.setattr(ollama_host, "probe_url", lambda url, timeout=None: False)
    assert discover_ollama_url() is None


@pytest.mark.parametrize("raw,expected", [("0", False), ("false", False), ("off", False),
                                          ("1", True), ("yes", True), (None, True)])
def test_autostart_is_env_gated(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("NOUGEN_OLLAMA_AUTOSTART", raising=False)
    else:
        monkeypatch.setenv("NOUGEN_OLLAMA_AUTOSTART", raw)
    assert autostart_enabled() is expected


def test_ensure_does_not_spawn_when_daemon_already_live(monkeypatch):
    monkeypatch.setattr(ollama_host, "discover_ollama_url",
                        lambda **kw: "http://127.0.0.1:11436")
    monkeypatch.setattr(ollama_host.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("must not ignite a live daemon"))
    assert ensure_ollama_url() == "http://127.0.0.1:11436"


def test_ensure_ignites_cold_daemon_then_returns_live_url(monkeypatch):
    spawned = []
    results = iter([None, "http://127.0.0.1:11436"])
    monkeypatch.setattr(ollama_host, "discover_ollama_url", lambda **kw: next(results, None))
    monkeypatch.setattr(ollama_host.subprocess, "Popen", lambda *a, **k: spawned.append(a[0]))
    monkeypatch.setattr(ollama_host.time, "sleep", lambda s: None)
    assert ensure_ollama_url(wait_s=10) == "http://127.0.0.1:11436"
    assert spawned and spawned[0][1] == "serve"


def test_ensure_degrades_instead_of_pretending(monkeypatch):
    """A genuinely dead lane returns None -- callers degrade honestly."""
    monkeypatch.setattr(ollama_host, "discover_ollama_url", lambda **kw: None)
    monkeypatch.setattr(ollama_host, "autostart_enabled", lambda: False)
    assert ensure_ollama_url() is None
