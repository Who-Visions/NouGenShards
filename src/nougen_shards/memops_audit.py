"""
MemOps memory-health audit harness (READ-ONLY).

Applies the failure taxonomy from "MemOps: Benchmarking Lifecycle Memory
Operations in Long-Horizon Conversations" (arXiv 2607.12893) to the live shard
store, plus the write-filter idea from "Shared Selective Persistent Memory for
Agentic LLM Systems" (arXiv 2607.09493).

The paper's contribution is that final-answer scoring conflates distinct memory
failures. It names three that map onto a shard store:

  * stale value      -- a fact superseded by a later correction is still asserted
  * wrong binding    -- an operation/fact attached to the wrong target entity
  * missing evidence -- content that exists but is never surfaced (blind spot)

This module implements one detector per class, plus a duplicate/near-duplicate
detector for shards that should have merged (the write-side counterpart to the
selective-memory paper's "don't persist redundant traces").

HARD CONSTRAINTS
----------------
* READ-ONLY. Every SQLite connection is opened with ``mode=ro`` via URI, so a
  stray write raises rather than mutating the vault. Nothing here deletes,
  edits, re-embeds, or re-indexes a shard. It is an auditor, not a mutator.
* Rule 0.2: every environment-, path-, threshold-, count-, or model-shaped
  value resolves env -> config -> runtime probe, with a constant as a LOGGED
  fallback only. See ``AuditConfig`` for the full knob list.
* Model-assisted contradiction adjudication routes to the LOCAL ollama fleet
  only, with small context and batch sizes for an 8GB-VRAM host, and degrades
  to pure-lexical heuristics whenever ollama is unreachable.

Usage::

    python -m nougen_shards.memops_audit            # audit + write report
    python -m nougen_shards.memops_audit --json-only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule 0.2 env resolution helpers. Every fallback is logged at debug level so a
# run can always answer "where did this number come from?".
# ---------------------------------------------------------------------------


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        logger.debug("audit knob %s unset; using logged fallback %r", name, default)
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        logger.debug("audit knob %s unset; using logged fallback %d", name, default)
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        logger.warning("audit knob %s=%r is not an int; using fallback %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        logger.debug("audit knob %s unset; using logged fallback %s", name, default)
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        logger.warning("audit knob %s=%r is not a float; using fallback %s", name, raw, default)
        return default


def _env_bool(name: str, default: Optional[bool]) -> Optional[bool]:
    """Tri-state: True / False / None ('auto' -> probe at runtime)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        logger.debug("audit knob %s unset; using logged fallback %s", name, default)
        return default
    val = raw.strip().lower()
    if val in {"auto", "probe", ""}:
        return None
    return val in {"1", "true", "yes", "on"}


def _env_list(name: str, default: Sequence[str]) -> List[str]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        logger.debug("audit knob %s unset; using logged fallback %s", name, list(default))
        return list(default)
    return [part.strip() for part in re.split(r"[,;]", raw) if part.strip()]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Non-environment-shaped linguistic constants. These describe English, not the
# host, so they are module constants rather than env knobs.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those there here of for to in on at by with
from as is are was were be been being it its it's do does did done have has had not no yes
we you they he she i me my our your their them us can could should would will shall may might
must about into over under after before while during when where which who whom whose what how
run runs ran using use used via per new old also more most less least very just only same
""".split())

_STATUS_NEGATIVE = frozenset({
    "broken", "failing", "failed", "fails", "blocked", "blocker", "down", "outage",
    "unreachable", "missing", "crashed", "crashing", "red", "regression", "stale",
    "unresolved", "dead", "disabled",
})
_STATUS_POSITIVE = frozenset({
    "fixed", "resolved", "working", "works", "passing", "passed", "restored", "green",
    "healthy", "reachable", "unblocked", "live", "operational", "enabled", "shipped",
})

# Markers that say "THIS shard is the retired side of an update". Deliberately
# narrow: 'rev.1', 'revised', 'update' are ambiguous (a rev.1 shard is not
# self-labelled as obsolete), and treating them as markers silently suppressed
# the exact stale-value class this harness exists to catch.
_SUPERSESSION_MARKERS = frozenset({
    "superseded", "obsolete", "deprecated", "outdated", "retracted", "invalidated",
    "replaced", "archived",
})

_NUMERIC_RE = re.compile(r"(?<![\w.])(\$?-?\d[\d,]*(?:\.\d+)?\s*%?)(?![\w])")
_ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_COMPACT_DATE_RE = re.compile(r"\b(20\d{2})(\d{2})(\d{2})\b")

# Named identifier patterns for the wrong-binding detector. Selectable by name
# through NOUGEN_AUDIT_BINDING_KINDS so a noisy class can be switched off
# without editing code.
_BINDING_PATTERNS: Dict[str, re.Pattern] = {
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "port": re.compile(r"(?<![\w.]):(\d{4,5})\b"),
    "winpath": re.compile(r"\b[A-Za-z]:[\\/][^\s'\"|,;)+]{4,}"),
    "sha": re.compile(r"\b[0-9a-f]{12,64}\b"),
    "docnum": re.compile(r"\b(?:doc(?:ument)?\s*(?:no|number|#)?\s*[:#]?\s*)(\d{5,})\b", re.I),
}

# Entity candidates for binding: capitalised or dotted names, model ids, etc.
_ENTITY_RE = re.compile(r"\b([A-Z][A-Za-z0-9]{2,}(?:[-_.][A-Za-z0-9]+)*)\b")


@dataclass
class AuditConfig:
    """Every environment-shaped value the harness needs, resolved once."""

    # --- stores -----------------------------------------------------------
    vault_dir: Path
    secondary_dirs: List[Tuple[str, Path]]
    primary_label: str
    max_db_count: int
    db_glob: str

    # --- sampling ---------------------------------------------------------
    sample_size: int              # max shards pulled per store for text detectors
    arxiv_sample: int             # hard cap on the arXiv backlog (do not mass-process)
    arxiv_prefixes: List[str]
    max_pairs: int                # comparison ceiling for O(n^2)-ish detectors
    max_content_chars: int        # per-shard body clamp; transcript rows are unbounded

    # --- stale value ------------------------------------------------------
    subject_overlap: float        # Jaccard on subject tokens to call two claims comparable
    title_overlap: float          # Jaccard on shard titles: are the two shards even on-topic?
    rare_token_df: int            # a token is 'rare' (=discriminating) below this doc freq
    numeric_context_tokens: int   # tokens of left context that label a number
    min_subject_tokens: int
    numeric_label_stoplist: List[str]   # structural keys that enumerate, not assert

    # --- wrong binding ----------------------------------------------------
    binding_kinds: List[str]
    date_tolerance_days: int
    date_exempt_types: List[str]  # event types that legitimately carry foreign dates

    # --- retrieval blind spots -------------------------------------------
    probe_sample: int
    probe_top_k: int
    probe_query_tokens: int
    probe_enabled: bool

    # --- duplicates -------------------------------------------------------
    shingle_size: int
    near_dup_threshold: float
    dup_block_tokens: int
    min_dup_chars: int

    # --- local model lane -------------------------------------------------
    llm_enabled: Optional[bool]   # None => probe
    ollama_host: str
    llm_model_prefs: List[str]
    llm_model: str
    llm_batch: int                # pairs per request; small for 8GB VRAM
    llm_num_ctx: int
    llm_max_pairs: int
    llm_snippet_chars: int
    llm_timeout: int

    # --- output -----------------------------------------------------------
    out_dir: Path
    snippet_chars: int

    resolved_from: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def resolve(cls, vault_dir: Optional[str] = None) -> "AuditConfig":
        """Resolve env -> config -> probe. Nothing here is a bare literal."""
        provenance: Dict[str, str] = {}

        # Vault dir: explicit arg > NOUGEN_VAULT_DIR > core's own resolution
        # (which itself probes ./.vault then ~/.nougen/shards). Probe last.
        if vault_dir:
            vd = Path(vault_dir)
            provenance["vault_dir"] = "argument"
        elif os.environ.get("NOUGEN_VAULT_DIR", "").strip():
            vd = Path(os.environ["NOUGEN_VAULT_DIR"].strip())
            provenance["vault_dir"] = "env:NOUGEN_VAULT_DIR"
        else:
            vd = Path(_probe_core_global_dir())
            provenance["vault_dir"] = "probe:core.GLOBAL_DIR"

        secondaries = _resolve_secondary_stores(vd)
        provenance["secondary_dirs"] = (
            "env:NOUGEN_SECONDARY_VAULT_DIRS" if os.environ.get("NOUGEN_SECONDARY_VAULT_DIRS")
            else "fallback:none"
        )

        primary_label = _env_str("NOUGEN_PRIMARY_STORE_LABEL", _store_label(vd))
        max_db_count = _env_int("NOUGEN_AUDIT_MAX_DB_COUNT", _probe_core_max_db_count())
        provenance["max_db_count"] = "env:NOUGEN_AUDIT_MAX_DB_COUNT|probe:core.MAX_DB_COUNT"

        cfg = cls(
            vault_dir=vd,
            secondary_dirs=secondaries,
            primary_label=primary_label,
            max_db_count=max_db_count,
            db_glob=_env_str("NOUGEN_AUDIT_DB_GLOB", "nougen_shards_*.db"),
            sample_size=_env_int("NOUGEN_AUDIT_SAMPLE_SIZE", 4000),
            arxiv_sample=_env_int("NOUGEN_AUDIT_ARXIV_SAMPLE", 150),
            arxiv_prefixes=_env_list("NOUGEN_AUDIT_ARXIV_PREFIXES", ("arxiv_", "arxiv ")),
            max_pairs=_env_int("NOUGEN_AUDIT_MAX_PAIRS", 200000),
            max_content_chars=_env_int("NOUGEN_AUDIT_MAX_CONTENT_CHARS", 20000),
            subject_overlap=_env_float("NOUGEN_AUDIT_SUBJECT_OVERLAP", 0.60),
            title_overlap=_env_float("NOUGEN_AUDIT_TITLE_OVERLAP", 0.40),
            rare_token_df=_env_int("NOUGEN_AUDIT_RARE_TOKEN_DF", 40),
            numeric_context_tokens=_env_int("NOUGEN_AUDIT_NUMERIC_CONTEXT_TOKENS", 5),
            min_subject_tokens=_env_int("NOUGEN_AUDIT_MIN_SUBJECT_TOKENS", 2),
            numeric_label_stoplist=_env_list(
                "NOUGEN_AUDIT_NUMERIC_LABEL_STOPLIST",
                ("source_row", "row", "rows", "index", "idx", "line", "lineno", "offset",
                 "port", "pid", "version", "rev", "step", "page", "seed", "chunk",
                 "byte", "bytes", "hash", "sha", "uuid", "release", "releases", "docs")),
            binding_kinds=_env_list("NOUGEN_AUDIT_BINDING_KINDS",
                                    ("ipv4", "port", "winpath", "docnum")),
            date_tolerance_days=_env_int("NOUGEN_AUDIT_DATE_TOLERANCE_DAYS", 3),
            date_exempt_types=_env_list("NOUGEN_AUDIT_DATE_EXEMPT_TYPES",
                                        ("research", "arxiv", "paper", "ingest", "import")),
            probe_sample=_env_int("NOUGEN_AUDIT_PROBE_SAMPLE", 40),
            probe_top_k=_env_int("NOUGEN_AUDIT_PROBE_TOP_K", 10),
            probe_query_tokens=_env_int("NOUGEN_AUDIT_PROBE_QUERY_TOKENS", 6),
            probe_enabled=bool(_env_bool("NOUGEN_AUDIT_PROBE_ENABLED", True)),
            shingle_size=_env_int("NOUGEN_AUDIT_SHINGLE_SIZE", 5),
            near_dup_threshold=_env_float("NOUGEN_AUDIT_NEAR_DUP_THRESHOLD", 0.85),
            dup_block_tokens=_env_int("NOUGEN_AUDIT_DUP_BLOCK_TOKENS", 4),
            min_dup_chars=_env_int("NOUGEN_AUDIT_MIN_DUP_CHARS", 80),
            llm_enabled=_env_bool("NOUGEN_AUDIT_LLM_ENABLED", None),
            ollama_host=_normalize_ollama_host(
                _env_str("NOUGEN_AUDIT_OLLAMA_HOST",
                         _env_str("OLLAMA_HOST", "http://127.0.0.1:11434"))),
            llm_model_prefs=_env_list("NOUGEN_AUDIT_LLM_MODEL_PREFS",
                                      ("gemma4:12b", "gemma4:31b-cloud", "gemma")),
            llm_model=_env_str("NOUGEN_AUDIT_LLM_MODEL", ""),
            llm_batch=_env_int("NOUGEN_AUDIT_LLM_BATCH", 4),
            llm_num_ctx=_env_int("NOUGEN_AUDIT_LLM_NUM_CTX", 2048),
            llm_max_pairs=_env_int("NOUGEN_AUDIT_LLM_MAX_PAIRS", 60),
            llm_snippet_chars=_env_int("NOUGEN_AUDIT_LLM_SNIPPET_CHARS", 400),
            llm_timeout=_env_int("NOUGEN_AUDIT_LLM_TIMEOUT", 90),
            out_dir=Path(_env_str("NOUGEN_AUDIT_OUT_DIR", str(Path.cwd() / "audit-runs"))),
            snippet_chars=_env_int("NOUGEN_AUDIT_SNIPPET_CHARS", 220),
        )
        cfg.resolved_from = provenance
        return cfg

    def knobs(self) -> Dict[str, object]:
        d = asdict(self)
        d["vault_dir"] = str(self.vault_dir)
        d["out_dir"] = str(self.out_dir)
        d["secondary_dirs"] = [[label, str(p)] for label, p in self.secondary_dirs]
        return d


def _normalize_ollama_host(raw: str) -> str:
    """Make an inherited OLLAMA_HOST dialable (Rule 0.2: never trust inherited env).

    Measured on this host: OLLAMA_HOST=0.0.0.0 -- a *bind* address with no scheme
    and no port. urllib rejects it outright ("unknown url type"), which silently
    looked like "ollama is down". Normalise instead of assuming.
    """
    host = (raw or "").strip()
    default_port = str(_env_int("NOUGEN_AUDIT_OLLAMA_PORT", 11434))
    if not host:
        return f"http://127.0.0.1:{default_port}"
    if "://" not in host:
        host = "http://" + host
    scheme, _, rest = host.partition("://")
    hostpart, sep, port = rest.partition(":")
    # 0.0.0.0 / :: are listen addresses; you cannot connect to them portably.
    if hostpart in ("0.0.0.0", "::", "[::]", ""):
        hostpart = "127.0.0.1"
    if not sep or not port.strip("/"):
        port = default_port
    normalized = f"{scheme}://{hostpart}:{port.rstrip('/')}"
    if normalized != (raw or "").strip():
        logger.info("normalized ollama host %r -> %r", raw, normalized)
    return normalized


def _store_label(path: Path) -> str:
    p = Path(path)
    if p.name.startswith(".") and p.parent.name:
        return p.parent.name
    return p.name or str(p)


def _probe_core_global_dir() -> str:
    """Probe the live core module rather than assuming a path (Rule 0.2)."""
    try:
        from . import core  # local import: unit tests must not need the live vault
        return str(core.GLOBAL_DIR)
    except Exception as exc:  # pragma: no cover - defensive
        fallback = str(Path.home() / ".nougen" / "shards")
        logger.warning("core.GLOBAL_DIR probe failed (%s); logged fallback %s", exc, fallback)
        return fallback


def _probe_core_max_db_count() -> int:
    try:
        from . import core
        return int(core.MAX_DB_COUNT)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("core.MAX_DB_COUNT probe failed (%s); logged fallback 9", exc)
        return 9


def _resolve_secondary_stores(primary: Path) -> List[Tuple[str, Path]]:
    """Reuse federation's parser when importable; else parse the same env var."""
    raw = os.environ.get("NOUGEN_SECONDARY_VAULT_DIRS", "").strip()
    if not raw:
        return []
    try:
        from . import federation
        stores = federation.secondary_stores()
        if stores:
            return [(label, Path(p)) for label, p in stores]
    except Exception as exc:
        logger.warning("federation.secondary_stores() unavailable (%s); parsing env directly", exc)

    out: List[Tuple[str, Path]] = []
    try:
        primary_key = str(primary.resolve()).lower()
    except OSError:
        primary_key = str(primary).lower()
    for entry in re.split(r"[;\n]", raw):
        entry = entry.strip().strip('"').strip("'")
        if not entry:
            continue
        label = None
        head, sep, tail = entry.partition("=")
        if sep and tail.strip() and not any(c in head for c in "\\/:"):
            label, entry = head.strip(), tail.strip()
        path = Path(os.path.expandvars(os.path.expanduser(entry)))
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key == primary_key or not path.is_dir():
            continue
        out.append((label or _store_label(path), path))
    return out


# ---------------------------------------------------------------------------
# Read-only shard access
# ---------------------------------------------------------------------------


@dataclass
class Shard:
    store: str
    db: str
    id: int
    timestamp: str
    event_type: str
    title: str
    content: str
    tags: str
    utility_score: float
    file_hash: str
    domain_key: str

    @property
    def ref(self) -> str:
        return f"{self.store}:{self.db}#{self.id}"

    @property
    def date(self) -> Optional[datetime]:
        return _parse_ts(self.timestamp)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (
        lambda t: datetime.fromisoformat(t),
        lambda t: datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S"),
        lambda t: datetime.strptime(t[:10], "%Y-%m-%d"),
    ):
        try:
            dt = parser(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Open a shard DB in true read-only mode. Writes raise, they do not apply."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=_env_float("NOUGEN_DB_TIMEOUT", 10.0))
    conn.row_factory = sqlite3.Row
    return conn


def discover_dbs(vault_dir: Path, cfg: AuditConfig) -> List[Path]:
    """Probe the filesystem for shard DBs rather than assuming 1..N exist."""
    if not vault_dir.is_dir():
        logger.warning("vault dir not found: %s", vault_dir)
        return []
    found = sorted(p for p in vault_dir.glob(cfg.db_glob) if p.is_file())
    if not found:
        logger.warning("no shard DBs matched %s in %s", cfg.db_glob, vault_dir)
    return found


def _is_arxiv(title: str, tags: str, cfg: AuditConfig) -> bool:
    hay = f"{title} {tags}".lower()
    return any(hay.startswith(p) or p in hay for p in (x.lower() for x in cfg.arxiv_prefixes))


def load_shards(store_label: str, vault_dir: Path, cfg: AuditConfig) -> List[Shard]:
    """Load a bounded, deterministic sample. arXiv backlog is capped separately."""
    shards: List[Shard] = []
    arxiv_kept = 0
    for db_path in discover_dbs(vault_dir, cfg):
        try:
            conn = open_readonly(db_path)
        except sqlite3.Error as exc:
            logger.warning("cannot open %s read-only: %s", db_path, exc)
            continue
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(shards)")}
            if not cols:
                continue
            select = ", ".join(
                c if c in cols else f"'' AS {c}"
                for c in ("id", "timestamp", "event_type", "title", "content",
                          "tags", "utility_score", "file_hash", "domain_key")
            )
            # Deterministic order (id) so two runs sample identically.
            rows = conn.execute(f"SELECT {select} FROM shards ORDER BY id")
            for row in rows:
                title = str(row["title"] or "")
                tags = str(row["tags"] or "")
                if _is_arxiv(title, tags, cfg):
                    if arxiv_kept >= cfg.arxiv_sample:
                        continue
                    arxiv_kept += 1
                shards.append(Shard(
                    store=store_label,
                    db=db_path.name,
                    id=int(row["id"]),
                    timestamp=str(row["timestamp"] or ""),
                    event_type=str(row["event_type"] or ""),
                    title=title,
                    # Clamp: a federated transcript row can be megabytes, and an
                    # unbounded corpus load is what kills the auditor before it
                    # reports anything. The clamp is a knob, not a constant.
                    content=str(row["content"] or "")[: cfg.max_content_chars],
                    tags=tags,
                    utility_score=float(row["utility_score"] or 0.0),
                    file_hash=str(row["file_hash"] or ""),
                    domain_key=str(row["domain_key"] or ""),
                ))
                if len(shards) >= cfg.sample_size:
                    logger.info("sample cap %d reached for store %s", cfg.sample_size, store_label)
                    return shards
        except sqlite3.Error as exc:
            logger.warning("read failed on %s: %s", db_path, exc)
        finally:
            conn.close()
    return shards


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    failure_class: str
    subclass: str
    severity: str
    summary: str
    refs: List[str]
    evidence: List[str]
    confidence: str = "lexical"   # lexical | llm-confirmed | llm-rejected
    detail: Dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------


def tokenize(text: str) -> List[str]:
    # The inner class allows '.', '_' and '-' so that ids like 'rev.1',
    # 'gemma4:12b' fragments and 'nougen_shards_1' survive intact -- but a
    # trailing separator is sentence punctuation, not part of the token
    # ('broken.' must match the status vocabulary as 'broken').
    raw = re.findall(r"[a-z0-9][a-z0-9_.\-]*", (text or "").lower())
    return [t for t in (tok.strip("._-") for tok in raw) if t]


def content_tokens(text: str) -> List[str]:
    return [t for t in tokenize(text) if t not in _STOPWORDS and len(t) > 2]


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def shingles(text: str, size: int) -> set:
    toks = tokenize(text)
    if len(toks) < size:
        return {tuple(toks)} if toks else set()
    return {tuple(toks[i:i + size]) for i in range(len(toks) - size + 1)}


def _norm_number(raw: str) -> str:
    return raw.replace(",", "").replace(" ", "").lstrip("$").rstrip("%").rstrip(".")


def _snippet(text: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", (text or "")).strip()
    return flat[:limit] + ("..." if len(flat) > limit else "")


# ---------------------------------------------------------------------------
# Detector 1 -- STALE VALUE
# ---------------------------------------------------------------------------


@dataclass
class Assertion:
    shard: Shard
    kind: str            # numeric | status
    subject: Tuple[str, ...]
    value: str
    line: str


def _looks_structural(line: str, start: int, end: int) -> bool:
    """True when a number is part of a path, version, or identifier rather than a claim.

    Measured on the live vault: without this gate the numeric detector reports
    'docs\\releases\\1.8.0 -> 2.0.0-rc.1' as a contradicted fact. Those are
    filenames, not assertions.
    """
    before = line[start - 1:start] if start else ""
    after = line[end:end + 1]
    if before in ("\\", "/", "_", "-") or after in ("\\", "/", "_"):
        return True
    if before == "." and start >= 2 and line[start - 2].isdigit():
        return True   # middle of a dotted version like 1.8.0
    if after == "." and end + 1 < len(line) and line[end + 1].isdigit():
        return True   # start of a dotted version
    if before == ":" and after == ":":
        return True
    return False


def extract_assertions(shard: Shard, cfg: AuditConfig) -> List[Assertion]:
    """Pull (subject, value) claims out of a shard's title+content."""
    out: List[Assertion] = []
    body = f"{shard.title}\n{shard.content}"
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        toks = tokenize(line)
        if not toks:
            continue

        # -- numeric claims: label = the content tokens immediately left of a number
        stoplist = {t.lower() for t in cfg.numeric_label_stoplist}
        for match in _NUMERIC_RE.finditer(line):
            if _looks_structural(line, match.start(), match.end()):
                continue
            left = line[:match.start()]
            label = [t for t in content_tokens(left)][-cfg.numeric_context_tokens:]
            label = [t for t in label if not t.replace(".", "").isdigit()]
            if len(label) < cfg.min_subject_tokens:
                continue
            # Structural keys enumerate records; they do not assert a fact whose
            # value can go stale ('source_row 338' vs 'source_row 394').
            if stoplist & set(label):
                continue
            out.append(Assertion(shard, "numeric", tuple(sorted(set(label))),
                                 _norm_number(match.group(1)), line))

        # -- status claims: polarity of a health statement about a subject
        low = set(toks)
        neg, pos = low & _STATUS_NEGATIVE, low & _STATUS_POSITIVE
        if neg and not pos:
            polarity = "negative"
        elif pos and not neg:
            polarity = "positive"
        else:
            continue
        subject = [t for t in content_tokens(line)
                   if t not in _STATUS_NEGATIVE and t not in _STATUS_POSITIVE]
        if len(subject) < cfg.min_subject_tokens:
            continue
        out.append(Assertion(shard, "status", tuple(sorted(set(subject))), polarity, line))
    return out


def _document_frequency(assertions: Sequence[Assertion]) -> Dict[str, int]:
    df: Dict[str, int] = defaultdict(int)
    for a in assertions:
        for tok in set(a.subject):
            df[tok] += 1
    return df


def detect_stale_values(shards: Sequence[Shard], cfg: AuditConfig) -> List[Finding]:
    """A claim asserted at t0 that a later shard contradicts, with no supersession link."""
    assertions: List[Assertion] = []
    for s in shards:
        assertions.extend(extract_assertions(s, cfg))
    if not assertions:
        return []

    df = _document_frequency(assertions)
    # Inverted index on RARE subject tokens only: a token seen everywhere carries
    # no binding power and would make the candidate set quadratic in the corpus.
    index: Dict[str, List[int]] = defaultdict(list)
    for i, a in enumerate(assertions):
        rare = [t for t in a.subject if df[t] <= cfg.rare_token_df]
        for tok in rare:
            index[tok].append(i)

    findings: List[Finding] = []
    seen_pairs = set()
    compared = 0
    for _tok, bucket in index.items():
        if len(bucket) < 2:
            continue
        for pos_i, i in enumerate(bucket):
            for j in bucket[pos_i + 1:]:
                if compared >= cfg.max_pairs:
                    logger.info("stale-value comparison cap %d reached", cfg.max_pairs)
                    return findings
                compared += 1
                key = (i, j) if i < j else (j, i)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                a, b = assertions[i], assertions[j]
                if a.kind != b.kind or a.shard.ref == b.shard.ref:
                    continue
                if a.value == b.value:
                    continue
                if jaccard(a.subject, b.subject) < cfg.subject_overlap:
                    continue
                # Topical gate: two shards must be about the same thing before a
                # shared numeric label counts as the same fact. Without it, every
                # document in the corpus that mentions "estimated time 2" collides
                # with every other one.
                if jaccard(content_tokens(a.shard.title),
                           content_tokens(b.shard.title)) < cfg.title_overlap:
                    continue
                da, db_ = a.shard.date, b.shard.date
                if not da or not db_ or da == db_:
                    continue
                older, newer = (a, b) if da < db_ else (b, a)
                # An explicit supersession marker on the newer shard means the
                # lifecycle 'update' operation was recorded -- that is correct
                # behaviour, not a stale-value failure. It is only stale when the
                # older assertion still stands unmarked.
                marked = bool(set(tokenize(older.shard.title + " " + older.shard.tags))
                              & _SUPERSESSION_MARKERS)
                if marked:
                    continue
                findings.append(Finding(
                    failure_class="stale_value",
                    subclass=older.kind,
                    severity="high" if older.kind == "numeric" else "medium",
                    summary=(f"'{' '.join(older.subject)}' asserted as {older.value!r} "
                             f"then as {newer.value!r} later; older shard carries no "
                             f"supersession marker"),
                    refs=[older.shard.ref, newer.shard.ref],
                    evidence=[_snippet(older.line, cfg.snippet_chars),
                              _snippet(newer.line, cfg.snippet_chars)],
                    detail={
                        "subject": list(older.subject),
                        "older_value": older.value,
                        "newer_value": newer.value,
                        "older_ts": older.shard.timestamp,
                        "newer_ts": newer.shard.timestamp,
                        "older_title": older.shard.title,
                        "newer_title": newer.shard.title,
                    },
                ))
    return findings


# ---------------------------------------------------------------------------
# Detector 2 -- WRONG BINDING
# ---------------------------------------------------------------------------


def _entities_in(line: str) -> List[str]:
    return [e for e in _ENTITY_RE.findall(line) if e.lower() not in _STOPWORDS]


def detect_wrong_bindings(shards: Sequence[Shard], cfg: AuditConfig) -> List[Finding]:
    """Three sub-classes: identifier->entity conflicts, date drift, cross-store attribution."""
    findings: List[Finding] = []

    # -- 2a. the same distinctive identifier bound to different owner entities
    patterns = {k: v for k, v in _BINDING_PATTERNS.items() if k in cfg.binding_kinds}
    if not patterns:
        logger.info("no binding patterns enabled (NOUGEN_AUDIT_BINDING_KINDS)")
    bindings: Dict[Tuple[str, str], Dict[str, List[Tuple[Shard, str]]]] = defaultdict(
        lambda: defaultdict(list))
    for s in shards:
        for raw_line in f"{s.title}\n{s.content}".splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for kind, pat in patterns.items():
                for m in pat.finditer(line):
                    ident = m.group(0)
                    owners = _entities_in(line[:m.start()]) or _entities_in(line)
                    if not owners:
                        continue
                    bindings[(kind, ident)][owners[-1]].append((s, line))

    for (kind, ident), owners in bindings.items():
        if len(owners) < 2:
            continue
        # Require each competing owner to be attested by a distinct shard;
        # one shard listing two names near an id is prose, not a binding error.
        distinct = {o: {sh.ref for sh, _ in hits} for o, hits in owners.items()}
        if len({r for refs in distinct.values() for r in refs}) < 2:
            continue
        refs, evidence = [], []
        for owner, hits in sorted(owners.items()):
            sh, line = hits[0]
            refs.append(sh.ref)
            evidence.append(f"{owner} <- {_snippet(line, cfg.snippet_chars)}")
        findings.append(Finding(
            failure_class="wrong_binding",
            subclass=f"identifier_{kind}",
            severity="medium",
            summary=f"{kind} identifier {ident!r} bound to {len(owners)} different entities: "
                    f"{', '.join(sorted(owners))}",
            refs=sorted(set(refs)),
            evidence=evidence[: max(2, cfg.min_subject_tokens)],
            detail={"identifier": ident, "kind": kind, "owners": sorted(owners)},
        ))

    # -- 2b. date binding drift: the fact's own datestamp disagrees with the row timestamp
    exempt = {t.lower() for t in cfg.date_exempt_types}
    for s in shards:
        if any(e in s.event_type.lower() or e in s.tags.lower() for e in exempt):
            continue
        if _is_arxiv(s.title, s.tags, cfg):
            continue
        row_dt = s.date
        if not row_dt:
            continue
        claimed: List[datetime] = []
        hay = f"{s.title}\n{s.content[:cfg.snippet_chars * 8]}"
        for y, mo, d in _ISO_DATE_RE.findall(hay):
            try:
                claimed.append(datetime(int(y), int(mo), int(d), tzinfo=timezone.utc))
            except ValueError:
                continue
        for y, mo, d in _COMPACT_DATE_RE.findall(s.title):
            try:
                claimed.append(datetime(int(y), int(mo), int(d), tzinfo=timezone.utc))
            except ValueError:
                continue
        if not claimed:
            continue
        # Only a conflict when EVERY claimed date is far from the row timestamp.
        deltas = [abs((c - row_dt).days) for c in claimed]
        if min(deltas) <= cfg.date_tolerance_days:
            continue
        nearest = claimed[deltas.index(min(deltas))]
        findings.append(Finding(
            failure_class="wrong_binding",
            subclass="date_drift",
            severity="low",
            summary=(f"shard timestamped {row_dt.date()} but its own content dates to "
                     f"{nearest.date()} ({min(deltas)}d apart)"),
            refs=[s.ref],
            evidence=[_snippet(s.title, cfg.snippet_chars)],
            detail={"row_ts": s.timestamp, "claimed_dates": [c.date().isoformat() for c in claimed],
                    "min_delta_days": min(deltas)},
        ))

    # -- 2c. cross-store attribution: same normalised title, different domain/type
    by_title: Dict[str, List[Shard]] = defaultdict(list)
    for s in shards:
        key = " ".join(content_tokens(s.title))
        if key:
            by_title[key].append(s)
    for key, group in by_title.items():
        stores = {s.store for s in group}
        if len(stores) < 2:
            continue
        domains = {s.domain_key for s in group if s.domain_key}
        if len(domains) < 2:
            continue
        findings.append(Finding(
            failure_class="wrong_binding",
            subclass="cross_store_attribution",
            severity="medium",
            summary=(f"'{_snippet(group[0].title, cfg.snippet_chars)}' appears in stores "
                     f"{sorted(stores)} under conflicting domains {sorted(domains)}"),
            refs=[s.ref for s in group[:4]],
            evidence=[f"{s.store}/{s.domain_key}: {s.timestamp}" for s in group[:4]],
            detail={"stores": sorted(stores), "domains": sorted(domains), "title_key": key},
        ))
    return findings


# ---------------------------------------------------------------------------
# Detector 3 -- RETRIEVAL BLIND SPOTS
# ---------------------------------------------------------------------------


def _default_retriever(cfg: AuditConfig):
    """Probe for the live retrieval path; None means the probe is unavailable."""
    try:
        from . import core, federation
        # Auditor contract: the probe exercises the production recall path but
        # must not migrate, re-index, or rewrite a store's journal mode while
        # doing so. core honours this flag in get_connection()/init_db().
        core.VAULT_READONLY = True
        def _run(query: str, limit: int):
            return federation.federated_retrieve(query, limit=limit)
        return _run
    except Exception as exc:
        logger.warning("federated_retrieve unavailable (%s); trying core.retrieve", exc)
    try:
        from . import core
        core.VAULT_READONLY = True
        def _run(query: str, limit: int):
            return core.retrieve(query, limit=limit)
        return _run
    except Exception as exc:
        logger.warning("core.retrieve unavailable (%s); retrieval probe disabled", exc)
        return None


def _probe_query(shard: Shard, cfg: AuditConfig) -> str:
    """Known-answer query: the shard's own most distinctive title tokens."""
    toks = content_tokens(shard.title) or content_tokens(shard.content)
    return " ".join(toks[: cfg.probe_query_tokens])


def detect_retrieval_blind_spots(shards: Sequence[Shard], cfg: AuditConfig,
                                 retriever=None) -> List[Finding]:
    """Known-answer probes: content that exists in the store but recall will not return."""
    if not cfg.probe_enabled:
        return []
    retriever = retriever or _default_retriever(cfg)
    if retriever is None:
        return [Finding(
            failure_class="retrieval_blind_spot", subclass="probe_unavailable",
            severity="info", summary="retrieval probe skipped: no retriever importable",
            refs=[], evidence=[], confidence="lexical")]

    # Deterministic stratified sample: spread across the id range of each store.
    by_store: Dict[str, List[Shard]] = defaultdict(list)
    for s in shards:
        by_store[s.store].append(s)
    sample: List[Shard] = []
    per_store = max(1, cfg.probe_sample // max(1, len(by_store)))
    for _store, group in sorted(by_store.items()):
        if not group:
            continue
        step = max(1, len(group) // per_store)
        sample.extend(group[::step][:per_store])

    findings: List[Finding] = []
    for s in sample:
        query = _probe_query(s, cfg)
        if not query:
            continue
        try:
            hits = retriever(query, cfg.probe_top_k) or []
        except Exception as exc:
            findings.append(Finding(
                failure_class="retrieval_blind_spot", subclass="probe_error",
                severity="info", summary=f"probe raised for {s.ref}: {exc}",
                refs=[s.ref], evidence=[query]))
            continue
        found = False
        for h in hits:
            hid = h.get("id") if isinstance(h, dict) else getattr(h, "id", None)
            htitle = (h.get("title") if isinstance(h, dict) else getattr(h, "title", "")) or ""
            if hid == s.id or (htitle and htitle.strip() == s.title.strip()):
                found = True
                break
        if not found:
            findings.append(Finding(
                failure_class="retrieval_blind_spot",
                subclass="unretrievable_shard",
                severity="high",
                summary=(f"shard is in the store but its own title query does not return it "
                         f"in top-{cfg.probe_top_k}"),
                refs=[s.ref],
                evidence=[f"query: {query}", f"title: {_snippet(s.title, cfg.snippet_chars)}",
                          f"returned: {len(hits)} hits"],
                detail={"query": query, "top_k": cfg.probe_top_k, "store": s.store,
                        "hit_count": len(hits)},
            ))
    return findings


def detect_unindexed_files(shards: Sequence[Shard], cfg: AuditConfig,
                           file_limit: Optional[int] = None) -> List[Finding]:
    """Disk-side blind spot: vault .md files with no shard bearing that title."""
    limit = file_limit if file_limit is not None else cfg.probe_sample
    if not cfg.vault_dir.is_dir():
        return []
    known_titles = {" ".join(content_tokens(s.title)) for s in shards}
    known_stems = {Path(s.title).stem.lower() for s in shards}
    findings: List[Finding] = []
    checked = 0
    for path in sorted(cfg.vault_dir.glob("*.md")):
        if checked >= limit:
            break
        if _is_arxiv(path.name, "", cfg):
            continue  # backlog is sampled, not swept
        checked += 1
        stem = path.stem.lower()
        key = " ".join(content_tokens(path.stem))
        if stem in known_stems or (key and key in known_titles):
            continue
        findings.append(Finding(
            failure_class="retrieval_blind_spot",
            subclass="unindexed_file",
            severity="medium",
            summary=f"vault file has no matching shard title: {path.name}",
            refs=[str(path)],
            evidence=[f"size={path.stat().st_size}B"],
            detail={"path": str(path)},
        ))
    return findings


# ---------------------------------------------------------------------------
# Detector 4 -- DUPLICATES / NEAR-DUPLICATES
# ---------------------------------------------------------------------------


def detect_duplicates(shards: Sequence[Shard], cfg: AuditConfig) -> List[Finding]:
    findings: List[Finding] = []

    # -- 4a. exact: identical file_hash on more than one row (dedup index missed it)
    by_hash: Dict[str, List[Shard]] = defaultdict(list)
    for s in shards:
        if s.file_hash:
            by_hash[s.file_hash].append(s)
    for fhash, group in by_hash.items():
        if len(group) < 2:
            continue
        findings.append(Finding(
            failure_class="duplicate",
            subclass="exact_hash",
            severity="high",
            summary=f"{len(group)} shards share file_hash {fhash[:16]}... (dedup miss)",
            refs=[s.ref for s in group[:5]],
            evidence=[f"{s.ref} {s.timestamp} {_snippet(s.title, cfg.snippet_chars)}"
                      for s in group[:3]],
            detail={"file_hash": fhash, "count": len(group),
                    "stores": sorted({s.store for s in group})},
        ))

    # -- 4b. near-duplicate content within a title block (blocking keeps this linear-ish)
    blocks: Dict[Tuple[str, ...], List[Shard]] = defaultdict(list)
    for s in shards:
        if len(s.content) < cfg.min_dup_chars:
            continue
        toks = content_tokens(s.title)
        if not toks:
            continue
        blocks[tuple(sorted(toks)[: cfg.dup_block_tokens])].append(s)

    compared = 0
    for _key, group in blocks.items():
        if len(group) < 2:
            continue
        cache = {s.ref: shingles(s.content, cfg.shingle_size) for s in group}
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if compared >= cfg.max_pairs:
                    logger.info("duplicate comparison cap %d reached", cfg.max_pairs)
                    return findings
                compared += 1
                if a.file_hash and a.file_hash == b.file_hash:
                    continue  # already reported as exact
                sim = jaccard(cache[a.ref], cache[b.ref])
                if sim < cfg.near_dup_threshold:
                    continue
                findings.append(Finding(
                    failure_class="duplicate",
                    subclass="near_duplicate",
                    severity="medium",
                    summary=f"near-duplicate shards (shingle Jaccard {sim:.2f}) that should "
                            f"have merged",
                    refs=[a.ref, b.ref],
                    evidence=[_snippet(a.title, cfg.snippet_chars),
                              _snippet(b.title, cfg.snippet_chars)],
                    detail={"similarity": round(sim, 4), "shingle_size": cfg.shingle_size,
                            "stores": sorted({a.store, b.store})},
                ))
    return findings


# ---------------------------------------------------------------------------
# Local fleet adjudication (ollama only, degrades to lexical)
# ---------------------------------------------------------------------------


class OllamaAdjudicator:
    """Second-opinion pass on stale-value candidates using the LOCAL gemma fleet.

    Never calls a cloud API. If the host is unreachable, every method is a no-op
    and the lexical verdicts stand unchanged.
    """

    def __init__(self, cfg: AuditConfig):
        self.cfg = cfg
        self.available = False
        self.model = ""
        self.reason = "not attempted"

    def probe(self) -> bool:
        if self.cfg.llm_enabled is False:
            self.reason = "disabled via NOUGEN_AUDIT_LLM_ENABLED=0"
            return False
        try:
            req = urllib.request.Request(f"{self.cfg.ollama_host.rstrip('/')}/api/tags")
            with urllib.request.urlopen(req, timeout=min(10, self.cfg.llm_timeout)) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            self.reason = f"ollama unreachable at {self.cfg.ollama_host}: {exc}"
            logger.warning("%s -- degrading to pure-lexical heuristics", self.reason)
            return False

        names = [m.get("name", "") for m in payload.get("models", [])]
        if self.cfg.llm_model and self.cfg.llm_model in names:
            self.model = self.cfg.llm_model
        else:
            for pref in self.cfg.llm_model_prefs:
                match = next((n for n in names if n == pref), None) or \
                        next((n for n in names if n.startswith(pref)), None)
                if match:
                    self.model = match
                    break
        if not self.model:
            self.reason = f"no preferred model among {names}"
            logger.warning("%s -- degrading to pure-lexical heuristics", self.reason)
            return False
        self.available = True
        self.reason = f"using local model {self.model}"
        logger.info("adjudicator %s", self.reason)
        return True

    def _chat(self, prompt: str) -> Optional[str]:
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Small context + short output: this must fit alongside whatever else
            # is resident on an 8GB card.
            "options": {"num_ctx": self.cfg.llm_num_ctx, "temperature": 0,
                        "num_predict": max(16, self.cfg.llm_batch * 12)},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.cfg.ollama_host.rstrip('/')}/api/generate", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace")).get("response", "")
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            logger.warning("adjudication call failed (%s); keeping lexical verdicts", exc)
            return None

    def adjudicate(self, findings: List[Finding]) -> Dict[str, int]:
        """Mark each candidate llm-confirmed / llm-rejected. Returns a tally."""
        tally = {"confirmed": 0, "rejected": 0, "unscored": 0, "batches": 0}
        if not self.available:
            tally["unscored"] = len(findings)
            return tally
        pool = findings[: self.cfg.llm_max_pairs]
        tally["unscored"] = len(findings) - len(pool)
        for start in range(0, len(pool), self.cfg.llm_batch):
            batch = pool[start:start + self.cfg.llm_batch]
            lines = []
            for n, f in enumerate(batch, 1):
                a = _snippet(f.evidence[0] if f.evidence else "", self.cfg.llm_snippet_chars)
                b = _snippet(f.evidence[1] if len(f.evidence) > 1 else "",
                             self.cfg.llm_snippet_chars)
                lines.append(f"{n}.\nEARLIER: {a}\nLATER: {b}")
            prompt = (
                "You check whether a later note corrects or contradicts an earlier note "
                "about the SAME thing.\n"
                "For each numbered pair answer exactly one word:\n"
                "CONTRADICTS - the later note gives a different value/state for the same fact\n"
                "CONSISTENT - both can be true at once\n"
                "UNRELATED - they are about different things\n"
                "Answer one line per number, format: <number>: <WORD>. No other text.\n\n"
                + "\n\n".join(lines)
            )
            raw = self._chat(prompt)
            tally["batches"] += 1
            if not raw:
                tally["unscored"] += len(batch)
                continue
            verdicts: Dict[int, str] = {}
            for line in raw.splitlines():
                m = re.match(r"\s*(\d+)\s*[:.\)]\s*(CONTRADICTS|CONSISTENT|UNRELATED)", line, re.I)
                if m:
                    verdicts[int(m.group(1))] = m.group(2).upper()
            for n, f in enumerate(batch, 1):
                verdict = verdicts.get(n)
                if verdict is None:
                    tally["unscored"] += 1
                    continue
                f.detail["llm_verdict"] = verdict
                f.detail["llm_model"] = self.model
                if verdict == "CONTRADICTS":
                    f.confidence = "llm-confirmed"
                    tally["confirmed"] += 1
                else:
                    f.confidence = "llm-rejected"
                    f.severity = "low"
                    tally["rejected"] += 1
        return tally


# ---------------------------------------------------------------------------
# Orchestration + reporting
# ---------------------------------------------------------------------------


def run_audit(cfg: Optional[AuditConfig] = None, shards: Optional[Sequence[Shard]] = None,
              retriever=None) -> Dict[str, object]:
    cfg = cfg or AuditConfig.resolve()
    started = datetime.now(timezone.utc)

    if shards is None:
        loaded: List[Shard] = load_shards(cfg.primary_label, cfg.vault_dir, cfg)
        for label, path in cfg.secondary_dirs:
            loaded.extend(load_shards(label, path, cfg))
        shards = loaded

    logger.info("corpus loaded: %d shards", len(shards))
    findings: List[Finding] = []
    stale = detect_stale_values(shards, cfg)
    logger.info("stale_value: %d", len(stale))
    findings.extend(stale)
    phase = detect_wrong_bindings(shards, cfg)
    logger.info("wrong_binding: %d", len(phase))
    findings.extend(phase)
    phase = detect_retrieval_blind_spots(shards, cfg, retriever=retriever)
    logger.info("retrieval_blind_spot(shards): %d", len(phase))
    findings.extend(phase)
    phase = detect_unindexed_files(shards, cfg)
    logger.info("retrieval_blind_spot(files): %d", len(phase))
    findings.extend(phase)
    phase = detect_duplicates(shards, cfg)
    logger.info("duplicate: %d", len(phase))
    findings.extend(phase)

    adjudicator = OllamaAdjudicator(cfg)
    adjudicator.probe()
    tally = adjudicator.adjudicate(stale)

    counts: Dict[str, int] = defaultdict(int)
    sub_counts: Dict[str, int] = defaultdict(int)
    for f in findings:
        counts[f.failure_class] += 1
        sub_counts[f"{f.failure_class}/{f.subclass}"] += 1

    # Deterministic ordering so two runs diff cleanly.
    findings.sort(key=lambda f: (f.failure_class, f.subclass, f.refs, f.summary))

    return {
        "schema": "nougen.memops_audit/1",
        "generated_at": started.isoformat(),
        "duration_s": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        "read_only": True,
        "source_taxonomy": "arXiv:2607.12893 MemOps (stale value / wrong binding / "
                           "missing evidence) + arXiv:2607.09493 selective write filter",
        "stores": {
            "primary": {"label": cfg.primary_label, "dir": str(cfg.vault_dir)},
            "secondary": [{"label": l, "dir": str(p)} for l, p in cfg.secondary_dirs],
        },
        "shards_examined": len(shards),
        "adjudicator": {"available": adjudicator.available, "model": adjudicator.model,
                        "reason": adjudicator.reason, **tally},
        "counts": dict(counts),
        "subclass_counts": dict(sub_counts),
        "config": cfg.knobs(),
        "config_provenance": cfg.resolved_from,
        "findings": [asdict(f) for f in findings],
    }


def render_report(result: Dict[str, object], max_examples: int = 5) -> str:
    lines = [
        "# NouGen memory-health audit (MemOps taxonomy)",
        "",
        f"- generated: {result['generated_at']} (read-only, no shards modified)",
        f"- shards examined: {result['shards_examined']}",
        f"- primary store: {result['stores']['primary']['dir']}",
        f"- secondary stores: {[s['dir'] for s in result['stores']['secondary']] or 'none'}",
        f"- adjudicator: {result['adjudicator']['reason']}",
        "",
        "## Counts per failure class",
        "",
        "| class | count |",
        "| --- | --- |",
    ]
    for cls, n in sorted(result["counts"].items()):
        lines.append(f"| {cls} | {n} |")
    lines += ["", "## Subclass breakdown", "", "| subclass | count |", "| --- | --- |"]
    for sub, n in sorted(result["subclass_counts"].items()):
        lines.append(f"| {sub} | {n} |")

    by_class: Dict[str, List[dict]] = defaultdict(list)
    for f in result["findings"]:
        by_class[f["failure_class"]].append(f)
    for cls, items in sorted(by_class.items()):
        lines += ["", f"## {cls} ({len(items)})", ""]
        for f in items[:max_examples]:
            lines.append(f"- **[{f['severity']}/{f['confidence']}] {f['summary']}**")
            lines.append(f"  - refs: {', '.join(f['refs']) or 'n/a'}")
            for ev in f["evidence"][:3]:
                lines.append(f"  - `{ev}`")
        if len(items) > max_examples:
            lines.append(f"- ...and {len(items) - max_examples} more (see JSON)")
    lines += ["", "---", "Auditor only: this harness never edits, deletes, or re-indexes a shard."]
    return "\n".join(lines) + "\n"


def write_outputs(result: Dict[str, object], cfg: AuditConfig) -> Tuple[Path, Path]:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = cfg.out_dir / f"memops_audit_{stamp}.json"
    md_path = cfg.out_dir / f"memops_audit_{stamp}.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                         encoding="utf-8")
    md_path.write_text(render_report(result), encoding="utf-8")
    return md_path, json_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MemOps memory-health audit (read-only)")
    parser.add_argument("--vault-dir", default=None, help="override NOUGEN_VAULT_DIR")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--no-llm", action="store_true", help="force pure-lexical heuristics")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.no_llm:
        os.environ["NOUGEN_AUDIT_LLM_ENABLED"] = "0"

    cfg = AuditConfig.resolve(args.vault_dir)
    logger.info("vault=%s (%s) secondaries=%s", cfg.vault_dir,
                cfg.resolved_from.get("vault_dir"), [str(p) for _, p in cfg.secondary_dirs])
    result = run_audit(cfg)
    md_path, json_path = write_outputs(result, cfg)
    if args.json_only:
        print(json.dumps({"counts": result["counts"],
                          "shards_examined": result["shards_examined"],
                          "json": str(json_path)}, indent=2))
    else:
        print(render_report(result))
        print(f"\nreport: {md_path}\njson:   {json_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
