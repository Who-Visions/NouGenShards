"""Crawl a website scope and shard every page (docs truth for sites that aren't Adobe's Markdown trees).

Breadth-first from start URL(s), following links whose URL starts with one of --scope prefixes
(full URL prefixes, e.g. https://ollama.com/library/gemma4). For each page it prefers a Markdown
source when the site offers one (<url>.md, as Mintlify docs do), else extracts readable text from the
HTML (scripts/styles/nav/footer dropped, headings/code/list structure kept). Raw text goes to
canon/<slug>/, one NouGen shard per page (split at 12k chars). No fetch stamp in shard bodies, so
re-runs dedupe by content hash; the manifest merges across runs.

  python web_shard.py https://ollama.com/library/gemma4:31b --scope https://ollama.com/library/gemma4 \
      --domain ollama-library-gemma4 --slug ollama-gemma4
"""
from __future__ import annotations

import argparse
import html as H
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

os.environ.setdefault("NOUGEN_VAULT_DIR", str(Path.home() / ".nougen" / "shards"))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from nougen_shards.core import capture  # noqa: E402
for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; never crash printing model output
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = {"User-Agent": "Mozilla/5.0 (NouGen web sharder)"}
PART = 12000
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".css", ".js", ".zip", ".pdf", ".mp4", ".woff", ".woff2", ".webp")


def fetch(url: str) -> tuple[str, str] | None:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                ctype = r.headers.get("Content-Type", "")
                if r.status == 200 and ("text" in ctype or "json" in ctype or "markdown" in ctype):
                    return ctype, r.read().decode("utf-8", "replace")
                return None
        except urllib.error.HTTPError as e:
            if e.code in (404, 403, 410):
                return None
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1 + 2 * attempt)
    return None


def html_text(h: str) -> str:
    h = re.sub(r"<(script|style|noscript|svg|nav|footer|header|template)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<pre[^>]*>(.*?)</pre>", lambda m: "\n```\n" + re.sub(r"<[^>]+>", "", m.group(1)) + "\n```\n", h, flags=re.S | re.I)
    h = re.sub(r"<h([1-6])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", h, flags=re.I)
    h = re.sub(r"<(li)[^>]*>", "\n- ", h, flags=re.I)
    h = re.sub(r"<(p|div|tr|br|section|article|table)[^>]*>", "\n", h, flags=re.I)
    t = H.unescape(re.sub(r"<[^>]+>", " ", h))
    lines = [re.sub(r"[ \t\u00a0]+", " ", l).strip() for l in t.splitlines()]
    out, prev = [], None
    for l in lines:
        if l and l != prev:
            out.append(l)
        prev = l
    return "\n".join(out)


def canonical(u: str) -> str:
    """One key per page: 'x.md' and 'x' are the same page on Mintlify-style docs (both were crawled on
    9/13/2026, doubling docs.ollama.com)."""
    u = urldefrag(u)[0]
    return u[:-3] if u.endswith(".md") and not u.endswith("/llms.md") else u


JUNK = re.compile(r"[*{}\s<>]|base-ui-|/_next/|/_mintlify/|mintlify-assets")  # script/CSS artifacts, not pages


def page(url: str) -> tuple[str, str, list[str], str] | None:
    """-> (source url, text, links, title) preferring a Markdown twin."""
    got = fetch(url)
    if not got:
        return None
    ctype, body = got
    title = ""
    links = [urldefrag(urljoin(url, m))[0] for m in re.findall(r'href="([^"]+)"', body)] if "html" in ctype else []
    if "html" in ctype:
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        title = H.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
        md = fetch(url.rstrip("/") + ".md")
        if md and not md[1].lstrip().lower().startswith(("<!doctype", "<html")):
            links += [urljoin(url, m) for m in re.findall(r"\]\(([^)\s]+)\)", md[1])]
            return url.rstrip("/") + ".md", md[1], links, title
        return url, html_text(body), links, title
    links = [urljoin(url, m) for m in re.findall(r"\]\(([^)\s]+)\)", body)]
    return url, body, links, title


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start", nargs="+")
    ap.add_argument("--scope", action="append", required=True, help="URL prefix to stay inside (repeatable)")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--max", type=int, default=400)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)

    def in_scope(u: str) -> bool:
        p = urlparse(u)
        return (p.scheme in ("http", "https") and not p.path.lower().endswith(SKIP_EXT) and not JUNK.search(p.path)
                and any(u.startswith(s) for s in a.scope))

    out = ROOT / "canon" / a.slug
    out.mkdir(parents=True, exist_ok=True)
    starts = [canonical(s) if not s.endswith("llms.txt") else s for s in a.start]
    seen = set(starts)
    queue, pages, missing, outside = deque(starts), {}, [], set()
    with ThreadPoolExecutor(a.workers) as ex:
        while queue and len(pages) < a.max:
            batch = [queue.popleft() for _ in range(min(len(queue), a.workers * 2))]
            for url, res in zip(batch, ex.map(page, batch)):
                if not res:
                    missing.append(url)
                    continue
                src, text, links, title = res
                pages[url] = {"src": src, "text": text, "title": title}
                for l in links:
                    l = canonical(l.split("?")[0] if "ollama.com" in l else l)
                    if in_scope(l):
                        if l not in seen:
                            seen.add(l)
                            queue.append(l)
                    elif l.startswith("http") and not JUNK.search(urlparse(l).path):
                        outside.add(l)
            print(f"  crawled {len(pages)}, queue {len(queue)}, missing {len(missing)}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    shards, new = [], 0
    for url in sorted(pages):
        text = pages[url]["text"]
        name = re.sub(r"[^\w.-]+", "_", urlparse(url).netloc + urlparse(url).path).strip("_")[:150] or "index"
        (out / f"{name}.md").write_text(f"SOURCE: {url}\n\n{text}", encoding="utf-8")
        title = (pages[url].get("title") or next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#") and l.lstrip("# ").strip()), "")
                 or urlparse(url).path)[:120]
        parts = [text[i:i + PART] for i in range(0, len(text), PART)] or [""]
        for k, body in enumerate(parts, 1):
            r = capture("doc-page", f"{title} ({urlparse(url).netloc}{urlparse(url).path})" + (f" part {k}/{len(parts)}" if len(parts) > 1 else ""),
                        f"SOURCE: {url}\nTEXT FROM: {pages[url]['src']}\nPART: {k}/{len(parts)}\n\n{body}",
                        tags=["web-docs", a.slug, urlparse(url).netloc], domain_key=a.domain, source_uri=url)
            new += isinstance(r, dict) and r.get("reason") == "written"
            shards.append({"url": url, "part": k, "shard": r.get("shard_id") if isinstance(r, dict) else None,
                           "db": r.get("db_index") if isinstance(r, dict) else None, "fetched_utc": stamp})
    mf = out / "_manifest.json"
    old = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    merged = {(e["url"], e["part"]): e for e in old.get("index", [])}
    merged.update({(e["url"], e["part"]): e for e in shards})
    have = {u for u, _ in merged}
    man = {"domain": a.domain, "scopes": sorted(set(old.get("scopes", [])) | set(a.scope)),
           "runs": old.get("runs", []) + [{"start": a.start, "fetched_utc": stamp, "pages": len(pages), "new_shards": new}],
           "pages": len(have), "shards": len(merged), "missing": sorted((set(old.get("missing", [])) | set(missing)) - have),
           "outside_links": sorted(set(old.get("outside_links", [])) | outside), "index": [merged[k] for k in sorted(merged)]}
    mf.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(json.dumps({"pages": len(pages), "shards": len(shards), "new_shards": new, "missing": len(missing),
                      "outside_links": len(outside), "dir": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
