"""Cue-anchored trigger delivery — "delivery, not storage".

Voluntary memory is a fiction: an agent handed a `recall` tool essentially never
calls it — voluntary recall rates in long sessions round to zero — and a
large share of intra-session re-reads re-buy content the session already paid
for. The fix is to stop asking the agent to remember to remember. Memories carry
first-class *trigger conditions*; the HARNESS evaluates them deterministically
and injects the survivors. The agent never has to think about it.

Design constraints that shaped this module:

* **Additive, zero-DDL.** Triggers live in their own sidecar DB
  (``nougen_triggers.db``) beside the shard cluster. No ALTER, no re-index, no
  migration of the 9-DB cluster. A vault with no trigger rows behaves exactly as
  it does today, and a shard with no triggers is untouched by this code path.
* **No model call.** Evaluation is glob/regex/arithmetic. Cheap, deterministic,
  VRAM-free, safe to run on every SessionStart and (optionally) PreToolUse.
* **Budgeted.** Injecting too much recreates the exact held-context cost this is
  meant to cure. Precision beats coverage: a hard shard cap AND a hard token
  cap, both env-tunable, with the last block truncated rather than blowing past.
* **Rule 0.2.** Every environment-shaped value resolves env -> probe -> logged
  constant fallback. No bare magic numbers.

Trigger vocabulary (composable):
    path      glob over paths the session touched / the cwd
    symbol    identifier appears in the session's symbols or text
    semantic  all comma-separated terms appear (case-insensitive) in the text
    event     named lifecycle moment (session_start, pre_tool_use, pre_commit…)
    temporal  window over the SHARD's own age, e.g. ``age<=7d``

Firing rule: temporal triggers are a **gate**, everything else is a **cue**.
If a shard declares any temporal trigger, at least one must hold or the shard is
suppressed outright. It fires when at least one non-temporal cue matches — or,
when temporal is the only family it declares, when the gate itself holds (that
is the "surface this for its first week" shape).
"""
from __future__ import annotations

import fnmatch
import json
import math
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Configuration (Rule 0.2: env -> probe -> logged constant fallback)
# ---------------------------------------------------------------------------

TRIGGER_TYPES = ("path", "symbol", "semantic", "event", "temporal")
GATE_TYPES = ("temporal",)
CUE_TYPES = tuple(t for t in TRIGGER_TYPES if t not in GATE_TYPES)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


def enabled() -> bool:
    """Master switch. Default ON, but inert: an empty trigger table injects
    nothing, so enabling costs one cheap SELECT until someone authors a rule."""
    return _env_flag("NOUGEN_TRIGGERS_ENABLED", True)


def autoderive_enabled() -> bool:
    """Capture-time auto-derivation. Default **OFF** — a wrong trigger is worse
    than no trigger, because it injects noise into every future session."""
    return _env_flag("NOUGEN_TRIGGERS_AUTODERIVE", False)


def pretooluse_enabled() -> bool:
    """PreToolUse-lane evaluation. Default **OFF**: it fires many times per turn,
    so it is opt-in even though the hook may be registered."""
    return _env_flag("NOUGEN_TRIGGERS_PRETOOLUSE", False)


def budget_tokens() -> int:
    return max(0, _env_int("NOUGEN_TRIGGER_BUDGET_TOKENS", 900))


def max_shards() -> int:
    return max(0, _env_int("NOUGEN_TRIGGER_MAX_SHARDS", 3))


def chars_per_token() -> float:
    return max(1.0, _env_float("NOUGEN_TRIGGER_CHARS_PER_TOKEN", 4.0))


def snippet_chars() -> int:
    return max(0, _env_int("NOUGEN_TRIGGER_SNIPPET_CHARS", 400))


def min_block_tokens() -> int:
    """A truncated block below this size carries no information; drop it."""
    return max(1, _env_int("NOUGEN_TRIGGER_MIN_BLOCK_TOKENS", 20))


def min_score() -> float:
    return _env_float("NOUGEN_TRIGGER_MIN_SCORE", 0.0)


def path_case_sensitive() -> bool:
    """Probed from the platform, overridable: NTFS globs are case-insensitive."""
    return _env_flag("NOUGEN_TRIGGER_PATH_CASE_SENSITIVE", os.name != "nt")


def type_weight(ttype: str) -> float:
    """Precision ordering. A path/symbol hit is a near-certain situational match;
    a semantic hit is a guess, so it ranks below both by default."""
    defaults = {
        "path": 1.5,
        "symbol": 1.4,
        "event": 1.0,
        "semantic": 0.8,
        "temporal": 0.5,
    }
    return _env_float(
        "NOUGEN_TRIGGER_WEIGHT_" + ttype.upper(), defaults.get(ttype, 1.0))


def _vault_dir() -> Path:
    """Resolved live, never cached at import: tests monkeypatch core.GLOBAL_DIR
    and a cached path would silently point at the operator's real vault."""
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return Path(env)
    try:
        from . import core  # local import keeps the import graph acyclic
        return Path(core.GLOBAL_DIR)
    except Exception:
        return Path.home() / ".nougen" / "shards"


def db_path() -> Path:
    override = os.environ.get("NOUGEN_TRIGGERS_DB")
    if override:
        return Path(override)
    return _vault_dir() / os.environ.get(
        "NOUGEN_TRIGGERS_DB_NAME", "nougen_triggers.db")


def log_path() -> Path:
    override = os.environ.get("NOUGEN_TRIGGER_LOG")
    if override:
        return Path(override)
    return _vault_dir() / "trigger_injections.jsonl"


# ---------------------------------------------------------------------------
# Sidecar store
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shard_triggers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    shard_ref    TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    pattern      TEXT NOT NULL,
    weight       REAL NOT NULL DEFAULT 1.0,
    source       TEXT NOT NULL DEFAULT 'manual',
    note         TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE(shard_ref, trigger_type, pattern)
);
CREATE INDEX IF NOT EXISTS idx_trig_type ON shard_triggers(trigger_type);
CREATE INDEX IF NOT EXISTS idx_trig_ref  ON shard_triggers(shard_ref);
"""

_INIT_LOCK = threading.Lock()
_INITIALIZED: set = set()


def connect() -> sqlite3.Connection:
    """Open (creating on first use) the trigger sidecar DB."""
    path = db_path()
    key = str(path)
    with _INIT_LOCK:
        if key not in _INITIALIZED:
            path.parent.mkdir(parents=True, exist_ok=True)
            boot = sqlite3.connect(str(path))
            try:
                boot.executescript(_SCHEMA)
                boot.commit()
            finally:
                boot.close()
            _INITIALIZED.add(key)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TriggerError(ValueError):
    """Raised for a malformed trigger spec — caught at every author boundary."""


def validate(trigger_type: str, pattern: str) -> Tuple[str, str]:
    ttype = (trigger_type or "").strip().lower()
    if ttype not in TRIGGER_TYPES:
        raise TriggerError(
            f"unknown trigger type {trigger_type!r}; expected one of {', '.join(TRIGGER_TYPES)}")
    pat = (pattern or "").strip()
    if not pat:
        raise TriggerError("trigger pattern must be non-empty")
    if ttype == "temporal":
        _parse_temporal(pat)  # raises TriggerError when malformed
    if ttype == "path":
        pat = _norm_path(pat)
    return ttype, pat


def add_trigger(shard_ref: str, trigger_type: str, pattern: str,
                weight: Optional[float] = None, source: str = "manual",
                note: Optional[str] = None) -> int:
    """Attach a trigger to a shard. Idempotent on (ref, type, pattern)."""
    ttype, pat = validate(trigger_type, pattern)
    ref = (shard_ref or "").strip()
    if not ref:
        raise TriggerError("shard_ref must be non-empty")
    w = 1.0 if weight is None else float(weight)
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO shard_triggers "
            "(shard_ref, trigger_type, pattern, weight, source, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ref, ttype, pat, w, source, note, _now()))
        conn.commit()
        if cur.lastrowid:
            return int(cur.lastrowid)
        row = conn.execute(
            "SELECT id FROM shard_triggers WHERE shard_ref=? AND trigger_type=? AND pattern=?",
            (ref, ttype, pat)).fetchone()
        return int(row["id"]) if row else 0
    finally:
        conn.close()


def list_triggers(shard_ref: Optional[str] = None,
                  trigger_type: Optional[str] = None) -> List[dict]:
    conn = connect()
    try:
        sql = "SELECT * FROM shard_triggers"
        clauses, params = [], []
        if shard_ref:
            clauses.append("shard_ref = ?")
            params.append(shard_ref)
        if trigger_type:
            clauses.append("trigger_type = ?")
            params.append(trigger_type.lower())
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY shard_ref, trigger_type, pattern"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def remove_trigger(trigger_id: int) -> bool:
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM shard_triggers WHERE id = ?", (int(trigger_id),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count_triggers() -> int:
    conn = connect()
    try:
        return int(conn.execute("SELECT COUNT(*) AS n FROM shard_triggers").fetchone()["n"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Matching primitives
# ---------------------------------------------------------------------------

def _norm_path(p: str) -> str:
    return str(p).replace("\\", "/").strip()


_TEMPORAL_RE = re.compile(
    r"^age\s*(<=|>=|<|>)\s*(\d+(?:\.\d+)?)\s*([smhdw])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0, "w": 604800.0}


def _parse_temporal(pattern: str) -> Tuple[str, float]:
    """``age<=7d`` -> ("<=", 604800.0). Raises TriggerError on anything else."""
    m = _TEMPORAL_RE.match((pattern or "").strip())
    if not m:
        raise TriggerError(
            f"temporal pattern {pattern!r} must look like 'age<=7d' "
            "(ops <,<=,>,>= ; units s,m,h,d,w)")
    op, qty, unit = m.group(1), float(m.group(2)), m.group(3).lower()
    return op, qty * _UNIT_SECONDS[unit]


def _match_path(pattern: str, ctx: "TriggerContext") -> bool:
    pat = _norm_path(pattern)
    candidates = list(ctx.norm_paths)
    if ctx.cwd:
        candidates.append(_norm_path(ctx.cwd))
    if not path_case_sensitive():
        pat = pat.lower()
        candidates = [c.lower() for c in candidates]
    for cand in candidates:
        # Anchored, suffix-anchored, and basename forms: a trigger authored as
        # "src/nougen_shards/core.py" must fire on an absolute touched path.
        if (fnmatch.fnmatchcase(cand, pat)
                or fnmatch.fnmatchcase(cand, "*/" + pat.lstrip("/"))
                or fnmatch.fnmatchcase(cand.rsplit("/", 1)[-1], pat)):
            return True
    return False


def _match_symbol(pattern: str, ctx: "TriggerContext") -> bool:
    sym = pattern.strip()
    if sym in ctx.symbols:
        return True
    if not ctx.text:
        return False
    try:
        return re.search(r"\b" + re.escape(sym) + r"\b", ctx.text) is not None
    except re.error:  # pragma: no cover - re.escape makes this unreachable
        return False


def _match_semantic(pattern: str, ctx: "TriggerContext") -> bool:
    """AND over comma-separated terms, case-insensitive. Deterministic by
    construction — no embedding, no model call, no VRAM."""
    terms = [t.strip().lower() for t in pattern.split(",") if t.strip()]
    if not terms:
        return False
    haystack = ctx.semantic_haystack
    return all(t in haystack for t in terms)


def _match_event(pattern: str, ctx: "TriggerContext") -> bool:
    if not ctx.event:
        return False
    wanted = {e.strip().lower() for e in pattern.split(",") if e.strip()}
    return ctx.event.strip().lower() in wanted


def _match_temporal(pattern: str, shard_ts: Optional[str],
                    ctx: "TriggerContext") -> bool:
    if not shard_ts:
        return False
    op, span = _parse_temporal(pattern)
    when = _parse_ts(shard_ts)
    if when is None:
        return False
    age = (ctx.now - when).total_seconds()
    if op == "<":
        return age < span
    if op == "<=":
        return age <= span
    if op == ">":
        return age > span
    return age >= span


def _parse_ts(value: str) -> Optional[datetime]:
    raw = (value or "").strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Context + results
# ---------------------------------------------------------------------------

@dataclass
class TriggerContext:
    """Everything the harness knows about the situation. Cheap to build."""
    event: str = ""
    cwd: str = ""
    paths: Sequence[str] = field(default_factory=tuple)
    symbols: Sequence[str] = field(default_factory=tuple)
    text: str = ""
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        self.norm_paths = tuple(_norm_path(p) for p in self.paths if p)
        self.symbols = tuple(s.strip() for s in self.symbols if s and s.strip())
        blob = " ".join([self.text or "", " ".join(self.symbols),
                         " ".join(self.norm_paths)])
        self.semantic_haystack = blob.lower()
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=timezone.utc)


@dataclass
class Match:
    shard_ref: str
    score: float
    reasons: List[str]
    title: str = ""
    content: str = ""
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Shard resolution (read-only; never mutates the shard cluster)
# ---------------------------------------------------------------------------

def resolve_shard(shard_ref: str) -> Optional[dict]:
    """Read a shard body for a ref. Supported ref forms:

        hash:<file_hash>   preferred — stable, routes straight to its DB
        db:<index>:<id>    direct rowid within one cluster DB
        file:<name>        a markdown shard file in the vault directory
    """
    ref = (shard_ref or "").strip()
    try:
        if ref.startswith("file:"):
            fp = _vault_dir() / ref[len("file:"):]
            if not fp.is_file():
                return None
            body = fp.read_text(encoding="utf-8", errors="replace")
            stat = fp.stat()
            return {
                "title": fp.stem,
                "content": body,
                "timestamp": datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        from . import core  # local import: core imports us lazily in capture()
        if ref.startswith("db:"):
            _, idx, rid = ref.split(":", 2)
            return _fetch_row(core, int(idx), "id = ?", (int(rid),))
        if ref.startswith("hash:"):
            fhash = ref[len("hash:"):]
            # Routing is a pure function of the hash, so this is one SELECT.
            idx = core.get_routing_index(fhash)
            row = _fetch_row(core, int(idx), "file_hash = ?", (fhash,))
            if row is not None:
                return row
            # Stale routing index: bounded sweep of the cluster, still O(9).
            for i in range(1, int(getattr(core, "MAX_DB_COUNT", 9)) + 1):
                if i == idx:
                    continue
                row = _fetch_row(core, i, "file_hash = ?", (fhash,))
                if row is not None:
                    return row
            return None
    except Exception:
        return None
    return None


def _fetch_row(core, index: int, where: str, params: tuple) -> Optional[dict]:
    try:
        path = core.get_db_path(index)
        if not Path(path).exists():
            return None
        conn = core.get_connection(index)
    except Exception:
        return None
    try:
        row = conn.execute(
            f"SELECT timestamp, title, content FROM shards WHERE {where} LIMIT 1",
            params).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Deterministic evaluator
# ---------------------------------------------------------------------------

def evaluate(ctx: TriggerContext) -> List[Match]:
    """Return every shard whose triggers fire, ranked. No budget applied here.

    Ranking key is fully deterministic: (-score, -recency, shard_ref). Two runs
    over the same vault and the same context always produce the same order.
    """
    if not enabled():
        return []
    try:
        rows = list_triggers()
    except Exception:
        return []
    if not rows:
        return []

    by_ref: Dict[str, List[dict]] = {}
    for r in rows:
        by_ref.setdefault(r["shard_ref"], []).append(r)

    matches: List[Match] = []
    for ref, trigs in by_ref.items():
        cue_hits: List[Tuple[str, str, float]] = []
        has_cue_match = False
        cheap_hit = False
        # Pass 1 — non-temporal cues need no shard body, so a shard that cannot
        # possibly fire never costs a read of the cluster.
        for t in trigs:
            ttype, pat = t["trigger_type"], t["pattern"]
            if ttype == "path":
                ok = _match_path(pat, ctx)
            elif ttype == "symbol":
                ok = _match_symbol(pat, ctx)
            elif ttype == "semantic":
                ok = _match_semantic(pat, ctx)
            elif ttype == "event":
                ok = _match_event(pat, ctx)
            else:
                continue
            if ok:
                has_cue_match = True
                cheap_hit = True
                cue_hits.append((ttype, pat, float(t["weight"]) * type_weight(ttype)))

        gates = [t for t in trigs if t["trigger_type"] in GATE_TYPES]
        only_gates = not any(t["trigger_type"] in CUE_TYPES for t in trigs)
        if not cheap_hit and not only_gates:
            continue  # no cue fired and it declares cues -> silent, no read

        shard = resolve_shard(ref)
        if shard is None:
            continue

        # Pass 2 — temporal gate. Declared temporal triggers must hold.
        if gates:
            gate_ok = False
            for g in gates:
                try:
                    if _match_temporal(g["pattern"], shard.get("timestamp"), ctx):
                        gate_ok = True
                        cue_hits.append((
                            "temporal", g["pattern"],
                            float(g["weight"]) * type_weight("temporal")))
                        break
                except TriggerError:
                    continue
            if not gate_ok:
                continue  # gate suppresses the shard entirely
            if only_gates:
                has_cue_match = True

        if not has_cue_match:
            continue

        score = sum(w for _, _, w in cue_hits)
        if score < min_score():
            continue
        matches.append(Match(
            shard_ref=ref,
            score=round(score, 6),
            reasons=[f"{tt}:{pat}" for tt, pat, _ in cue_hits],
            title=shard.get("title", "") or "",
            content=shard.get("content", "") or "",
            timestamp=shard.get("timestamp", "") or "",
        ))

    matches.sort(key=lambda m: (-m.score, _sort_recency(m.timestamp), m.shard_ref))
    return matches


def _sort_recency(ts: str) -> float:
    dt = _parse_ts(ts)
    return -dt.timestamp() if dt else 0.0


# ---------------------------------------------------------------------------
# Budgeting + rendering
# ---------------------------------------------------------------------------

def _est_tokens(text: str) -> int:
    return int(math.ceil(len(text) / chars_per_token()))


def _render_block(m: Match, chars: int) -> str:
    body = " ".join((m.content or "").split())
    if chars > 0 and len(body) > chars:
        body = body[:chars].rstrip() + "…"
    elif chars <= 0:
        body = ""
    head = f"• {m.title or m.shard_ref}  [cue: {', '.join(m.reasons)}]"
    return head + ("\n  " + body if body else "")


@dataclass
class Selection:
    blocks: List[str] = field(default_factory=list)
    injected: List[Match] = field(default_factory=list)
    candidates: int = 0
    tokens: int = 0
    truncated: bool = False


def select(ctx: TriggerContext, matches: Optional[List[Match]] = None) -> Selection:
    """Apply the hard caps. Precision first: highest-scoring shards get the
    budget, and the block that straddles the boundary is truncated rather than
    silently blowing the cap."""
    if matches is None:
        matches = evaluate(ctx)
    sel = Selection(candidates=len(matches))
    cap_shards, cap_tokens = max_shards(), budget_tokens()
    if cap_shards <= 0 or cap_tokens <= 0:
        return sel
    snip = snippet_chars()
    for m in matches:
        if len(sel.injected) >= cap_shards:
            sel.truncated = True
            break
        remaining = cap_tokens - sel.tokens
        if remaining <= 0:
            sel.truncated = True
            break
        block = _render_block(m, snip)
        cost = _est_tokens(block)
        if cost > remaining:
            # Shrink this block's snippet to whatever budget is left.
            head_cost = _est_tokens(_render_block(m, 0))
            spare_chars = int((remaining - head_cost) * chars_per_token())
            if remaining < min_block_tokens() or spare_chars <= 0:
                sel.truncated = True
                break
            block = _render_block(m, spare_chars)
            cost = _est_tokens(block)
            if cost > remaining:
                sel.truncated = True
                break
            sel.truncated = True
        sel.blocks.append(block)
        sel.injected.append(m)
        sel.tokens += cost
    if len(sel.injected) < len(matches):
        sel.truncated = True
    return sel


HEADER = ("🎯 CUE-ANCHORED MEMORY (auto-delivered by the harness — you did not "
          "have to ask; each line names the cue that fired):")


def render(ctx: TriggerContext, selection: Optional[Selection] = None) -> str:
    """The injectable text. Empty string when nothing fired — callers append
    unconditionally, so an empty result must be a genuine no-op."""
    sel = selection if selection is not None else select(ctx)
    if not sel.blocks:
        return ""
    return HEADER + "\n" + "\n".join(sel.blocks)


def log_injection(ctx: TriggerContext, sel: Selection) -> None:
    """Append-only audit of what was injected and why. Never raises."""
    if not _env_flag("NOUGEN_TRIGGER_LOG_ENABLED", True):
        return
    try:
        record = {
            "ts": _now(),
            "event": ctx.event,
            "cwd": ctx.cwd,
            "paths": list(ctx.norm_paths)[:_env_int("NOUGEN_TRIGGER_LOG_MAX_PATHS", 10)],
            "candidates": sel.candidates,
            "injected": [{"ref": m.shard_ref, "score": m.score, "cues": m.reasons}
                         for m in sel.injected],
            "tokens": sel.tokens,
            "budget_tokens": budget_tokens(),
            "truncated": sel.truncated,
        }
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def deliver(event: str, cwd: str = "", paths: Sequence[str] = (),
            symbols: Sequence[str] = (), text: str = "") -> str:
    """One-call harness entry point: build context, evaluate, budget, log, render.

    Swallows everything — a memory lane must never wedge a hook.
    """
    try:
        if not enabled():
            return ""
        ctx = TriggerContext(event=event, cwd=cwd, paths=tuple(paths),
                             symbols=tuple(symbols), text=text)
        sel = select(ctx)
        if sel.injected:
            log_injection(ctx, sel)
        return render(ctx, sel)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Authoring: conservative auto-derivation
# ---------------------------------------------------------------------------

# A path-shaped token: at least one directory separator OR a known code
# extension, so prose like "see core" never becomes a path trigger.
_PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_./\\-]*[A-Za-z0-9_-]\.[A-Za-z0-9]{1,5}")
_DEF_RE = re.compile(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]{2,})")

_DEFAULT_EXTS = "py,ts,tsx,js,jsx,rs,go,java,rb,c,h,cpp,sql,sh,ps1,toml,yaml,yml,json"
_DEFAULT_SYMBOL_STOPLIST = (
    "self,None,True,False,return,import,object,string,result,value,config,"
    "handler,manager,wrapper,helper,Exception,__init__,main,test,setup")


def _autoderive_exts() -> set:
    return {e.strip().lower().lstrip(".") for e in
            os.environ.get("NOUGEN_TRIGGER_AUTODERIVE_EXTS", _DEFAULT_EXTS).split(",")
            if e.strip()}


def _symbol_stoplist() -> set:
    return {s.strip() for s in os.environ.get(
        "NOUGEN_TRIGGER_SYMBOL_STOPLIST", _DEFAULT_SYMBOL_STOPLIST).split(",") if s.strip()}


def derive_triggers(title: str, content: str,
                    repo_root: Optional[str] = None) -> List[Tuple[str, str]]:
    """Propose triggers for a shard. Deliberately stingy.

    Three guards, because a wrong trigger costs tokens in *every* future session
    while a missing one costs nothing:

    1. A path token must **resolve to a file that actually exists** under the
       repo root right now (probe, not guess — Rule 0.2).
    2. If a shard names more than ``NOUGEN_TRIGGER_AUTODERIVE_MAX`` distinct
       real files it is a survey/roundup shard, not a situational one, so it
       gets **nothing** — breadth is the signal that path cues would misfire.
    3. Symbols come only from ``def``/``class`` definition sites, must clear a
       minimum length, and must not be on the stoplist.

    Semantic triggers are never auto-derived. Judging "aboutness" without a
    model is guesswork, and guessed semantics is exactly the noise this avoids.
    """
    root = Path(repo_root or os.environ.get(
        "NOUGEN_REPO", str(Path(__file__).resolve().parents[2])))
    blob = f"{title or ''}\n{content or ''}"
    max_paths = _env_int("NOUGEN_TRIGGER_AUTODERIVE_MAX", 2)
    min_sym_len = _env_int("NOUGEN_TRIGGER_MIN_SYMBOL_LEN", 6)
    max_syms = _env_int("NOUGEN_TRIGGER_AUTODERIVE_MAX_SYMBOLS", 2)
    exts = _autoderive_exts()

    seen_paths: List[str] = []
    for tok in _PATH_TOKEN_RE.findall(blob):
        rel = _norm_path(tok).lstrip("./")
        if not rel or rel.rsplit(".", 1)[-1].lower() not in exts:
            continue
        if rel in seen_paths:
            continue
        try:
            if not (root / rel).is_file():
                continue  # guard 1: the file must really exist
        except OSError:
            continue
        seen_paths.append(rel)
        if len(seen_paths) > max_paths:
            break

    out: List[Tuple[str, str]] = []
    if seen_paths and len(seen_paths) <= max_paths:  # guard 2
        out.extend(("path", p) for p in seen_paths)

    stop = _symbol_stoplist()
    syms: List[str] = []
    for name in _DEF_RE.findall(blob):  # guard 3
        if len(name) >= min_sym_len and name not in stop and name not in syms:
            syms.append(name)
    if syms and len(syms) <= max_syms:
        out.extend(("symbol", s) for s in syms)
    return out


def auto_attach(shard_ref: str, title: str, content: str,
                repo_root: Optional[str] = None) -> List[Tuple[str, str]]:
    """Derive and persist. Returns what was actually attached; never raises."""
    attached: List[Tuple[str, str]] = []
    try:
        for ttype, pat in derive_triggers(title, content, repo_root):
            try:
                add_trigger(shard_ref, ttype, pat, source="auto")
                attached.append((ttype, pat))
            except Exception:
                continue
    except Exception:
        return attached
    return attached


def on_capture(file_hash: str, title: str, content: str) -> None:
    """Capture-time hook. No-op unless NOUGEN_TRIGGERS_AUTODERIVE is on."""
    if not enabled() or not autoderive_enabled():
        return
    auto_attach(f"hash:{file_hash}", title, content)
