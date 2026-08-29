"""Every grid fan-out must guard its own get_connection().

Two humans-with-tools read core.py carefully on 2026-08-29 and the first pass
still left two fan-out loops unguarded -- including the SECOND pass inside
_keyword_retrieve, whose first pass had just been fixed. One function, two
fan-outs, one patch. Reading harder is not the fix; the invariant is
mechanically checkable, so check it mechanically.

INVARIANT: if a loop's body calls get_connection(<the loop variable>), that
call must sit inside a try whose handlers catch sqlite3.DatabaseError.

Why the CALL and not just the body: get_connection() runs
PRAGMA journal_mode=WAL, so a corrupt file raises there -- before a try that
opens outside itself is ever entered. That exact placement bug shipped once.
"""
# pylint: disable=protected-access
import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "nougen_shards" / "core.py"


def _catches_database_error(handler: ast.ExceptHandler) -> bool:
    types = handler.type
    if types is None:
        return True  # bare except catches everything
    candidates = types.elts if isinstance(types, ast.Tuple) else [types]
    for node in candidates:
        name = ast.unparse(node)
        if name in ("sqlite3.DatabaseError", "sqlite3.Error", "Exception", "BaseException"):
            return True
    return False


def _guarded_calls(node, guarding_tries):
    """Yield (call_node, is_guarded) for get_connection calls under `node`."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "get_connection":
        yield node, bool(guarding_tries)
        return
    if isinstance(node, ast.Try):
        guards = guarding_tries + [node] if any(
            _catches_database_error(h) for h in node.handlers) else guarding_tries
        for child in node.body:
            yield from _guarded_calls(child, guards)
        # handlers/orelse/finalbody are NOT protected by their own try
        for section in (node.handlers, node.orelse, node.finalbody):
            for child in section:
                yield from _guarded_calls(child, guarding_tries)
        return
    for child in ast.iter_child_nodes(node):
        yield from _guarded_calls(child, guarding_tries)


def test_every_grid_fanout_opens_its_connection_inside_a_guard():
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    offenders = []
    fanouts = 0

    for loop in [n for n in ast.walk(tree) if isinstance(n, ast.For)]:
        if not isinstance(loop.target, ast.Name):
            continue
        loop_var = loop.target.id
        # A fan-out is a loop that opens a connection keyed on its own variable.
        opens_per_iteration = any(
            isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "get_connection"
            and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == loop_var
            for n in ast.walk(loop)
        )
        if not opens_per_iteration:
            continue
        fanouts += 1
        for statement in loop.body:
            for call, guarded in _guarded_calls(statement, []):
                if not guarded:
                    offenders.append(f"line {call.lineno} (loop var '{loop_var}' at line {loop.lineno})")

    assert fanouts >= 5, f"only found {fanouts} fan-out loops - did the detector stop matching?"
    assert not offenders, (
        "grid fan-out opens a connection outside any sqlite3.DatabaseError guard, so "
        "one corrupt database aborts the whole loop and takes the healthy ones with it:\n  "
        + "\n  ".join(offenders)
    )
