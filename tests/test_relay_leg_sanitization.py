"""Regression test for issue #350: relay_claim_leg/relay_ack_leg path traversal.

leg_id used to be interpolated raw into a claims-dir filename. Path's "/"
operator does not normalize "..", so a crafted leg_id like
"../../../etc/whatever" escaped claims_dir entirely (arbitrary file write).
_sanitize_leg_id collapses leg_id to a safe filename component before it is
ever used to build a path.
"""
import ast


def _load_sanitize_leg_id():
    """Pull _sanitize_leg_id out of app.py without importing it (it imports
    gradio at module scope, which is not a test dependency)."""
    src = open("app.py", encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_sanitize_leg_id")
    mod = ast.Module(body=[fn], type_ignores=[])
    ns = {}
    exec(compile(ast.fix_missing_locations(mod), "app.py", "exec"), {"re": __import__("re")}, ns)
    return ns["_sanitize_leg_id"]


def test_parent_dir_traversal_is_neutralized():
    sanitize = _load_sanitize_leg_id()
    assert "/" not in sanitize("../../../../etc/passwd")
    assert ".." not in sanitize("../../../../etc/passwd")


def test_absolute_path_is_neutralized():
    sanitize = _load_sanitize_leg_id()
    assert "/" not in sanitize("/etc/cron.d/evil")


def test_legitimate_leg_id_passes_through():
    sanitize = _load_sanitize_leg_id()
    assert sanitize("20260914T190000Z__whoart__claude-cli") == "20260914T190000Z__whoart__claude-cli"


def test_empty_or_all_unsafe_falls_back_to_placeholder():
    sanitize = _load_sanitize_leg_id()
    assert sanitize("") == "leg"
    assert sanitize("....") == "leg"
