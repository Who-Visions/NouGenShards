"""Optional node plugins.

Private feature packs (creative-canon tooling, agent personas) register their
routes and MCP tools through the ``nougen_shards.node_plugins`` entry-point
group instead of living in this public repo. A fresh clone has none installed
and serves the core node unchanged; a plugin that fails to load is reported,
never fatal, so one broken pack cannot take the node down.
"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any, Dict, Iterable, List, Optional

GROUP = "nougen_shards.node_plugins"
log = logging.getLogger(__name__)


def load_node_plugins(app: Any, mcp: Any, eps: Optional[Iterable[Any]] = None) -> List[Dict[str, str]]:
    """Call ``register(app, mcp)`` for every installed plugin; return one
    status record per plugin (``loaded`` or ``failed: <error>``)."""
    found = list(eps) if eps is not None else list(entry_points(group=GROUP))
    report = []
    for ep in found:
        try:
            ep.load()(app, mcp)
            report.append({"plugin": ep.name, "status": "loaded"})
        except Exception as exc:  # a broken pack must not stop the node
            log.error("node plugin %s failed to load: %s", ep.name, exc)
            report.append({"plugin": ep.name, "status": f"failed: {type(exc).__name__}: {exc}"})
    return report
