"""Backfill arXiv cs.AI vault artifacts for a date gap via the export.arxiv.org API.

Writes BOTH vault artifacts:
- intelligence_shard_arxiv_{base_id}_{slug}.md  (format of Sol-Ai/tools/arxiv_rss_scanner.py;
  its dedupe glob stays authoritative)
- arxiv_cs_AI_{YYYYMMDD}_{Title_Slug}.md daily docs, keyed by the API `published`
  (v1 submission) timestamp — matching the historical daily-doc lane exactly.
  Shards use RSS announce dates instead, so daily docs must come from the API,
  never be derived from shards (announce-vs-submission date mismatch duplicates papers).

Dynamic per Rule 0.2: vault dir from env/config, dates from CLI or gap probe,
optional mirror via NOUGEN_ARXIV_MIRROR_DIR.
"""
import os
import re
import sys
import json
import glob
import time
import argparse
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arxiv_lane_config as _cfg  # noqa: E402

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
# arXiv's docs still print the http:// form, which 301s to https. urlopen follows
# that today, but a redirect-policy change would break the lane; request https
# directly and keep the env override for anyone who needs the documented URL.
API_URL, API_URL_SRC = _cfg.resolve(
    "NOUGEN_ARXIV_API_URL", "arxiv_api_url", "https://export.arxiv.org/api/query")
PAGE_SIZE, PAGE_SIZE_SRC = _cfg.resolve(
    "NOUGEN_ARXIV_PAGE_SIZE", "arxiv_page_size", "100", int)
RATE_DELAY, RATE_DELAY_SRC = _cfg.resolve(
    "NOUGEN_ARXIV_RATE_DELAY_S", "arxiv_rate_delay_s", "3.0", float)
MAX_TOTAL, MAX_TOTAL_SRC = _cfg.resolve(
    "NOUGEN_ARXIV_BACKFILL_MAX", "arxiv_backfill_max", "4000", int)
UA = os.environ.get("NOUGEN_ARXIV_UA", "NouGenAi-Orchestrator/4.0 (dave@whovisions.com)")

# Artifact name prefixes. These are the lane's NAMESPACE, not a category claim:
# the daily-doc prefix is what both the gap probe below and lane_freshness.py
# glob on, so writer and probe must always resolve from the same value or gap
# detection and freshness reporting drift apart. Multi-category since 2026-07-26.
DOC_PREFIX = _cfg.DOC_PREFIX
SHARD_PREFIX = _cfg.SHARD_PREFIX
TOPIC_PREFIX = _cfg.TOPIC_PREFIX
# Emit a progress line every N papers so a multi-hour backfill is observable.
PROGRESS_EVERY = int(os.environ.get("NOUGEN_ARXIV_PROGRESS_EVERY", "500"))

# arXiv's export API hard-fails (HTTP 500) once `start` reaches this offset, so
# NO single query can ever retrieve more than this many results no matter the
# page size. Measured 2026-07-26: start=9500 -> 200 with 500 entries;
# start=10000/12000/20000 -> 500. A 75,278-result window therefore has to be
# split into date sub-windows that each stay under the ceiling.
API_MAX_OFFSET, API_MAX_OFFSET_SRC = _cfg.resolve(
    "NOUGEN_ARXIV_API_MAX_OFFSET", "arxiv_api_max_offset", "10000", int)
# Aim comfortably below the ceiling; arXiv counts can drift up between the
# planning probe and the actual fetch.
CHUNK_TARGET, CHUNK_TARGET_SRC = _cfg.resolve(
    "NOUGEN_ARXIV_CHUNK_TARGET", "arxiv_chunk_target",
    str(int(API_MAX_OFFSET * 0.8)), int)
CHUNK_MAX_DEPTH = int(os.environ.get("NOUGEN_ARXIV_CHUNK_MAX_DEPTH", "12"))


def _resolve_vault_root():
    """Delegated to the shared lane config so the writer, the gap probe and
    lane_freshness.py can never resolve the vault three different ways."""
    return _cfg.resolve_vault_root()[0]


def index_existing(vault):
    """One directory scan -> the set of arXiv ids that already have a shard.

    Replaces a per-paper glob.glob(). Each glob is O(files-in-dir) on NTFS, so
    checking N papers against a directory of M files was O(N*M) — at 75k papers
    against a vault heading for 145k files that is quadratic and runs for days.
    One scandir plus set lookups is O(M + N). Returns (shard_ids, doc_names).
    """
    shard_ids, doc_names = set(), set()
    # Names are {SHARD_PREFIX}{base_id}_{slug}.md and base_id ("2607.21550")
    # never contains "_", so the id is exactly the run up to the first underscore.
    # Do not use a lazy .+? here: the slug is full of underscores and the match
    # would run past the id to the last one.
    shard_re = re.compile(re.escape(SHARD_PREFIX) + r"([^_]+)_")
    with os.scandir(vault) as it:
        for e in it:
            n = e.name
            if n.startswith(SHARD_PREFIX):
                if m := shard_re.match(n):
                    shard_ids.add(m.group(1))
            elif n.startswith(DOC_PREFIX):
                doc_names.add(n)
    return shard_ids, doc_names


def entry_category(entry):
    """This paper's own primary arXiv category, e.g. "cs.AI" or "econ.TH".

    The lane now pulls cs.*, q-fin.* and econ.* together, so a single global
    label would stamp an economics paper as cs.AI. Prefer arxiv:primary_category,
    fall back to the first atom:category, then to the configured label.
    """
    pc = entry.find(f"{ARXIV_NS}primary_category")
    if pc is not None and pc.get("term"):
        return pc.get("term")
    for c in entry.findall(f"{ATOM}category"):
        if c.get("term"):
            return c.get("term")
    return CATEGORY_LABEL


def slugify(text, max_len=80):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:max_len].rstrip("_")


DAILYDOC_SLUG_MAX = int(os.environ.get("NOUGEN_ARXIV_DAILYDOC_SLUG_MAX", "60"))
# Last-resort label only. Each paper's real primary category comes off its own
# API entry (see entry_category); this fires only when the entry omits one.
CATEGORY_LABEL = os.environ.get("NOUGEN_ARXIV_CATEGORY_LABEL", "unknown")

# Kept in lockstep with Sol-Ai/tools/arxiv_rss_scanner.py: if the daily scanner
# subscribes to four categories, the recovery lane must be able to backfill the
# same four, or capped/missed days are only ever recoverable as cs.AI.
FALLBACK_CATEGORIES = "cs.AI,cs.CL,cs.LG,cs.CV"


def resolve_categories():
    """env -> ~/.nougen/config.json -> logged fallback constant (Rule 0.2)."""
    raw = os.environ.get("NOUGEN_ARXIV_CATEGORIES")
    source = "env:NOUGEN_ARXIV_CATEGORIES"
    if not raw:
        try:
            cfg_path = os.path.join(os.path.expanduser("~"), ".nougen", "config.json")
            with open(cfg_path, encoding="utf-8") as f:
                v = json.load(f).get("arxiv_categories")
            if v:
                raw, source = (",".join(v) if isinstance(v, list) else str(v)), "config:arxiv_categories"
        except Exception:
            pass
    if not raw:
        raw, source = FALLBACK_CATEGORIES, "fallback-constant"
    return [c.strip() for c in re.split(r"[,\s]+", raw) if c.strip()], source


CATEGORIES, CATEGORIES_SOURCE = resolve_categories()


def dailydoc_slug(title, max_len=None):
    """Historical daily-doc filename style: case preserved, hyphens kept."""
    s = re.sub(r"[^A-Za-z0-9\- ]", "", title)
    s = re.sub(r"\s+", "_", s.strip())
    return s[: (max_len or DAILYDOC_SLUG_MAX)].rstrip("_")


def fetch_page(start_dt, end_dt, offset, page_size=None):
    cat_clause = " OR ".join(f"cat:{c}" for c in CATEGORIES)
    q = f"({cat_clause}) AND submittedDate:[{start_dt} TO {end_dt}]"
    params = urllib.parse.urlencode({
        "search_query": q,
        "start": offset,
        "max_results": page_size or PAGE_SIZE,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    })
    req = urllib.request.Request(f"{API_URL}?{params}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _bounds(day_start, day_end):
    """('2026-01-01','2026-01-31') -> ('202601010000','202601312359')."""
    return day_start.replace("-", "") + "0000", day_end.replace("-", "") + "2359"


def count_window(day_start, day_end):
    """totalResults for a date window, or -1 if the count can't be read."""
    s, e = _bounds(day_start, day_end)
    try:
        root = ET.fromstring(fetch_page(s, e, 0, page_size=1))
        tr = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
        return int(tr.text) if tr is not None and tr.text else -1
    except Exception:
        return -1


def plan_windows(day_start, day_end, depth=0):
    """Split [day_start, day_end] into sub-windows that each fit under the
    API's offset ceiling. Bisects by date until every piece is small enough.

    A single day that still exceeds the ceiling cannot be split further; it is
    returned anyway and the caller reports the shortfall rather than silently
    dropping the overflow.
    """
    total = count_window(day_start, day_end)
    if total <= CHUNK_TARGET or depth >= CHUNK_MAX_DEPTH:
        return [(day_start, day_end, total)]
    d0 = datetime.datetime.strptime(day_start, "%Y-%m-%d").date()
    d1 = datetime.datetime.strptime(day_end, "%Y-%m-%d").date()
    if d0 >= d1:
        return [(day_start, day_end, total)]
    mid = d0 + datetime.timedelta(days=(d1 - d0).days // 2)
    time.sleep(RATE_DELAY)
    left = plan_windows(day_start, mid.strftime("%Y-%m-%d"), depth + 1)
    time.sleep(RATE_DELAY)
    right = plan_windows((mid + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
                         day_end, depth + 1)
    return left + right


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", help="YYYY-MM-DD inclusive (default: probe gap)")
    ap.add_argument("--end", help="YYYY-MM-DD inclusive (default: today)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--print-config", action="store_true",
                    help="show every resolved value and where it came from")
    args = ap.parse_args()

    if args.print_config:
        print(_cfg.describe([
            ("api_url", API_URL, API_URL_SRC),
            ("page_size", PAGE_SIZE, PAGE_SIZE_SRC),
            ("rate_delay_s", RATE_DELAY, RATE_DELAY_SRC),
            ("max_total", MAX_TOTAL, MAX_TOTAL_SRC),
            ("api_max_offset", API_MAX_OFFSET, API_MAX_OFFSET_SRC),
            ("chunk_target", CHUNK_TARGET, CHUNK_TARGET_SRC),
        ]))
        return 0

    vault = _resolve_vault_root()
    if not os.path.isdir(vault):
        print(json.dumps({"error": f"vault dir missing: {vault}"}))
        return 1

    end = args.end or datetime.date.today().strftime("%Y-%m-%d")
    if args.start:
        start = args.start
    else:
        # probe: newest daily arxiv doc date + 1 day
        # Same DOC_PREFIX the writer uses, so probe and writer cannot drift.
        probe_re = re.compile(re.escape(DOC_PREFIX) + r"(\d{8})_")
        dates = sorted({
            m.group(1)
            for f in glob.iglob(os.path.join(vault, f"{DOC_PREFIX}*.md"))
            if (m := probe_re.match(os.path.basename(f)))
        })
        if not dates:
            print(json.dumps({"error": "no existing daily docs to derive gap from; pass --start"}))
            return 1
        d = datetime.datetime.strptime(dates[-1], "%Y%m%d").date() + datetime.timedelta(days=1)
        start = d.strftime("%Y-%m-%d")

    print(f"Backfilling {','.join(CATEGORIES)} (source: {CATEGORIES_SOURCE}) "
          f"submittedDate [{start} TO {end}] -> {vault}", file=sys.stderr)

    shard_ids, doc_names = index_existing(vault)
    print(f"indexed existing: {len(shard_ids)} shards, {len(doc_names)} daily docs",
          file=sys.stderr)

    # One query can only ever reach API_MAX_OFFSET, so split the range first.
    windows = plan_windows(start, end)
    planned = sum(t for _, _, t in windows if t > 0)
    oversized = [(s, e, t) for s, e, t in windows if t > API_MAX_OFFSET]
    print(f"planned {len(windows)} sub-window(s), ~{planned} papers", file=sys.stderr)
    for s, e, t in oversized:
        print(f"WARNING: sub-window {s}..{e} has {t} papers but the API ceiling "
              f"is {API_MAX_OFFSET}; the overflow is unreachable", file=sys.stderr)

    written, skipped = 0, 0
    docs_written, docs_skipped, docs_per_day = 0, 0, {}
    mirror = os.environ.get("NOUGEN_ARXIV_MIRROR_DIR")
    grand_scanned, grand_total = 0, 0
    for w_i, (w_start, w_end, w_total) in enumerate(windows, 1):
        start_dt, end_dt = _bounds(w_start, w_end)
        offset, total_avail = 0, None
        backoff = 30.0
        print(f"[{w_i}/{len(windows)}] window {w_start}..{w_end} (~{w_total})",
              file=sys.stderr)
        while offset < MAX_TOTAL and offset < API_MAX_OFFSET:
            try:
                xml_data = fetch_page(start_dt, end_dt, offset)
            except Exception as e:
                print(f"fetch failed at offset {offset}: {e}; backing off {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                if backoff > 240:
                    print(json.dumps({"error": "persistent arXiv API failure", "written": written, "skipped": skipped}))
                    return 2
                continue
            backoff = 30.0

            # Parse defensively: a truncated or non-XML body must retry via the
            # existing backoff, not crash the run with a bare ParseError.
            if not xml_data or not xml_data.strip():
                print(f"empty body at offset {offset}; backing off {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                if backoff > 240:
                    print(json.dumps({"error": "persistent empty arXiv API response",
                                      "written": written, "skipped": skipped}))
                    return 2
                continue
            try:
                root = ET.fromstring(xml_data)
            except ET.ParseError as e:
                print(f"unparseable XML at offset {offset}: {e}; backing off {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                if backoff > 240:
                    print(json.dumps({"error": f"persistent arXiv API parse failure: {e}",
                                      "written": written, "skipped": skipped}))
                    return 2
                continue

            entries = root.findall(f"{ATOM}entry")
            # Per the API manual, errors come back as a normal Atom feed carrying a
            # single entry titled "Error" -- otherwise indistinguishable from a
            # legitimately empty result set.
            if len(entries) == 1 and (entries[0].findtext(f"{ATOM}title") or "").strip().lower() == "error":
                detail = (entries[0].findtext(f"{ATOM}summary") or "unspecified").strip()
                print(json.dumps({"error": f"arXiv API error response: {detail}",
                                  "written": written, "skipped": skipped}))
                return 2

            if total_avail is None:
                tr = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
                total_avail = int(tr.text) if tr is not None and tr.text else -1
                print(f"totalResults: {total_avail}", file=sys.stderr)

            if not entries:
                break

            for e in entries:
                eid = e.findtext(f"{ATOM}id", "")
                versioned_id = eid.split("/abs/")[-1] if "/abs/" in eid else ""
                if not versioned_id:
                    continue
                base_id = re.sub(r"v\d+$", "", versioned_id)
                shard_exists = base_id in shard_ids

                title = re.sub(r"\s+", " ", e.findtext(f"{ATOM}title", "Untitled")).strip()
                abstract = re.sub(r"\s+", " ", e.findtext(f"{ATOM}summary", "")).strip()
                authors = ", ".join(
                    a.findtext(f"{ATOM}name", "").strip()
                    for a in e.findall(f"{ATOM}author")
                ) or "Unknown"
                published = e.findtext(f"{ATOM}published", "")
                try:
                    pub_dt = datetime.datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
                    published_iso = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    pub_date_text = pub_dt.strftime("%d %b %Y %H:%M:%S GMT")
                except Exception:
                    published_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    pub_date_text = published or "unknown"

                primary_cat = entry_category(e)
                link = f"https://arxiv.org/abs/{versioned_id}"
                pdf_url = f"https://arxiv.org/pdf/{versioned_id}"
                created_at_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

                md_content = f"""---
topic: {TOPIC_PREFIX}{base_id}
source: arxiv
category: TECHNICAL_DEEP_DIVE
arxiv_category: {primary_cat}
authors: {authors}
published_date: {published_iso}
arxiv_id: {versioned_id}
pdf_url: {pdf_url}
created_at: {created_at_iso}
---

# {title}

## Metadata
- **Authors:** {authors}
- **Published Date:** {pub_date_text}
- **arXiv Link:** [{link}]({link})
- **PDF Link:** [{pdf_url}]({pdf_url})

## Abstract
{abstract}

---
*Ingested via NouGenAi-Orchestrator API backfill (gap-fill lane) under the Dave @ Who Visions authorization system.*
"""
                if shard_exists:
                    skipped += 1
                else:
                    filename = f"{SHARD_PREFIX}{base_id}_{slugify(title)}.md"
                    if args.dry_run:
                        print(f"DRY shard: {filename}", file=sys.stderr)
                    else:
                        with open(os.path.join(vault, filename), "w", encoding="utf-8") as f:
                            f.write(md_content)
                    # Keep the index current so a duplicate id later in the same run
                    # is skipped rather than rewritten.
                    shard_ids.add(base_id)
                    written += 1

                # Daily doc keyed by v1 submission date (API `published`), window-bounded.
                pub_day = published[:10].replace("-", "")
                if start.replace("-", "") <= pub_day <= end.replace("-", ""):
                    doc_name = f"{DOC_PREFIX}{pub_day}_{dailydoc_slug(title)}.md"
                    doc_path = os.path.join(vault, doc_name)
                    if doc_name in doc_names or os.path.exists(doc_path):
                        docs_skipped += 1
                    else:
                        doc_content = f"""# {title}

**Published:** {published_iso}
**Authors:** {authors}
**Link:** http://arxiv.org/abs/{versioned_id}
**Category:** {primary_cat}

## Abstract
{abstract}
"""
                        if args.dry_run:
                            print(f"DRY doc: {doc_name}", file=sys.stderr)
                        else:
                            with open(doc_path, "w", encoding="utf-8") as f:
                                f.write(doc_content)
                            if mirror and os.path.isdir(mirror):
                                with open(os.path.join(mirror, doc_name), "w", encoding="utf-8") as f:
                                    f.write(doc_content)
                        doc_names.add(doc_name)
                        docs_written += 1
                        docs_per_day[pub_day] = docs_per_day.get(pub_day, 0) + 1

            offset += len(entries)
            if PROGRESS_EVERY and offset % PROGRESS_EVERY < PAGE_SIZE:
                print(f"progress: {offset}/{total_avail} scanned, "
                      f"{written} shards + {docs_written} docs written", file=sys.stderr)
            if total_avail is not None and 0 <= total_avail <= offset:
                break
            time.sleep(RATE_DELAY)

        grand_scanned += offset
        if total_avail and total_avail > 0:
            grand_total += total_avail

    # A run that stops on MAX_TOTAL must never look like a completed one. The
    # cap silently truncated results before 2026-07-26: a 75k-paper window with
    # the 4000 default reported success having covered 5% of it.
    truncated = bool(grand_total and grand_total > grand_scanned) or bool(oversized)
    summary = {
        "window": [start, end],
        "total_available": grand_total,
        "shards_written": written,
        "shards_skipped_existing": skipped,
        "daily_docs_written": docs_written,
        "daily_docs_skipped_existing": docs_skipped,
        "daily_docs_per_day": dict(sorted(docs_per_day.items())),
        "vault": vault,
        "mirror": mirror or None,
        "scanned": grand_scanned,
        "sub_windows": len(windows),
        "truncated": truncated,
    }
    if truncated:
        summary["not_done"] = (
            f"stopped at {grand_scanned} of {grand_total} papers "
            f"(NOUGEN_ARXIV_BACKFILL_MAX={MAX_TOTAL}); "
            f"{grand_total - grand_scanned} unscanned — raise the cap, or lower NOUGEN_ARXIV_CHUNK_TARGET so sub-windows fit the API ceiling"
        )
        print(f"WARNING: {summary['not_done']}", file=sys.stderr)
    print(json.dumps(summary))
    return 2 if truncated else 0


if __name__ == "__main__":
    sys.exit(main())
