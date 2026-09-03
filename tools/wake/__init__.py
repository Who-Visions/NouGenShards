"""Optional wake adapters: start an idle agent, where delivery only reaches a live one.

Two different capabilities are easy to conflate. `deliver_to_live_sessions`
reaches a session that ALREADY EXISTS. Waking reaches a machine where no
session is running and STARTS one, handing it the message as its opening
context. Starting an agent is strictly more than delivering to one, so this
sits behind every gate the delivery path has and is unavailable by default.

DISCOVERY, NOT CONFIGURATION. An adapter is available only if its module
imports on this platform. No message field, environment variable or service
definition can switch waking on: a node without a working adapter simply
cannot be woken, and says so. That is deliberate. A capability that reaches
execution should be a property of what is installed, not of what a caller
asks for, because the caller is exactly who an attacker controls.

Unavailability is REPORTED, never silent. A caller gets
``{"attempted": False, "wake": "unavailable", ...}`` rather than nothing,
because a silent no-op is indistinguishable from a broken scheme, and a node
that quietly ignores wakes wastes the same hours as a node that quietly fails
to deliver.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

# Import-guarded, exactly like a POSIX-only module on Windows: if the platform
# adapter will not import, the capability does not exist here.
_ADAPTERS: List[Any] = []
_IMPORT_ERRORS: Dict[str, str] = {}

# Imported RELATIVE to this package, never by a hardcoded "tools.wake.x" path.
# A hardcoded package path makes availability a function of sys.path SHAPE
# rather than of runtime presence: the daemon runs with tools/ itself on the
# path, so "tools" is not importable there and every adapter failed with
# ModuleNotFoundError, which is indistinguishable from "no runtime installed".
# Worse in the other direction: anyone who later normalised the daemon's
# sys.path would have silently switched waking ON with no decision taken.
# Using __name__ works under either import shape, so the ONLY thing that can
# make an adapter appear is the runtime it looks for.
for _name in ("antigravity",):
    try:
        _mod = __import__("{}.{}".format(__name__, _name), fromlist=["Adapter"])
        _ADAPTERS.append(_mod.Adapter())
    except Exception as _exc:  # pylint: disable=broad-except
        _IMPORT_ERRORS[_name] = "{}: {}".format(type(_exc).__name__, str(_exc)[:80])


def available() -> List[str]:
    """Names of adapters that imported on this node. Empty is a valid state."""
    return [a.name for a in _ADAPTERS]


def status() -> Dict[str, Any]:
    """What can and cannot wake here, and why not. Diagnosable without guessing."""
    return {"available": available(), "unavailable": _IMPORT_ERRORS}


def wake(target: str, text: str, event: Dict[str, Any] = None) -> Dict[str, Any]:
    """Wake idle agents matching ``target``. Never raises into the caller.

    Returns a report whose shape does not depend on whether anything ran, so
    the receiver can always put it in its response.
    """
    if not _ADAPTERS:
        return {"attempted": False, "wake": "unavailable",
                "reason": "no wake adapter imports on this node", "detail": _IMPORT_ERRORS}
    want = (target or "").strip().lower() or "all"
    results = {}
    for adapter in _ADAPTERS:
        if want not in ("all", adapter.name) and want not in adapter.aliases:
            continue
        try:
            if not adapter.is_idle():
                results[adapter.name] = {"woken": False, "reason": "already running"}
                continue
            results[adapter.name] = adapter.wake(text, event or {})
        except Exception as exc:  # pylint: disable=broad-except
            results[adapter.name] = {"woken": False, "error": "{}: {}".format(
                type(exc).__name__, str(exc)[:120])}
    if not results:
        return {"attempted": False, "wake": "no adapter matches target {!r}".format(target),
                "available": available()}
    return {"attempted": True, "wake": "dispatched", "results": results}


def enabled() -> bool:
    """Whether waking is possible here at all. Not a switch, a fact."""
    return bool(_ADAPTERS) and os.environ.get("NOUGEN_WAKE_DISABLED", "").strip().lower() \
        not in ("1", "true", "on")
