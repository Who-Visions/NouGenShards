"""Optional node plugins.

Private feature packs (creative-canon tooling, agent personas) register their
routes and MCP tools through the ``nougen_shards.node_plugins`` entry-point
group instead of living in this public repo. A fresh clone has none installed
and serves the core node unchanged; a plugin that fails to load is reported,
never fatal, so one broken pack cannot take the node down.
"""
from __future__ import annotations

import inspect
import logging
from importlib.metadata import entry_points
from typing import Any, Dict, Iterable, List, Optional

GROUP = "nougen_shards.node_plugins"
log = logging.getLogger(__name__)


def _wants_ctx(fn: Any) -> bool:
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return sum(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params) >= 3 or any(
        p.kind is p.VAR_POSITIONAL for p in params)


def load_node_plugins(app: Any, mcp: Any, eps: Optional[Iterable[Any]] = None,
                      ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Call ``register(app, mcp)`` -- or ``register(app, mcp, ctx)`` when the
    pack takes a third argument -- for every installed plugin. ``ctx`` carries
    node helpers (offload decorator, tenant dependency, bounded Rhea call) so a
    pack does not import app.py. Returns one status record per plugin
    (``loaded`` or ``failed: <error>``)."""
    found = list(eps) if eps is not None else list(entry_points(group=GROUP))
    report = []
    for ep in found:
        try:
            register = ep.load()
            if _wants_ctx(register):
                register(app, mcp, dict(ctx or {}))
            else:
                register(app, mcp)
            report.append({"plugin": ep.name, "status": "loaded"})
        except Exception as exc:  # a broken pack must not stop the node
            log.error("node plugin %s failed to load: %s", ep.name, exc)
            report.append({"plugin": ep.name, "status": f"failed: {type(exc).__name__}: {exc}"})
    return report
