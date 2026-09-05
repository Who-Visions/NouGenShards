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
