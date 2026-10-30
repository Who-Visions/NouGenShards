"""OpenRouter requests turn reasoning off by default; other lanes are untouched."""
import importlib.util
import json
import sys
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
