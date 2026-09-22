"""agy_msg: inbox dir, HTTP fallback config, and send_local transport paths."""
from pathlib import Path
from unittest.mock import MagicMock

from nougen_shards import agy_msg
from nougen_shards.agy_msg import AgyMsgBus, get_inbox_dir


def _pipe_down(monkeypatch):
    monkeypatch.setattr(
        AgyMsgBus,
        "send_pipe_windows",
        staticmethod(lambda payload, pipe_name=agy_msg.PIPE_NAME: {"delivered": False, "error": "WinError 2"}),
    )


def test_get_inbox_dir_env(tmp_path, monkeypatch):
    env_path = tmp_path / "custom_inbox"
    monkeypatch.setenv("NOUGEN_AGY_INBOX_DIR", str(env_path))
    assert get_inbox_dir() == env_path


def test_get_inbox_dir_default_does_not_create(tmp_path, monkeypatch):
    monkeypatch.delenv("NOUGEN_AGY_INBOX_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    res = get_inbox_dir()
    assert res == tmp_path / ".nougen" / "agy_inbox"
    assert not res.exists()


def test_http_timeout(monkeypatch, caplog):
    monkeypatch.delenv("NOUGEN_AGY_MSG_TIMEOUT_S", raising=False)
    assert agy_msg._http_timeout() == agy_msg.DEFAULT_HTTP_TIMEOUT_S

    monkeypatch.setenv("NOUGEN_AGY_MSG_TIMEOUT_S", "4")
    assert agy_msg._http_timeout() == 4.0

    monkeypatch.setenv("NOUGEN_AGY_MSG_TIMEOUT_S", "abc")
    assert agy_msg._http_timeout() == agy_msg.DEFAULT_HTTP_TIMEOUT_S
    assert "NOUGEN_AGY_MSG_TIMEOUT_S" in caplog.text

    monkeypatch.setenv("NOUGEN_AGY_MSG_TIMEOUT_S", "0")
    assert agy_msg._http_timeout() == agy_msg.DEFAULT_HTTP_TIMEOUT_S


def test_http_url_empty_env_falls_back(monkeypatch):
    monkeypatch.setenv("NOUGEN_AGY_MSG_URL", "")
    assert agy_msg._http_url() == agy_msg.DEFAULT_HTTP_URL


def test_send_local_http_uses_env_url_and_timeout(monkeypatch):
    _pipe_down(monkeypatch)
    monkeypatch.setenv("NOUGEN_AGY_MSG_URL", "http://127.0.0.1:1/x")
    monkeypatch.setenv("NOUGEN_AGY_MSG_TIMEOUT_S", "2.5")
    recorded = {}

    def fake_urlopen(req, timeout=None):
        recorded["url"] = req.full_url
        recorded["timeout"] = timeout
        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = b'{"ok": true}'
        return resp

    monkeypatch.setattr(agy_msg.urllib.request, "urlopen", fake_urlopen)
    res = AgyMsgBus.send_local("hello")

    assert res == {"delivered": True, "transport": "http", "response": {"ok": True}}
    assert recorded == {"url": "http://127.0.0.1:1/x", "timeout": 2.5}


def test_send_local_both_transports_down(monkeypatch):
    _pipe_down(monkeypatch)

    def fake_urlopen(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(agy_msg.urllib.request, "urlopen", fake_urlopen)
    res = AgyMsgBus.send_local("hello")

    assert res["delivered"] is False
    assert "pipe_and_http_failed" in res["error"]
    assert res["pipe_error"] in ("WinError 2", None)


def test_antigravity_adapter_health_reports_inbox_dir(tmp_path, monkeypatch):
    """Regression: health() imported a get_inbox_dir that agy_msg never defined."""
    from nougen_shards.wake.adapters import AntigravityAdapter

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("NOUGEN_AGY_INBOX_DIR", str(tmp_path / "inbox"))
    adapter = AntigravityAdapter()
    monkeypatch.setattr(adapter, "_bin_path", lambda: None)

    health = adapter.health()

    assert health["inbox_dir"] == str(tmp_path / "inbox")
    assert health["status"] == "missing"
