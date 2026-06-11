from pathlib import Path
from typing import List
from .candidate import CandidateFile
from .registry import GLOBAL_ROOTS, PROJECT_ROOT_NAMES, PROJECT_FILES, DANGER_ZONES, SKIP_DIRS, SUPPORTED_EXTS
from .classifiers import classify_file, detect_tool

def _is_safe_dir(path: Path) -> bool:
    for d in path.parts:
        if d.lower() in SKIP_DIRS or d.lower() in DANGER_ZONES or d.startswith(".ssh") or d.startswith(".aws"):
            return False
    return True

def scan_environment(project_path: str = None, include_unknown: bool = False) -> List[CandidateFile]:
    """Scans the environment for local AI tool history and context."""
    candidates = []
    
    # 1. Project Scan
    if project_path:
        root = Path(project_path).resolve()
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in SUPPORTED_EXTS and _is_safe_dir(p.parent):
                is_proj_ctx = any(part in PROJECT_ROOT_NAMES for part in p.parts) or p.name in PROJECT_FILES
                if is_proj_ctx or include_unknown:
                    score = classify_file(p)
                    if score in ["high", "medium"]:
                        tool = detect_tool(p)
                        sz = p.stat().st_size / (1024 * 1024)
                        if sz <= 25: # Skip files > 25MB
                            candidates.append(CandidateFile(p, tool, True, score, sz))
                            
    # 2. Global Scan
    # We skip Path.home() generic rglob to avoid crawling the whole user disk.
    # We only scan the specific tool directories (GLOBAL_ROOTS[1:]).
    for g_root in GLOBAL_ROOTS[1:]:
        if not g_root.exists() or not g_root.is_dir(): continue
        for p in g_root.rglob("*"):
            # Limit depth relative to g_root to prevent infinite symlinks
            if len(p.relative_to(g_root).parts) > 5: continue
            
            if p.is_file() and p.suffix in SUPPORTED_EXTS and _is_safe_dir(p.parent):
                score = classify_file(p)
                if score in ["high", "medium"]:
                    tool = detect_tool(p)
                    if tool != "unknown" or include_unknown:
                        sz = p.stat().st_size / (1024 * 1024)
                        if sz <= 25:
                            candidates.append(CandidateFile(p, tool, False, score, sz))
    
    # Deduplicate candidates by path
    seen = set()
    unique_cands = []
    for c in candidates:
        s_path = str(c.path.absolute())
        if s_path not in seen:
            seen.add(s_path)
            unique_cands.append(c)
            
    return unique_cands
