"""Node tools must call NouGenMsg methods on the class that defines them.

Regression for 2026-09-14: app.py's `nougenmsg` and `fleet_send` tools called
`AgentPinger.emit_fleet(...)`, but emit_fleet is defined on `NouGenMsgBus`.
Every call raised AttributeError, which FastMCP reports only as
"Error executing tool nougenmsg", so the connector's gateway delivery path
failed on every node and silently fell back to phoebus /msg or a relay leg.

Static on purpose: importing app.py boots the whole node. Parsing every
`<Class>.<method>(...)` call on the NouGenMsg surface and resolving it
against the real module catches exactly this class of bug (a method looked
up on the wrong class) without that cost.
"""
import ast
import inspect
from pathlib import Path

from nougen_shards import nougenmsg

APP = Path(__file__).resolve().parents[1] / "app.py"
METHODS = {"emit_fleet", "emit_node", "live_ping"}
CLASSES = {n for n, o in vars(nougenmsg).items()
           if inspect.isclass(o) and o.__module__ == nougenmsg.__name__}


def _calls():
    """(function name, 'Class.method') for every NouGenMsg class-method call in app.py."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for c in ast.walk(fn):
            f = getattr(c, "func", None)
            if (isinstance(c, ast.Call) and isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name) and f.attr in METHODS
                    and f.value.id in CLASSES):
                yield fn.name, f"{f.value.id}.{f.attr}"


def test_node_tools_reach_the_msg_bus():
    names = {fn for fn, _ in _calls()}
    assert {"nougenmsg", "fleet_send"} <= names


def test_every_msg_method_exists_on_the_class_it_is_called_on():
    missing = [f"{fn}: {call}" for fn, call in _calls()
               if not callable(getattr(getattr(nougenmsg, call.split(".")[0]), call.split(".")[1], None))]
    assert not missing, "app.py calls NouGenMsg methods on the wrong class: " + "; ".join(missing)
