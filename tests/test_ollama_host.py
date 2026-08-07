"""Rule 0.2 regression: OLLAMA_HOST is a bind address, not a client target."""

import pytest

from nougen_shards.ollama_host import (
    DEFAULT_OLLAMA_PORT,
    api,
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
