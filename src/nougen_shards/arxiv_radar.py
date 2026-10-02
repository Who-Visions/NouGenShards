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

import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

RADAR_REPO_ENV = "NOUGEN_RADAR_DIR"


def find_radar_root() -> Optional[Path]:
    """Locate the canonical nougen-radar repository root."""
    env_path = os.environ.get(RADAR_REPO_ENV)
    if env_path:
        p = Path(env_path).resolve()
        tools_dir = p / "tools" if (p / "tools").is_dir() else p
        if (tools_dir / "arxiv_rss_radar.py").exists() and (tools_dir / "arxiv_lab_watch.py").exists():
            return p

    candidates = [
        Path.home() / "Outpost" / "nougen-radar",
        Path.home() / "The Observatory" / "NouGen" / "nougen-radar",
        Path.home() / "The Observatory" / "tools",
        Path.home() / ".nougen" / "tools",
        Path.home() / "Observatory" / "tools",
    ]
    for c in candidates:
        root_dir = c.parent if c.name == "tools" else c
        tools_dir = root_dir / "tools" if (root_dir / "tools").is_dir() else root_dir
        if (tools_dir / "arxiv_rss_radar.py").exists() and (tools_dir / "arxiv_lab_watch.py").exists():
            return root_dir
    return None


def _load_module(mod_name: str, file_path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    if not file_path.exists():
        return None
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
    required = ["arxiv_rss_radar.py", "arxiv_lab_watch.py", "arxiv_paper.py", "morph_gate.py"]
    if not all((tools_dir / f).exists() for f in required):
        return None
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


# What this wrapper calls on tools/arxiv_rss_radar.py, and the keyword parameters it passes.
# Checked at call time so API drift degrades with names instead of an AttributeError
# (the 2026-10-01 failure: the wrapper called run_radar_cycle, which never existed).
RADAR_CONTRACT = {
    "fetch_arxiv_rss_conditional": ("channel", "cursor"),
    "parse_arxiv_item": (),
    "compute_percentiles": (),
    "route_papers": (),
    "load_route_recipe": (),
    "run_pipeline": ("mode", "channels", "broadcast_target"),
}
MODES = ("preview", "sweep", "reconcile")
# Same operator gate as the canonical nougen-radar MCP server (tools/mcp_server.py): a remote
# caller can ask for commit=true, but writing queues, the cursor and shards also needs this env var.
MUTATION_ENV = "NOUGEN_ARXIV_MCP_ALLOW_MUTATION"
MAX_CHANNELS = 5
MAX_LIMIT = 50
LOG_TAIL_CHARS = 2000
_CHANNEL_RE = re.compile(r"^[a-z][a-z-]*(\.[a-z][a-z-]*)?$", re.IGNORECASE)


def radar_contract_problems(radar: Any) -> List[str]:
    """Names of functions or parameters the wrapper needs that the radar module lacks."""
    problems: List[str] = []
    for name, params in RADAR_CONTRACT.items():
        fn = getattr(radar, name, None)
        if not callable(fn):
            problems.append(f"missing {name}")
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        takes_any_kw = any(q.kind is inspect.Parameter.VAR_KEYWORD for q in sig.parameters.values())
        for param in params:
            if param not in sig.parameters and not takes_any_kw:
                problems.append(f"{name} has no parameter '{param}'")
    return problems


def allowed_recipe_dirs(radar: Any = None) -> List[Path]:
    """Where a caller-supplied recipe may live: the radar's own state dir and checkout."""
    dirs = [Path.home() / ".nougen" / "shards" / "radar"]
    root = find_radar_root()
    if root is not None:
        dirs.append(root)
    return dirs


def _load_recipe(radar: Any, recipe_path: Optional[str]) -> Dict[str, Any]:
    if not recipe_path:
        return radar.load_route_recipe()
    target = Path(recipe_path).expanduser().resolve()
    if not any(target == d.resolve() or d.resolve() in target.parents for d in allowed_recipe_dirs(radar)):
        # Remote-callable tool: never read an arbitrary path or echo what is in it.
        raise ValueError("recipe_path must be inside the radar state or checkout directory")
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("lanes"), dict):
        raise ValueError("recipe must be a JSON object with a 'lanes' object")
    return data


def _top(papers: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    return [{"id": p.get("id"), "title": p.get("title"), "primary_category": p.get("primary_category"),
             "priority_pct": p.get("priority_pct"), "reason_codes": p.get("reason_codes", [])}
            for p in papers[:limit]]


def _preview(radar: Any, channels: List[str], recipe: Dict[str, Any], limit: int) -> Dict[str, Any]:
    """The radar's read-only half: fetch, parse, score, route. Persists and broadcasts nothing."""
    papers: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    for channel in channels:
        try:
            content, _headers = radar.fetch_arxiv_rss_conditional(channel, {})   # empty cursor: nothing saved
            channel_el = ET.fromstring(content).find("channel")
            for item in (channel_el.findall("item") if channel_el is not None else []):
                parsed = radar.parse_arxiv_item(item)
                if parsed.get("id"):
                    papers.append(parsed)
        except Exception as exc:  # one dead channel must not hide the others
            errors[channel] = str(exc)
    result: Dict[str, Any] = {"channels": channels, "papers_count": len(papers), "errors": errors}
    if papers:
        routed = radar.route_papers(radar.compute_percentiles(papers), recipe)
        result["lanes"] = {lane: {"count": len(items), "top": _top(items, limit)} for lane, items in routed.items()}
    return {"status": "error" if errors and not papers else "success", "result": result}


def run_arxiv_radar(channels: Optional[List[str]] = None, mode: str = "preview", limit: int = 5,
                    commit: bool = False, recipe_path: Optional[str] = None) -> Dict[str, Any]:
    """Run the arXiv radar. Read-only unless `commit` is true, `mode` is 'sweep' or 'reconcile',
    and the operator has set NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1.

    preview: fetch, score and route the feed, return the lanes; writes nothing.
    sweep / reconcile with commit=True: the full pipeline (queues, cursor, digest, shard ingest);
    the fleet broadcast is kept local. Without commit they run as a preview.
    """
    chans = channels if channels else ["cs"]
    if mode not in MODES:
        return {"status": "error", "mode": mode, "error": f"mode must be one of {', '.join(MODES)}"}
    if (not isinstance(chans, list) or len(chans) > MAX_CHANNELS
            or any(not isinstance(c, str) or not _CHANNEL_RE.match(c) for c in chans)):
        return {"status": "error", "mode": mode,
                "error": f"channels must be 1-{MAX_CHANNELS} arXiv channel names like 'cs' or 'cs.AR'"}
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return {"status": "error", "mode": mode, "error": f"limit must be an integer 1-{MAX_LIMIT}"}
    if commit and mode == "preview":
        return {"status": "error", "mode": mode, "error": "commit requires mode 'sweep' or 'reconcile'"}
    if commit and recipe_path:
        return {"status": "error", "mode": mode, "error": "a custom recipe is preview only; commit uses the radar's own recipe"}
    if commit and os.environ.get(MUTATION_ENV, "").strip() != "1":
        return {"status": "mutation_disabled", "mode": mode, "mutated": False,
                "error": f"commit needs the server operator to set {MUTATION_ENV}=1; read-only preview remains available"}

    tools = get_radar_tools()
    if not tools or not tools.get("radar"):
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or arxiv_rss_radar.py missing",
        }
    radar = tools["radar"]
    provenance = "Who-Visions/nougen-radar tools/arxiv_rss_radar.py"
    problems = radar_contract_problems(radar)
    if problems:
        return {"status": "degraded", "available": True, "mode": mode, "missing_symbols": problems,
                "error": "nougen-radar API no longer matches this wrapper", "provenance": provenance}

    buffer = io.StringIO()
    try:
        # The radar prints progress; on an MCP stdio transport a stray stdout line corrupts the stream.
        with contextlib.redirect_stdout(buffer):
            if commit:
                result = {"pipeline": radar.run_pipeline(mode=mode, channels=chans, broadcast_target="local")}
                out: Dict[str, Any] = {"status": "success", "result": result}
            else:
                out = _preview(radar, chans, _load_recipe(radar, recipe_path), limit)
    except Exception as exc:
        return {"status": "error", "available": True, "mode": mode, "mutated": False, "error": str(exc),
                "provenance": provenance}
    out.update({"available": True, "mode": mode, "mutated": bool(commit), "provenance": provenance})
    if not commit and mode != "preview":
        out["note"] = f"mode '{mode}' ran as a read-only preview; pass commit=true to run the full pipeline"
    log = buffer.getvalue().strip()
    if log:
        out["log_tail"] = log[-LOG_TAIL_CHARS:]
    return out


def _lab_entry(e: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": e.get("id"), "title": e.get("title"), "score": e.get("score"),
            "classes": e.get("classes", []), "tier": e.get("tier")}


def run_arxiv_lab_watch(channel: str = "cs.AR", backfill: bool = False, limit: int = 25,
                        commit: bool = False) -> Dict[str, Any]:
    """arXiv lab watcher for hardware/systems research. Read-only unless `commit` is true and the
    operator has set NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1 (same gate as the radar and the canonical
    nougen-radar MCP server): lab.run() advances the cursor, the graft queue and the digest.

    preview: fetch, screen and dedupe the feed; returns graft/watch lists clipped to `limit`.
    commit: run the full cycle (queue, cursor, digest). Novelty stays unjudged; nothing is sharded.
    """
    provenance = "Who-Visions/nougen-radar tools/arxiv_lab_watch.py"
    if not isinstance(channel, str) or not _CHANNEL_RE.match(channel):
        return {"status": "error", "error": "channel must be an arXiv channel name like 'cs.AR'"}
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return {"status": "error", "channel": channel, "error": f"limit must be an integer 1-{MAX_LIMIT}"}
    if commit and os.environ.get(MUTATION_ENV, "").strip() != "1":
        return {"status": "mutation_disabled", "channel": channel, "mutated": False,
                "error": f"commit needs the server operator to set {MUTATION_ENV}=1; read-only preview remains available"}
    tools = get_radar_tools()
    if not tools or not tools.get("lab"):
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or arxiv_lab_watch.py missing",
        }
    lab = tools["lab"]
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            if commit:
                res = lab.run(channel=channel, backfill=backfill)
                out: Dict[str, Any] = {"result": res}
            else:
                items, _hdr = lab.fetch_feed(channel, {}, lab._radar())   # empty cursor: nothing saved
                if backfill:
                    items += lab.backfill_recent(channel)
                fresh, seen = [], set()
                for e in items:
                    if e["id"] not in seen:
                        seen.add(e["id"])
                        fresh.append(e)
                graft = sorted((e for e in fresh if e.get("graft")), key=lambda x: -x.get("score", 0))
                watch = sorted((e for e in fresh if e.get("tier") == "watch"), key=lambda x: -x.get("score", 0))
                out = {"result": {"channel": channel, "screened": len(fresh),
                                  "graft_candidates": len(graft), "watch": len(watch),
                                  "graft_top": [_lab_entry(e) for e in graft[:limit]],
                                  "watch_top": [_lab_entry(e) for e in watch[:limit]],
                                  "auto_shard": False}}
        out.update({"status": "success", "available": True, "channel": channel, "mutated": bool(commit),
                    "novelty": "unjudged", "provenance": provenance})
        log = buffer.getvalue().strip()
        if log:
            out["log_tail"] = log[-LOG_TAIL_CHARS:]
        return out
    except Exception as e:
        return {
            "status": "error",
            "available": True,
            "channel": channel,
            "mutated": False,
            "error": str(e),
            "provenance": provenance,
        }


MAX_FULLTEXT_CHARS = int(os.environ.get("NOUGEN_ARXIV_MCP_MAX_FULLTEXT_CHARS", "24000"))


def run_arxiv_paper(action: str = "lookup", ref: str = "", pattern: Optional[str] = None,
                    max_chars: Optional[int] = None, refresh: bool = False) -> Dict[str, Any]:
    """Inspect an arXiv paper: lookup metadata, cache LaTeX fulltext, or search body claims."""
    if not ref or not str(ref).strip():
        return {
            "status": "error",
            "available": True,
            "action": action,
            "error": "ref is required and cannot be empty",
        }
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
            try:
                p = paper.fulltext(aid, refresh=refresh)
            except TypeError as te:
                err_msg = str(te)
                if "unexpected keyword argument 'refresh'" in err_msg or ("unexpected keyword argument" in err_msg and "refresh" in err_msg):
                    p = paper.fulltext(aid)
                else:
                    raise
            text = p.read_text(encoding="utf-8")
            cap = MAX_FULLTEXT_CHARS if max_chars is None else max(1000, min(int(max_chars), MAX_FULLTEXT_CHARS))
            clipped = text[:cap]
            return {
                "status": "success",
                "available": True,
                "action": action,
                "paper_id": aid,
                "cached_path": str(p),
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "chars_total": len(text),
                "chars_returned": len(clipped),
                "text_length": len(clipped),
                "truncated": len(clipped) < len(text),
                "text": clipped,
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
    if not ref or not str(ref).strip():
        return {
            "status": "error",
            "available": True,
            "error": "ref is required and cannot be empty",
        }
    if not claims or not isinstance(claims, list):
        return {
            "status": "error",
            "available": True,
            "error": "claims must be a non-empty list of strings",
        }
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
