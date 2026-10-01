#!/usr/bin/env python3
"""NouGen research lab watcher: arXiv cs.AR (hardware architecture) -> graft candidates.

Pipeline (deterministic; it screens, it does not judge):
  fetch new submissions -> fleet-relevance classes -> candidate queue + digest.

What it deliberately does NOT do: decide novelty, or write shards. A keyword classifier can
say "this paper touches placement / KV streaming / behavior verification"; only a read of
the abstract against the CURRENT architecture can say "this is new". Every queue entry is
marked novelty="unjudged"; promotion to a shard is a separate, explicit act (NouGenMorph
engine score, then `nougen add`).

Reuses the canonical radar's fetch/parse (tools/arxiv_rss_radar.py) so there is one copy of
the arXiv plumbing. Lab state lives apart from the radar's beacon/review lanes:
  ~/.nougen/shards/lab/<channel>/{cursor.json,queue.json,digests/}

  arxiv_lab_watch.py --channel cs.AR            # fetch today's feed, queue new candidates
  arxiv_lab_watch.py --channel cs.AR --backfill # also seed from /list/<channel>/recent + arXiv API
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

_HERE = Path(__file__).resolve().parent
LAB_ROOT = Path(os.path.expanduser("~/.nougen/shards/lab"))
UA = "nougen-lab-watch/0.1 (+phoebus)"


def _radar():
    spec = importlib.util.spec_from_file_location("arxiv_rss_radar", _HERE / "arxiv_rss_radar.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("arxiv_rss_radar", mod)
    spec.loader.exec_module(mod)
    return mod


# Each class is a fleet constraint or architecture seam, not a topic. Word-boundary regexes so
# short tokens never fire inside longer words. `strong` classes count double.
CLASSES = {
    "placement_scheduling": (2, r"\b(profile-guided|offload(?:ing)?|heterogeneous|engine selection|host-(?:versus|vs\.?)-\w+|workload placement|placement decisions?|request scheduling|task scheduling|resource budget)\b"),
    "context_streaming":    (2, r"\b(kv cache|kv history|prefix cach\w*|streaming|speculative decoding|long-context|context window)\b"),
    "behavior_verification": (2, r"\b(behavior model\w*|behaviou?r ir|golden (?:model|reference)|functional behaviou?r|equivalence check\w*|specification-behavior)\b"),
    "agentic_systems":      (2, r"\b(llm agents?|agentic|self-improv\w*|multi-agent|agent for)\b"),
    "engine_portfolio":     (2, r"\b(multi-engine|engine combination|engine abstraction\w*|resource budget|design space|aggregate execution cost|workload-aware)\b"),
    "memory_traffic":       (2, r"\b(memory-bound|memory bandwidth|data movement|memory traffic|io-aware|fus(?:e|es|ed|ion)|epilogue)\b"),
    "low_bit_inference":    (1, r"\b(ternary|bitnet|low-bit|quantiz\w*|int4|mixed-precision)\b"),
    "diagnostics":          (1, r"\b(bottleneck|profil(?:er|ing|ed)|tracing|telemetry|observab\w*)\b"),
    "isolation_safety":     (1, r"\b(cheri|compartmentali[sz]ation|capabilit(?:y|ies)-based|memory safety|sandbox\w*)\b"),
}
# Hardware-only vocabulary that makes a hit non-transferable to a CPU-only, swap-bound node
# unless the paper ALSO names a transferable mechanism (>=2 distinct classes).
HW_ONLY = re.compile(r"\b(rtl|asic|fpga|analog|neuromorphic|spiking|dram controller|ddr[0-9]|lpddr[0-9]|photonic|memristor|hls)\b")
MECHANISM_CUE = re.compile(r"\b(we (?:present|propose|introduce|show|find)|this (?:paper|work) (?:presents|proposes|introduces))\b")
THRESHOLD = 4   # weighted class score to enter the lab queue (tier 'graft')
WATCH = 2       # 2..THRESHOLD-1: listed in the digest only (tier 'watch'), never queued


def classify(title: str, abstract: str) -> dict:
    text = f"{title}. {abstract}".lower()
    hits = {name: w for name, (w, rx) in CLASSES.items() if re.search(rx, text)}
    score = sum(hits.values())
    hw_only = bool(HW_ONLY.search(text)) and len(hits) < 2
    return {
        "classes": sorted(hits),
        "score": score,
        "hw_only": hw_only,
        "mechanism_cue": bool(MECHANISM_CUE.search(text)),
        "graft": score >= THRESHOLD and not hw_only,
        "tier": "graft" if (score >= THRESHOLD and not hw_only) else ("watch" if score >= WATCH and not hw_only else "skip"),
    }


def _paths(channel: str) -> dict:
    root = LAB_ROOT / channel
    return {"root": root, "cursor": root / "cursor.json", "queue": root / "queue.json", "digests": root / "digests"}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _entry(arxiv_id: str, title: str, abstract: str, meta: dict) -> dict:
    c = classify(title, abstract)
    return {
        "id": arxiv_id, "title": title, "abstract": abstract[:1400], **meta, **c,
        "novelty": "unjudged",  # never inferred here; see module docstring
        "first_seen": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def fetch_feed(channel: str, cursor: dict, radar) -> tuple[list[dict], dict]:
    """Today's RSS items via the canonical radar fetch/parse. Returns (items, new cursor info)."""
    content, hdr = radar.fetch_arxiv_rss_conditional(channel, cursor)
    if hdr.get("status") == 304 or not content:
        return [], {}
    out = []
    for it in ET.fromstring(content).findall("./channel/item"):
        p = radar.parse_arxiv_item(it)
        if p.get("id"):
            out.append(_entry(p["id"], p["title"], p["abstract"],
                              {"announce_type": p.get("announce_type"), "primary_category": p.get("primary_category")}))
    return out, {"etag": hdr.get("etag"), "last_modified": hdr.get("last_modified")}


def backfill_recent(channel: str) -> list[dict]:
    """The /list/<channel>/recent page (last ~5 announce days) + arXiv API for abstracts."""
    req = urllib.request.Request(f"https://arxiv.org/list/{channel}/recent?skip=0&show=500", headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    ids = list(dict.fromkeys(re.findall(r'href\s*=\s*"/abs/(\d{4}\.\d{4,5})"', html)))
    ns, out = {"a": "http://www.w3.org/2005/Atom"}, []
    for i in range(0, len(ids), 60):
        chunk = ids[i:i + 60]
        url = f"http://export.arxiv.org/api/query?max_results={len(chunk)}&id_list={','.join(chunk)}"
        xml = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40).read()
        for e in ET.fromstring(xml).findall("a:entry", ns):
            aid = e.findtext("a:id", namespaces=ns).split("/abs/")[-1].split("v")[0]
            out.append(_entry(aid, " ".join(e.findtext("a:title", namespaces=ns).split()),
                              " ".join(e.findtext("a:summary", namespaces=ns).split()),
                              {"published": e.findtext("a:published", namespaces=ns)[:10]}))
        time.sleep(3)  # arXiv API etiquette
    return out


def run(channel: str = "cs.AR", backfill: bool = False, now: dt.datetime | None = None) -> dict:
    radar = _radar()
    P = _paths(channel)
    P["digests"].mkdir(parents=True, exist_ok=True)
    cursor = _load(P["cursor"], {"seen_ids": [], "etag": None, "last_modified": None})
    queue = _load(P["queue"], [])
    seen = set(cursor.get("seen_ids", []))

    items, newhdr = fetch_feed(channel, {"channels": {channel.lower(): cursor}}, radar)
    if backfill:
        items += backfill_recent(channel)
    fresh, ids_now = [], set()
    for e in items:
        if e["id"] in seen or e["id"] in ids_now:
            continue
        ids_now.add(e["id"])
        fresh.append(e)
    queue_ids = {q["id"] for q in queue}
    added = [e for e in fresh if e["graft"] and e["id"] not in queue_ids]
    queue.extend(added)
    cursor.update(newhdr)
    cursor["seen_ids"] = sorted(seen | ids_now)[-20000:]

    P["queue"].write_text(json.dumps(queue, indent=2), encoding="utf-8")
    P["cursor"].write_text(json.dumps(cursor, indent=2), encoding="utf-8")
    slug = (now or dt.datetime.now()).strftime("%Y-%m-%d")
    watch = [e for e in fresh if e["tier"] == "watch"]
    lines = [f"# Lab watch: arXiv {channel} - {slug}", "",
             f"{len(fresh)} new papers screened, {len(added)} graft candidates, {len(watch)} on watch (novelty UNJUDGED; nothing sharded).", ""]
    for e in sorted(added, key=lambda x: -x["score"]):
        lines += [f"- **{e['id']}** [{e['score']}] {e['title']}", f"  classes: {', '.join(e['classes'])}"]
    if watch:
        lines += ["", "## Watch (near-misses, not queued)"] + [f"- {e['id']} [{e['score']}] {e['title']}" for e in sorted(watch, key=lambda x: -x["score"])]
    (P["digests"] / f"lab_{channel}_{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"channel": channel, "screened": len(fresh), "candidates_added": len(added), "watch": len(watch), "queue_size": len(queue),
            "status": "success" if items or newhdr else "noop"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--channel", default="cs.AR")
    ap.add_argument("--backfill", action="store_true", help="also seed from /list/<channel>/recent + arXiv API")
    a = ap.parse_args()
    print(json.dumps(run(a.channel, a.backfill)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
