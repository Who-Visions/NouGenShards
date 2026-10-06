"""Request budgets survive route loading and explicit probe overrides."""
import io
import json

import pytest

from tools import fleet


@pytest.mark.parametrize("explicit,floor,expected", [
    (None, 0, 2048),
    (128, 0, 128),
    (128, 1400, 1400),
    (None, 4096, 4096),
])
def test_configured_route_request_budget(tmp_path, monkeypatch, explicit, floor, expected):
    config = tmp_path / "routes.json"
    config.write_text(json.dumps({"mcpServers": {"local-fixture": {
        "type": "openai-compatible", "url": "https://example.invalid/v1",
        "model": "fixture", "min_tokens": floor,
    }}}))
    dispatcher = fleet.Fleet(str(config), include_local=False, include_vertex=False)

    def respond(request, timeout):
        assert json.loads(request.data)["max_tokens"] == expected
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')

    monkeypatch.setattr(fleet.urllib.request, "urlopen", respond)
    options = {} if explicit is None else {"max_tokens": explicit}
    assert dispatcher._call(dispatcher.routes[0], "fixture", **options) == "ok"


def test_map_request_budget_caps_total_upstream_calls(monkeypatch):
    """A dead pool must not cost prompts*(retries+1) calls. One shared budget caps
    the total; a retry that finds it spent fails fast rather than hammering routes."""
    calls = {"n": 0}

    class _F(fleet.Fleet):
        def __init__(self):
            self.healthy = [{"name": f"r{i}", "model": f"m{i}", "kind": "openrouter"} for i in range(4)]
            self.routes = self.healthy

        def _call(self, rt, prompt, **kw):
            calls["n"] += 1
            raise RuntimeError("boom")

    monkeypatch.setattr(fleet, "_breaker_open", lambda k: None)
    monkeypatch.setattr(fleet, "_breaker_record", lambda *a, **k: None)
    f = _F()
    prompts = ["p1", "p2", "p3", "p4"]
    res = f.map(prompts, retries=2)  # naive worst case = 4*3 = 12 calls
    cap = len(prompts) + max(2, len(prompts) // 2)  # == 6
    assert calls["n"] <= cap
    assert all("FAILED" in r[1] for r in res)
    assert any("budget exhausted" in r[1] for r in res)

    # explicit cap is honoured
    calls["n"] = 0
    f.map(prompts, retries=5, max_requests=3)
    assert calls["n"] <= 3
