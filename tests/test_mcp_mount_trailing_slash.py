"""`/mcp` and `/mcp/` must route identically.

`/mcp` is the documented public front door: a healthy node answers a bad
token with 401, never 404. Starlette's Mount hands the inner ASGI app an
EMPTY path for the bare mount point, so every inner route missed and the door
answered 404 while `/mcp/` served fine in the same process - clients that
omit the trailing slash were told the front door did not exist (2026-09-01
retrieval incident).

These assert ROUTING, using a rejected token so the request is answered by
the gate and never reaches the MCP session manager (which needs the app
lifespan, and whose startup would quick_check the live grid).
"""
import pytest

pytest.importorskip("gradio")

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(app_module, "NODE_TOKEN", "test-token", raising=False)
    return TestClient(app_module.app, follow_redirects=False)


def _status(client, path):
    return client.get(path, headers={"X-NGS-Token": "wrong-token"}).status_code


def test_bare_mcp_is_not_a_404(client):
    assert _status(client, "/mcp") != 404, (
        "/mcp answered 404 - the bare mount point must route into the gate "
        "exactly like /mcp/ does")


def test_bare_and_slashed_mcp_route_identically(client):
    assert _status(client, "/mcp") == _status(client, "/mcp/")


def test_gate_still_rejects_a_bad_token_on_the_bare_path(client):
    # The rewrite must not widen the gate: a wrong token is still a 401.
    assert _status(client, "/mcp") == 401
