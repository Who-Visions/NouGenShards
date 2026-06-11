from pathlib import Path
from .registry import HIGH_SIGNAL_TERMS, MEDIUM_SIGNAL_TERMS, LOW_SIGNAL_TERMS

def classify_file(path: Path) -> str:
    """Scores a file as 'high', 'medium', or 'low' signal based on path and name heuristics."""
    name_lower = path.name.lower()
    parent_lower = path.parent.name.lower()
    
    # 1. Immediate Low Signal Rejection
    for term in LOW_SIGNAL_TERMS:
        if term in name_lower or term in parent_lower:
            return "low"
            
    # 2. Check High Signal
    for term in HIGH_SIGNAL_TERMS:
        if term in name_lower or term in parent_lower:
            return "high"
            
    # 3. Check Medium Signal
    for term in MEDIUM_SIGNAL_TERMS:
        if term in name_lower or term in parent_lower:
            return "medium"
            
    # Default fallback for recognized extensions that didn't match specific terms
    if path.suffix in [".md", ".txt"]:
        return "medium"
        
    return "low"

def detect_tool(path: Path) -> str:
    """Attempts to identify the source tool from the path."""
    parts = [p.lower() for p in path.parts]
    for tool in ["claude", "gemini", "codex", "cursor", "continue", "copilot", "openhands", "mem0", "ollama", "qwen", "roo", "vscode", "github"]:
        if f".{tool}" in parts or tool in parts:
            return tool
    return "unknown"
