from pathlib import Path
from typing import List, Optional
from .candidate import CandidateFile
from .registry import (GLOBAL_ROOTS, PROJECT_ROOT_NAMES, PROJECT_FILES, DANGER_ZONES,
                       SKIP_DIRS, SUPPORTED_EXTS, SQLITE_EXTS, SELF_EXCLUDE_DIRS)
from .classifiers import classify_file, detect_tool

# Text candidates are read whole, so a large one is a memory hazard and almost
# always a build artifact rather than history.
MAX_TEXT_MB = 25

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
        if d.lower() in SELF_EXCLUDE_DIRS:
            return False
    return True


def _within_size_budget(path: Path, size_mb: Optional[float]) -> bool:
    """SQLite sources are queried row by row, so their file size is irrelevant.

    Applying the text ceiling to them was what silently dropped the largest
    memory stores on the machine (a 99MB file index, ~159k rows).
    """
    if size_mb is None:
        return False
    if path.suffix.lower() in SQLITE_EXTS:
        return True
    return size_mb <= MAX_TEXT_MB

def _is_safe_file(path: Path) -> bool:
    """A file is safe to scan only if it is a real file (not a symlink, which
    could escape the scanned tree into ~/.ssh etc.) and is not a known
    credential store. Symlinks are skipped outright rather than resolved."""
    if path.is_symlink():
        return False
    if path.name.lower() in DANGER_FILES:
        return False
    return _is_safe_dir(path.parent)

def _safe_size_mb(path: Path) -> Optional[float]:
    """Return file size in MB, or None if it is unreadable (broken symlink,
    permission denied, race). Never let one bad file abort the whole scan."""
    try:
        return path.stat().st_size / (1024 * 1024)
    except OSError:
        return None

def _root_tool_name(root: Path, path: Path) -> str:
    """Names the source tool for a database outside the known dot-directories.

    `detect_tool` only recognizes the hard-coded tool list, so an Iris or
    Watchtower store came back "unknown" and was filtered out. Falling back to
    the root directory name keeps the shard attributable.
    """
    tool = detect_tool(path)
    if tool != "unknown":
        return tool
    return root.name.lstrip(".").lower() or "unknown"


def scan_databases(include_generic: bool = False) -> List[CandidateFile]:
    """Finds SQLite memory stores across the tool roots.

    Classification here is by *schema*, not filename: `classify_file` scores on
    path terms alone, which rated the machine-wide file index "low" purely
    because its filename contains no keyword. A database that resolves to a
    known handler is high signal whatever it is called.
    """
    from .sqlite_sources import detect_handler  # local: avoids an import cycle

    found: List[CandidateFile] = []
    # GLOBAL_ROOTS[0] is Path.home(); walking it would crawl the whole disk.
    for root in GLOBAL_ROOTS[1:]:
        if not root.exists() or not root.is_dir():
            continue
        for p in root.rglob("*"):
            try:
                if len(p.relative_to(root).parts) > 6:
                    continue
            except ValueError:
                continue
            if p.suffix.lower() not in SQLITE_EXTS:
                continue
            if not p.is_file() or not _is_safe_file(p):
                continue
            handler = detect_handler(p)
            if handler is None:
                continue  # not SQLite, unreadable, or empty
            if handler == "generic" and not include_generic:
                continue
            sz = _safe_size_mb(p)
            found.append(CandidateFile(p, _root_tool_name(root, p), False,
                                       "high", sz or 0.0))
    return found


def scan_environment(project_path: Optional[str] = None, include_unknown: bool = False) -> List[CandidateFile]:
    """Scans the environment for local AI tool history and context."""
    candidates = []
    
    # 1. Project Scan
    if project_path:
        root = Path(project_path).resolve()
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in SUPPORTED_EXTS and _is_safe_file(p):
                is_proj_ctx = any(part in PROJECT_ROOT_NAMES for part in p.parts) or p.name in PROJECT_FILES
                if is_proj_ctx or include_unknown:
                    score = classify_file(p)
                    if score in ["high", "medium"]:
                        tool = detect_tool(p)
                        sz = _safe_size_mb(p)
                        if _within_size_budget(p, sz):
                            candidates.append(CandidateFile(p, tool, True, score, sz or 0.0))
                            
    # 2. Global Scan
    # We skip Path.home() generic rglob to avoid crawling the whole user disk.
    # We only scan the specific tool directories (GLOBAL_ROOTS[1:]).
    for g_root in GLOBAL_ROOTS[1:]:
        if not g_root.exists() or not g_root.is_dir(): continue
        for p in g_root.rglob("*"):
            # Limit depth relative to g_root to prevent infinite symlinks.
            # relative_to is safe here because we skip symlinks (no tree escape).
            try:
                if len(p.relative_to(g_root).parts) > 5: continue
            except ValueError:
                continue

            if p.is_file() and p.suffix in SUPPORTED_EXTS and _is_safe_file(p):
                score = classify_file(p)
                if score in ["high", "medium"]:
                    tool = detect_tool(p)
                    if tool != "unknown" or include_unknown:
                        sz = _safe_size_mb(p)
                        if _within_size_budget(p, sz):
                            candidates.append(CandidateFile(p, tool, False, score, sz or 0.0))

    # 3. Database Scan
    candidates.extend(scan_databases(include_generic=include_unknown))

    # Deduplicate candidates by path
    seen = set()
    unique_cands = []
    for c in candidates:
        s_path = str(c.path.absolute())
        if s_path not in seen:
            seen.add(s_path)
            unique_cands.append(c)
            
    return unique_cands
