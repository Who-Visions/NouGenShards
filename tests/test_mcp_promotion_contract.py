"""MCP promotion contract: advertised -> importable -> invocable -> implementation reached -> structured failure."""
import ast
import asyncio
import importlib
import json
from pathlib import Path

import pytest

from nougen_shards import arxiv_radar, mcp

MCP_SRC = Path(mcp.__file__)


def _call(name, args):
    res = asyncio.run(mcp.mcp.call_tool(name, args))
    return json.loads(res.content[0].text)


def _lazy_imports():
    """Every `from .mod import a, b` executed inside a tool body, with the tool that owns it."""
    tree = ast.parse(MCP_SRC.read_text(encoding="utf-8"))
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                out.extend((fn.name, node.module, a.name) for a in node.names)
    return out


def test_every_lazy_import_in_a_tool_body_resolves():
    """Discovery/runtime parity: a tool cannot be advertised while its implementation symbol is missing."""
    missing = []
    found = _lazy_imports()
    assert len(found) >= 20, "scanner found too few lazy imports; a zero here is a blind instrument, not a clean bill"
    for tool, module, name in found:
        try:
            mod = importlib.import_module(f"nougen_shards.{module}")
        except Exception as exc:  # import failure is itself the counterexample
            missing.append(f"{tool}: nougen_shards.{module} import failed: {exc!r}")
            continue
        if not hasattr(mod, name):
            missing.append(f"{tool}: nougen_shards.{module}.{name} missing")
    assert not missing, "advertised tools with unresolved implementation symbols:\n" + "\n".join(missing)


def test_registered_tools_match_decorated_functions():
    advertised = {t.name for t in asyncio.run(mcp.mcp.list_tools())}
    tree = ast.parse(MCP_SRC.read_text(encoding="utf-8"))
    decorated = {
        n.name for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and any("tool" in ast.unparse(d) for d in n.decorator_list)
    }
    assert advertised == decorated, (advertised ^ decorated)


@pytest.mark.parametrize("ref", ["", "   ", "\t\n"])
@pytest.mark.parametrize("action", ["lookup", "fulltext", "claim"])
def test_arxiv_paper_empty_ref_fails_explicitly_through_registered_path(ref, action):
    res = _call("arxiv_paper", {"action": action, "ref": ref, "pattern": "x"})
    assert res["status"] == "error"
    assert "ref required" in res["error"]


def test_arxiv_paper_reaches_implementation_through_registered_path(monkeypatch, tmp_path):
    seen = {}

    class Paper:
        def normalize_id(self, ref):
            seen["ref"] = ref
            return "2609.00001"

        def lookup(self, aid):
            seen["aid"] = aid
            return {"title": "t"}

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": Paper()})
    res = _call("arxiv_paper", {"action": "lookup", "ref": "arXiv:2609.00001"})
    assert res["status"] == "success" and res["metadata"] == {"title": "t"}
    assert seen == {"ref": "arXiv:2609.00001", "aid": "2609.00001"}


def test_refresh_passed_when_signature_declares_it(monkeypatch, tmp_path):
    f = tmp_path / "p.tex"
    f.write_text("hello " * 400, encoding="utf-8")
    calls = []

    class Paper:
        def normalize_id(self, ref):
            return ref

        def fulltext(self, aid, refresh=False):
            calls.append(refresh)
            return f

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": Paper()})
    assert arxiv_radar.run_arxiv_paper("fulltext", "2609.00001", refresh=True)["status"] == "success"
    assert calls == [True]


def test_legacy_fulltext_without_refresh_still_works(monkeypatch, tmp_path):
    f = tmp_path / "p.tex"
    f.write_text("hello " * 400, encoding="utf-8")

    class Paper:
        def normalize_id(self, ref):
            return ref

        def fulltext(self, aid):
            return f

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": Paper()})
    assert arxiv_radar.run_arxiv_paper("fulltext", "2609.00001", refresh=True)["status"] == "success"


def test_genuine_implementation_typeerror_is_not_swallowed(monkeypatch):
    """Counterexample for the old `except TypeError: retry` fallback: it re-ran the call and hid the real bug."""
    calls = []

    class Paper:
        def normalize_id(self, ref):
            return ref

        def fulltext(self, aid, refresh=False):
            calls.append(refresh)
            raise TypeError("implementation bug: unsupported operand")

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": Paper()})
    res = arxiv_radar.run_arxiv_paper("fulltext", "2609.00001")
    assert res["status"] == "error" and "implementation bug" in res["error"]
    assert calls == [False], "implementation must be invoked exactly once, not retried"
