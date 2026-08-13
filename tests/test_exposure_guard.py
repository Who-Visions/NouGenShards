"""Fail-closed exposure guards in app.py.

The node decides two things at import time from the resolved bind: whether to
mount the unauthenticated Cortex HUD, and whether to publish the interactive API
docs (/docs, /redoc, /openapi.json). Both must stay OFF on a network-reachable
host unless the operator explicitly configures otherwise - the data endpoints are
token-gated, but an open API map hands an unauthenticated caller the full surface
including the /sync/pull whole-vault export.

The decision runs at module import, so each case reloads app.py under a patched
environment and the module is restored to the baseline afterwards.
"""
import importlib
import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

_tmp = tempfile.mkdtemp(prefix="ngs_exposure_")
os.environ.setdefault("NGS_NODE_TOKEN", "test-node-token")
os.environ["NOUGEN_HOME"] = _tmp
os.environ["NOUGEN_VAULT_DIR"] = os.path.join(_tmp, ".vault")

import app as node  # noqa: E402


def _reload(monkeypatch, **env):
    """Reload app.py with SPACE_ID / NGS_DOCS_PUBLIC set to the given values.

    A value of None deletes the variable. monkeypatch restores the environment,
    and the fixture below reloads the module back to the baseline so later test
    modules see the app they expect.
    """
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return importlib.reload(node)


@pytest.fixture(autouse=True)
def _restore_baseline():
    yield
    for key in ("SPACE_ID", "NGS_DOCS_PUBLIC"):
        os.environ.pop(key, None)
    importlib.reload(node)


def test_loopback_serves_docs(monkeypatch):
    """A local node keeps its docs - that's where you want them."""
    m = _reload(monkeypatch, SPACE_ID=None, NGS_DOCS_PUBLIC=None)
    assert m._network_exposed is False
    assert m._serve_docs is True
    assert m.app.docs_url == "/docs"
    assert m.app.openapi_url == "/openapi.json"


def test_exposed_withholds_docs(monkeypatch):
    """On a managed platform (SPACE_ID) the API map is withheld by default."""
    m = _reload(monkeypatch, SPACE_ID="nougenai/NouGenShards", NGS_DOCS_PUBLIC=None)
    assert m._network_exposed is True
    assert m._serve_docs is False
    assert m.app.docs_url is None
    assert m.app.redoc_url is None
    assert m.app.openapi_url is None


def test_exposed_withholds_docs_over_http(monkeypatch):
    """The withheld routes actually 404 - not merely unset on the app object."""
    from fastapi.testclient import TestClient

    m = _reload(monkeypatch, SPACE_ID="nougenai/NouGenShards", NGS_DOCS_PUBLIC=None)
    client = TestClient(m.app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # The guard is scoped to the docs: health stays public by design.
    assert client.get("/health").status_code == 200


def test_docs_opt_in_is_reported_in_health(monkeypatch):
    """Opting in is allowed but must be visible in the readiness report."""
    from fastapi.testclient import TestClient

    m = _reload(monkeypatch, SPACE_ID="nougenai/NouGenShards", NGS_DOCS_PUBLIC="1")
    assert m._serve_docs is True
    body = TestClient(m.app).get("/health").json()
    assert body["api_docs_public"] is True
    assert any("NGS_DOCS_PUBLIC" in w for w in body["warnings"])


def test_health_reports_docs_withheld(monkeypatch):
    """Default exposed deploy reports no public docs and raises no docs warning."""
    from fastapi.testclient import TestClient

    m = _reload(monkeypatch, SPACE_ID="nougenai/NouGenShards", NGS_DOCS_PUBLIC=None)
    body = TestClient(m.app).get("/health").json()
    assert body["api_docs_public"] is False
    assert not any("NGS_DOCS_PUBLIC" in w for w in body["warnings"])


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("  ", False),
])
def test_docs_opt_in_parsing(monkeypatch, value, expected):
    """The opt-in is env-driven; accept the usual truthy spellings only."""
    m = _reload(monkeypatch, SPACE_ID="nougenai/NouGenShards", NGS_DOCS_PUBLIC=value)
    assert m._serve_docs is expected


def test_hud_withheld_when_exposed_without_auth(monkeypatch):
    """The original guard this file is named for: no HUD on an exposed host."""
    from fastapi.testclient import TestClient

    m = _reload(monkeypatch, SPACE_ID="nougenai/NouGenShards", NGS_DOCS_PUBLIC=None)
    assert m._hud_auth is None
    # Root is the Gradio mount point; unmounted means 404, not an open UI.
    assert TestClient(m.app).get("/").status_code == 404


def test_mcp_stays_up_when_guards_fire(monkeypatch):
    """Withholding the HUD and docs must not take the token gate down with it."""
    from fastapi.testclient import TestClient

    m = _reload(monkeypatch, SPACE_ID="nougenai/NouGenShards", NGS_DOCS_PUBLIC=None)
    # 401 (not 404) proves the mount is live and rejecting on the token.
    assert TestClient(m.app).get("/mcp/").status_code == 401
