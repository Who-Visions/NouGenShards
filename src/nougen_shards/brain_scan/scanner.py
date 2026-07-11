import os
from pathlib import Path
from typing import Iterator, List, Optional
from .candidate import CandidateFile
from .registry import GLOBAL_ROOTS, PROJECT_ROOT_NAMES, PROJECT_FILES, DANGER_ZONES, SKIP_DIRS, SUPPORTED_EXTS
from .classifiers import classify_file, detect_tool

# Well-known credential files that are not directories (so DANGER_ZONES, which
# matches path parts/dirs, never catches them). Matched on the file name.
DANGER_FILES = {
    ".netrc", "_netrc", ".git-credentials", ".pgpass", ".npmrc", ".pypirc",
    ".env", "credentials", "credentials.json", "id_rsa", "id_ed25519",
}

def _is_safe_dir(path: Path) -> bool:
    for d in path.parts:
        if d.lower() in SKIP_DIRS or d.lower() in DANGER_ZONES or d.startswith(".ssh") or d.startswith(".aws"):
            return False
    return True

def _is_safe_file(path: Path) -> bool:
    """A file is safe to scan only if it is a real file (not a symlink, which
    could escape the scanned tree into ~/.ssh etc.) and is not a known
    credential store. Symlinks are skipped outright rather than resolved."""
    if path.is_symlink():
        return False
    if path.name.lower() in DANGER_FILES:
        return False
    return _is_safe_dir(path.parent)

def _walk_files(root: Path, max_depth: Optional[int] = None) -> Iterator[Path]:
    """os.walk with in-place dirname pruning so heavy/unsafe subtrees
    (SKIP_DIRS, DANGER_ZONES, dotfiles like .ssh/.aws) are never descended
    into, instead of being walked in full and discarded by rglob("*")."""
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root_str):
        rel_parts = Path(dirpath).relative_to(root).parts
        if max_depth is not None and len(rel_parts) >= max_depth:
            dirnames[:] = []
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in SKIP_DIRS
            and d.lower() not in DANGER_ZONES
            and not d.startswith(".ssh")
            and not d.startswith(".aws")
        ]
        for name in filenames:
            yield Path(dirpath) / name

def _safe_size_mb(path: Path) -> Optional[float]:
    """Return file size in MB, or None if it is unreadable (broken symlink,
    permission denied, race). Never let one bad file abort the whole scan."""
    try:
        return path.stat().st_size / (1024 * 1024)
    except OSError:
        return None

def scan_environment(project_path: Optional[str] = None, include_unknown: bool = False) -> List[CandidateFile]:
    """Scans the environment for local AI tool history and context."""
    candidates = []
    
    # 1. Project Scan
    if project_path:
        root = Path(project_path).resolve()
        for p in _walk_files(root):
            if p.is_file() and p.suffix in SUPPORTED_EXTS and _is_safe_file(p):
                is_proj_ctx = any(part in PROJECT_ROOT_NAMES for part in p.parts) or p.name in PROJECT_FILES
                if is_proj_ctx or include_unknown:
                    score = classify_file(p)
                    if score in ["high", "medium"]:
                        tool = detect_tool(p)
                        sz = _safe_size_mb(p)
                        if sz is not None and sz <= 25: # Skip files > 25MB / unreadable
                            candidates.append(CandidateFile(p, tool, True, score, sz))
                            
    # 2. Global Scan
    # We skip Path.home() generic rglob to avoid crawling the whole user disk.
    # We only scan the specific tool directories (GLOBAL_ROOTS[1:]).
    for g_root in GLOBAL_ROOTS[1:]:
        if not g_root.exists() or not g_root.is_dir(): continue
        # Depth capped at the walk level (not post-hoc) so deep symlink loops
        # or huge subtrees are never descended into in the first place.
        for p in _walk_files(g_root, max_depth=5):
            if p.is_file() and p.suffix in SUPPORTED_EXTS and _is_safe_file(p):
                score = classify_file(p)
                if score in ["high", "medium"]:
                    tool = detect_tool(p)
                    if tool != "unknown" or include_unknown:
                        sz = _safe_size_mb(p)
                        if sz is not None and sz <= 25:
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
