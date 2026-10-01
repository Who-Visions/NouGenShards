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


_RADAR_PROVENANCE = "Who-Visions/nougen-radar tools/arxiv_rss_radar.py"
_RADAR_MODES = ("preview", "sweep", "reconcile")
_PAPER_KEYS = (
    "id", "version", "title", "link", "abstract", "primary_category",
    "announce_type", "authors", "pub_date", "doi", "score",
    "matched_pillars", "reason_codes", "global_pct", "category_pct",
    "priority_pct", "route",
)


def _env_int(name: str, fallback: int) -> int:
    """Env-resolved integer; the constant is only a fallback."""
    try:
        return max(1, int(os.environ.get(name, "")))
    except ValueError:
        return fallback


def _default_channels() -> List[str]:
    raw = os.environ.get("NOUGEN_ARXIV_DEFAULT_CHANNELS", "")
    return [c.strip() for c in raw.split(",") if c.strip()] or ["cs"]


def _mutation_allowed() -> bool:
    return os.environ.get("NOUGEN_ARXIV_MCP_ALLOW_MUTATION", "").strip() == "1"


def run_arxiv_radar(
    mode: str = "preview",
    recipe_path: Optional[str] = None,
    channels: Optional[List[str]] = None,
    limit: Optional[int] = None,
    commit: bool = False,
    broadcast_target: Optional[str] = None,
) -> Dict[str, Any]:
    """Scan arXiv through the canonical radar.

    Read-only by default: ``commit=False`` fetches each channel with an empty
    cursor, so it never touches the scheduler's ETag cursor, queues, or
    broadcasts. ``commit=True`` runs the radar's real ``run_pipeline`` and is
    additionally gated by NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1.
    """
    mode = (mode or "preview").strip().lower()
    if mode not in _RADAR_MODES:
        return {
            "status": "error",
            "available": True,
            "error": f"mode must be one of {', '.join(_RADAR_MODES)}",
            "provenance": _RADAR_PROVENANCE,
        }
    tools = get_radar_tools()
    if not tools or not tools.get("radar"):
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or arxiv_rss_radar.py missing",
        }
    radar = tools["radar"]
    channels = list(channels) if channels else _default_channels()
    out: Dict[str, Any] = {
        "available": True,
        "mode": mode,
        "channels": channels,
        "provenance": _RADAR_PROVENANCE,
    }
    if recipe_path:
        # load_route_recipe() takes no path; say so instead of silently ignoring it.
        out["recipe_path_ignored"] = recipe_path

    try:
        if commit:
            if not _mutation_allowed():
                return {
                    **out,
                    "status": "mutation_disabled",
                    "mutation": False,
                    "reason": (
                        "Server operator must set NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1. "
                        "Read-only preview remains available."
                    ),
                }
            result = radar.run_pipeline(
                mode="reconcile" if mode == "preview" else mode,
                channels=channels,
                broadcast_target=broadcast_target or "",
            )
            return {**out, "status": "committed", "mutation": True, "result": result}

        import xml.etree.ElementTree as ET

        papers: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []
        for channel in channels:
            try:
                content, _headers = radar.fetch_arxiv_rss_conditional(
                    channel, {"channels": {}, "seen_ids": []}
                )
                if not content:
                    continue
                root = ET.fromstring(content)
                for item in root.findall("./channel/item"):
                    paper = radar.parse_arxiv_item(item)
                    if paper.get("id"):
                        papers.append(paper)
            except Exception as exc:  # one bad channel must not sink the preview
                errors.append({"channel": channel, "error": f"{type(exc).__name__}: {exc}"})

        lanes = radar.route_papers(radar.compute_percentiles(papers), radar.load_route_recipe())
        cap = max(1, min(
            int(limit) if limit else _env_int("NOUGEN_ARXIV_PREVIEW_LIMIT", 25),
            _env_int("NOUGEN_ARXIV_MAX_RESULTS", 100),
        ))
        return {
            **out,
            "mode": "preview",
            "mutation": False,
            "status": "partial" if errors else "success",
            "counts": {name: len(rows) for name, rows in lanes.items()} | {"total": len(papers)},
            "lanes": {
                name: [{k: p.get(k) for k in _PAPER_KEYS if k in p} for p in rows[:cap]]
                for name, rows in lanes.items()
            },
            "errors": errors,
        }
    except Exception as e:
        return {**out, "status": "error", "error": f"{type(e).__name__}: {e}"}


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
