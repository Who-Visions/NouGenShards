"""Manifest and workflow bridge for external skill collections.

The bridge keeps an upstream collection intact while exposing its discovery
metadata to NouGen.  Skill bodies remain files and are loaded only when the
normal skill resolver activates them; the catalog and workflow files are
metadata surfaces, not prompt payloads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from . import skills


def _configured_root() -> Optional[Path]:
    """Return the configured repository or skills directory, if any."""
    raw = os.environ.get("NOUGEN_SKILLS_DIR", "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser().resolve()
    if candidate.is_dir() and candidate.name.lower() == "skills":
        candidate = candidate.parent
    if (candidate / "skills_index.json").is_file() and (candidate / "skills").is_dir():
        return candidate
    return None


def repository_root() -> Optional[Path]:
    """Resolve an external manifest-bearing skill repository."""
    return _configured_root()


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def manifest() -> list[dict[str, Any]]:
    root = repository_root()
    if not root:
        return []
    value = _read_json(root / "skills_index.json", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def workflows() -> list[dict[str, Any]]:
    root = repository_root()
    if not root:
        return []
    value = _read_json(root / "data" / "workflows.json", {})
    items = value.get("workflows", []) if isinstance(value, dict) else []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def status() -> dict[str, Any]:
    """Return an evidence-backed full-catalog health snapshot."""
    root = repository_root()
    records = manifest()
    if not root:
        return {
            "configured": False,
            "manifest_count": 0,
            "discovered_count": 0,
            "workflow_count": 0,
        }

    discovered = skills.discover([root])
    manifest_paths = {
        str((root / record["path"] / "SKILL.md").resolve())
        for record in records
        if isinstance(record.get("path"), str)
    }
    discovered_paths = {str(skill.path.resolve()) for skill in discovered}
    return {
        "configured": True,
        "repository": str(root),
        "manifest_count": len(records),
        "discovered_count": len(discovered),
        "missing_from_files": len(manifest_paths - discovered_paths),
        "unlisted_files": len(discovered_paths - manifest_paths),
        "workflow_count": len(workflows()),
        "plugin_manifest_count": len(list((root / "plugins").rglob("plugin.json")))
        if (root / "plugins").is_dir()
        else 0,
    }


def workflow_roster() -> list[dict[str, Any]]:
    """Return compact workflow metadata without loading skill bodies."""
    result = []
    for workflow in workflows():
        result.append(
            {
                "id": workflow.get("id"),
                "name": workflow.get("name"),
                "description": workflow.get("description"),
                "category": workflow.get("category"),
                "steps": [
                    {
                        "title": step.get("title"),
                        "recommendedSkills": step.get("recommendedSkills", []),
                    }
                    for step in workflow.get("steps", [])
                    if isinstance(step, dict)
                ],
            }
        )
    return result
