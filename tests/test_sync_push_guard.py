"""One bad row must never 500 a /sync/push batch.

Regression for a guard that has now been lost once: #148 added it, a later
merge dropped it, and on 2026-08-31 the loss resurfaced as deterministic 500
cascades (rows whose encrypted bodies fail cross-machine decrypt raised
before capture and killed whole 100-row batches, three retries each). The
guard must wrap the ENTIRE per-shard body - decrypt, parsing, and capture.
These are AST structure tests so the invariant survives refactors and cannot
pass by accident against an unguarded loop.
"""
import ast
from pathlib import Path


def _sync_push_fn():
    src = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "sync_push")


def test_sync_push_wraps_whole_per_shard_body_in_guard():
    fn = _sync_push_fn()
    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    assert loops, "sync_push lost its shard loop"
    first = loops[0].body[0]
    assert isinstance(first, ast.Try), (
        "sync_push's per-shard guard is MISSING (again) - the whole per-shard "
        "body must sit inside a try so one bad row cannot 500 the batch")
    guarded = ast.dump(first)
    assert "decrypt_text" in guarded, "decrypt must be inside the guard"
    assert "capture" in guarded, "capture must be inside the guard"
    handler_dump = " ".join(ast.dump(h) for h in first.handlers)
    assert "errored" in handler_dump, "failures must be counted, not raised"


def test_sync_push_reports_errored_field():
    fn = _sync_push_fn()
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert any("errored" in ast.dump(r) for r in returns), (
        "sync_push's response must expose the errored count")
