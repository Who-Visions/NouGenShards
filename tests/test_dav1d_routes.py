"""dav1d/exec and dav1d/agy must not block the shared threadpool.

2026-09-01, pairs with #161's async /health fix (shard 17607: every heavy
endpoint here shared one anyio threadpool; a wedged /dav1d call could starve
everything else, including /health). See wargame dav1d-end-to-end.md, Move
A1/A2. Prior to this fix these routes hung ~45s on a slow AGY command
(shard 22729) while running as plain sync def on the shared pool.
"""
import asyncio
import time

import pytest


@pytest.fixture()
def app_module():
    pytest.importorskip("gradio")
    import app
    return app


class TestDav1dRoutesAsync:
    def test_routes_are_coroutine_functions(self, app_module):
        assert asyncio.iscoroutinefunction(app_module.dav1d_exec_endpoint)
        assert asyncio.iscoroutinefunction(app_module.dav1d_agy_endpoint)

    def test_exec_endpoint_offloads_and_returns_result(self, app_module, monkeypatch):
        calls = {}

        def fake_run_dav1d_agy(**kwargs):
            calls.update(kwargs)
            return {"status": "ok", "exit_code": 0}

        monkeypatch.setattr(app_module, "run_dav1d_agy", fake_run_dav1d_agy)
        req = app_module.Dav1dExecRequest(
            command="agy", subcommand="mcp list", args=None, prompt=None, timeout=30
        )
        result = asyncio.run(app_module.dav1d_exec_endpoint(req, _tenant=None))
        assert result == {"status": "ok", "exit_code": 0}
        assert calls["command"] == "agy"
        assert calls["subcommand"] == "mcp list"
        assert calls["timeout"] == 30

    def test_agy_endpoint_forces_command_agy(self, app_module, monkeypatch):
        monkeypatch.setattr(
            app_module, "run_dav1d_agy", lambda **kw: {"status": "ok", "command": kw["command"]}
        )
        req = app_module.Dav1dExecRequest(
            command="ignored", subcommand="models", args=["x"], prompt="p", timeout=5
        )
        result = asyncio.run(app_module.dav1d_agy_endpoint(req, _tenant=None))
        # /dav1d/agy always forces command="agy" regardless of the request body.
        assert result["command"] == "agy"

    def test_slow_dav1d_call_does_not_block_a_concurrent_coroutine(self, app_module, monkeypatch):
        """The actual bug this fix prevents: a slow blocking dav1d call must
        not starve other async work sharing the event loop."""

        def slow_run_dav1d_agy(**kwargs):
            time.sleep(0.3)  # stands in for the real blocking subprocess.run
            return {"status": "ok"}

        monkeypatch.setattr(app_module, "run_dav1d_agy", slow_run_dav1d_agy)
        req = app_module.Dav1dExecRequest()
        events = []

        async def other_coro():
            for _ in range(6):
                await asyncio.sleep(0.05)
                events.append("tick")

        async def run_both():
            await asyncio.gather(
                app_module.dav1d_exec_endpoint(req, _tenant=None),
                other_coro(),
            )

        asyncio.run(run_both())
        # If the blocking call ran on the event loop instead of the
        # threadpool, these ticks would be serialized after it finished
        # instead of interleaving while it runs.
        assert len(events) == 6
