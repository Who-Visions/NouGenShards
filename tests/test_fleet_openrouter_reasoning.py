"""OpenRouter requests turn reasoning off by default; other lanes are untouched."""
import importlib.util
import json
import sys
import time
import urllib.error
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "fleet.py"
_spec = importlib.util.spec_from_file_location("fleet_reasoning_under_test", _TOOL)
fleet = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = fleet
_spec.loader.exec_module(fleet)


def _body(monkeypatch, kind):
    sent = {}

    class Stop(Exception):
        pass

    def fake(req, timeout=0):
        sent.update(json.loads(req.data))
        raise Stop()
    monkeypatch.setattr(fleet.urllib.request, "urlopen", fake)
    f = fleet.Fleet.__new__(fleet.Fleet)
    try:
        f._call_once({"name": "r", "kind": kind, "model": "m", "url": "https://x.test/v1", "headers": {}}, "hi")
    except Stop:
        pass
    return sent


def test_reasoning_off_on_openrouter_only_unless_opted_in(monkeypatch):
    monkeypatch.delenv("NOUGEN_OPENROUTER_REASONING", raising=False)
    monkeypatch.delenv("NOUGEN_PRIVACY", raising=False)
    assert _body(monkeypatch, "openrouter")["reasoning"] == {"enabled": False}
    assert "reasoning" not in _body(monkeypatch, "ollama-cloud")
    monkeypatch.setenv("NOUGEN_OPENROUTER_REASONING", "on")
    assert "reasoning" not in _body(monkeypatch, "openrouter")


def test_mandatory_reasoning_retry_respects_remaining_timeout(monkeypatch):
    """The 400-retry must not reuse the full original timeout -- only what's left
    of it, or a call near its deadline can double its total wait."""
    monkeypatch.delenv("NOUGEN_OPENROUTER_REASONING", raising=False)
    monkeypatch.delenv("NOUGEN_PRIVACY", raising=False)
    calls = []

    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return b'{"choices": [{"message": {"content": "ok"}}]}'

    def fake(req, timeout=0):
        calls.append(timeout)
        if len(calls) == 1:
            monkeypatch.setattr(time, "monotonic", lambda: _t0 + 25)  # eat 25s of the 30s budget
            err = urllib.error.HTTPError(req.full_url, 400, "mandatory", {}, None)
            err.read = lambda: b"Reasoning is mandatory"
            raise err
        return FakeResp()

    monkeypatch.setattr(fleet.urllib.request, "urlopen", fake)
    monkeypatch.setattr(fleet.json, "load", lambda r: json.loads(r.read()))
    _t0 = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: _t0)
    f = fleet.Fleet.__new__(fleet.Fleet)
    f._call_once({"name": "r", "kind": "openrouter", "model": "m",
                 "url": "https://x.test/v1", "headers": {}}, "hi", timeout=30)
    assert len(calls) == 2
    assert calls[0] == 30          # first attempt: full timeout
    assert calls[1] <= 6           # retry: ~30 - 25 elapsed, not another 30
