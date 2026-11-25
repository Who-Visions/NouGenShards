"""Rhea's `relay` tool: reading the fleet baton must not raise NameError.

`_run_tool` read `leg_id` without ever taking it from the call, so every relay
call (with or without an id) crashed. The prompt documents `{"tool": "relay",
"id": "<leg id>"}` and says to omit id for the latest leg.
"""
import base64
import json

import rhea_noir


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _b64(text):
    return {"content": base64.b64encode(text.encode()).decode()}


def _install(monkeypatch, seen):
    monkeypatch.setenv("NOUGEN_RELAY_GITHUB_TOKEN", "t")
    monkeypatch.setenv("NOUGEN_RELAY_REPO", "o/r")

    def fake_urlopen(req, timeout=30):
        url = req.full_url
        seen.append(url)
        if "/git/trees/" in url:
            return _Resp({"tree": [
                {"path": ".handoffs/a-1.json", "type": "blob"},
                {"path": ".handoffs/b-2.json", "type": "blob"},
                {"path": ".handoffs/b-2.md", "type": "blob"},
            ]})
        if url.endswith(".json?ref=main"):
            return _Resp(_b64(json.dumps({"status": "open", "goal": "g"})))
        if url.endswith(".md?ref=main"):
            return _Resp(_b64("body text"))
        raise AssertionError(url)

    monkeypatch.setattr(rhea_noir.urllib.request, "urlopen", fake_urlopen)


def test_relay_without_id_reads_latest_leg(monkeypatch):
    seen = []
    _install(monkeypatch, seen)
    out = rhea_noir._run_tool({"tool": "relay"})
    assert out["id"] == "b-2"
    assert out["goal"] == "g"
    assert out["body"] == "body text"


def test_relay_with_id_reads_that_leg_and_sanitizes(monkeypatch):
    seen = []
    _install(monkeypatch, seen)
    out = rhea_noir._run_tool({"tool": "relay", "id": "a-1/../x"})
    assert out["id"] == "a-1..x"
    assert any("/.handoffs/a-1..x.json" in u for u in seen)
    assert not any("/git/trees/" in u for u in seen)
