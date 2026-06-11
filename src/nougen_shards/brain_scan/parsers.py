import json
import hashlib
from pathlib import Path
from typing import List
from datetime import datetime, timezone
from .candidate import NormalizedRecord

def _safe_read(path: Path) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        return ""

def _hash(content: str) -> str:
    return hashlib.md5(content.encode('utf-8', errors='ignore')).hexdigest()

def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"

def parse_json(path: Path, tool: str, is_project: bool) -> List[NormalizedRecord]:
    content = _safe_read(path)
    if not content: return []
    try:
        data = json.loads(content)
        title = path.name
        # Heuristic extraction
        if isinstance(data, dict):
            if "name" in data: title = str(data["name"])
            elif "title" in data: title = str(data["title"])
        return [NormalizedRecord(
            source_tool=tool,
            source_kind="json_data",
            source_path=str(path.absolute()),
            project_path=str(path.parent) if is_project else None,
            conversation_id=None,
            role="system",
            timestamp=_timestamp(),
            title=title,
            content=json.dumps(data, indent=2)[:5000], # truncate huge JSON
            parser="json_parser",
            confidence=0.5,
            source_hash=_hash(content),
            content_hash=_hash(json.dumps(data))
        )]
    except json.JSONDecodeError:
        return []

def parse_jsonl(path: Path, tool: str, is_project: bool) -> List[NormalizedRecord]:
    content = _safe_read(path)
    if not content: return []
    records = []
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        try:
            data = json.loads(line)
            role = data.get("role", "system")
            text = data.get("content", str(data))
            records.append(NormalizedRecord(
                source_tool=tool,
                source_kind="jsonl_event",
                source_path=str(path.absolute()),
                project_path=str(path.parent) if is_project else None,
                conversation_id=data.get("session_id"),
                role=role,
                timestamp=data.get("timestamp", _timestamp()),
                title=f"{path.name} - Line {idx}",
                content=text[:5000],
                parser="jsonl_parser",
                confidence=0.7,
                source_hash=_hash(line),
                content_hash=_hash(text)
            ))
        except json.JSONDecodeError:
            continue
    return records

def parse_markdown(path: Path, tool: str, is_project: bool) -> List[NormalizedRecord]:
    content = _safe_read(path)
    if not content: return []
    title = path.name
    return [NormalizedRecord(
        source_tool=tool,
        source_kind="markdown_document",
        source_path=str(path.absolute()),
        project_path=str(path.parent) if is_project else None,
        conversation_id=None,
        role="system",
        timestamp=_timestamp(),
        title=title,
        content=content[:10000],
        parser="markdown_parser",
        confidence=0.8,
        source_hash=_hash(content),
        content_hash=_hash(content[:10000])
    )]

def parse_universal(path: Path, tool: str, is_project: bool) -> List[NormalizedRecord]:
    if path.suffix == ".json":
        return parse_json(path, tool, is_project)
    elif path.suffix in [".jsonl"]:
        return parse_jsonl(path, tool, is_project)
    elif path.suffix in [".md", ".txt"]:
        return parse_markdown(path, tool, is_project)
    
    # Fallback to a basic read for other text files
    content = _safe_read(path)
    if not content: return []
    return [NormalizedRecord(
        source_tool=tool,
        source_kind="text_log",
        source_path=str(path.absolute()),
        project_path=str(path.parent) if is_project else None,
        conversation_id=None,
        role="system",
        timestamp=_timestamp(),
        title=path.name,
        content=content[:5000],
        parser="universal_text",
        confidence=0.3,
        source_hash=_hash(content),
        content_hash=_hash(content[:5000])
    )]
