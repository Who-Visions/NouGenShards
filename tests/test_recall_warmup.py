"""The node warms the vector cache at startup so the first recall does not miss
the federation deadline. Loaded via AST so importing app at module scope
(gradio, network) is avoided, matching the other app.py tests."""
import ast
import threading
from pathlib import Path

import pytest

import nougen_shards.core as core


def _load(names):
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(fns) == len(names), f"missing {set(names) - {f.name for f in fns}}"
    ns = {"os": __import__("os"), "core": core, "time": __import__("time"), "logging": __import__("logging")}
    exec(compile(ast.fix_missing_locations(ast.Module(body=fns, type_ignores=[])), "app.py", "exec"), ns)
    return ns


@pytest.fixture(autouse=True)
def tmp_vault(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.delenv("NOUGEN_WARMUP", raising=False)
    yield tmp_path


def _warmup_threads():
    return [t for t in threading.enumerate() if t.name == "nougen-recall-warmup"]


def test_warmup_starts_a_daemon_thread_when_a_grid_exists(monkeypatch):
    core.init_db(1)
    ns = _load(["_warmup_enabled", "_start_recall_warmup"])
    calls = []
    monkeypatch.setattr(core, "retrieve", lambda *a, **k: calls.append(k) or [])
    ns["_start_recall_warmup"]()
    for t in _warmup_threads():
        t.join(5)
    assert calls and calls[0]["domain_key"] == "*" and calls[0]["limit"] == 1


def test_warmup_skips_an_empty_grid_and_never_creates_db_files(monkeypatch, tmp_path):
    ns = _load(["_warmup_enabled", "_start_recall_warmup"])
    monkeypatch.setattr(core, "retrieve", lambda *a, **k: pytest.fail("must not retrieve on an empty grid"))
    ns["_start_recall_warmup"]()
    assert not _warmup_threads()
    assert not list(tmp_path.glob("*.db"))


def test_warmup_is_env_switchable(monkeypatch):
    core.init_db(1)
    ns = _load(["_warmup_enabled", "_start_recall_warmup"])
    monkeypatch.setenv("NOUGEN_WARMUP", "0")
    assert ns["_warmup_enabled"]() is False
    monkeypatch.setattr(core, "retrieve", lambda *a, **k: pytest.fail("disabled warm-up must not retrieve"))
    ns["_start_recall_warmup"]()
    assert not _warmup_threads()


def test_warmup_failure_is_logged_not_raised(monkeypatch):
    core.init_db(1)
    ns = _load(["_warmup_enabled", "_start_recall_warmup"])

    def boom(*a, **k):
        raise RuntimeError("ollama down")
    monkeypatch.setattr(core, "retrieve", boom)
    ns["_start_recall_warmup"]()
    for t in _warmup_threads():
        t.join(5)
