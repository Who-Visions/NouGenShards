"""HF Space handoff sync: timeout resolves from env, pull encodes the agent label."""

import json
import logging
import urllib.request

import pytest

from nougen_shards import handoff


class _Resp:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


@pytest.fixture(autouse=True)
def space_env(monkeypatch):
    monkeypatch.delenv("NOUGEN_HF_SYNC_TIMEOUT_S", raising=False)
    monkeypatch.setenv("HF_SPACE_URL", "https://space.example/")
    monkeypatch.setenv("HF_TOKEN", "t0k")


def _record_urlopen(monkeypatch, body: bytes) -> list:
    calls = []

    def fake(req, timeout=None):
        calls.append((req, timeout))
        return _Resp(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


def test_timeout_defaults_when_unset():
    assert handoff._space_sync_timeout() == handoff._SPACE_SYNC_TIMEOUT_FALLBACK_S == 30.0


def test_timeout_env_override(monkeypatch):
    monkeypatch.setenv("NOUGEN_HF_SYNC_TIMEOUT_S", "4.5")
    assert handoff._space_sync_timeout() == 4.5


@pytest.mark.parametrize("val", ["abc", "0", "-3", "nan", "inf"])
def test_timeout_bad_values_fall_back_and_warn(monkeypatch, caplog, val):
    monkeypatch.setenv("NOUGEN_HF_SYNC_TIMEOUT_S", val)
    with caplog.at_level(logging.WARNING, logger="nougen_shards.handoff"):
        assert handoff._space_sync_timeout() == handoff._SPACE_SYNC_TIMEOUT_FALLBACK_S
    assert "NOUGEN_HF_SYNC_TIMEOUT_S" in caplog.text


def test_push_posts_with_env_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_HF_SYNC_TIMEOUT_S", "7")
    calls = _record_urlopen(monkeypatch, b'{"status":"ok"}')
    monkeypatch.setattr(handoff, "_find_handoff",
                        lambda a, i, n: (tmp_path / "h.json", {"handoff_id": "abc", "goal": "g"}))

    handoff.push_handoff_to_space("claude", "abc")

    assert len(calls) == 1
    req, timeout = calls[0]
    assert timeout == 7.0
    assert req.full_url == "https://space.example/sync/push"
    assert req.get_method() == "POST"
    body = json.loads(req.data)
    assert body["agent"] == "claude"
    assert body["handoff_id"] == "abc"


def test_pull_encodes_agent_and_uses_default_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(handoff, "HANDOFF_DIR", tmp_path)
    payload = {"handoff_id": "x1", "goal": "g", "git": {"branch": "main"}, "tasks": {}}
    calls = _record_urlopen(monkeypatch, json.dumps(payload).encode())
    monkeypatch.setattr(handoff, "_sync_handoff_to_db", lambda p, d: True)
    monkeypatch.setattr(handoff, "_handoff_context_metadata", lambda p, d, **k: {})
    monkeypatch.setattr(handoff, "_log_context_event", lambda *a: None)

    handoff.pull_handoff_from_space("Claude Cli")

    assert len(calls) == 1
    req, timeout = calls[0]
    assert timeout == 30.0
    assert req.full_url == "https://space.example/sync/pull?agent=Claude+Cli"
    assert req.get_header("Authorization") == "Bearer t0k"
    assert len(list(tmp_path.rglob("handoff_x1.json"))) == 1
