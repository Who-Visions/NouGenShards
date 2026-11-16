"""The per-prompt recall hook must answer and leave.

Two failures kept it from doing either on a busy vault: a read wrote an
ACCESSED row and waited for the history database's writer slot, and the
process could not exit while pool threads were still waiting there.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from nougen_shards import core, history, recall_hook  # noqa: E402


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_NODE", "0")
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.setenv("NOUGEN_EMBED_CAPTURE_TIMEOUT_S", "0.2")
    monkeypatch.setenv("NOUGEN_RECON_SWEEP_TRIGGER", "never")
    return tmp_path


@pytest.fixture
def written(monkeypatch):
    """Record every row the history layer is asked to write, without a database."""
    rows: list = []

    class _Conn:
        def executemany(self, _sql, batch):
            rows.extend(batch)

        def execute(self, _sql, row=()):
            rows.append(row)

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(history, "get_history_connection", lambda: _Conn())
    monkeypatch.setattr(history, "init_history_db", lambda: None)
    return rows


def _types(rows):
    return [r[2] for r in rows]


def test_access_rows_are_written_by_default(written):
    history.log_events([(1, 0, "ACCESSED"), (2, 0, "ACCESSED")])
    history.log_event(3, 0, "ACCESSED")
    assert _types(written) == ["ACCESSED", "ACCESSED", "ACCESSED"]


def test_switch_drops_access_rows_and_keeps_everything_else(written):
    previous = history.set_access_logging(False)
    try:
        history.log_events([(1, 0, "ACCESSED"), (0, 0, "DB_DEGRADED"), (2, 0, "ACCESSED")])
        history.log_event(3, 0, "ACCESSED")
        history.log_event(0, 1, "SEARCH_FALLBACK")
    finally:
        history.set_access_logging(previous)
    assert _types(written) == ["DB_DEGRADED", "SEARCH_FALLBACK"]


def test_adapter_reads_without_writing_and_restores_the_switch(vault, monkeypatch):
    seen: list = []

    def fake_recall(_prompt, **_kw):
        seen.append(history._ACCESS_LOGGING)  # pylint: disable=protected-access
        return {"tier": "keyword", "partial": False, "shards": [], "mark": {}}

    monkeypatch.setattr(recall_hook, "recall_hook", fake_recall)
    assert history._ACCESS_LOGGING is True  # pylint: disable=protected-access
    recall_hook.claude_code_hook(json.dumps({"prompt": "bridge token rotation"}))
    assert seen == [False]
    assert history._ACCESS_LOGGING is True  # pylint: disable=protected-access


def test_adapter_keeps_access_rows_when_asked(vault, monkeypatch):
    seen: list = []
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_ACCESS_LOG", "1")
    monkeypatch.setattr(recall_hook, "recall_hook",
                        lambda _p, **_k: seen.append(history._ACCESS_LOGGING) or {"tier": "none", "shards": []})  # pylint: disable=protected-access
    recall_hook.claude_code_hook(json.dumps({"prompt": "bridge token rotation"}))
    assert seen == [True]


@pytest.mark.parametrize("raw,expected", [
    ("", recall_hook.DEFAULT_BUDGET_MS), ("3500", 3500), ("nonsense", recall_hook.DEFAULT_BUDGET_MS),
    ("0", recall_hook.DEFAULT_BUDGET_MS), ("-5", recall_hook.DEFAULT_BUDGET_MS),
])
def test_installed_hook_budget_comes_from_env(vault, monkeypatch, raw, expected):
    got: list = []
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_BUDGET_MS", raw)
    monkeypatch.setattr(recall_hook, "recall_hook",
                        lambda _p, **kw: got.append(kw.get("budget_ms")) or {"tier": "none", "shards": []})
    recall_hook.claude_code_hook(json.dumps({"prompt": "bridge token rotation"}))
    assert got == [expected]


def test_explicit_budget_beats_env(vault, monkeypatch):
    got: list = []
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_BUDGET_MS", "9000")
    monkeypatch.setattr(recall_hook, "recall_hook",
                        lambda _p, **kw: got.append(kw.get("budget_ms")) or {"tier": "none", "shards": []})
    recall_hook.claude_code_hook(json.dumps({"prompt": "bridge token rotation"}), budget_ms=1234)
    assert got == [1234]


# A driver that makes the recall leave a pool thread stuck, the way a scan
# waiting on the history writer slot does, then runs the real CLI entry.
_DRIVER = """
import sys, time
from concurrent.futures import ThreadPoolExecutor
from nougen_shards import agent_hooks, cli

STUCK_S = float(sys.argv[1])
pool = ThreadPoolExecutor(max_workers=1)

def prompt_handler(_evt):
    pool.submit(time.sleep, STUCK_S)   # joined at interpreter exit unless the entry leaves first
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "answered"}}

agent_hooks.HANDLERS["prompt"] = prompt_handler
sys.argv = ["nougen", "hook", "run", "prompt"]
cli.main()
"""


def _run_driver(tmp_path, hard_exit: str, stuck_s: float):
    env = {**os.environ, "PYTHONPATH": str(SRC), "NOUGEN_HOOK_HARD_EXIT": hard_exit,
           "NOUGEN_VAULT_DIR": str(tmp_path)}
    started = time.monotonic()
    proc = subprocess.run([sys.executable, "-c", _DRIVER, str(stuck_s)], input=b"{}",
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                          timeout=stuck_s * 4 + 60, check=False)
    return proc, time.monotonic() - started


def test_prompt_hook_leaves_as_soon_as_it_has_answered(tmp_path):
    stuck_s = 8.0
    # Control: without the hard exit the stuck thread holds the process.
    control, control_s = _run_driver(tmp_path, "0", stuck_s)
    assert b"answered" in control.stdout
    assert control_s >= stuck_s, f"control did not reproduce the hang ({control_s:.1f}s)"

    proc, took = _run_driver(tmp_path, "1", stuck_s)
    assert proc.returncode == 0
    assert b"answered" in proc.stdout, "the answer must be flushed before leaving"
    assert took < control_s - stuck_s / 2, f"hook stayed {took:.1f}s with a stuck thread (control {control_s:.1f}s)"
