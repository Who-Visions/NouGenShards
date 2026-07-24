"""Shard registry MCP server (``nougen-fleet-registry``).

Ships the *product* surface: read/write access to the caller's own shard vault
(primary ``NOUGEN_VAULT_DIR`` plus any ``NOUGEN_SECONDARY_VAULT_DIRS``), riding
the existing federation engine rather than reimplementing retrieval.

Everything environment-shaped resolves env -> probe -> logged fallback; there
are no absolute paths in this module, so a fresh clone starts it unmodified.

Operator-specific capability (fleet node inventory, mesh/registry diagnostics,
node ingestion) is deliberately NOT in this repo. It loads from an optional
local extension named by ``NOUGEN_REGISTRY_EXT``:

    NOUGEN_REGISTRY_EXT=C:/path/to/my_registry_ext.py    (file path)
    NOUGEN_REGISTRY_EXT=my_package.registry_ext          (importable module)

The extension must expose ``register(mcp)``. It may also expose
``CLAIMS = ["shard_get", ...]`` to take over a product tool name; claimed names
are skipped here so registration never collides. A missing, unreadable, or
raising extension is logged to stderr and the product surface still starts.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised only when the optional dep is absent
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    class FastMCP:  # type: ignore[no-redef]
        """Minimal stand-in so importing this module never hard-fails."""

        def __init__(self, name: str, dependencies: Optional[list] = None):
            self.name = name

        def tool(self):
            return lambda f: f

        def run(self):
            print("mcp package not installed; install `mcp` to serve.", file=sys.stderr)

from . import core
from . import federation


SERVER_NAME = os.environ.get("NOUGEN_REGISTRY_SERVER_NAME", "nougen-fleet-registry")
mcp = FastMCP(SERVER_NAME, dependencies=["mcp"])


# ---------------------------------------------------------------------------
# Config resolution (Rule 0.2: env -> probe -> logged fallback, never hardcode)
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; falling back to %d", name, raw, default)
        return default


DEFAULT_LIMIT = _env_int("NOUGEN_REGISTRY_DEFAULT_LIMIT", 10)
MAX_LIMIT = _env_int("NOUGEN_REGISTRY_MAX_LIMIT", 100)
RECENT_SCAN_CAP = _env_int("NOUGEN_REGISTRY_RECENT_SCAN_CAP", 2000)


def _clamp(limit: int) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _ok(payload: Dict[str, Any]) -> str:
    payload.setdefault("status", "ok")
    return json.dumps(payload, ensure_ascii=False, default=str)


def _err(exc: BaseException, **extra: Any) -> str:
    payload = {"status": "error", "error": str(exc), "error_type": type(exc).__name__}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _stores() -> List[Dict[str, Any]]:
    """Probe the live store layout instead of trusting configured paths."""
    out: List[Dict[str, Any]] = []
    try:
        primary = Path(core.GLOBAL_DIR)
        out.append({
            "label": federation.primary_store_label(),
            "path": str(primary),
            "role": "primary",
            "exists": primary.is_dir(),
        })
    except Exception as exc:  # noqa: BLE001 - a probe must never abort a tool
        logger.warning("primary store probe failed: %s", exc)
    try:
        for label, path in federation.secondary_stores():
            out.append({"label": label, "path": str(path), "role": "secondary",
                        "exists": Path(path).is_dir()})
    except Exception as exc:  # noqa: BLE001
        logger.warning("secondary store probe failed: %s", exc)
    return out


def _shard_dir() -> Path:
    """Directory holding shard markdown, resolved from env then probed."""
    override = os.environ.get("NOUGEN_SHARD_MD_DIR", "").strip()
    if override:
        return Path(os.path.expandvars(os.path.expanduser(override)))
    base = Path(core.GLOBAL_DIR)
    for name in ("shards", "Markdowns", "markdown"):
        cand = base / name
        if cand.is_dir():
            return cand
    logger.info("no shard markdown subdir found under %s; using it directly", base)
    return base


# ---------------------------------------------------------------------------
# Optional local extension
# ---------------------------------------------------------------------------

_EXT_STATE: Dict[str, Any] = {"loaded": False, "source": None, "claims": [], "error": None}


def _import_extension(spec: str):
    path = Path(os.path.expandvars(os.path.expanduser(spec)))
    if path.suffix == ".py" or path.exists():
        if not path.is_file():
            raise FileNotFoundError(f"extension file not found: {path}")
        mod_spec = importlib.util.spec_from_file_location("nougen_registry_ext", path)
        if mod_spec is None or mod_spec.loader is None:
            raise ImportError(f"cannot load extension from {path}")
        module = importlib.util.module_from_spec(mod_spec)
        sys.modules["nougen_registry_ext"] = module
        mod_spec.loader.exec_module(module)
        return module, str(path)
    return importlib.import_module(spec), spec


def _load_extension_claims() -> List[str]:
    """Import the extension (if any) and return the tool names it will own."""
    spec = os.environ.get("NOUGEN_REGISTRY_EXT", "").strip()
    if not spec:
        _EXT_STATE["error"] = None
        return []
    try:
        module, source = _import_extension(spec)
        _EXT_STATE["module"] = module
        _EXT_STATE["source"] = source
        claims = [str(c) for c in getattr(module, "CLAIMS", [])]
        _EXT_STATE["claims"] = claims
        return claims
    except Exception as exc:  # noqa: BLE001 - never let an extension kill the server
        _EXT_STATE["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[nougen-fleet-registry] extension '{spec}' not loaded: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return []


_CLAIMED = _load_extension_claims()


def product_tool(name: str):
    """Register a product tool unless the local extension claimed the name."""
    def deco(func):
        if name in _CLAIMED:
            print(f"[nougen-fleet-registry] '{name}' provided by local extension",
                  file=sys.stderr)
            return func
        return mcp.tool()(func)
    return deco


def _activate_extension() -> None:
    module = _EXT_STATE.get("module")
    if module is None:
        return
    try:
        module.register(mcp)
        _EXT_STATE["loaded"] = True
        print(f"[nougen-fleet-registry] extension loaded: {_EXT_STATE['source']}",
              file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        _EXT_STATE["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[nougen-fleet-registry] extension register() failed: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Product tools
# ---------------------------------------------------------------------------

@product_tool("shard_search")
def shard_search(query: str, limit: int = DEFAULT_LIMIT) -> str:
    """Search every configured shard store (primary + secondary vaults).

    Args:
        query: Text to match against shard titles and content.
        limit: Maximum shards to return.
    """
    try:
        hits = federation.federated_retrieve(query, limit=_clamp(limit)) or []
        return _ok({
            "query": query,
            "count": len(hits),
            "stores": [s["label"] for s in _stores()],
            "results": [{
                "id": h.get("id"),
                "title": h.get("title"),
                "event_type": h.get("event_type"),
                "tags": h.get("tags"),
                "timestamp": h.get("timestamp"),
                "store": h.get("store"),
                "db_index": h.get("db_index"),
                "score": h.get("score"),
                "content": (h.get("content") or "")[:1200],
            } for h in hits],
        })
    except Exception as exc:  # noqa: BLE001
        return _err(exc, query=query)


@product_tool("shard_related")
def shard_related(query: str, limit: int = 5) -> str:
    """Find shards contextually related to a query, as a compiled recall packet.

    Args:
        query: Topic or context to find neighbours for.
        limit: Maximum related shards to consider.
    """
    try:
        hits = federation.federated_retrieve(query, limit=_clamp(limit)) or []
        return _ok({"query": query, "count": len(hits),
                    "packet": core.compile_recall_packet(hits)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc, query=query)


@product_tool("shard_get")
def shard_get(shard_id: int, db_index: int = 1) -> str:
    """Fetch one shard in full by id.

    Args:
        shard_id: The shard's numeric id (as returned by shard_search).
        db_index: Which database in the local grid holds it (default 1).
    """
    try:
        shard = core.get_shard_by_id(int(shard_id), int(db_index))
        if not shard:
            return _ok({"found": False, "shard_id": shard_id, "db_index": db_index})
        return _ok({"found": True, "shard": shard})
    except Exception as exc:  # noqa: BLE001
        return _err(exc, shard_id=shard_id, db_index=db_index)


@product_tool("shard_stats")
def shard_stats() -> str:
    """Report vault health: store layout, shard counts, embedding coverage."""
    try:
        health = core.lane_health()
        return _ok({
            "server": SERVER_NAME,
            "stores": _stores(),
            "lane_health": health,
            "extension": {"configured": bool(os.environ.get("NOUGEN_REGISTRY_EXT")),
                          "loaded": _EXT_STATE["loaded"],
                          "source": _EXT_STATE["source"],
                          "error": _EXT_STATE["error"]},
        })
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@product_tool("shard_schema")
def shard_schema() -> str:
    """Return the shard table schema and the store map for this vault."""
    try:
        tables: Dict[str, List[str]] = {}
        conn = core.get_connection(core.get_active_db_index())
        try:
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'").fetchall()]
            for tname in names:
                tables[tname] = [r[1] for r in
                                 conn.execute(f"PRAGMA table_info({tname})").fetchall()]
        finally:
            conn.close()
        return _ok({"stores": _stores(), "tables": tables})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@product_tool("recent_shards")
def recent_shards(limit: int = 5) -> str:
    """List the most recently captured shards in the primary vault.

    Args:
        limit: How many recent shards to return.
    """
    limit = _clamp(limit)
    try:
        rows: List[Dict[str, Any]] = []
        conn = core.get_connection(core.get_active_db_index())
        try:
            cur = conn.execute(
                "SELECT id, event_type, title, tags, timestamp FROM shards "
                "ORDER BY id DESC LIMIT ?", (limit,))
            for r in cur.fetchall():
                rows.append({"id": r[0], "event_type": r[1], "title": r[2],
                             "tags": r[3], "timestamp": r[4]})
        finally:
            conn.close()

        files: List[Dict[str, Any]] = []
        md_dir = _shard_dir()
        if md_dir.is_dir():
            found = []
            for i, p in enumerate(md_dir.rglob("*.md")):
                if i >= RECENT_SCAN_CAP:
                    logger.info("recent_shards scan capped at %d files", RECENT_SCAN_CAP)
                    break
                try:
                    found.append((p.stat().st_mtime, p))
                except OSError:
                    continue
            for mtime, p in sorted(found, reverse=True)[:limit]:
                files.append({"path": str(p), "name": p.name, "mtime": mtime})

        return _ok({"store": federation.primary_store_label(),
                    "shards": rows, "markdown": files})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@product_tool("write_memory")
def write_memory(title: str, content: str, tags: str = "",
                 event_type: str = "KNOWLEDGE") -> str:
    """Persist a memory shard into the primary vault.

    Args:
        title: Short descriptive title.
        content: Full body of the memory.
        tags: Comma-separated tags.
        event_type: Category, e.g. KNOWLEDGE / DECISION / ERROR.
    """
    try:
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        created = core.capture(event_type, title, content, tag_list)
        return _ok({"written": bool(created),
                    "detail": "shard captured" if created else "duplicate shard, not rewritten",
                    "store": federation.primary_store_label(), "title": title})
    except Exception as exc:  # noqa: BLE001
        return _err(exc, title=title)


# ---------------------------------------------------------------------------

_activate_extension()


def main() -> None:
    """Entry point: serve over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
