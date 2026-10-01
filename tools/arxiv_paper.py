#!/usr/bin/env python3
"""Single-paper arXiv recall: metadata, LaTeX full text, and claim checks.

    arxiv_paper.py lookup 2609.34785            # metadata via the arXiv API (both id styles)
    arxiv_paper.py fulltext 2609.34785          # fetch e-print source, cache extracted .tex text
    arxiv_paper.py claim 2609.34785 '55\\.0\\%'  # where does this appear in the paper BODY?

Why: radar and lab decisions were made from abstracts only. The e-print source is the
paper's own LaTeX, so a claim can be checked against the body with plain text search,
no PDF parsing. Clean-room: method inspired by Tom Brown's arxiv.py (GPL-3), no code taken.

Disk discipline (this node runs near full): only extracted .tex text is kept, under
~/.nougen/shards/lab/papers/<id>/fulltext.tex; downloads over MAX_SOURCE_BYTES are refused.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import tarfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = "nougen-radar/arxiv_paper (+phoebus)"
CACHE = Path(os.path.expanduser("~/.nougen/shards/lab/papers"))
MAX_SOURCE_BYTES = 25_000_000
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_NEW = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
_OLD = re.compile(r"^([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$", re.I)


def normalize_id(ref: str) -> str:
    """Accept '2609.34785', 'arXiv:2609.34785v2', 'hep-th/9711200', abs/pdf URLs. Version kept if given."""
    r = ref.strip()
    r = re.sub(r"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|e-print)/", "", r)
    r = re.sub(r"\.pdf$", "", r)
    r = re.sub(r"^arxiv:", "", r, flags=re.I)
    for rx in (_NEW, _OLD):
        m = rx.match(r)
        if m:
            return m.group(1) + (m.group(2) or "")
    raise ValueError(f"not an arXiv identifier: {ref!r}")


def _get(url: str, timeout: float = 40.0, retries: int = 4) -> bytes:
    """GET with arXiv etiquette: on 429/503 honour Retry-After (else back off 5s, 10s, 20s...)."""
    import urllib.error
    for attempt in range(retries + 1):
        try:
            return _get_once(url, timeout)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == retries:
                raise
            wait = e.headers.get("Retry-After")
            time.sleep(min(120.0, float(wait)) if wait and wait.isdigit() else 5.0 * 2 ** attempt)
        except (TimeoutError, urllib.error.URLError):  # arXiv throttles by slowing down, too
            if attempt == retries:
                raise
            time.sleep(5.0 * 2 ** attempt)
    raise AssertionError("unreachable")


def _get_once(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        length = int(r.headers.get("Content-Length") or 0)
        if length > MAX_SOURCE_BYTES:
            raise IOError(f"refusing {length} bytes (> {MAX_SOURCE_BYTES})")
        data = r.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise IOError(f"download exceeded {MAX_SOURCE_BYTES} bytes")
        return data


def parse_entry(xml: bytes) -> dict:
    e = ET.fromstring(xml).find("a:entry", NS)
    if e is None or e.find("a:title", NS) is None:
        raise LookupError("arXiv API returned no entry")
    text = lambda tag: " ".join((e.findtext(tag, default="", namespaces=NS) or "").split())
    return {
        "id": e.findtext("a:id", namespaces=NS).split("/abs/")[-1],
        "title": text("a:title"),
        "authors": [" ".join(a.findtext("a:name", namespaces=NS).split()) for a in e.findall("a:author", NS)],
        "abstract": text("a:summary"),
        "published": text("a:published")[:10],
        "updated": text("a:updated")[:10],
        "primary_category": (e.find("arxiv:primary_category", NS).get("term") if e.find("arxiv:primary_category", NS) is not None else ""),
        "categories": [c.get("term") for c in e.findall("a:category", NS)],
        "comment": text("arxiv:comment") or None,
        "journal_ref": text("arxiv:journal_ref") or None,
        "doi": text("arxiv:doi") or None,
    }


def lookup(ref: str) -> dict:
    aid = normalize_id(ref)
    return parse_entry(_get(f"https://export.arxiv.org/api/query?id_list={aid}&max_results=1"))


def extract_tex(blob: bytes) -> str:
    """e-print payloads are a gzipped tar of sources, a single gzipped .tex, or a bare PDF."""
    if blob[:4] == b"%PDF":
        raise LookupError("no LaTeX source: this paper is PDF-only on arXiv")
    raw = gzip.decompress(blob) if blob[:2] == b"\x1f\x8b" else blob
    try:
        with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
            texs = {m.name: tf.extractfile(m).read().decode("utf-8", "replace")
                    for m in tf.getmembers() if m.isfile() and m.name.endswith(".tex")}
    except tarfile.ReadError:
        texs = {"main.tex": raw.decode("utf-8", "replace")}
    if not texs:
        raise LookupError("source archive contains no .tex files")
    main = next((n for n, t in texs.items() if "\\documentclass" in t), max(texs, key=lambda n: len(texs[n])))
    body = texs[main]

    def inline(text: str, depth: int = 0) -> str:  # resolve \input{...} / \include{...}
        if depth > 5:
            return text
        def sub(m):
            name = m.group(1) if m.group(1).endswith(".tex") else m.group(1) + ".tex"
            hit = next((t for n, t in texs.items() if n.endswith(name)), None)
            return inline(hit, depth + 1) if hit is not None else m.group(0)
        return re.sub(r"\\(?:input|include)\{([^}]+)\}", sub, text)

    return re.sub(r"(?m)(?<!\\)%.*$", "", inline(body))  # drop LaTeX comments


def fulltext(ref: str, refresh: bool = False) -> Path:
    aid = normalize_id(ref)
    out = CACHE / aid.replace("/", "_") / "fulltext.tex"
    if out.exists() and not refresh:
        return out
    tex = extract_tex(_get(f"https://arxiv.org/e-print/{aid}"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tex, encoding="utf-8")
    meta = out.parent / "meta.json"
    if not meta.exists():
        time.sleep(3)  # arXiv API etiquette between the two calls
        try:  # metadata is a convenience; never lose the full text over it
            meta.write_text(json.dumps(lookup(aid), indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            (out.parent / "meta.error").write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
    return out


def body_only(tex: str) -> str:
    """The paper minus its abstract. A claim 'verified in the body' must not be satisfied by the
    abstract, which is part of the LaTeX source."""
    return re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", " ", tex, flags=re.S)


def claim(ref: str, pattern: str, context: int = 90) -> list[str]:
    """Every place a claim pattern appears in the BODY (abstract excluded), with surrounding text."""
    text = " ".join(body_only(fulltext(ref).read_text(encoding="utf-8")).split())
    return [text[max(0, m.start() - context): m.end() + context] for m in re.finditer(pattern, text)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("lookup", "fulltext"):
        p = sub.add_parser(name)
        p.add_argument("ref")
    sub.choices["fulltext"].add_argument("--refresh", action="store_true")
    pc = sub.add_parser("claim")
    pc.add_argument("ref")
    pc.add_argument("pattern")
    a = ap.parse_args()
    if a.cmd == "lookup":
        print(json.dumps(lookup(a.ref), indent=2))
    elif a.cmd == "fulltext":
        p = fulltext(a.ref, a.refresh)
        print(f"{p} ({p.stat().st_size} bytes)")
    else:
        hits = claim(a.ref, a.pattern)
        print(f"{len(hits)} occurrence(s) in the body")
        for h in hits[:20]:
            print(f"  ...{h}...")
        return 0 if hits else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
