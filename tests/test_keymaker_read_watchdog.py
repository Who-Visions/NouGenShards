"""get_secret is bounded: a blocked read returns None instead of hanging the caller."""
import threading
import time

import pytest

from nougen_shards import keymaker


def test_blocked_read_returns_none_within_timeout(monkeypatch):
    release = threading.Event()
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "0.3")
    monkeypatch.setattr(keymaker, "_get_secret_unbounded", lambda key: release.wait(30))
    started = time.monotonic()
    try:
        assert keymaker.get_secret("ANY_KEY") is None
        assert time.monotonic() - started < 5
    finally:
        release.set()


def test_normal_read_passes_value_through(monkeypatch):
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "5")
    monkeypatch.setattr(keymaker, "_get_secret_unbounded", lambda key: f"v-{key}")
    assert keymaker.get_secret("K") == "v-K"


def test_read_errors_propagate(monkeypatch):
    def boom(key):
        raise keymaker.VaultDivergenceError("diverged")

    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "5")
    monkeypatch.setattr(keymaker, "_get_secret_unbounded", boom)
    with pytest.raises(keymaker.VaultDivergenceError):
        keymaker.get_secret("K")


def test_zero_timeout_disables_the_watchdog(monkeypatch):
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "0")
    seen = {}

    def fake(key):
        seen["thread"] = threading.current_thread()
        return "x"

    monkeypatch.setattr(keymaker, "_get_secret_unbounded", fake)
    assert keymaker.get_secret("K") == "x"
    assert seen["thread"] is threading.main_thread()


def test_bad_timeout_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "not-a-number")
    assert keymaker._read_timeout_s() == keymaker._READ_TIMEOUT_DEFAULT_S


def test_tenant_context_survives_the_thread_hop(monkeypatch):
    import contextvars
    var = contextvars.ContextVar("probe", default="unset")
    var.set("tenant-a")
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "5")
    monkeypatch.setattr(keymaker, "_get_secret_unbounded", lambda key: var.get())
    assert keymaker.get_secret("K") == "tenant-a"


def test_stuck_reader_is_not_duplicated(monkeypatch):
    """Review on PR 1202: repeated calls for a blocked key must not spawn a new thread each time."""
    release = threading.Event()
    calls = []
    monkeypatch.setattr(keymaker, "_STUCK_READERS", {})
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "0.2")

    def blocked(key):
        calls.append(key)
        release.wait(30)

    monkeypatch.setattr(keymaker, "_get_secret_unbounded", blocked)
    try:
        assert keymaker.get_secret("CTX7") is None        # starts one reader, times out
        started = time.monotonic()
        for _ in range(5):
            assert keymaker.get_secret("CTX7") is None    # no new reader, no wait
        assert time.monotonic() - started < 0.5
        assert calls == ["CTX7"]
    finally:
        release.set()


def test_total_stuck_readers_are_capped(monkeypatch):
    release = threading.Event()
    calls = []
    monkeypatch.setattr(keymaker, "_STUCK_READERS", {})
    monkeypatch.setattr(keymaker, "_STUCK_READERS_MAX", 2)
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "0.1")
    monkeypatch.setattr(keymaker, "_get_secret_unbounded",
                        lambda key: calls.append(key) or release.wait(30))
    try:
        for k in ("A", "B", "C", "D"):
            assert keymaker.get_secret(k) is None
        assert calls == ["A", "B"]
    finally:
        release.set()


def test_reader_that_finishes_late_frees_its_slot(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(keymaker, "_STUCK_READERS", {})
    monkeypatch.setenv(keymaker.ENV_READ_TIMEOUT, "0.1")
    state = {"block": True}

    def read(key):
        if state["block"]:
            release.wait(30)
            return None
        return "fresh"

    monkeypatch.setattr(keymaker, "_get_secret_unbounded", read)
    assert keymaker.get_secret("K2") is None
    state["block"] = False
    release.set()
    time.sleep(0.2)
    assert keymaker.get_secret("K2") == "fresh"
