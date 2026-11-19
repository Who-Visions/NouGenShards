"""ngs_node_serve must hand the chosen port to the child as NGS_PORT so the
app's listener self-check guards the port uvicorn actually binds."""
import importlib.util
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parents[1] / "tools" / "ngs_node_serve.py"
    spec = importlib.util.spec_from_file_location("ngs_node_serve", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_child_env_exports_chosen_port_and_token(monkeypatch):
    monkeypatch.delenv("NGS_PORT", raising=False)
    mod = _load()
    env = mod.child_env(4457, "tok")
    assert env["NGS_PORT"] == "4457" and env["NGS_NODE_TOKEN"] == "tok"
    assert "src" in env["PYTHONPATH"]


def test_child_env_overrides_stale_env_port(monkeypatch):
    monkeypatch.setenv("NGS_PORT", "1111")
    mod = _load()
    assert mod.child_env(4444, None)["NGS_PORT"] == "4444"
    assert "NGS_NODE_TOKEN" not in mod.child_env(4444, None) or mod.child_env(4444, None).get("NGS_NODE_TOKEN") == __import__("os").environ.get("NGS_NODE_TOKEN")
