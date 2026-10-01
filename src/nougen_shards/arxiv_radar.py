"""arXiv research radar and lab watcher integration for NouGen MCP.

Integrates canonical tools from `Who-Visions/nougen-radar` dynamically when available:
- `arxiv_radar`: backed by tools/arxiv_rss_radar.py
- `arxiv_lab_watch`: backed by tools/arxiv_lab_watch.py
- `arxiv_paper`: backed by tools/arxiv_paper.py
- `morph_gate`: backed by tools/morph_gate.py

Preserves radar semantics: beacon/review/shard lanes, cs.AR/lab channel support,
novelty remains 'unjudged' unless promoted, and no automatic sharding from lab-watch.
Degrades gracefully when radar tools or network feeds are unavailable.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RADAR_REPO_ENV = "NOUGEN_RADAR_DIR"


def find_radar_root() -> Optional[Path]:
    """Locate the canonical nougen-radar repository root."""
    env_path = os.environ.get(RADAR_REPO_ENV)
    if env_path:
        p = Path(env_path).resolve()
        if (p / "tools" / "arxiv_rss_radar.py").exists():
            return p

    candidates = [
        Path.home() / "Outpost" / "nougen-radar",
        Path.home() / ".nougen" / "tools",
        Path.home() / "Observatory" / "tools",
    ]
    for c in candidates:
        if (c / "arxiv_rss_radar.py").exists():
            return c.parent if c.name == "tools" else c
        if (c / "tools" / "arxiv_rss_radar.py").exists():
            return c
    return None


def _load_module(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def get_radar_tools():
    root = find_radar_root()
    if not root:
        return None
    tools_dir = root / "tools" if (root / "tools").is_dir() else root
    radar_mod = _load_module("arxiv_rss_radar", tools_dir / "arxiv_rss_radar.py")
    lab_mod = _load_module("arxiv_lab_watch", tools_dir / "arxiv_lab_watch.py")
    paper_mod = _load_module("arxiv_paper", tools_dir / "arxiv_paper.py")
    morph_mod = _load_module("morph_gate", tools_dir / "morph_gate.py")
    return {
        "radar": radar_mod,
        "lab": lab_mod,
        "paper": paper_mod,
        "morph": morph_mod,
        "root": str(root),
    }


def run_arxiv_radar(mode: str = "sweep", recipe_path: Optional[str] = None) -> Dict[str, Any]:
    """Execute an arXiv RSS radar cycle (sweep or reconcile)."""
    tools = get_radar_tools()
    if not tools or not tools.get("radar"):
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or arxiv_rss_radar.py missing",
        }
    radar = tools["radar"]
    try:
        recipe = radar.load_route_recipe(Path(recipe_path)) if recipe_path else radar.load_route_recipe()
        res = radar.run_radar_cycle(mode=mode, recipe=recipe)
        return {
            "status": "success",
            "available": True,
            "mode": mode,
            "result": res,
            "provenance": "Who-Visions/nougen-radar tools/arxiv_rss_radar.py",
        }
    except Exception as e:
        return {
            "status": "error",
            "available": True,
            "mode": mode,
            "error": str(e),
            "provenance": "Who-Visions/nougen-radar tools/arxiv_rss_radar.py",
        }


def run_arxiv_lab_watch(channel: str = "cs.AR", backfill: bool = False) -> Dict[str, Any]:
    """Execute an arXiv lab watcher cycle for hardware/systems research."""
    tools = get_radar_tools()
    if not tools or not tools.get("lab"):
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or arxiv_lab_watch.py missing",
        }
    lab = tools["lab"]
    try:
        res = lab.run(channel=channel, backfill=backfill)
        return {
            "status": "success",
            "available": True,
            "channel": channel,
            "result": res,
            "novelty": "unjudged",
            "provenance": "Who-Visions/nougen-radar tools/arxiv_lab_watch.py",
        }
    except Exception as e:
        return {
            "status": "error",
            "available": True,
            "channel": channel,
            "error": str(e),
            "provenance": "Who-Visions/nougen-radar tools/arxiv_lab_watch.py",
        }


def run_arxiv_paper(action: str, ref: str, pattern: Optional[str] = None) -> Dict[str, Any]:
    """Inspect an arXiv paper: lookup metadata, cache LaTeX fulltext, or search body claims."""
    tools = get_radar_tools()
    if not tools or not tools.get("paper"):
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or arxiv_paper.py missing",
        }
    paper = tools["paper"]
    try:
        aid = paper.normalize_id(ref)
        if action == "lookup":
            data = paper.lookup(aid)
            return {"status": "success", "available": True, "action": action, "paper_id": aid, "metadata": data}
        elif action == "fulltext":
            p = paper.fulltext(aid)
            return {
                "status": "success",
                "available": True,
                "action": action,
                "paper_id": aid,
                "cached_path": str(p),
                "bytes": p.stat().st_size,
            }
        elif action == "claim":
            if not pattern:
                return {"status": "error", "error": "pattern required for claim search"}
            hits = paper.claim(aid, pattern)
            return {
                "status": "success",
                "available": True,
                "action": action,
                "paper_id": aid,
                "pattern": pattern,
                "hits_count": len(hits),
                "occurrences": hits[:20],
            }
        else:
            return {"status": "error", "error": f"unknown action: {action}. Must be lookup, fulltext, or claim"}
    except Exception as e:
        return {"status": "error", "available": True, "action": action, "error": str(e)}


def run_morph_gate(ref: str, claims: List[str]) -> Dict[str, Any]:
    """Turn candidate key claims into verified evidence by regex checking the LaTeX body."""
    tools = get_radar_tools()
    if not tools or not tools.get("morph"):
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or morph_gate.py missing",
        }
    morph = tools["morph"]
    try:
        res = morph.gate(ref, claims)
        return {
            "status": "success",
            "available": True,
            "evidence": res,
            "provenance": "Who-Visions/nougen-radar tools/morph_gate.py",
        }
    except Exception as e:
        return {"status": "error", "available": True, "error": str(e)}
