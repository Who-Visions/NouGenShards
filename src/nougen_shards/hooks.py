"""Reversed Hooks Lane for NouGenShards.

Intercepts and compacts message history into high-signal Semantic Anchors.
Also exposes a Codex-friendly preflight anchor that can be printed by the CLI
without mutating shell profiles or global runtime config.
"""
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Union


DEFAULT_ANCHOR_MAX_CHARS = 8000

def extract_invariants(messages: List[Dict[str, Any]]) -> str:
    """
    Semantic Extraction: Pipes the message array through lightweight regex/AST 
    parsing to extract structural invariants (types, schema, explicit directives).
    """
    invariants = []
    
    # Patterns for high-signal architectural markers
    patterns = [
        r"(?:type|interface|class|def|function)\s+([a-zA-Z0-9_]+)",
        r"(?:endpoint|url|path|api)\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"(?:directive|mandate|rule)\s*[:=]\s*([^.\n]+)",
        r"database\s+schema\s*[:=]\s*([^.\n]+)"
    ]

    seen_markers = set()
    
    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
            
        for p in patterns:
            matches = re.findall(p, content, re.IGNORECASE)
            for m in matches:
                if m not in seen_markers:
                    invariants.append(m)
                    seen_markers.add(m)
                    
    # Limit to top invariants to keep under token budget
    summary = ", ".join(invariants[:20])
    return f"Structural Invariants: {summary}" if invariants else "No new invariants detected."

def inject_semantic_anchors(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Cache Alignment: Replaces raw chronological history with a compressed 
    'Semantic Anchor' block containing strict graph delta pointers.
    """
    if len(messages) <= 3:
        return messages # Don't compact short sessions
        
    # 1. Preserve System Prompt (The Anchor)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    
    # 2. Extract Invariants from the entire buffer
    anchors_text = extract_invariants(messages)
    
    # 3. Create the compact anchor message
    # This replaces the middle 'tail' of the conversation
    compact_anchor = {
        "role": "user",
        "content": f"[REVERSED_HOOK] Semantic Anchor (History Virtualized): {anchors_text}"
    }
    
    # 4. Keep the most recent user request (The Execution Shard)
    recent_msgs = [m for m in messages if m.get("role") != "system"][-2:]
    
    return system_msgs + [compact_anchor] + recent_msgs

def pre_tool_use_hook(message_payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Main entry point for Play 2: Pointer Compaction.
    Intercepts the history buffer before serialization.
    """
    return inject_semantic_anchors(message_payload)


def _clip(text: object, limit: int = 900) -> str:
    value = "" if text is None else str(text).strip()
    value = re.sub(r"\s+", " ", value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _handoff_db_path(repo_root: Optional[Path] = None) -> Path:
    if os.environ.get("NOUGEN_HANDOFF_DIR"):
        return Path(os.environ["NOUGEN_HANDOFF_DIR"]) / "handoffs.db"
    root = repo_root or _default_repo_root()
    return root / ".handoffs" / "handoffs.db"


def _fetch_handoff_rows(limit: int = 5, repo_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    db_path = _handoff_db_path(repo_root)
    if not db_path.exists():
        return []

    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT handoff_id, agent, status, goal, message, branch, path,
                   created_at, acknowledged_by, acknowledged_at, updated_at
            FROM handoff_records
            ORDER BY created_at DESC, handoff_id DESC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.Error, OSError):
        return []
    finally:
        if conn is not None:
            conn.close()


def get_latest_anchor(
    limit: int = 5,
    max_chars: int = DEFAULT_ANCHOR_MAX_CHARS,
    repo_root: Optional[Union[str, Path]] = None,
) -> str:
    """Return a compact Codex preflight anchor from the local handoff index.

    The output is intentionally stable and small so provider sessions can pin a
    hot prefix instead of replaying raw handoff JSON, transcripts, or logs.
    """
    root = Path(repo_root) if repo_root else _default_repo_root()
    rows = _fetch_handoff_rows(limit=limit, repo_root=root)

    lines = [
        "[NOUGEN_CONTEXT_ANCHOR]",
        "Role: Coach, not Player. Use compact recall before broad scans.",
        "Cache SLO: target >=90% cache-read share; stop and compact below 85%.",
        "Protocol: handoff read -> ack on takeover -> work -> create handoff -> rebuild-db.",
        "Safety: do not replay raw transcripts, full handoffs, full token reports, or large logs.",
        f"Source: { _handoff_db_path(root) }",
    ]

    if not rows:
        lines.append("Latest handoffs: none indexed. Run handoff rebuild-db if records exist.")
    else:
        lines.append("Latest handoffs:")
        for row in rows:
            ack = row.get("acknowledged_by") or "unclaimed"
            lines.append(
                "- "
                f"id={_clip(row.get('handoff_id'), 120)}; "
                f"agent={_clip(row.get('agent'), 40)}; "
                f"status={_clip(row.get('status'), 40)}; "
                f"ack={_clip(ack, 40)}; "
                f"branch={_clip(row.get('branch'), 80)}; "
                f"goal={_clip(row.get('goal'), 220)}; "
                f"note={_clip(row.get('message'), 420)}"
            )

    anchor = "\n".join(lines).strip()
    if len(anchor) > max_chars:
        anchor = anchor[: max(0, max_chars - 28)].rstrip() + "\n[ANCHOR_TRUNCATED]"
    return anchor


def get_space_orchestration_anchor(
    limit: int = 5,
    max_chars: int = DEFAULT_ANCHOR_MAX_CHARS,
    space_id: Optional[str] = None,
    token_key: Optional[str] = None,
) -> str:
    """Return the HF Space overlay anchor without replacing local handoffs."""
    from . import space_orchestration

    return space_orchestration.get_space_orchestration_anchor(
        limit=limit,
        max_chars=max_chars,
        space_id=space_id,
        token_key=token_key,
    )


def install_local_codex_hook(
    output_dir: Optional[Union[str, Path]] = None,
    limit: int = 5,
    max_chars: int = DEFAULT_ANCHOR_MAX_CHARS,
) -> Path:
    """Write local hook artifacts for Codex without touching global profiles."""
    root = _default_repo_root()
    target_dir = Path(output_dir) if output_dir else root / ".nougen-hooks"
    target_dir.mkdir(parents=True, exist_ok=True)

    anchor_path = target_dir / "codex-preflight-anchor.md"
    space_anchor_path = target_dir / "hf-space-orchestration-anchor.md"
    script_path = target_dir / "codex-anchor.ps1"
    cmd_path = target_dir / "codex-anchor.cmd"
    anchor_path.write_text(
        get_latest_anchor(limit=limit, max_chars=max_chars, repo_root=root) + "\n",
        encoding="utf-8",
    )
    space_anchor_path.write_text(
        get_space_orchestration_anchor(limit=limit, max_chars=max_chars) + "\n",
        encoding="utf-8",
    )
    script_path.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"$env:PYTHONPATH = '{root / 'src'}'",
                f"& '{root / '.venv' / 'Scripts' / 'python.exe'}' -m nougen_shards.cli hook codex-anchor",
                "",
            ]
        ),
        encoding="utf-8",
    )
    cmd_path.write_text(
        "\n".join(
            [
                "@echo off",
                f"set \"PYTHONPATH={root / 'src'}\"",
                f"\"{root / '.venv' / 'Scripts' / 'python.exe'}\" -m nougen_shards.cli hook codex-anchor",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return target_dir
