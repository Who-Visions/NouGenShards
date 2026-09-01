"""One malformed grid DB must never 500 a /sync/pull or /sync/hashes sweep.

Regression for the 2026-09-01 Space-sqlite P1 (grid DBs 1,2,4,6,7,9 "disk
image is malformed"): both export endpoints iterated every grid DB with no
per-DB guard, so the first corrupt index raised sqlite3.DatabaseError and the
whole export 500'd -- exactly when a puller needs everything the OTHER
indices still hold. Salvage of the healthy indices was impossible until the
guard existed.

AST structure tests, same doctrine as test_sync_push_guard.py: the invariant
survives refactors and cannot pass by accident against an unguarded loop.
"""
import ast
from pathlib import Path


def _fn(name):
    src = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _per_db_try(fn_node):
    loops = [n for n in ast.walk(fn_node) if isinstance(n, ast.For)]
    assert loops, f"{fn_node.name} lost its per-DB loop"
    tries = [n for n in ast.walk(loops[0]) if isinstance(n, ast.Try)]
    assert tries, f"{fn_node.name}'s per-DB guard is MISSING"
    return tries[0]


def _catches_database_error(try_node):
    for handler in try_node.handlers:
        types = handler.type
        if types is None:
            return True
        candidates = types.elts if isinstance(types, ast.Tuple) else [types]
        for node in candidates:
            if ast.unparse(node) in ("sqlite3.DatabaseError", "sqlite3.Error",
                                     "Exception", "BaseException"):
                return True
    return False


def test_sync_pull_guards_each_db_against_malformed_files():
    guard = _per_db_try(_fn("sync_pull"))
    assert _catches_database_error(guard), (
        "sync_pull's per-DB try must catch sqlite3.DatabaseError -- "
        "OperationalError alone never matches 'disk image is malformed'")


def test_sync_pull_surfaces_degraded_dbs():
    fn = _fn("sync_pull")
    dump = ast.dump(fn)
    assert "X-NGS-Degraded-DBs" in dump, (
        "sync_pull must surface skipped DBs (degraded state must be "
        "observable, not silently partial)")


def test_sync_hashes_guards_each_db_against_malformed_files():
    guard = _per_db_try(_fn("sync_hashes"))
    assert _catches_database_error(guard), (
        "sync_hashes' per-DB try must catch sqlite3.DatabaseError")


def test_sync_hashes_reports_skipped_dbs():
    fn = _fn("sync_hashes")
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert any("databases_skipped" in ast.dump(r) for r in returns), (
        "sync_hashes' response must expose databases_skipped")
