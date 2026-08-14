"""Drain the deliberately-deferred arXiv backlog into the shard DBs.

`core.DEFAULT_BACKLOG_GLOBS` holds arXiv artifacts OUT of ingestion under a
forward-only policy — not because they are noise, but because they are
"legitimately memory, deliberately deferred ... when embedding capacity is the
bottleneck". Draining that backlog is therefore a deliberate, separately
authorised campaign (GM authorised 2026-07-26), never a side effect of a repair
sweep. This tool is that campaign and nothing else.

`core.capture()` embeds inline ("shards are born recallable"), so one pass does
both ingest and embedding. It also dedupes on a UNIQUE file_hash, so this tool
is idempotent: re-running skips everything already ingested.

SCOPE — intelligence shards only, by default. The backlog globs cover two
artifact families that describe the SAME papers: `intelligence_shard_arxiv_*.md`
(rich: frontmatter with arxiv_id, authors, pdf_url, category) and
`arxiv_*.md` daily docs (a thinner rendering of the same title+abstract).
Ingesting both would put two near-duplicate rows in recall for every paper —
precisely the flooding the NOISE policy exists to prevent. Override with
NOUGEN_ARXIV_INGEST_GLOBS only if you actually want both.

Env (Rule 0.2 — nothing environment-shaped is baked in):
  NOUGEN_VAULT_DIR                vault root (else ~/.nougen/config.json)
  NOUGEN_ARXIV_INGEST_GLOBS       ';'-separated filename globs to drain
  NOUGEN_ARXIV_INGEST_TAGS        ';'-separated tags applied to each shard
  NOUGEN_ARXIV_INGEST_PROGRESS    progress line every N files
  NOUGEN_ARXIV_INGEST_LIMIT       stop after N files (0 = no limit)
"""
import argparse
import fnmatch
import json
import os
import sys
import time


import arxiv_lane_config as cfg


def _resolve_vault_root():
    """Kept as a thin alias so existing callers/imports do not break."""
    return cfg.resolve_vault_root()[0]


# Default scope is derived from the lane's own shard prefix rather than a second
# copy of the literal — change the prefix once and the drain follows.
GLOBS, GLOBS_SRC = cfg.resolve_list(
    "NOUGEN_ARXIV_INGEST_GLOBS", "arxiv_ingest_globs", cfg.SHARD_PREFIX + "*.md")
TAGS, TAGS_SRC = cfg.resolve_list(
    "NOUGEN_ARXIV_INGEST_TAGS", "arxiv_ingest_tags",
    "ingested;arxiv;research;backlog-drain")
PROGRESS_EVERY, PROGRESS_SRC = cfg.resolve(
    "NOUGEN_ARXIV_INGEST_PROGRESS", "arxiv_ingest_progress", "250", int)
LIMIT, LIMIT_SRC = cfg.resolve(
    "NOUGEN_ARXIV_INGEST_LIMIT", None, "0", int)
EVENT_TYPE, EVENT_TYPE_SRC = cfg.resolve(
    "NOUGEN_ARXIV_INGEST_EVENT_TYPE", "arxiv_ingest_event_type", "INGEST")


def local_density(content):
    """core.calculate_contrastive_perplexity's OWN gzip fallback, computed here.

    Profiled 2026-07-26: capture() spends ~1.2s of its ~1.38s per document
    inside calculate_contrastive_perplexity, which issues FOUR model
    round-trips per shard — embedding is a single call and only ~13% of the
    cost. Supplying density_score short-circuits that (core.py:807), taking the
    drain from ~0.7/s to roughly 5/s: ~28 hours down to ~4.

    This is not a made-up constant. It is the identical compression-ratio
    heuristic core falls back to whenever the models are unavailable, so shards
    ingested here carry the same kind of score they would have gotten on a
    model-less host — not a fabricated 1.0.
    """
    import zlib
    try:
        raw = content.encode("utf-8")
        ratio = len(zlib.compress(raw)) / max(1, len(raw))
        return float(min(1.0, max(0.1, ratio * 1.5)))
    except Exception:
        return 0.5


def iter_backlog(vault):
    """One scandir pass. The vault is ~145k files in a flat directory, so a
    per-glob glob.glob() would re-walk the whole directory once per pattern."""
    with os.scandir(vault) as it:
        for e in it:
            if e.is_file() and any(fnmatch.fnmatch(e.name, g) for g in GLOBS):
                yield e.name, e.path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--vault", default=None)
    ap.add_argument("--execute", action="store_true",
                    help="without this, counts only and writes nothing")
    ap.add_argument("--print-config", action="store_true",
                    help="show every resolved value and where it came from")
    args = ap.parse_args()

    if args.print_config:
        print(cfg.describe([
            ("ingest_globs", ";".join(GLOBS), GLOBS_SRC),
            ("ingest_tags", ";".join(TAGS), TAGS_SRC),
            ("progress_every", PROGRESS_EVERY, PROGRESS_SRC),
            ("limit", LIMIT, LIMIT_SRC),
            ("event_type", EVENT_TYPE, EVENT_TYPE_SRC),
        ]))
        return 0

    vault = args.vault or _resolve_vault_root()
    if not os.path.isdir(vault):
        print(json.dumps({"error": f"vault dir missing: {vault}"}))
        return 1

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== arXiv backlog drain [{mode}] vault={vault} globs={GLOBS} ===",
          flush=True)

    files = sorted(iter_backlog(vault))
    if LIMIT:
        files = files[:LIMIT]
    print(f"backlog files matched: {len(files)}", flush=True)
    if not args.execute:
        print(json.dumps({"mode": "dry-run", "matched": len(files),
                          "globs": GLOBS, "tags": TAGS, "vault": vault}))
        return 0

    from nougen_shards import core as shards

    captured = skipped = failed = 0
    t0 = time.time()
    for i, (name, path) in enumerate(files, 1):
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # capture() returns False on a dedup hit or a junk-gate rejection;
            # both mean "already handled / not wanted", not an error.
            if shards.capture(EVENT_TYPE, name, content, list(TAGS),
                              density_score=local_density(content)):
                captured += 1
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"  FAIL {name}: {type(e).__name__}: {e}", flush=True)
        if PROGRESS_EVERY and i % PROGRESS_EVERY == 0:
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(files) - i) / rate if rate else 0
            print(f"progress: {i}/{len(files)} captured={captured} "
                  f"skipped={skipped} failed={failed} "
                  f"{rate:.1f}/s eta={eta/60:.0f}m", flush=True)

    print(json.dumps({
        "mode": "execute", "matched": len(files), "captured": captured,
        "skipped_dedupe_or_junk": skipped, "failed": failed,
        "elapsed_s": round(time.time() - t0, 1), "vault": vault,
    }), flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
