from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

@dataclass
class NormalizedRecord:
    source_tool: str
    source_kind: str
    source_path: str
    project_path: Optional[str]
    conversation_id: Optional[str]
    role: str
    timestamp: str
    title: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    parser: str = "unknown"
    confidence: float = 0.0
    source_hash: Optional[str] = None
    content_hash: Optional[str] = None

@dataclass
class CandidateFile:
    path: Path
    tool: str
    is_project_context: bool
    score_tier: str  # "high", "medium", "low"
    size_mb: float
