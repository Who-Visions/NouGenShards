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
        return io.BytesIO(json.dumps({
            "model": "fixture",
            "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        }).encode())

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


def test_openrouter_accounts_auto_diversify_and_probe_uses_reasoning_budget(tmp_path, monkeypatch):
    config = tmp_path / "routes.json"
    config.write_text(json.dumps({"mcpServers": {
        "openrouter-a": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "rate-limited/one:free"},
        "openrouter-b": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "rate-limited/one:free"},
        "openrouter-c": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "rate-limited/one:free"},
    }}))
    # __init__ must diversify without hitting the network
    monkeypatch.setattr(fleet, "refresh_or_diverse", lambda *a, **k: (_ for _ in ()).throw(AssertionError("init must not fetch")))
    f = fleet.Fleet(str(config), include_local=False, include_vertex=False)
    models_init = [r["model"] for r in f.routes]
    assert len(set(models_init)) == 3
    assert all(r["min_tokens"] >= fleet.DIVERSIFY_MIN_TOKENS for r in f.routes)

    # probe() refreshes once, sends max_tokens >= 2048, and resets self.healthy on repeat runs
    refreshes = {"n": 0}

    def fake_refresh(*a, **k):
        refreshes["n"] += 1
        live = [("alpha", "vendor/alpha:free"), ("beta", "vendor/beta:free"), ("gamma", "vendor/gamma:free")]
        monkeypatch.setattr(fleet, "OR_DIVERSE", live)
        return live

    monkeypatch.setattr(fleet, "refresh_or_diverse", fake_refresh)
    seen_budgets = []

    def respond(request, timeout):
        body = json.loads(request.data)
        seen_budgets.append(body["max_tokens"])
        return io.BytesIO(json.dumps({
            "model": body["model"],
            "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
        }).encode())

    monkeypatch.setattr(fleet.urllib.request, "urlopen", respond)
    healthy = f.probe(verbose=False)
    assert refreshes["n"] == 1
    assert len(healthy) == 3
    assert {r["model"] for r in healthy} == {"vendor/alpha:free", "vendor/beta:free", "vendor/gamma:free"}
    assert all(b >= fleet.PROBE_MAX_TOKENS for b in seen_budgets)
    # Repeat probe clears self.healthy rather than accumulating duplicates
    assert len(f.probe(verbose=False)) == 3
    assert len(f.healthy) == 3


def test_call_with_metadata_retries_empty_length_starved_reasoning(tmp_path, monkeypatch):
    config = tmp_path / "routes.json"
    config.write_text(json.dumps({"mcpServers": {
        "nvidia-nim": {"type": "openai-compatible", "url": "https://integrate.api.nvidia.com/v1", "model": "reasoning-m"},
    }}))
    f = fleet.Fleet(str(config), include_local=False, include_vertex=False)
    budgets = []

    def respond(request, timeout):
        body = json.loads(request.data)
        budgets.append(body["max_tokens"])
        if len(budgets) == 1:
            return io.BytesIO(json.dumps({
                "model": "reasoning-m",
                "choices": [{"finish_reason": "length", "message": {"content": "", "reasoning_content": "thinking..."}}],
            }).encode())
        return io.BytesIO(json.dumps({
            "model": "reasoning-m",
            "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
        }).encode())

    monkeypatch.setattr(fleet.urllib.request, "urlopen", respond)
    assert f._call(f.routes[0], "OK") == "OK"
    assert budgets == [2048, 4096]


def test_distinct_openrouter_models_are_preserved(tmp_path):
    config = tmp_path / "routes.json"
    config.write_text(json.dumps({"mcpServers": {
        "openrouter-a": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "custom/a:free"},
        "openrouter-b": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "custom/b:free"},
    }}))
    f = fleet.Fleet(str(config), include_local=False, include_vertex=False)
    assert [r["model"] for r in f.routes] == ["custom/a:free", "custom/b:free"]


def test_identity_mismatch_reported_explicitly_without_500(tmp_path, monkeypatch, capsys):
    config = tmp_path / "routes.json"
    config.write_text(json.dumps({"mcpServers": {
        "nvidia-ds": {"type": "openai-compatible", "url": "https://integrate.api.nvidia.com/v1", "model": "deepseek-ai/DeepSeek-V4-Pro"},
    }}))
    fleet.breaker_reset()
    monkeypatch.setattr(fleet, "BREAKER_MAX", 1)
    monkeypatch.setattr(fleet.time, "sleep", lambda s: None)
    f = fleet.Fleet(str(config), include_local=False, include_vertex=False)

    def respond(request, timeout):
        return io.BytesIO(json.dumps({
            "model": "deepseek/deepseek-chat",
            "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
        }).encode())

    monkeypatch.setattr(fleet.urllib.request, "urlopen", respond)
    assert f.probe(verbose=True) == []
    probe_out = capsys.readouterr().out
    assert "identity_mismatch" in probe_out and "500" not in probe_out

    res = f.map(["prompt"], retries=0)
    assert "identity_mismatch" in res[0][1]
    assert "deepseek-ai/DeepSeek-V4-Pro" in res[0][1]
    assert "deepseek/deepseek-chat" in res[0][1]
    assert "500" not in res[0][1]

    tripped = f.map(["prompt"], retries=0)[0][1]
    assert "identity_mismatch" in tripped and "re-point the route" in tripped


def test_constructor_diversify_opt_out_preserved_across_probe(tmp_path, monkeypatch):
    config = tmp_path / "routes.json"
    config.write_text(json.dumps({"mcpServers": {
        "openrouter-a": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "pinned/m:free"},
        "openrouter-b": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "pinned/m:free"},
    }}))
    f = fleet.Fleet(str(config), include_local=False, include_vertex=False, diversify=False)
    assert [r["model"] for r in f.routes] == ["pinned/m:free", "pinned/m:free"]

    seen_models = []

    def respond(request, timeout):
        body = json.loads(request.data)
        seen_models.append(body["model"])
        return io.BytesIO(json.dumps({
            "model": body["model"],
            "choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
        }).encode())

    monkeypatch.setattr(fleet.urllib.request, "urlopen", respond)
    healthy = f.probe(verbose=False)
    assert len(healthy) == 2
    assert seen_models == ["pinned/m:free", "pinned/m:free"]


def test_live_privacy_mode_blocks_remote_refresh_on_probe(tmp_path, monkeypatch):
    config = tmp_path / "routes.json"
    config.write_text(json.dumps({"mcpServers": {
        "openrouter-a": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "pinned/m:free"},
        "openrouter-b": {"type": "openai-compatible", "url": "https://openrouter.ai/api/v1", "model": "pinned/m:free"},
    }}))
    monkeypatch.delenv("NOUGEN_PRIVACY", raising=False)
    monkeypatch.setattr(fleet, "OR_FREE_CACHE", str(tmp_path / "absent.json"))
    f = fleet.Fleet(str(config), include_local=False, include_vertex=False)

    def boom(*a, **k):
        raise AssertionError("network must not be touched under live NOUGEN_PRIVACY")

    monkeypatch.setattr(fleet.urllib.request, "urlopen", boom)
    monkeypatch.setenv("NOUGEN_PRIVACY", "1")
    f.diversify(refresh=True)
    assert f.probe(verbose=False) == []
    assert f.probe(verbose=False, diversify=True) == []
