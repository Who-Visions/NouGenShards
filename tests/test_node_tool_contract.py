"""The node MCP tools in app.py must accept every argument the MCP-layer twin accepts.

The ChatGPT/edge path calls app.py's node_mcp tools, not src/nougen_shards/mcp.py. On
2026-10-01 app.py's arxiv_radar took only (mode, recipe_path), so a caller's channels,
limit and commit were dropped and every request ran as channels=["cs"] (audit leg
20261001T165934Z). app.py imports gradio at module scope, so it is read with ast.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("arxiv_radar", "arxiv_lab_watch", "arxiv_paper", "morph_gate")


def _params(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            decorators = [ast.unparse(d) for d in node.decorator_list]
            if any("tool" in d for d in decorators):
                args = node.args
                return {a.arg for a in args.args + args.kwonlyargs}
    return None


def test_node_tools_accept_every_mcp_layer_argument():
    for name in TOOLS:
        node = _params(ROOT / "app.py", name)
        layer = _params(ROOT / "src" / "nougen_shards" / "mcp.py", name)
        assert node is not None, f"app.py has no node_mcp tool {name}"
        assert layer is not None, f"mcp.py has no tool {name}"
        assert layer <= node, f"{name}: app.py drops {sorted(layer - node)}"


def test_arxiv_radar_node_tool_forwards_what_it_accepts():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    start = src.index("def arxiv_radar(")
    body = src[start:src.index("@node_mcp.tool()", start)]
    for arg in ("channels", "mode", "limit", "commit", "recipe_path"):
        assert f"{arg}={arg}" in body, f"arxiv_radar does not forward {arg}"
