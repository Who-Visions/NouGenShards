"""The boot quick_check heal runs off the startup path, so a slow O(vault) scan
can never hold the node unbound (WhoArt 9/14/2026: 7+ min unbound, 15 GB read).
Loaded via AST like tests/test_recall_warmup.py, so gradio/network never import."""
import ast
import logging
import threading
import time
from pathlib import Path

import nougen_shards.core as core


def _load():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_start_boot_quarantine"]
    assert len(fns) == 1
    ns = {"core": core, "time": time, "logger": logging.getLogger("test_boot_quarantine")}
    exec(compile(ast.fix_missing_locations(ast.Module(body=fns, type_ignores=[])), "app.py", "exec"), ns)
    return ns["_start_boot_quarantine"]


def test_returns_at_once_and_warmup_follows_the_heal(monkeypatch):
    order, done = [], threading.Event()

    def slow_heal():
        time.sleep(0.5)
        order.append("heal")
        return []
    monkeypatch.setattr(core, "quarantine_malformed_dbs", slow_heal)
    started = time.perf_counter()
    _load()(then=lambda: (order.append("warmup"), done.set()))
    assert time.perf_counter() - started < 0.2, "the heal must not block startup"
    assert done.wait(5)
    assert order == ["heal", "warmup"]


def test_warmup_still_runs_when_the_heal_raises(monkeypatch):
    done = threading.Event()

    def broken():
        raise OSError("volume gone")
    monkeypatch.setattr(core, "quarantine_malformed_dbs", broken)
    _load()(then=done.set)
    assert done.wait(5)


def test_lifespan_no_longer_scans_inline():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    lifespan = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_lifespan")
    attr_calls = {n.func.attr for n in ast.walk(lifespan)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    name_calls = {n.func.id for n in ast.walk(lifespan)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "quarantine_malformed_dbs" not in attr_calls
    assert "_start_boot_quarantine" in name_calls
