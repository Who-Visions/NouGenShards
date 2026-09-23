import pytest

from nougen_shards.google_workspace.auth import (
    GoogleAuthError,
    resolve_loopback_listener,
)


def test_installed_client_uses_random_port():
    lst = resolve_loopback_listener("installed", ["http://localhost"])
    assert lst.port == 0
    assert lst.host == "localhost"


def test_web_client_binds_exact_registered_localhost_port():
    lst = resolve_loopback_listener("web", ["http://localhost:4444"])
    assert (lst.host, lst.port, lst.trailing_slash) == ("localhost", 4444, False)
    assert lst.redirect_uri == "http://localhost:4444"


def test_web_client_trailing_slash_preserved():
    lst = resolve_loopback_listener("web", ["http://localhost:4444/"])
    assert lst.trailing_slash is True
    assert lst.redirect_uri == "http://localhost:4444/"


def test_web_client_skips_non_loopback_and_pathed_uris():
    uris = [
        "https://example.firebaseapp.com/__/auth/handler",
        "http://localhost:8765/oauth2callback",
        "http://127.0.0.1:5555",
    ]
    lst = resolve_loopback_listener("web", uris)
    assert (lst.host, lst.port) == ("127.0.0.1", 5555)


def test_web_client_without_loopback_uri_fails_fast():
    with pytest.raises(GoogleAuthError, match="redirect_uri_mismatch"):
        resolve_loopback_listener("web", ["https://example.workers.dev/google/callback"])


def test_web_client_with_no_redirect_uris_fails_fast():
    with pytest.raises(GoogleAuthError):
        resolve_loopback_listener("web", [])


def test_env_client_falls_back_to_random_port():
    lst = resolve_loopback_listener("env", ["http://localhost:8765/"])
    # env-kind has a usable loopback URI registered in-config, so it's honoured
    assert lst.port == 8765


def test_env_override_beats_registered_list(monkeypatch):
    monkeypatch.setenv("NOUGEN_GOOGLE_REDIRECT_URI", "http://localhost:8765")
    lst = resolve_loopback_listener("web", ["https://example.workers.dev/cb"])
    assert (lst.host, lst.port, lst.trailing_slash) == ("localhost", 8765, False)


def test_env_override_rejects_pathed_uri(monkeypatch):
    monkeypatch.setenv("NOUGEN_GOOGLE_REDIRECT_URI", "http://localhost:8765/oauth2callback")
    with pytest.raises(GoogleAuthError, match="no path"):
        resolve_loopback_listener("web", [])
