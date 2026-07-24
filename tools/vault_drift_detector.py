#!/usr/bin/env python3
"""Vault drift detector.

Compares the .md files actually on disk in the Memory Vault against the rows
actually present in the dedup index, and reports the gap. It NEVER trusts an
ingester's success message -- the only inputs are live filesystem state and
live index state.

Background: an ingest tool can print "Successfully Sharded: N" while writing
into a repo-local `.vault/` store instead of the configured Memory Vault. The
vault then drifts silently for as long as nobody checks, because the only
signal anyone looks at is the tool's own stdout. This detector exists so that
state, not stdout, is the alarm.

Two distinct numbers are reported, because conflating them makes the alarm
useless:

  EXPECTED BACKLOG - files matching the backlog globs (arxiv digests by default)
      that are NOT in the dedup index. It is a REMAINDER, not a file count:
      backlog files on disk MINUS the backlog files already indexed. There is a
      deliberate forward-only policy on that backlog due to Stadium GPU limits,
      so those files are knowingly unindexed. Reported, never alarmed on (unless
      an explicit backlog ceiling is configured).

      Read that twice before quoting the number. It is routinely compared
      against a shell count of `arxiv_*.md` on disk and the two look
      contradictory -- but they measure different things: the shell count is ONE
      glob family counted regardless of index state, while this figure spans
      BOTH backlog glob families and counts only the unindexed remainder. The
      report prints on-disk totals per glob alongside the remainder so the two
      can never be confused.

  UNEXPECTED DRIFT - everything else that is on disk but not in the index. This
      is the number that fires the alarm.

  INDEX HEALTH - a shard can be in the DB and still be unsearchable, which no
      file-vs-index comparison above can ever see. Row count is compared against
      the rows the FTS index actually contains (via the fts5 _docsize shadow
      table -- `SELECT count(*) FROM shards_fts` is answered from the content
      table and always agrees, so it can never detect this) and any divergence
      is an alarm. NULL embeddings are reported, not alarmed: embedding needs a
      reachable model, so it is best-effort by design, but never silent.

Rule 0.2 (Dynamic State Doctrine): every environment-shaped value resolves
env -> config -> probe, with a constant only as a logged fallback. No bare magic
numbers.

Exit codes:
    0  clean          unexpected drift <= NOUGEN_DRIFT_MAX
    1  DRIFT          unexpected drift  > NOUGEN_DRIFT_MAX   (alarm)
    2  ERROR          vault or dedup index could not be resolved / read
    3  BACKLOG        backlog exceeded NOUGEN_DRIFT_BACKLOG_MAX (only if set)
    4  INDEX          shards present in a DB but missing from its FTS index
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------
EXIT_CLEAN = 0
EXIT_DRIFT = 1
EXIT_ERROR = 2
EXIT_BACKLOG = 3
EXIT_INDEX = 4

# --------------------------------------------------------------------------
# Fallback constants. These are LAST RESORT values, logged whenever used, and
# never machine-specific: the vault is discovered by probing user-relative
# candidates, not by hardcoding one operator's drive layout.
# --------------------------------------------------------------------------
FALLBACK_DEDUP_DB_NAME = "dedup_index.db"
FALLBACK_INCLUDE_GLOBS = "**/*.md"
# Editor/tooling noise that is never memory and never a backlog: VS Code's
# local-history store (`vault/User/History/**`) is autosave snapshots of files
# already tracked elsewhere, so ingesting it floods recall with near-duplicate
# revisions. The ingester refuses these, therefore we must not count them --
# a file ingest skips but drift counts is UNEXPECTED drift on every run,
# forever. Dropped from accounting entirely (files_excluded), not classified as
# backlog, because nothing is ever going to drain them. Canonical value lives in
# nougen_shards.core.DEFAULT_NOISE_EXCLUDE_GLOBS; this literal is the last
# resort when src/ is not importable. Override with NOUGEN_DRIFT_EXCLUDE_GLOBS.
FALLBACK_EXCLUDE_GLOBS = "User/History/*"
# The forward-only arxiv backlog reaches the vault under two naming families:
# the raw digests (`arxiv_*.md`) and the derived intelligence shards
# (`intelligence_shard_arxiv_*.md`). BOTH families must be classified as
# backlog: matching only the raw digests leaves the derived family sitting in
# the alarm bucket, which is exactly the cry-wolf failure this split exists to
# prevent. Override with NOUGEN_DRIFT_BACKLOG_GLOBS.
FALLBACK_BACKLOG_GLOBS = "arxiv_*.md;intelligence_shard_arxiv_*.md"
FALLBACK_DRIFT_MAX = 0
FALLBACK_RECALL_MARKER = "=== NOUGENSHARDS RECALL PACKET"
FALLBACK_SAMPLE_SIZE = 5
GLOB_SEP = ";"

_LOG_PREFIX = "[drift]"


def log(msg: str) -> None:
    print(f"{_LOG_PREFIX} {msg}", flush=True)


# --------------------------------------------------------------------------
# Config resolution: env -> CLI -> probe -> logged fallback
# --------------------------------------------------------------------------
def env_str(name: str, fallback: str, *, secret: bool = False) -> str:
    raw = os.environ.get(name)
    if raw is not None and raw.strip() != "":
        log(f"cfg {name}={raw if not secret else '***'} (env)")
        return raw
    log(f"cfg {name}={fallback!r} (fallback)")
    return fallback


def env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is not None and raw.strip() != "":
        try:
            val = int(raw.strip())
            log(f"cfg {name}={val} (env)")
            return val
        except ValueError:
            log(f"cfg {name}={raw!r} is not an int; using fallback {fallback}")
    else:
        log(f"cfg {name}={fallback} (fallback)")
    return fallback


def env_int_opt(name: str):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        val = int(raw.strip())
        log(f"cfg {name}={val} (env)")
        return val
    except ValueError:
        log(f"cfg {name}={raw!r} is not an int; ignoring")
        return None


def split_globs(raw: str) -> list[str]:
    """Accept ';' or ',' separated glob lists."""
    if not raw:
        return []
    parts: list[str] = []
    for chunk in raw.replace(",", GLOB_SEP).split(GLOB_SEP):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def resolve_vault_dir(cli_value: str | None) -> Path | None:
    """Discover the vault at runtime instead of asserting where it lives.

    Order: --vault-dir -> NOUGEN_VAULT_DIR -> %WATCHTOWER_ROOT%/vault ->
    ~/Watchtower/vault -> ~/.nougen/shards -> ./.vault
    A candidate only wins if it exists AND carries a dedup index, so we can
    never silently measure drift against an empty or wrong store.
    """
    candidates: list[tuple[str, Path]] = []
    if cli_value:
        candidates.append(("--vault-dir", Path(cli_value)))
    env_vault = os.environ.get("NOUGEN_VAULT_DIR")
    if env_vault:
        candidates.append(("NOUGEN_VAULT_DIR", Path(env_vault)))
    wt_root = os.environ.get("WATCHTOWER_ROOT")
    if wt_root:
        candidates.append(("WATCHTOWER_ROOT/vault", Path(wt_root) / "vault"))
    home = Path.home()
    candidates.append(("~/Watchtower/vault", home / "Watchtower" / "vault"))
    candidates.append(("~/.nougen/shards", home / ".nougen" / "shards"))
    candidates.append(("./.vault", Path.cwd() / ".vault"))

    dedup_name = os.environ.get("NOUGEN_DEDUP_DB_NAME") or FALLBACK_DEDUP_DB_NAME

    first_existing: tuple[str, Path] | None = None
    for source, path in candidates:
        try:
            if not path.is_dir():
                continue
        except OSError:
            continue
        if first_existing is None:
            first_existing = (source, path)
        if (path / dedup_name).is_file():
            log(f"vault resolved to {path} (source: {source}, has {dedup_name})")
            return path
    if first_existing:
        source, path = first_existing
        log(f"vault resolved to {path} (source: {source}, WARNING: no {dedup_name})")
        return path
    log("vault could NOT be resolved from any candidate")
    return None


def resolve_dedup_db(vault_dir: Path, cli_value: str | None) -> Path:
    if cli_value:
        log(f"dedup db {cli_value} (--dedup-db)")
        return Path(cli_value)
    env_db = os.environ.get("NOUGEN_DEDUP_DB")
    if env_db:
        log(f"dedup db {env_db} (NOUGEN_DEDUP_DB)")
        return Path(env_db)
    name = env_str("NOUGEN_DEDUP_DB_NAME", FALLBACK_DEDUP_DB_NAME)
    return vault_dir / name


# --------------------------------------------------------------------------
# Hashing -- must be byte-for-byte the identity core.capture() writes into the
# dedup index, otherwise the detector invents phantom drift that can never be
# closed. We import that function rather than reimplementing it: reimplementing
# it is precisely how the 2026-07-24 redaction mismatch happened (capture()
# hashed secret-redacted content, the tools hashed raw content, so every file
# containing a credential-shaped string drifted forever).
# --------------------------------------------------------------------------
def canonical_default(attr: str, literal: str) -> str:
    """Prefer the canonical glob default from core; fall back to the literal.

    The ingester and this detector must not disagree about what is out of
    scope, so both read the same names out of nougen_shards.core. core is
    imported lazily (as with the hasher) to keep the detector runnable and
    still honest about its config when src/ is missing.
    """
    repo_src = Path(__file__).resolve().parent.parent / "src"
    if str(repo_src) not in sys.path:
        sys.path.insert(0, str(repo_src))
    try:
        import nougen_shards.core as _core  # type: ignore
        value = getattr(_core, attr, None)
        if value:
            log(f"glob default {attr}={value!r} (core, canonical)")
            return str(value)
        log(f"WARNING: core has no {attr}; using local literal {literal!r} -- "
            "verify it still matches the ingester's exclusion list")
    except Exception as exc:
        log(f"WARNING: could not import core for {attr} ({exc}); "
            f"using local literal {literal!r} -- may diverge from the ingester")
    return literal


def resolve_hasher(marker: str):
    """Return (hash_fn, source_label). Prefers the canonical core function."""
    repo_src = Path(__file__).resolve().parent.parent / "src"
    if str(repo_src) not in sys.path:
        sys.path.insert(0, str(repo_src))
    try:
        from nougen_shards.core import compute_dedup_hash  # type: ignore
        log("hash source: nougen_shards.core.compute_dedup_hash (canonical)")
        return compute_dedup_hash, "core.compute_dedup_hash"
    except Exception as exc:
        log(f"WARNING: could not import core.compute_dedup_hash ({exc}); "
            "falling back to a local replica -- results may diverge from capture()")

    def _local(content: str) -> str:
        try:
            from nougen_shards.brain_scan.redaction import redact_content as _r
            content = _r(content)
        except Exception:
            pass
        clean = content
        if marker and marker in content:
            clean = content.split(marker)[0].strip()
        return hashlib.md5(clean.encode("utf-8", errors="ignore")).hexdigest()

    return _local, "local-replica"


def file_hash(path: Path, hash_fn) -> str | None:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    try:
        return hash_fn(content)
    except Exception:
        return None


def matches_any(path: Path, vault_dir: Path, globs: list[str]) -> bool:
    if not globs:
        return False
    name = path.name
    try:
        rel = path.relative_to(vault_dir).as_posix()
    except ValueError:
        rel = path.as_posix()
    for g in globs:
        gp = g.replace("\\", "/")
        if fnmatch.fnmatch(name, gp) or fnmatch.fnmatch(rel, gp):
            return True
    return False


def describe(path: Path, vault_dir: Path) -> dict:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    try:
        rel = str(path.relative_to(vault_dir))
    except ValueError:
        rel = str(path)
    return {
        "path": rel,
        "mtime": mtime,
        "mtime_iso": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        if mtime
        else None,
    }


def bounds(items: list[dict]) -> tuple[dict | None, dict | None]:
    if not items:
        return None, None
    ordered = sorted(items, key=lambda d: d["mtime"])
    return ordered[0], ordered[-1]


# --------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Detect Memory Vault ingest drift.")
    ap.add_argument("--vault-dir", default=None, help="override vault root")
    ap.add_argument("--dedup-db", default=None, help="override dedup index path")
    ap.add_argument("--max", dest="max_drift", type=int, default=None,
                    help="max unexpected missing files before exit 1")
    ap.add_argument("--include", default=None, help="glob list of files to count")
    ap.add_argument("--exclude", default=None, help="glob list ignored entirely")
    ap.add_argument("--backlog", default=None,
                    help="glob list treated as EXPECTED (forward-only) backlog")
    ap.add_argument("--no-backlog-split", action="store_true",
                    help="treat backlog files as ordinary drift")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="write the report as JSON to this path")
    ap.add_argument("--sample", type=int, default=None,
                    help="how many example missing files to print")
    args = ap.parse_args(argv)

    started = time.time()
    log(f"run start {datetime.now(timezone.utc).isoformat()}")

    vault_dir = resolve_vault_dir(args.vault_dir)
    if vault_dir is None:
        log("FATAL: no vault directory found")
        return EXIT_ERROR

    # Bind before any core import: core resolves GLOBAL_DIR at import time, and
    # an unbound import would point its side effects at a different store.
    os.environ["NOUGEN_VAULT_DIR"] = str(vault_dir)

    dedup_db = resolve_dedup_db(vault_dir, args.dedup_db)
    if not dedup_db.is_file():
        log(f"FATAL: dedup index not found at {dedup_db}")
        return EXIT_ERROR

    include_globs = split_globs(
        args.include if args.include is not None
        else env_str("NOUGEN_DRIFT_INCLUDE_GLOBS", FALLBACK_INCLUDE_GLOBS)
    )
    exclude_globs = split_globs(
        args.exclude if args.exclude is not None
        else env_str("NOUGEN_DRIFT_EXCLUDE_GLOBS",
                     canonical_default("DEFAULT_NOISE_EXCLUDE_GLOBS",
                                       FALLBACK_EXCLUDE_GLOBS))
    )
    backlog_globs = [] if args.no_backlog_split else split_globs(
        args.backlog if args.backlog is not None
        else env_str("NOUGEN_DRIFT_BACKLOG_GLOBS",
                     canonical_default("DEFAULT_BACKLOG_GLOBS",
                                       FALLBACK_BACKLOG_GLOBS))
    )
    max_drift = (args.max_drift if args.max_drift is not None
                 else env_int("NOUGEN_DRIFT_MAX", FALLBACK_DRIFT_MAX))
    backlog_max = env_int_opt("NOUGEN_DRIFT_BACKLOG_MAX")
    marker = env_str("NOUGEN_DRIFT_RECALL_MARKER", FALLBACK_RECALL_MARKER)
    sample_size = (args.sample if args.sample is not None
                   else env_int("NOUGEN_DRIFT_SAMPLE", FALLBACK_SAMPLE_SIZE))
    json_out = args.json_out or os.environ.get("NOUGEN_DRIFT_JSON") or None

    # ---- live index state -------------------------------------------------
    try:
        conn = sqlite3.connect(f"file:{dedup_db}?mode=ro", uri=True)
        indexed_hashes = {row[0] for row in conn.execute("SELECT file_hash FROM hashes")}
        conn.close()
    except Exception as exc:
        log(f"FATAL: could not read dedup index {dedup_db}: {exc}")
        return EXIT_ERROR
    log(f"indexed rows in dedup index: {len(indexed_hashes)}")

    # ---- live disk state --------------------------------------------------
    on_disk: list[Path] = []
    for g in include_globs:
        on_disk.extend(p for p in vault_dir.glob(g) if p.is_file())
    # de-dup across overlapping globs
    seen: set[str] = set()
    files: list[Path] = []
    for p in on_disk:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            files.append(p)

    total_found = len(files)
    excluded = [p for p in files if matches_any(p, vault_dir, exclude_globs)]
    scanned = [p for p in files if p not in excluded] if exclude_globs else files
    if exclude_globs:
        ex = set(map(str, excluded))
        scanned = [p for p in files if str(p) not in ex]

    hash_fn, hash_source = resolve_hasher(marker)

    matched = 0
    unreadable: list[dict] = []
    missing_backlog: list[dict] = []
    missing_drift: list[dict] = []

    # On-disk backlog tally, kept SEPARATELY from the unindexed remainder and
    # broken out per glob. This is the pair of numbers whose conflation caused
    # the 8,769-vs-10,171 contradiction; both are now printed side by side.
    backlog_on_disk = 0
    backlog_by_glob: dict[str, int] = {g: 0 for g in backlog_globs}

    for p in scanned:
        glob_hits = [g for g in backlog_globs if matches_any(p, vault_dir, [g])]
        if glob_hits:
            backlog_on_disk += 1
            for g in glob_hits:
                backlog_by_glob[g] += 1
        fh = file_hash(p, hash_fn)
        if fh is None:
            unreadable.append(describe(p, vault_dir))
            continue
        if fh in indexed_hashes:
            matched += 1
            continue
        entry = describe(p, vault_dir)
        if glob_hits:
            missing_backlog.append(entry)
        else:
            missing_drift.append(entry)

    index_health = check_index_health(vault_dir)

    elapsed = time.time() - started
    b_old, b_new = bounds(missing_backlog)
    d_old, d_new = bounds(missing_drift)

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "vault_dir": str(vault_dir),
        "dedup_db": str(dedup_db),
        "include_globs": include_globs,
        "exclude_globs": exclude_globs,
        "backlog_globs": backlog_globs,
        "drift_max": max_drift,
        "backlog_max": backlog_max,
        "hash_source": hash_source,
        "elapsed_sec": round(elapsed, 2),
        "totals": {
            "files_found": total_found,
            "files_excluded": total_found - len(scanned),
            "files_scanned": len(scanned),
            "indexed_rows": len(indexed_hashes),
            "matched": matched,
            "unreadable": len(unreadable),
            "missing_total": len(missing_backlog) + len(missing_drift),
            "missing_expected_backlog": len(missing_backlog),
            "missing_unexpected_drift": len(missing_drift),
        },
        "backlog_on_disk": {
            "_meaning": "files on disk matching the backlog globs, INDEXED OR NOT",
            "total": backlog_on_disk,
            "by_glob": backlog_by_glob,
            "already_indexed": backlog_on_disk - len(missing_backlog),
            "not_indexed": len(missing_backlog),
        },
        "index_health": index_health,
        "expected_backlog": {
            "_meaning": ("backlog files NOT in the dedup index (a REMAINDER, "
                         "not an on-disk file count -- see backlog_on_disk)"),
            "count": len(missing_backlog),
            "oldest": b_old,
            "newest": b_new,
            "sample": missing_backlog[:sample_size],
        },
        "unexpected_drift": {
            "count": len(missing_drift),
            "oldest": d_old,
            "newest": d_new,
            "sample": sorted(missing_drift, key=lambda d: d["mtime"])[:sample_size],
        },
        "unreadable_sample": unreadable[:sample_size],
    }

    # ---- human report -----------------------------------------------------
    t = report["totals"]
    print("")
    print("=== VAULT DRIFT REPORT ===")
    print(f"vault              : {vault_dir}")
    print(f"dedup index        : {dedup_db} ({t['indexed_rows']} indexed rows)")
    print(f"files on disk      : {t['files_found']}  "
          f"(excluded {t['files_excluded']}, scanned {t['files_scanned']})")
    print(f"indexed (matched)  : {t['matched']}")
    print(f"missing total      : {t['missing_total']}")
    print(f"  expected backlog : {t['missing_expected_backlog']}  "
          f"= backlog files NOT in the index (a remainder, NOT files on disk)")
    print(f"  UNEXPECTED drift : {t['missing_unexpected_drift']}  (threshold {max_drift})")
    if backlog_globs:
        print(f"backlog on disk    : {backlog_on_disk} files match the backlog globs "
              f"(indexed or not)")
        for g, n in backlog_by_glob.items():
            print(f"    {g:<34}: {n} on disk")
        print(f"    -> of those {backlog_on_disk} on disk, "
              f"{backlog_on_disk - len(missing_backlog)} are indexed and "
              f"{len(missing_backlog)} are not (that is the backlog figure above)")
    if t["unreadable"]:
        print(f"unreadable files   : {t['unreadable']}")
    if b_old:
        print(f"backlog oldest     : {b_old['mtime_iso']}  {b_old['path']}")
        print(f"backlog newest     : {b_new['mtime_iso']}  {b_new['path']}")
    if d_old:
        print(f"DRIFT oldest       : {d_old['mtime_iso']}  {d_old['path']}")
        print(f"DRIFT newest       : {d_new['mtime_iso']}  {d_new['path']}")
        print("DRIFT sample:")
        for item in report["unexpected_drift"]["sample"]:
            print(f"  - {item['mtime_iso']}  {item['path']}")
    ih = report["index_health"]
    print(f"index health       : {ih['total_rows']} rows / "
          f"{ih['total_rows'] - ih['total_unindexed']} in FTS index "
          f"(fts5 _docsize, the only honest count)")
    if ih["total_unindexed"]:
        print(f"  UNSEARCHABLE     : {ih['total_unindexed']} shard(s) written but "
              f"NOT in the FTS index -- run nougen_shards.core.repair_fts_index()")
        for e in ih["databases"]:
            if e.get("unindexed"):
                print(f"    - {e['db']}: {e['unindexed']} of {e['rows']} rows unindexed")
    if ih["missing_triggers"]:
        print(f"  MISSING TRIGGERS : {', '.join(ih['missing_triggers'])} "
              f"(writes to these bypass the FTS index)")
    print(f"  null embeddings  : {ih['total_null_embedding']} "
          f"(reported, not alarmed: embedding needs a reachable model)")
    print(f"elapsed            : {report['elapsed_sec']}s")

    if json_out:
        try:
            Path(json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
            log(f"json report written to {json_out}")
        except Exception as exc:
            log(f"WARNING: could not write json report: {exc}")

    # A shard in the DB but not in the FTS index is unsearchable memory. That is
    # never "expected backlog" and never within a drift threshold, so it gets its
    # own non-zero exit ahead of the file-level verdicts.
    if report["index_health"]["total_unindexed"] or report["index_health"]["missing_triggers"]:
        print(f"RESULT: INDEX  ({report['index_health']['total_unindexed']} shard(s) "
              f"written but unsearchable)")
        return EXIT_INDEX
    if len(missing_drift) > max_drift:
        print(f"RESULT: DRIFT  ({len(missing_drift)} unexpected > max {max_drift})")
        return EXIT_DRIFT
    if backlog_max is not None and len(missing_backlog) > backlog_max:
        print(f"RESULT: BACKLOG ({len(missing_backlog)} > backlog max {backlog_max})")
        return EXIT_BACKLOG
    print("RESULT: CLEAN")
    return EXIT_CLEAN


def check_index_health(vault_dir: Path) -> dict:
    """Per-DB row count vs rows the FTS index ACTUALLY holds, plus NULL vectors.

    Why this lives in the drift detector: the file-vs-index comparison above
    cannot see a shard that was written to the DB but never indexed. That shard
    is returned by recent_shards and by retrieve(), and is invisible to
    shard_search -- forever, silently. It happened (2026-07-24), and the reason
    nobody caught it earlier is that the obvious check is a lie:

        SELECT count(*) FROM shards_fts        -- external-content FTS5:
                                               -- answered from `shards`, so it
                                               -- ALWAYS equals the row count

    The honest count comes from the fts5 `_docsize` shadow table, which holds
    one row per genuinely indexed document. Divergence there exits EXIT_INDEX.

    NULL embeddings are counted and reported but never alarmed on: embedding
    requires a reachable model (FTS does not), so it is best-effort by design.
    Reported so "best-effort" can never quietly become "silently never".
    """
    dbs = sorted(Path(vault_dir).glob("nougen_shards_*.db"))
    per_db: list[dict] = []
    tot_rows = tot_unindexed = tot_null_emb = 0
    for db in dbs:
        entry = {"db": db.name}
        try:
            conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            entry["error"] = str(exc)
            per_db.append(entry)
            continue
        try:
            entry["rows"] = int(conn.execute(
                "SELECT count(*) FROM shards").fetchone()[0])
            try:
                entry["fts_indexed"] = int(conn.execute(
                    "SELECT count(*) FROM shards_fts_docsize").fetchone()[0])
                entry["unindexed"] = int(conn.execute(
                    "SELECT count(*) FROM shards s WHERE NOT EXISTS "
                    "(SELECT 1 FROM shards_fts_docsize d WHERE d.id = s.id)"
                ).fetchone()[0])
            except sqlite3.Error as exc:
                entry["fts_indexed"] = None
                entry["unindexed"] = None
                entry["fts_error"] = str(exc)
            entry["null_embedding"] = int(conn.execute(
                "SELECT count(*) FROM shards WHERE embedding IS NULL").fetchone()[0])
            entry["triggers"] = sorted(r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND name IN ('shards_ai','shards_ad','shards_au')"))
        except sqlite3.Error as exc:
            entry["error"] = str(exc)
        finally:
            conn.close()
        tot_rows += entry.get("rows") or 0
        tot_unindexed += entry.get("unindexed") or 0
        tot_null_emb += entry.get("null_embedding") or 0
        per_db.append(entry)
    return {
        "_meaning": ("rows vs rows the FTS index actually contains "
                     "(fts5 _docsize); unindexed > 0 means written-but-unsearchable"),
        "databases": per_db,
        "total_rows": tot_rows,
        "total_unindexed": tot_unindexed,
        "total_null_embedding": tot_null_emb,
        "missing_triggers": [e["db"] for e in per_db
                             if len(e.get("triggers") or []) < 3],
    }


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
