"""cc_msg's default sender resolves from this node at call time, never a baked-in identity."""

import importlib.util
import pathlib


_TOOL = pathlib.Path(__file__).resolve().parent.parent / "tools" / "cc_msg.py"


def _load():
    spec = importlib.util.spec_from_file_location("cc_msg_under_test", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_sender_follows_node_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE", "probe-node-xyz")
    assert _load().default_sender() == "probe-node-xyz"


def test_default_sender_is_not_the_old_hardcoded_identity(monkeypatch):
    for var in ("NOUGEN_NODE", "NOUGEN_NODE_NAME", "NOUGEN_MACHINE"):
        monkeypatch.delenv(var, raising=False)
    assert _load().default_sender() != "Apollo-AGY"


def test_default_sender_falls_back_without_raising(monkeypatch):
    mod = _load()
    import builtins

    real_import = builtins.__import__

    def boom(name, *a, **k):
        if name == "nougen_shards.locator":
            raise ImportError("simulated")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", boom)
    assert mod.default_sender() == "unknown"
