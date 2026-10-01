#!/usr/bin/env python3
"""First-class MCP surface for the canonical NouGen arXiv radar.

Design laws
-----------
1. Read-only by default.
2. Advertise only handlers that import successfully.
3. No caller-supplied tenant/user authority. Public gateways derive scope from auth.
4. Lab-watch never promotes novelty automatically.
5. Radar mutation requires BOTH explicit commit=True and an operator env gate.
6. Every response carries provenance and degraded/error state.
7. The MCP transport is replaceable; the canonical Python tools remain ordinary,
   unit-testable functions.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

HERE = Path(__file__).resolve().parent
ALLOW_MUTATION = os.environ.get("NOUGEN_ARXIV_MCP_ALLOW_MUTATION", "").strip() == "1"
MAX_RESULTS = int(os.environ.get("NOUGEN_ARXIV_MCP_MAX_RESULTS", "50"))
MAX_FULLTEXT_CHARS = int(os.environ.get("NOUGEN_ARXIV_MCP_MAX_FULLTEXT_CHARS", "24000"))


# ---------------------------------------------------------------------------
# MCP compatibility: mirror NouGenShards' mcp.py behavior across MCP majors.
# ---------------------------------------------------------------------------

class MockMCP:
    def __init__(self, name: str, **_: Any):
        self.name = name

    def tool(self, *args: Any, **kwargs: Any):
        del args, kwargs
        return lambda fn: fn

    def run(self) -> None:
        print("MCP SDK not installed.", file=sys.stderr)


try:
    from mcp.server.mcpserver import MCPServer  # mcp >= 2
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer  # mcp < 2
    except ImportError:
        MCPServer = MockMCP  # type: ignore[misc,assignment]


def _load(name: str, filename: str):
    """Load a sibling tool module without requiring nougen-radar to be packaged."""
    path = HERE / filename
    if not path.exists():
        return None, f"missing:{path}"
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None, f"no_import_spec:{path}"
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(name, mod)
        spec.loader.exec_module(mod)
        return mod, None
    except Exception as exc:  # startup truth: bad handler is not advertised
        return None, f"{type(exc).__name__}:{exc}"


RADAR, RADAR_ERR = _load("nougen_arxiv_radar", "arxiv_rss_radar.py")
LAB, LAB_ERR = _load("nougen_arxiv_lab_watch", "arxiv_lab_watch.py")
PAPER, PAPER_ERR = _load("nougen_arxiv_paper", "arxiv_paper.py")
MORPH, MORPH_ERR = _load("nougen_arxiv_morph_gate", "morph_gate.py")


def _instructions() -> str:
    return (
        "NouGen arXiv research MCP. Read-only operations are the default. "
        "Radar mutation is disabled unless the server operator enables "
        "NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1 and the caller also passes commit=true. "
        "Lab-watch novelty is always unjudged until an explicit downstream review. "
        "A missing tool means its canonical handler failed capability checks at startup."
    )


try:
    mcp = MCPServer("NouGenArxiv", dependencies=["mcp"], instructions=_instructions())
except TypeError:
    mcp = MCPServer("NouGenArxiv", dependencies=["mcp"])


# ---------------------------------------------------------------------------
# Shared response helpers
# ---------------------------------------------------------------------------

def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _capability(name: str, mod: Any, error: Optional[str]) -> dict[str, Any]:
    return {
        "name": name,
        "available": mod is not None,
        "error": error,
    }


def _provenance(tool: str, **extra: Any) -> dict[str, Any]:
    out = {
        "provider": "arXiv",
        "surface": "nougen-radar",
        "tool": tool,
        "canonical_repo": "Who-Visions/nougen-radar",
    }
    out.update(extra)
    return out


def _clip(items: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), MAX_RESULTS))
    return list(items)[:lim]


def _paper_projection(p: dict[str, Any]) -> dict[str, Any]:
    """Stable machine-readable subset. Avoid leaking implementation-only fields."""
    keep = (
        "id", "version", "title", "link", "abstract", "primary_category",
        "announce_type", "authors", "pub_date", "doi", "score",
        "matched_pillars", "reason_codes", "global_pct", "category_pct",
        "priority_pct", "route",
    )
    return {k: p.get(k) for k in keep if k in p}


# ---------------------------------------------------------------------------
# Tool 0: explicit capability truth
# ---------------------------------------------------------------------------

@mcp.tool()
def arxiv_capabilities() -> str:
    """Return the arXiv MCP handlers actually available in this process."""
    return _json({
        "ok": True,
        "mutation_enabled": ALLOW_MUTATION,
        "capabilities": [
            _capability("arxiv_radar", RADAR, RADAR_ERR),
            _capability("arxiv_lab_watch", LAB, LAB_ERR),
            _capability("arxiv_paper", PAPER, PAPER_ERR),
            _capability("morph_gate", MORPH, MORPH_ERR),
        ],
        "provenance": _provenance("arxiv_capabilities"),
    })


# ---------------------------------------------------------------------------
# Tool 1: radar
#
# preview = network read + in-memory score/route only. NO cursor write,
# NO Shards ingestion, NO NouGenMsg broadcast.
#
# commit = current canonical run_pipeline, but requires a double gate.
# ---------------------------------------------------------------------------

if RADAR is not None:

    @mcp.tool()
    def arxiv_radar(
        channels: Optional[list[str]] = None,
        mode: str = "preview",
        limit: int = 25,
        commit: bool = False,
        broadcast_target: Optional[str] = None,
    ) -> str:
        """Scan current arXiv channels through NouGen's canonical radar.

        Args:
            channels: RSS channels, e.g. ["cs"] or ["cs.AI", "cs.LG"].
            mode: "preview", "sweep", or "reconcile".
            limit: Maximum papers returned per lane.
            commit: False by default. True may update radar state and ingest priority
                papers only when the server operator also enabled mutation.
            broadcast_target: Optional NouGenMsg target for an authorized committed run.

        Read-only preview intentionally bypasses persisted ETag cursors so a web MCP
        client can ask "what is current?" without mutating the operator's scheduler.
        """
        channels = channels or ["cs"]
        mode = mode.strip().lower()
        if mode not in {"preview", "sweep", "reconcile"}:
            raise ValueError("mode must be preview, sweep, or reconcile")

        if commit:
            if not ALLOW_MUTATION:
                return _json({
                    "ok": False,
                    "status": "mutation_disabled",
                    "reason": (
                        "Server operator must set NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1. "
                        "Read-only preview remains available."
                    ),
                    "provenance": _provenance("arxiv_radar"),
                })

            # Existing run_pipeline writes queues/cursor, ingests beacon+review papers,
            # and may broadcast. This path therefore remains explicitly privileged.
            result = RADAR.run_pipeline(
                mode="reconcile" if mode == "preview" else mode,
                channels=channels,
                broadcast_target=broadcast_target or "",
            )
            return _json({
                "ok": True,
                "status": "committed",
                "result": result,
                "provenance": _provenance(
                    "arxiv_radar",
                    mutation=True,
                    mode=mode,
                    channels=channels,
                ),
            })

        # Pure preview.
        papers: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        for channel in channels:
            try:
                # Empty cursor means a fresh read and does not modify scheduler state.
                content, headers = RADAR.fetch_arxiv_rss_conditional(
                    channel,
                    {"channels": {}, "seen_ids": []},
                )
                if not content:
                    continue

                import xml.etree.ElementTree as ET
                root = ET.fromstring(content)
                for item in root.findall("./channel/item"):
                    p = RADAR.parse_arxiv_item(item)
                    if p.get("id"):
                        papers.append(p)
            except Exception as exc:
                errors.append({
                    "channel": channel,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        scored = RADAR.compute_percentiles(papers)
        lanes = RADAR.route_papers(scored, RADAR.load_route_recipe())

        return _json({
            "ok": bool(papers) or not errors,
            "status": "partial" if errors else "success",
            "counts": {
                "total": len(scored),
                "beacon": len(lanes["beacon"]),
                "review": len(lanes["review"]),
                "shard": len(lanes["shard"]),
            },
            "lanes": {
                name: [_paper_projection(p) for p in _clip(rows, limit)]
                for name, rows in lanes.items()
            },
            "errors": errors,
            "provenance": _provenance(
                "arxiv_radar",
                mutation=False,
                mode="preview",
                channels=channels,
            ),
        })


# ---------------------------------------------------------------------------
# Tool 2: lab watch
#
# Preview must preserve the existing invariant: novelty is "unjudged".
# Running the canonical LAB.run() mutates queue/cursor/digest, so it is gated.
# ---------------------------------------------------------------------------

if LAB is not None:

    @mcp.tool()
    def arxiv_lab_watch(
        channel: str = "cs.AR",
        limit: int = 25,
        backfill: bool = False,
        commit: bool = False,
    ) -> str:
        """Screen an arXiv lab channel for NouGen architecture graft candidates.

        The classifier screens. It does NOT judge novelty. Every candidate remains
        novelty="unjudged" until explicit review/NouGenMorph evaluation.
        """
        if commit:
            if not ALLOW_MUTATION:
                return _json({
                    "ok": False,
                    "status": "mutation_disabled",
                    "reason": "Enable NOUGEN_ARXIV_MCP_ALLOW_MUTATION=1 on the server.",
                    "provenance": _provenance("arxiv_lab_watch", channel=channel),
                })
            result = LAB.run(channel=channel, backfill=backfill)
            return _json({
                "ok": True,
                "status": "committed",
                "result": result,
                "provenance": _provenance(
                    "arxiv_lab_watch",
                    channel=channel,
                    mutation=True,
                ),
            })

        # In-memory preview. No queue/cursor/digest write.
        radar = LAB._radar()
        items, _headers = LAB.fetch_feed(
            channel,
            {"channels": {}, "seen_ids": []},
            radar,
        )
        if backfill:
            items.extend(LAB.backfill_recent(channel))

        # Deduplicate without mutating the canonical lab cursor.
        seen: set[str] = set()
        unique = []
        for item in items:
            aid = item.get("id")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            unique.append(item)

        graft = [x for x in unique if x.get("tier") == "graft"]
        watch = [x for x in unique if x.get("tier") == "watch"]

        return _json({
            "ok": True,
            "status": "preview",
            "channel": channel,
            "counts": {
                "total": len(unique),
                "graft": len(graft),
                "watch": len(watch),
            },
            "graft": _clip(graft, limit),
            "watch": _clip(watch, limit),
            "novelty_policy": "unjudged",
            "auto_shard": False,
            "provenance": _provenance(
                "arxiv_lab_watch",
                channel=channel,
                mutation=False,
            ),
        })


# ---------------------------------------------------------------------------
# Tool 3: paper
# ---------------------------------------------------------------------------

if PAPER is not None:

    @mcp.tool()
    def arxiv_paper(
        ref: str,
        action: str = "lookup",
        pattern: Optional[str] = None,
        refresh: bool = False,
        max_chars: int = MAX_FULLTEXT_CHARS,
    ) -> str:
        """Inspect one arXiv paper.

        action:
          lookup   -> structured metadata from arXiv API
          fulltext -> cached/source LaTeX text, bounded for MCP transport
          claim    -> regex occurrences in BODY ONLY; abstract is excluded
        """
        action = action.strip().lower()
        if action not in {"lookup", "fulltext", "claim"}:
            raise ValueError("action must be lookup, fulltext, or claim")

        aid = PAPER.normalize_id(ref)

        if action == "lookup":
            payload = PAPER.lookup(aid)
            return _json({
                "ok": True,
                "action": action,
                "paper": payload,
                "provenance": _provenance("arxiv_paper", arxiv_id=aid),
            })

        if action == "claim":
            if not pattern:
                raise ValueError("pattern is required when action='claim'")
            # Validate early so catastrophic regex failures are visible as caller errors.
            re.compile(pattern)
            hits = PAPER.claim(aid, pattern)
            return _json({
                "ok": True,
                "action": action,
                "arxiv_id": aid,
                "pattern": pattern,
                "count": len(hits),
                "hits": hits[:20],
                "scope": "paper_body_excluding_abstract",
                "provenance": _provenance("arxiv_paper", arxiv_id=aid),
            })

        path = PAPER.fulltext(aid, refresh=refresh)
        text = path.read_text(encoding="utf-8")
        cap = max(1000, min(int(max_chars), MAX_FULLTEXT_CHARS))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        clipped = text[:cap]

        return _json({
            "ok": True,
            "action": action,
            "arxiv_id": aid,
            "sha256": digest,
            "chars_total": len(text),
            "chars_returned": len(clipped),
            "truncated": len(clipped) < len(text),
            "text": clipped,
            "provenance": _provenance("arxiv_paper", arxiv_id=aid),
        })


# ---------------------------------------------------------------------------
# Tool 4: morph evidence gate
# ---------------------------------------------------------------------------

if MORPH is not None:

    @mcp.tool()
    def morph_gate(ref: str, claims: list[str]) -> str:
        """Check key claim regexes against the arXiv paper BODY.

        Returns the canonical NouGenMorph-compatible evidence row. All claims found
        in body -> paper_body. Any missing/unavailable -> abstract_only. No automatic
        promotion occurs here.
        """
        if not claims:
            raise ValueError("claims must contain at least one anchored regex")
        if len(claims) > 32:
            raise ValueError("refusing more than 32 claims in one gate")

        # Compile before network/cache work; bad regex is a request error, not evidence.
        for pattern in claims:
            re.compile(pattern)

        row = MORPH.gate(ref, claims)
        return _json({
            "ok": row.get("evidence_type") == "paper_body",
            "evidence": row,
            "promotion": "none",
            "provenance": _provenance("morph_gate"),
        })


if __name__ == "__main__":
    mcp.run()
