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

ATOM = "{http://www.w3.org/2005/Atom}"
API_URL = os.environ.get("NOUGEN_ARXIV_API_URL", "http://export.arxiv.org/api/query")
PAGE_SIZE = int(os.environ.get("NOUGEN_ARXIV_PAGE_SIZE", "100"))
RATE_DELAY = float(os.environ.get("NOUGEN_ARXIV_RATE_DELAY_S", "3.0"))
MAX_TOTAL = int(os.environ.get("NOUGEN_ARXIV_BACKFILL_MAX", "4000"))
UA = os.environ.get("NOUGEN_ARXIV_UA", "NouGenAi-Orchestrator/4.0 (dave@whovisions.com)")


def _resolve_vault_root():
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return env
    try:
        cfg_path = os.path.join(os.path.expanduser("~"), ".nougen", "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            vd = json.load(f).get("vault_dir")
        if vd:
            return vd
    except Exception:
        pass
    return r"C:\Users\super\Watchtower\vault"


def slugify(text, max_len=80):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:max_len].rstrip("_")


DAILYDOC_SLUG_MAX = int(os.environ.get("NOUGEN_ARXIV_DAILYDOC_SLUG_MAX", "60"))
CATEGORY_LABEL = os.environ.get("NOUGEN_ARXIV_CATEGORY_LABEL", "cs.AI (Artificial Intelligence)")


def dailydoc_slug(title, max_len=None):
    """Historical daily-doc filename style: case preserved, hyphens kept."""
    s = re.sub(r"[^A-Za-z0-9\- ]", "", title)
    s = re.sub(r"\s+", "_", s.strip())
    return s[: (max_len or DAILYDOC_SLUG_MAX)].rstrip("_")


def fetch_page(start_dt, end_dt, offset):
    q = f"cat:cs.AI AND submittedDate:[{start_dt} TO {end_dt}]"
    params = urllib.parse.urlencode({
        "search_query": q,
        "start": offset,
        "max_results": PAGE_SIZE,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    })
    req = urllib.request.Request(f"{API_URL}?{params}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", help="YYYY-MM-DD inclusive (default: probe gap)")
    ap.add_argument("--end", help="YYYY-MM-DD inclusive (default: today)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    vault = _resolve_vault_root()
    if not os.path.isdir(vault):
        print(json.dumps({"error": f"vault dir missing: {vault}"}))
        return 1

    end = args.end or datetime.date.today().strftime("%Y-%m-%d")
    if args.start:
        start = args.start
    else:
        # probe: newest daily arxiv doc date + 1 day
        dates = sorted({
            m.group(1)
            for f in glob.iglob(os.path.join(vault, "arxiv_cs_AI_*.md"))
            if (m := re.match(r"arxiv_cs_AI_(\d{8})_", os.path.basename(f)))
        })
        if not dates:
            print(json.dumps({"error": "no existing daily docs to derive gap from; pass --start"}))
            return 1
        d = datetime.datetime.strptime(dates[-1], "%Y%m%d").date() + datetime.timedelta(days=1)
        start = d.strftime("%Y-%m-%d")

    start_dt = start.replace("-", "") + "0000"
    end_dt = end.replace("-", "") + "2359"
    print(f"Backfilling cs.AI submittedDate [{start_dt} TO {end_dt}] -> {vault}", file=sys.stderr)

    written, skipped, offset, total_avail = 0, 0, 0, None
    docs_written, docs_skipped, docs_per_day = 0, 0, {}
    mirror = os.environ.get("NOUGEN_ARXIV_MIRROR_DIR")
    backoff = 30.0
    while offset < MAX_TOTAL:
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

        root = ET.fromstring(xml_data)
        if total_avail is None:
            tr = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
            total_avail = int(tr.text) if tr is not None else -1
            print(f"totalResults: {total_avail}", file=sys.stderr)

        entries = root.findall(f"{ATOM}entry")
        if not entries:
            break

        for e in entries:
            eid = e.findtext(f"{ATOM}id", "")
            versioned_id = eid.split("/abs/")[-1] if "/abs/" in eid else ""
            if not versioned_id:
                continue
            base_id = re.sub(r"v\d+$", "", versioned_id)
            shard_exists = bool(glob.glob(os.path.join(vault, f"intelligence_shard_arxiv_{base_id}_*.md")))

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

            link = f"https://arxiv.org/abs/{versioned_id}"
            pdf_url = f"https://arxiv.org/pdf/{versioned_id}"
            created_at_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            md_content = f"""---
topic: arxiv_cs_ai_{base_id}
source: arxiv
category: TECHNICAL_DEEP_DIVE
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
                filename = f"intelligence_shard_arxiv_{base_id}_{slugify(title)}.md"
                if args.dry_run:
                    print(f"DRY shard: {filename}", file=sys.stderr)
                else:
                    with open(os.path.join(vault, filename), "w", encoding="utf-8") as f:
                        f.write(md_content)
                written += 1

            # Daily doc keyed by v1 submission date (API `published`), window-bounded.
            pub_day = published[:10].replace("-", "")
            if start.replace("-", "") <= pub_day <= end.replace("-", ""):
                doc_name = f"arxiv_cs_AI_{pub_day}_{dailydoc_slug(title)}.md"
                doc_path = os.path.join(vault, doc_name)
                if os.path.exists(doc_path):
                    docs_skipped += 1
                else:
                    doc_content = f"""# {title}

**Published:** {published_iso}
**Authors:** {authors}
**Link:** http://arxiv.org/abs/{versioned_id}
**Category:** {CATEGORY_LABEL}

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
                    docs_written += 1
                    docs_per_day[pub_day] = docs_per_day.get(pub_day, 0) + 1

        offset += len(entries)
        if total_avail is not None and 0 <= total_avail <= offset:
            break
        time.sleep(RATE_DELAY)

    print(json.dumps({
        "window": [start, end],
        "total_available": total_avail,
        "shards_written": written,
        "shards_skipped_existing": skipped,
        "daily_docs_written": docs_written,
        "daily_docs_skipped_existing": docs_skipped,
        "daily_docs_per_day": dict(sorted(docs_per_day.items())),
        "vault": vault,
        "mirror": mirror or None,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
