"""The Black Glass MCP tools over the Xoah self archive (app.py).

Each tool is exercised against a synthetic archive in a temp dir, so the tests
pin wiring and layers, not canon.
"""
import asyncio
import inspect
import json
import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")
pytest.importorskip("mcp")

_tmp = tempfile.mkdtemp(prefix="ngs_xoah_tools_")
os.environ.setdefault("NGS_NODE_TOKEN", "test-xoah-token")
os.environ.setdefault("NOUGEN_HOME", _tmp)
os.environ.setdefault("NOUGEN_VAULT_DIR", os.path.join(_tmp, ".vault"))

import app as node  # noqa: E402
from nougen_shards import self_archive as sa  # noqa: E402

PROV = ["shard:test"]
TOOLS = ("xoah_relationship", "xoah_then_vs_now", "xoah_precedents",
         "xoah_conservation", "xoah_unwritten", "xoah_active_scars")


def _call(name, **kwargs):
    result = getattr(node, name)(**kwargs)
    return asyncio.run(result) if inspect.isawaitable(result) else result


@pytest.fixture
def archive(tmp_path, monkeypatch):
    data = {
        "birth_year": 2160, "terminal_year": 2300, "volume_years": {"1": 2170},
        "nodes": [
            {"id": "n_a", "year": 2170, "episode": 1, "coordinate": "2170", "provenance": PROV,
             "event": "the fire", "belief_then": "the fire was an accident",
             "revealed_truth": "SECRET_REVEAL", "terminal_interpretation": "SECRET_TERMINAL",
             "precedents": [{"summary": "held the line under fire", "tags": ["fire"]}]},
            {"id": "n_b", "year": 2180, "episode": 2, "coordinate": "2180", "provenance": PROV,
             "event": "she leaves"},
        ],
        "edges": [{"from": "n_a", "to": "n_b", "type": "CAUSES"},
                  {"from": "n_a", "to": "w_burn", "type": "TRAUMATIZES"}],
        "wounds": [{"id": "w_burn", "name": "burn", "year": 2170, "bias": "avoids fire",
                    "blocks": [], "provenance": PROV}],
        "relationships": [{"entity": "Mara", "provenance": PROV,
                           "timeline": [{"year": 2170, "love": 0.9, "trust": 0.1}]}],
    }
    path = tmp_path / "archive.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("NOUGEN_SELF_ARCHIVE_PATH", str(path))
    sa.load_archive(path, force=True)
    return path


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(node.node_mcp.list_tools())}
    assert set(TOOLS) <= names


def test_tools_answer_from_the_archive(archive):
    rel = _call("xoah_relationship", entity="Mara", coordinate="2175")
    assert (rel["state"]["love"], rel["state"]["trust"]) == (0.9, 0.1)
    assert rel["provenance"] == PROV

    tvn = _call("xoah_then_vs_now", coordinate="2170")
    assert "SECRET_REVEAL" not in json.dumps(tvn["then"])

    prec = _call("xoah_precedents", topic="fire", coordinate="2175")
    assert prec["precedents"] and prec["precedents"][0]["node"] == "n_a"

    cost = _call("xoah_conservation", removed_event_id="n_a")
    assert cost["violation"] is True and cost["lost_wounds"] == ["w_burn"]

    assert _call("xoah_unwritten", query="episode 7")["layer"] == "UNWRITTEN_SELF"
    assert _call("xoah_unwritten", query="episode 1")["layer"] == "AUTHORED"

    scars = _call("xoah_active_scars", coordinate="2175")
    assert [w["id"] for w in scars["active_scars"]] == ["w_burn"]


def test_rest_routes_match_the_tools(archive):
    """The fleet connector reaches the node over REST, not MCP."""
    from fastapi.testclient import TestClient

    client = TestClient(node.app)
    auth = {"X-NGS-Token": node.NODE_TOKEN}
    cases = (("/xoah/relationship", {"entity": "Mara", "coordinate": "2175"}, "xoah_relationship"),
             ("/xoah/then_vs_now", {"coordinate": "2170"}, "xoah_then_vs_now"),
             ("/xoah/precedents", {"topic": "fire", "coordinate": "2175"}, "xoah_precedents"),
             ("/xoah/conservation", {"removed_event_id": "n_a"}, "xoah_conservation"),
             ("/xoah/unwritten", {"query": "episode 7"}, "xoah_unwritten"),
             ("/xoah/active_scars", {"coordinate": "2175"}, "xoah_active_scars"))
    for route, body, tool in cases:
        res = client.post(route, json=body, headers=auth)
        assert res.status_code == 200, (route, res.text)
        assert res.json() == _call(tool, **body), route
    assert client.post("/xoah/unwritten", json={"query": "episode 7"}).status_code in (401, 403)


def test_tools_report_archive_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_SELF_ARCHIVE_PATH", str(tmp_path / "missing.json"))
    for name, kwargs in (("xoah_relationship", {"entity": "Mara", "coordinate": "2175"}),
                         ("xoah_then_vs_now", {"coordinate": "2170"}),
                         ("xoah_conservation", {"removed_event_id": "n_a"}),
                         ("xoah_unwritten", {"query": "episode 7"}),
                         ("xoah_active_scars", {"coordinate": "2175"})):
        assert _call(name, **kwargs)["layer"] == sa.ARCHIVE_ABSENT, name
