"""Read-only connector for sibling SQLite vaults on this machine.

The shard substrate (`nougen_shards_1..9.db`) is only part of what lives in the
vault directory. Years of material sit in sibling databases — memories, journals,
per-project vaults — that `core.retrieve` never opens, so a federated caller was
being told "not found" about content the box demonstrably holds.

This is intentionally NOT the external-DB connector. That one speaks to network
databases and refuses sqlite/file URIs as an SSRF guard; local vaults are the
opposite trust class (operator-registered paths, opened read-only, no credentials
involved), so they get their own lane rather than a hole in that guard.

Every source degrades independently: a moved file, a renamed table, or a locked
database drops that vault from the sweep and leaves the rest of federation intact.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: Rows returned per vault. These tables are large (one holds 379k rows) and the
#: match is a LIKE scan, so the sweep is bounded and the bound is tunable.
MAX_ROWS = int(os.environ.get("NOUGEN_LOCAL_VAULT_MAX_ROWS", "200"))


def _timeout_s() -> float:
    """Per-store wall-clock budget. Read at call time, not import time, so tests
    and operators can retune without a process restart.

    Why this exists: measured 2026-08-17, one unindexed 1 GB store
    (veilverse_canon_vault, no *_ngsfts table -> LIKE full scan) cost 46s per
    query and the concurrent sweep's wall-clock IS the slowest store — one vault
    held the entire federated merge hostage. The budget is enforced with
    SQLite's progress handler and the store is reported as errored, never
    silently skipped (coverage honesty)."""
    return float(os.environ.get("NOUGEN_LOCAL_VAULT_TIMEOUT_S", "2.0"))


def _tier2_enabled() -> bool:
    """Cold-tier gate (legacy-federation war-game Move 5 fork). Default off:
    the hot tier answers inline; big unindexed stores wait for an explicit
    NOUGEN_FEDERATE_TIER2=on."""
    return os.environ.get("NOUGEN_FEDERATE_TIER2", "").strip().lower() in (
        "1", "true", "on", "yes")


def _hot_pins() -> set:
    """Stores always swept inline, whatever their size. Seeded from evidence:
    the stores that actually returned hits in past smokes plus the operator's
    canonical memory stores."""
    return {s.strip().lower() for s in os.environ.get(
        "NOUGEN_FEDERATE_HOT",
        "nougen_memories,dav1d_vault,rhea_noir_vault,valerion_code_vault"
    ).split(",") if s.strip()}


def _hot_max_bytes() -> int:
    """Files at or under this size are hot by default — a LIKE scan of a small
    file is cheaper than deciding anything about it (measured: every store
    under ~30 MB swept in <0.6s)."""
    return int(float(os.environ.get("NOUGEN_FEDERATE_HOT_MAX_MB", "32")) * 1_000_000)


#: FTS-probe cache keyed by (path, mtime): an indexed store is hot regardless of
#: size (bm25 lookups on the 3.1 GB store measure ~0.03s). mtime keying means a
#: written-to store is re-probed, an idle one never is.
_FTS_PROBE_CACHE: dict = {}


def _has_fts_file(path: Path, table: str) -> bool:
    """Whether `path` carries the connector's own FTS index for `table`."""
    try:
        key = (str(path), path.stat().st_mtime_ns, table)
    except OSError:
        return False
    if key not in _FTS_PROBE_CACHE:
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
            try:
                _FTS_PROBE_CACHE[key] = bool(_has_fts(conn, table))
            finally:
                conn.close()
        except sqlite3.Error:
            _FTS_PROBE_CACHE[key] = False
    return _FTS_PROBE_CACHE[key]


def _partition_tiers(vault_configs: list) -> tuple:
    """Split registered stores into (hot, cold).

    Hot = pinned by name, small on disk, or FTS-indexed — everything measured
    cheap. Cold = large AND unindexed: exactly the stores whose LIKE scans were
    the 52s, swept only when tier 2 is enabled."""
    hot, cold = [], []
    pins = _hot_pins()
    max_bytes = _hot_max_bytes()
    for conf in vault_configs:
        path = Path(str(conf.get("path", "")))
        stem = path.stem.lower()
        try:
            size = path.stat().st_size
        except OSError:
            size = 0  # missing file: keep hot, it degrades instantly anyway
        if (stem in pins or size <= max_bytes
                or _has_fts_file(path, str(conf.get("table_name", "")))):
            hot.append(conf)
        else:
            cold.append(conf)
    return hot, cold

#: Path fragments that mark generated/vendored files rather than authored ones.
#: Whole project trees were ingested over the years, build output included, so a
#: term appearing in a project's *directory name* makes every compiled chunk under
#: it a title match — hundreds of `.next/dev/server/...` rows outranking the actual
#: document. These are demoted, never dropped: the content is still reachable, it
#: just stops crowding out authored material.
NOISE_MARKERS = tuple(
    m.strip().lower() for m in os.environ.get(
        "NOUGEN_LOCAL_VAULT_NOISE",
        ".next,node_modules,__pycache__,site-packages,dist/,build/,.git/,.venv,"
        "vendor/,coverage/,.cache,package-lock.json,yarn.lock"
    ).split(",") if m.strip()
)


def _noise_penalty(title: str) -> float:
    """How much to demote a generated/vendored path. 0.0 for authored content."""
    low = (title or "").lower().replace("\\", "/")
    return 0.40 if any(marker in low for marker in NOISE_MARKERS) else 0.0


def _allowed_roots() -> list[Path]:
    """Where a registered vault is allowed to live. Defaults to the vault dir
    core already resolves, so registration cannot be used to read arbitrary files."""
    raw = os.environ.get("NOUGEN_LOCAL_VAULT_ROOTS")
    if raw:
        return [Path(p.strip()).resolve() for p in raw.split(os.pathsep) if p.strip()]
    from .. import core  # local import: avoid a cycle at module load
    return [Path(core.GLOBAL_DIR).resolve()]


def _is_valid_identifier(ident: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", ident or ""))


def _stable_hash(value) -> str:
    """Deterministic across processes — Python's hash() is salted per run, which
    would give the same row a different identity on every restart and break dedup."""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _path_is_allowed(path: Path) -> bool:
    """Registered path must resolve inside an allowed root. Blocks a tampered
    registry row from turning a federated search into arbitrary file access."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _build_query(table: str, title_col: str, content_col: str, keywords: list, limit: int):
    """The ranked per-vault SELECT, plus its parameters in STATEMENT order.

    Ranking matters here: without an ORDER BY, LIMIT returns whatever rowids come
    first, so a vault holding thousands of genuine matches surfaces whichever rows
    happen to sit early in the file — documents that merely contain the word, while
    the documents *about* it never appear.

    Two signals, both cheap and index-free:
      title_hits  a term in the title is a far stronger statement of aboutness
                  than one buried in a long body
      term_count  occurrences, measured by how much shorter the content gets with
                  the term removed; combined with body length below this keeps a
                  short note that is entirely about the term above a huge log that
                  mentions it once
    """
    where = " OR ".join(
        f'("{title_col}" LIKE ? OR "{content_col}" LIKE ?)' for _ in keywords)
    title_score = " + ".join(
        f'(CASE WHEN "{title_col}" LIKE ? THEN 1 ELSE 0 END)' for _ in keywords)
    # Single quotes on the empty string are REQUIRED: in SQLite "" is an
    # *identifier*, not an empty literal. The double-quoted form raises, and
    # because this connector degrades per vault, every vault would silently drop
    # out of the sweep and look like an empty corpus.
    density = " + ".join(
        f"((length(\"{content_col}\") - length(replace(lower(\"{content_col}\"), ?, ''))) "
        f"/ (length(?) * 1.0))" for _ in keywords)

    sql = (
        f'SELECT "{title_col}" AS title, "{content_col}" AS content, '
        f'({title_score}) AS title_hits, '
        f'({density}) AS term_count, '
        f'length("{content_col}") AS body_len '
        f'FROM "{table}" WHERE {where} '
        f'ORDER BY title_hits DESC, '
        f'(term_count * 1000.0 / (body_len + 1)) DESC, '
        f'term_count DESC '
        f'LIMIT ?'
    )

    # Bind in the order the placeholders appear in the SQL TEXT, not in logical
    # order. Both scoring expressions live in the SELECT list, ahead of the WHERE.
    # Binding WHERE-first hands the LIKE clauses the bare terms with no % wildcards
    # and matches zero rows everywhere — a bug indistinguishable from missing data.
    params: list = []
    for kw in keywords:                       # 1. title_score (SELECT)
        params.append(f"%{kw}%")
    for kw in keywords:                       # 2. density (SELECT)
        params.extend([kw.lower(), kw.lower()])
    for kw in keywords:                       # 3. WHERE
        params.extend([f"%{kw}%", f"%{kw}%"])
    params.append(min(limit, MAX_ROWS))       # 4. LIMIT
    return sql, params


#: Index suffix written by tools/build_vault_fts.py. Kept distinct from any
#: pre-existing `<table>_fts` so we never query an index we did not build and
#: whose column layout we cannot assume.
FTS_SUFFIX = "_ngsfts"


def _fts_match_expr(keywords: list) -> str:
    """FTS5 MATCH expression with every term quoted as a literal phrase.

    Unquoted user text is parsed as FTS5 syntax, so a term containing `-`
    (`Rhea-Noir`), `*`, `:` or a bare `AND`/`OR`/`NEAR` raises OperationalError
    and takes the whole vault out of the sweep. Quoting makes every term inert.
    """
    return " ".join('"' + kw.replace('"', '""') + '"' for kw in keywords)


def _build_fts_query(table: str, fts: str, title_col: str, content_col: str,
                     keywords: list, limit: int):
    """Ranked SELECT against an external-content FTS5 index, plus its params.

    bm25() is the ranking signal here rather than the hand-rolled density used on
    the LIKE path — it already accounts for term frequency and document length,
    which is what that heuristic was approximating. Title matches still get an
    explicit boost because aboutness beats frequency for canon lookups.
    """
    sql = (
        f'SELECT t."{title_col}" AS title, t."{content_col}" AS content, '
        f'(CASE WHEN lower(t."{title_col}") LIKE ? THEN 1 ELSE 0 END) AS title_hits, '
        f'bm25(f."{fts}") AS bm25_rank '
        f'FROM "{fts}" f JOIN "{table}" t ON t.rowid = f.rowid '
        f'WHERE f."{fts}" MATCH ? '
        f'ORDER BY title_hits DESC, bm25_rank ASC '
        f'LIMIT ?'
    )
    params = [f"%{keywords[0].lower()}%", _fts_match_expr(keywords), min(limit, MAX_ROWS)]
    return sql, params


def _has_fts(conn: sqlite3.Connection, table: str) -> str | None:
    """The FTS index name for this table, or None when it was never built."""
    fts = f"{table}{FTS_SUFFIX}"
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (fts,)).fetchone()
    return fts if row else None


def _query_one_vault(conf: dict, keywords: list, limit: int) -> tuple:
    """Sweep a single vault. Never raises: a bad vault degrades to no rows.

    Returns ``(rows, error)`` — error is None on success, otherwise a short
    reason string ("timeout after 2.0s", "file missing", ...). Callers that
    only want the rows unpack index 0; query_local_vaults carries the error
    into its sweep report so a dropped store is visible, not silent."""
    vid = conf.get("id", "?")
    try:
        path = Path(conf["path"])
        table = conf["table_name"]
        title_col = conf["title_col"]
        content_col = conf["content_col"]

        if not all(_is_valid_identifier(x) for x in (table, title_col, content_col)):
            logger.warning("local vault skipped (%s): invalid identifier", vid)
            return [], "invalid identifier"
        if not _path_is_allowed(path):
            logger.warning("local vault skipped (%s): path outside allowed roots", vid)
            return [], "path outside allowed roots"
        if not path.exists():
            logger.warning("local vault skipped (%s): file missing", vid)
            return [], "file missing"

        # Read-only URI: this connector must never be able to mutate a vault.
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row

        # Wall-clock budget, enforced inside SQLite's VM: the progress handler
        # runs every N opcodes and a nonzero return aborts the statement with
        # OperationalError('interrupted'). This is the only reliable way to
        # stop a LIKE scan mid-flight from the same thread.
        budget = _timeout_s()
        deadline = time.monotonic() + budget

        def _over_budget():
            return 1 if time.monotonic() > deadline else 0

        if budget > 0:
            conn.set_progress_handler(_over_budget, 4000)

        def _timed_out(exc: sqlite3.OperationalError) -> bool:
            return "interrupt" in str(exc).lower() or time.monotonic() > deadline

        try:
            # Prefer the index when one exists. On a large vault this is the whole
            # difference between an indexed lookup and reading every row — the LIKE
            # path is correct but scans, which is what made the sweep disk-bound.
            fts = _has_fts(conn, table)
            if fts:
                sql, params = _build_fts_query(table, fts, title_col, content_col,
                                               keywords, limit)
                try:
                    rows = conn.execute(sql, params).fetchall()
                except sqlite3.OperationalError as exc:
                    if _timed_out(exc):
                        # Budget exhausted: falling back to the LIKE scan here
                        # would spend even longer. Report, don't retry.
                        raise
                    # A malformed/corrupt index must not lose the vault: fall back
                    # to the scan rather than returning nothing.
                    logger.warning("local vault %s: FTS query failed (%s), using LIKE", vid, exc)
                    sql, params = _build_query(table, title_col, content_col, keywords, limit)
                    rows = conn.execute(sql, params).fetchall()
            else:
                sql, params = _build_query(table, title_col, content_col, keywords, limit)
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if _timed_out(exc):
                logger.warning("local vault %s: timed out after %.1fs, dropped from sweep",
                               vid, budget)
                return [], f"timeout after {budget:.1f}s"
            raise
        finally:
            conn.close()

        results = []
        for row in rows:
            item = dict(row)
            results.append({
                "id": f"vault_{vid}_{_stable_hash(item['title'])[:16]}",
                "event_type": "LOCAL_VAULT",
                "title": item["title"] or "Untitled",
                "content": item["content"] or "",
                "tags": json.dumps(["local_vault", path.stem]),
                "utility_score": 1.0,
                "access_count": 0,
                "file_hash": _stable_hash(item["content"]),
                "bm25_score": 0.0,
                # Carry the in-vault ranking into the RRF merge. A flat score for
                # every local row made the merge fall back to source order, so
                # whichever vault was registered first won regardless of match
                # quality.
                # bm25 is negative and more-negative == stronger, so it is mapped
                # through a bounded decreasing function rather than compared raw
                # against the LIKE path's occurrence count. Either way the score
                # lands in roughly [0.45, 1.0] so the two paths stay comparable.
                "final_score": round(max(0.05,
                    0.45
                    + (0.35 if item.get("title_hits") else 0.0)
                    + (min(0.20, 0.20 * (-(item["bm25_rank"]) / 10.0))
                       if item.get("bm25_rank") is not None
                       else min(0.20, (item.get("term_count") or 0) / 50.0))
                    - _noise_penalty(item["title"])),
                    6),
                "_db_index": f"vault_{path.stem}",
            })
        return results, None
    except (sqlite3.Error, KeyError, TypeError, ValueError, OSError) as exc:
        # One bad vault must not kill the sweep — but say which one and why.
        logger.warning("local vault skipped (%s): %s: %s", vid, type(exc).__name__, exc)
        return [], f"{type(exc).__name__}: {exc}"


def query_local_vaults(query: str, vault_configs: list, limit: int = 3,
                       sweep_report: dict | None = None) -> list:
    """Keyword-sweep registered local vaults, mapped to the standard shard shape.

    Vaults are swept CONCURRENTLY. Each is a separate file opened read-only on its
    own connection, so there is nothing to serialise them for, and a sequential
    sweep paid the sum of every vault's scan — with ~500k rows across 28 vaults
    that dominated the entire federated request. Wall-clock is now the slowest
    single vault instead of the total.

    Two-tier sweep (war-game Move 5 fork, fired 2026-08-17): the hot tier
    (pinned / small / FTS-indexed stores) is swept inline; the cold tier (large
    AND unindexed) only when NOUGEN_FEDERATE_TIER2 is on. Cold stores that were
    deferred, and any store that errored or timed out, land in ``sweep_report``
    when the caller passes a dict — a dropped store must be visible, never a
    silent hole in the corpus (coverage honesty).
    """
    keywords = [w for w in query.split() if len(w) >= 3]
    if not keywords:
        keywords = [query]
    if not vault_configs:
        return []

    hot, cold = _partition_tiers(vault_configs)
    tier2 = _tier2_enabled()
    to_sweep = hot + cold if tier2 else hot
    if sweep_report is not None:
        sweep_report["stores_registered"] = len(vault_configs)
        sweep_report["stores_swept"] = len(to_sweep)
        sweep_report["tier2"] = tier2
        sweep_report["tier2_deferred"] = sorted(
            Path(str(c.get("path", ""))).stem for c in cold) if not tier2 else []
        sweep_report.setdefault("errored", [])

    workers = int(os.environ.get("NOUGEN_LOCAL_VAULT_WORKERS", "0")) or min(
        16, max(4, (os.cpu_count() or 4)))

    results: list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_query_one_vault, conf, keywords, limit):
                   Path(str(conf.get("path", ""))).stem for conf in to_sweep}
        for fut, stem in futures.items():
            # _query_one_vault degrades internally; this catches anything that
            # escaped it so one vault still cannot kill the sweep.
            try:
                rows, err = fut.result()
                results.extend(rows)
                if err and sweep_report is not None:
                    sweep_report["errored"].append({"store": stem, "error": err})
            except Exception as exc:  # noqa: BLE001
                logger.warning("local vault future failed: %s: %s", type(exc).__name__, exc)
                if sweep_report is not None:
                    sweep_report["errored"].append(
                        {"store": stem, "error": f"{type(exc).__name__}: {exc}"})

    # Dedupe before returning. The same document genuinely exists in more than one
    # vault (project trees were ingested repeatedly over the years), and RRF only
    # dedupes across its input LISTS — duplicates inside one list survive and can
    # fill a top-8 with three copies of one file. Keyed on content hash + title so
    # same-name-different-content stays distinct; highest score wins.
    best: dict = {}
    for item in results:
        key = (item["file_hash"], item["title"])
        if key not in best or item["final_score"] > best[key]["final_score"]:
            best[key] = item
    return sorted(best.values(), key=lambda x: -x["final_score"])
