"""Grid canon-lock bridge for canon pressure.

GM canon locks are captured as shards in the grid ("GM CANON LOCK ...",
"CANON LOCK: ...", "CANON INVARIANT ..."), not in the seed self-model, so the
pressure engine never saw them and every claim touching a locked fact scored
UNKNOWN. This module reads those shards read-only and tests a candidate
against each lock clause with three conservative rules (a number/year
mismatch, a claim the lock negates, a candidate that denies the lock) plus a
strict affirmation rule. Everything tunable comes from env with a logged
fallback; nothing here knows any story, character or universe.
"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PREFIXES = "GM CANON LOCK,CANON LOCK,CANON INVARIANT"
DEFAULT_LIMIT = 500
DEFAULT_MIN_OVERLAP = 2
DEFAULT_TTL_S = 300.0

_STOP = frozenset({
    "the", "a", "an", "is", "was", "are", "were", "be", "been", "in", "on", "at",
    "of", "to", "and", "or", "for", "with", "by", "as", "that", "this", "it",
    "its", "his", "her", "their", "has", "have", "had", "does", "did", "do",
    "from", "into", "who", "which",
})
_NEG = frozenset({"not", "never", "no", "nor", "cannot", "isnt", "wasnt", "doesnt",
                  "didnt", "arent", "werent"})
_YEAR = re.compile(r"^\d{4}$")
_DATE_LEAD = re.compile(r"^\d{4}-\d{2}-\d{2}")
_SEP_LEAD = re.compile(r"^[:\-\s]+")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+)")
_DB_LABEL = re.compile(r"(\d+)")

_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; falling back to %s", key, raw, default)
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; falling back to %s", key, raw, default)
        return default


def prefixes() -> List[str]:
    """Lock title prefixes, longest first so 'GM CANON LOCK' wins over 'CANON LOCK'."""
    raw = os.environ.get("NOUGEN_CANON_LOCK_PREFIXES", "").strip() or DEFAULT_PREFIXES
    out = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return sorted(out, key=len, reverse=True)


def lock_dir() -> Optional[Path]:
    """Shard grid directory: NOUGEN_CANON_LOCK_DIR, else the node's (tenant-aware) shard dir."""
    override = os.environ.get("NOUGEN_CANON_LOCK_DIR", "").strip()
    if override:
        return Path(override)
    try:
        from . import dynamic_api
        return Path(dynamic_api._shards_dir())
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("canon lock dir unresolved: %s: %s", type(exc).__name__, exc)
        return None


def _clauses(title: str, content: Optional[str], pfx: List[str]) -> List[str]:
    body = (title or "").strip()
    upper = body.upper()
    for pre in pfx:
        if upper.startswith(pre):
            body = body[len(pre):].strip()
            break
    body = _SEP_LEAD.sub("", _DATE_LEAD.sub("", body).strip()).strip()
    found = [c.strip() for c in body.split(";")]
    for line in (content or "").splitlines():
        m = _NUMBERED.match(line)
        if m:
            found.append(m.group(1).strip())
    seen: Set[str] = set()
    out = []
    for c in found:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def load_locks(shards_dir: Optional[Path] = None, *, force: bool = False) -> List[Dict[str, Any]]:
    """Read lock shards from every nougen_shards_*.db in the grid dir (read-only, TTL cached)."""
    shards_dir = Path(shards_dir) if shards_dir else lock_dir()
    if shards_dir is None or not shards_dir.is_dir():
        return []
    key = str(shards_dir)
    ttl = _env_float("NOUGEN_CANON_LOCK_TTL_S", DEFAULT_TTL_S)
    hit = _CACHE.get(key)
    if not force and hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    pfx = prefixes()
    limit = _env_int("NOUGEN_CANON_LOCK_LIMIT", DEFAULT_LIMIT)
    where = " OR ".join("upper(ltrim(title)) LIKE ?" for _ in pfx)
    params = [f"{p}%" for p in pfx]
    locks: List[Dict[str, Any]] = []
    for db in sorted(shards_dir.glob("nougen_shards_*.db")):
        if len(locks) >= limit:
            break
        m = _DB_LABEL.search(db.stem)
        label = f"db{m.group(1)}" if m else db.stem
        try:
            with contextlib.closing(sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)) as conn:
                rows = conn.execute(
                    f"SELECT id, title, content FROM shards WHERE {where} ORDER BY id DESC LIMIT ?",
                    params + [limit - len(locks)]).fetchall()
        except sqlite3.Error as exc:
            logger.warning("canon lock read skipped %s: %s", db.name, exc)
            continue
        for row_id, title, content in rows:
            title = title or ""
            locks.append({
                "id": f"lock:{row_id}@{label}",
                "shard": f"{row_id}@{label}",
                "title": title,
                "authority": "gm_lock" if title.strip().upper().startswith("GM ") else "gm",
                "clauses": _clauses(title, content, pfx),
            })
    _CACHE[key] = (time.monotonic(), locks)
    return locks


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", "").replace("’", ""))


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _split(text: str) -> Tuple[Set[str], Set[str], bool, Set[str]]:
    """(tokens before the first negation, tokens only after it, negated?, numbers)."""
    words = _words(text)
    neg_at = next((i for i, w in enumerate(words) if w in _NEG), -1)

    def content(seg: List[str]) -> Set[str]:
        return {_stem(w) for w in seg if len(w) > 2 and not w.isdigit() and w not in _STOP and w not in _NEG}

    numbers = {w for w in words if w.isdigit()}
    if neg_at < 0:
        return content(words), set(), False, numbers
    pos = content(words[:neg_at])
    return pos, content(words[neg_at + 1:]) - pos, True, numbers


def _numbers_clash(a: Set[str], b: Set[str]) -> bool:
    ya = {n for n in a if _YEAR.match(n)}
    yb = {n for n in b if _YEAR.match(n)}
    if ya and yb:
        return not (ya & yb)
    return bool(a and b and not (a & b))


def check(candidate: str, locks: List[Dict[str, Any]], *, min_overlap: Optional[int] = None) -> Dict[str, Any]:
    """Test a candidate against lock clauses. One conflict or affirmation per lock."""
    if min_overlap is None:
        min_overlap = _env_int("NOUGEN_CANON_LOCK_MIN_OVERLAP", DEFAULT_MIN_OVERLAP)
    sentences = [s.strip() for s in re.split(r"[.;!?]+", candidate or "") if s.strip()]
    conflicts: List[Dict[str, Any]] = []
    affirmations: List[Dict[str, Any]] = []
    for lock in locks:
        conflict = affirm = None
        for clause in lock.get("clauses", []):
            c_pos, c_neg, c_negated, c_num = _split(clause)
            all_c = c_pos | c_neg
            for sent in sentences:
                s_pos, s_neg, s_negated, s_num = _split(sent)
                all_s = s_pos | s_neg
                shared = all_c & all_s
                enough = len(shared) >= min_overlap
                rule, matched = None, []
                if enough and _numbers_clash(c_num, s_num):
                    rule, matched = "number_mismatch", sorted(s_num)
                elif (enough and c_negated and not s_negated and (c_pos & s_pos or not c_pos)
                      and c_neg & all_s):
                    rule, matched = "negated_by_lock", sorted(c_neg & all_s)
                elif (enough and s_negated and not c_negated and (s_pos & c_pos or not s_pos)
                      and s_neg & all_c):
                    rule, matched = "candidate_denies_lock", sorted(s_neg & all_c)
                if rule:
                    conflict = {"lock": lock["id"], "shard": lock["shard"], "authority": lock["authority"],
                                "clause": clause, "rule": rule, "matched": matched}
                    break
                if (affirm is None and not c_negated and not s_negated and len(c_pos) >= min_overlap
                        and c_pos <= all_s and (not c_num or c_num <= s_num)):
                    affirm = {"lock": lock["id"], "shard": lock["shard"], "authority": lock["authority"],
                              "clause": clause, "rule": "affirms", "matched": sorted(c_pos)}
            if conflict:
                break
        if conflict:
            conflicts.append(conflict)
        elif affirm:
            affirmations.append(affirm)
    return {"conflicts": conflicts, "affirmations": affirmations, "consulted": len(locks)}


def lock_findings(candidate: str, locks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Entry point for pressure(). NOUGEN_CANON_LOCKS=0 turns the bridge off."""
    if os.environ.get("NOUGEN_CANON_LOCKS", "").strip() == "0":
        return {"conflicts": [], "affirmations": [], "consulted": 0, "disabled": True}
    if locks is None:
        locks = load_locks()
    return check(candidate, locks)
