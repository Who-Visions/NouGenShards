#!/usr/bin/env python3
"""arXiv RSS Radar & Automated 3-Lane Route Engine (Phoebus Fleet Standard).

Implements the official Peer Advisory Blueprint (from @openrouter:stealth/space-bunny-alpha):
  - 3-Lane Topology:
      1. beacon (p99.5, cap 10) -> Immediate operator & fleet beacon alerts.
      2. review (p97.0, cap 60) -> Human & downstream node specialist queue.
      3. shard (p0.0..p96.9)   -> Searchable substrate memory (108K+ cluster), 0 active load.
  - Formula:
      priority_pct = 0.70 * global_pct + 0.30 * primary_category_pct
  - Category Priors & Conditional Gates (cs.AI, cs.LG, cs.MA, cs.CL, etc.)
  - Dual Cadence:
      * Hourly Delta Sweep (--sweep): Conditional ETag/Last-Modified cursor, exits if unchanged.
      * Daily 05:15 AM ET Reconciliation (--reconcile): Full settlement & morning beacon digest.
"""

import argparse
import datetime
import email.utils
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Paths
RADAR_DIR = Path(os.path.expanduser("~/.nougen/shards/radar"))
ROUTE_RECIPE_PATH = RADAR_DIR / "route-v1.json"
CURSOR_PATH = RADAR_DIR / "cursor.json"
QUEUES_DIR = RADAR_DIR / "queues"
DIGESTS_DIR = RADAR_DIR / "digests"

NAMESPACES = {
    "arxiv": "http://arxiv.org/schemas/atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
}

DEFAULT_USER_AGENT = os.environ.get(
    "NOUGEN_ARXIV_UA",
    "NouGenAi-Orchestrator/4.0 (Observatory; fleet-mesh; +https://whovisions.com)"
)

# Core pillars for scoring
OBSERVATORY_PILLARS = {
    "Agentic Architecture": ["agent", "agents", "multi-agent", "agentic", "tool use", "harness", "workflow", "bounded-autonomy"],
    "Memory & World Models": ["memory", "episodic", "world model", "counterfactual", "retrieval", "rag", "dense memory"],
    "Inference & Speculative": ["inference", "multi-token", "kv-cache", "speculative decoding", "gpu acceleration", "latency", "quantization"],
    "Context Virtualization": ["context compression", "long context", "attention sink", "state compaction", "sandbox intercept"],
    "Embodied & VLA": ["vla", "vision-language-action", "robotics", "physical simulation", "world reconstruction", "embodied"],
}



# agentic_memory_breakthrough needs BOTH an agent/LLM context and a memory/retrieval
# context, matched on word boundaries, and is vetoed by weight-space topics. A bare
# "memory" match tagged RNN / continual-learning / loss-landscape papers (2609.38081).
_AGENT_CONTEXT = re.compile(
    r"\b(agents?|agentic|multi-agent|llm agents?|language[- ]model agents?|large language models?|llms?|assistants?)\b")
# Precision first: beacons are top-percentile alerts, so a memory hit needs an explicit
# agent-memory phrase, not the bare word "memory" (GPU memory, RNN memory tasks), and memory
# has to be what the paper is ABOUT, not one item in a list. Regression corpus:
# ~/.nougen/tests/test_arxiv_radar_tagger.py + radar_fixtures_memory_tagging.json.
#
# STRONG phrases stand on their own. WEAK terms (rag, world model, counterfactual, context
# window/compression/...) are generic and fire on RL, driving, video and RAG papers, so they
# only count within _NEAR_TOKENS words of "memor*".
_STRONG_MEMORY = re.compile(
    r"\b(?:(?:agent(?:ic)?|long[- ]term|external|persistent|conversational|personali[sz]ed|graph|latent|editable"
    r"|episodic|semantic|working|structured|durable|procedural|spatial|experiential) memor(?:y|ies)"
    r"|memory (?:store|bank|module|system|tree|graph|architecture|management|consolidation|reconsolidation"
    r"|retrieval|index(?:ing)?|agent|bridge)s?|memory-(?:augmented|driven))\b")
_WEAK_MEMORY = re.compile(
    r"\b(?:rag|retrieval[- ]augmented(?: generation)?|world models?|counterfactuals?"
    r"|context (?:window|management|compression|reconstruction))\b")
# Generic context handling counts in a TITLE alongside an agent term ("... Context Compression
# for LLM Agents"), where it is the paper's subject; in an abstract it is incidental.
_TITLE_CONTEXT_OPS = re.compile(r"\bcontext (?:management|compression|reconstruction)\b")
_NEAR_TOKENS = 8
# Memory as silicon, not as agent state.
_HARDWARE_MEMORY = re.compile(r"\b(npus?|dram|hbm|sram|memory bandwidth|memory hierarchy|processing-in-memory)\b")
_AGENT_CONTEXT = re.compile(
    r"\b(agents?|agentic|multi-agent|llm agents?|language[- ]model agents?|large language models?|llms?|assistants?)\b")
_NOT_AGENT_MEMORY = re.compile(
    r"\b(hessian|loss[- ]landscapes?|weight[- ]space|parameter[- ]space|null[- ]space|solution space"
    r"|mode[- ]connect\w*|model[- ]editing|linear mode connectivity)\b")


def _weak_near_memory(text: str) -> int:
    """Count WEAK hits that sit within _NEAR_TOKENS words of 'memor*' (same sentence window)."""
    words, hits = text.split(), 0
    for m in _WEAK_MEMORY.finditer(text):
        i = len(text[:m.start()].split())
        window = " ".join(words[max(0, i - _NEAR_TOKENS): i + _NEAR_TOKENS + len(m.group(0).split())])
        if re.search(r"\bmemor", window):
            hits += 1
    return hits


# Broad surveys, practitioner guides, and foundational overviews cover memory as one of
# many surveyed topics (planning, tools, reflection). They only qualify if memory is the TITLE subject.
_SURVEY_GUIDE = re.compile(r"\b(surveys?|guides?|overview|foundations? to systems?)\b")


def is_agentic_memory(searchable: str, title: str = "") -> bool:
    """True only for agent/LLM memory work. Weight-space and hardware-memory papers never qualify,
    and a lone incidental mention does not: need the phrase in the title, or two or more hits."""
    text, ttl = searchable.lower(), title.lower()
    if _NOT_AGENT_MEMORY.search(text) or _HARDWARE_MEMORY.search(text):
        return False
    if not _AGENT_CONTEXT.search(text):
        return False
    if _TITLE_CONTEXT_OPS.search(ttl) and _AGENT_CONTEXT.search(ttl):
        return True
    if _STRONG_MEMORY.search(ttl):
        return True
    # Bare "memory" is fine in a TITLE that also names agents: there it is the subject.
    if re.search(r"\bmemor(?:y|ies)\b", ttl) and _AGENT_CONTEXT.search(ttl):
        return True
    # Broad surveys/guides cover memory alongside planning, tools, and reflection;
    # they must name memory in the title to qualify as an agentic memory breakthrough.
    if _SURVEY_GUIDE.search(ttl):
        return False
    return len(_STRONG_MEMORY.findall(text)) + _weak_near_memory(text) >= 2


def load_route_recipe() -> dict:
    if ROUTE_RECIPE_PATH.exists():
        try:
            return json.loads(ROUTE_RECIPE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "lanes": {
            "beacon": {"min_percentile": 99.5, "burst_cap": 10},
            "review": {"min_percentile": 97.0, "burst_cap": 60},
            "shard": {"min_percentile": 0.0, "burst_cap": None}
        },
        "category_priors": {
            "promotion_eligible": ["cs.AI", "cs.MA", "cs.LG", "stat.ML", "cs.CL", "cs.IR", "cs.DC", "cs.OS", "cs.DS"],
            "conditional": ["cs.CR", "cs.RO", "cs.CV", "cs.SE", "cs.PL", "cs.NE"]
        }
    }


def load_cursor() -> dict:
    if CURSOR_PATH.exists():
        try:
            return json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"channels": {}, "seen_ids": []}


def save_cursor(cursor: dict):
    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_PATH.write_text(json.dumps(cursor, indent=2), encoding="utf-8")


def fetch_arxiv_rss_conditional(channel: str = "cs", cursor: dict = None) -> tuple[bytes, dict]:
    """Fetch RSS with conditional ETag/Last-Modified headers."""
    clean_channel = channel.strip().lower()
    url = f"https://rss.arxiv.org/rss/{clean_channel}"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/rss+xml, application/xml, text/xml"
    }
    ch_info = (cursor or {}).get("channels", {}).get(clean_channel, {})
    if ch_info.get("etag"):
        headers["If-None-Match"] = ch_info["etag"]
    if ch_info.get("last_modified"):
        headers["If-Modified-Since"] = ch_info["last_modified"]

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            resp_headers = {
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "status": 200
            }
            return content, resp_headers
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return b"", {"status": 304}
        raise


def parse_arxiv_item(item: ET.Element) -> dict:
    """Parse item according to official spec."""
    title_el = item.find("title")
    title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
    
    link_el = item.find("link")
    link = (link_el.text or "").strip() if link_el is not None else ""
    
    guid_el = item.find("guid")
    guid = (guid_el.text or "").strip() if guid_el is not None else ""
    
    pub_date_el = item.find("pubDate")
    pub_date = (pub_date_el.text or "").strip() if pub_date_el is not None else ""
    
    category_el = item.find("category")
    primary_category = (category_el.text or "").strip() if category_el is not None else ""
    
    announce_type_el = item.find(f"{{{NAMESPACES['arxiv']}}}announce_type")
    announce_type = (announce_type_el.text or "").strip() if announce_type_el is not None else "new"
    
    doi_el = item.find(f"{{{NAMESPACES['arxiv']}}}DOI")
    doi = (doi_el.text or "").strip() if doi_el is not None else None
    
    creator_el = item.find(f"{{{NAMESPACES['dc']}}}creator")
    authors_raw = (creator_el.text or "").strip() if creator_el is not None else ""
    authors = [a.strip() for a in authors_raw.split(",") if a.strip()] if authors_raw else []
    
    desc_el = item.find("description")
    desc_text = (desc_el.text or "").strip() if desc_el is not None else ""
    
    arxiv_id = None
    version = None
    m = re.search(r"arXiv:(\d{4}\.\d{4,5})(?:v(\d+))?", desc_text)
    if m:
        arxiv_id = m.group(1)
        version = f"v{m.group(2)}" if m.group(2) else "v1"
    elif link:
        m2 = re.search(r"/abs/(\d{4}\.\d{4,5})", link)
        if m2:
            arxiv_id = m2.group(1)
            version = "v1"
            
    m_abs = re.search(r"Abstract:\s*(.*)", desc_text, re.DOTALL)
    if m_abs:
        abstract = " ".join(m_abs.group(1).split())
    else:
        abstract = " ".join(desc_text.split())

    searchable = f"{title} {abstract}".lower()
    score = 0
    matched_pillars = []
    reason_codes = []
    
    for pillar, kws in OBSERVATORY_PILLARS.items():
        hits = sum(1 for kw in kws if kw in searchable)
        if hits > 0:
            score += hits
            matched_pillars.append(pillar)

    if any(k in searchable for k in ["benchmark", "benchmarking", "evaluation suite"]):
        reason_codes.append("reproducible_benchmark")
    if any(k in searchable for k in ["runtime", "framework", "library", "open-source", "github.com", "codebase"]):
        reason_codes.append("usable_artifact")
    if any(k in searchable for k in ["orchestration", "multi-agent", "coordination", "harness"]):
        reason_codes.append("orchestration_mechanism")
    if is_agentic_memory(searchable, title=title):
        reason_codes.append("agentic_memory_breakthrough")
    if any(k in searchable for k in ["failure", "vulnerability", "jailbreak", "exploit", "hallucination"]):
        reason_codes.append("verified_failure_mode")

    return {
        "id": arxiv_id or (guid.split(":")[-1] if guid else ""),
        "version": version or "v1",
        "title": title,
        "link": link,
        "abstract": abstract,
        "primary_category": primary_category,
        "announce_type": announce_type,
        "authors": authors,
        "pub_date": pub_date,
        "doi": doi,
        "score": score,
        "matched_pillars": matched_pillars,
        "reason_codes": reason_codes,
    }


def compute_percentiles(papers: list[dict]) -> list[dict]:
    """Compute global and category-specific percentiles, and weighted priority_pct."""
    n = len(papers)
    if n == 0:
        return []

    # Sort globally by raw score
    sorted_global = sorted(papers, key=lambda x: x["score"])
    for rank, p in enumerate(sorted_global):
        p["global_pct"] = round((rank / max(1, n - 1)) * 100.0, 2)

    # Group by category and compute category percentile
    by_cat = {}
    for p in papers:
        by_cat.setdefault(p["primary_category"], []).append(p)

    for cat, group in by_cat.items():
        sorted_cat = sorted(group, key=lambda x: x["score"])
        m = len(sorted_cat)
        for rank, p in enumerate(sorted_cat):
            p["category_pct"] = round((rank / max(1, m - 1)) * 100.0, 2)

    # Calculate authoritative priority_pct = 0.70 * global_pct + 0.30 * category_pct
    for p in papers:
        g_pct = p.get("global_pct", 50.0)
        c_pct = p.get("category_pct", 50.0)
        p["priority_pct"] = round(0.70 * g_pct + 0.30 * c_pct, 2)

    return sorted(papers, key=lambda x: x["priority_pct"], reverse=True)


def route_papers(papers: list[dict], recipe: dict) -> dict[str, list[dict]]:
    """Route papers into beacon, review, and shard lanes."""
    lanes = {"beacon": [], "review": [], "shard": []}
    priors = recipe.get("category_priors", {})
    eligible_cats = set(priors.get("promotion_eligible", []))
    conditional_cats = set(priors.get("conditional", []))

    beacon_cap = recipe.get("lanes", {}).get("beacon", {}).get("burst_cap", 10)
    review_cap = recipe.get("lanes", {}).get("review", {}).get("burst_cap", 60)

    for p in papers:
        pct = p["priority_pct"]
        cat = p["primary_category"]
        has_reasons = len(p["reason_codes"]) > 0
        has_pillars = len(p["matched_pillars"]) > 0

        # Hard Gate: Min abstract length
        if len(p["abstract"].split()) < 15:
            lanes["shard"].append(p)
            p["route"] = "shard"
            continue

        # Beacon Lane: p99.5+, pillars passed, concrete reason code, and cap not reached
        if (pct >= 99.0 and has_reasons and has_pillars and len(lanes["beacon"]) < beacon_cap and 
            (cat in eligible_cats or (cat in conditional_cats and p["score"] >= 3))):
            lanes["beacon"].append(p)
            p["route"] = "beacon"
        # Review Lane: p97.0+, eligible or conditional with relevance, cap not reached
        elif (pct >= 95.0 and len(lanes["review"]) < review_cap and 
              (cat in eligible_cats or cat in conditional_cats or has_pillars)):
            lanes["review"].append(p)
            p["route"] = "review"
        # Shard Lane: All other valid papers
        else:
            lanes["shard"].append(p)
            p["route"] = "shard"

    return lanes


def ingest_lane_to_substrate(papers: list[dict]) -> dict:
    """Ingest papers directly into the NouGenShards cluster via dynamic discovery."""
    try:
        arxiv_core = importlib.import_module("nougen_shards.arxiv_core")
    except ImportError:
        # Fallback to local user paths dynamically without hardcoded usernames
        candidate = Path.home() / ".nougen" / "src" / "nougenshards" / "src"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        try:
            arxiv_core = importlib.import_module("nougen_shards.arxiv_core")
        except ImportError as exc:
            return {
                "ok": False,
                "error": "nougen_shards.arxiv_core unavailable",
                "detail": f"{type(exc).__name__}: {exc}",
                "ingested": 0,
                "deduplicated": 0,
                "total": len(papers),
            }

    ingested = 0
    skipped = 0
    for p in papers:
        paper_obj = {
            "arxiv_id": p["id"],
            "title": p["title"],
            "summary": p["abstract"],
            "published": p["pub_date"],
            "authors": p["authors"],
            "url": p["link"],
            "pdf_url": f"https://arxiv.org/pdf/{p['id']}.pdf"
        }
        res = arxiv_core.ingest_paper_to_shard(paper_obj)
        if res.get("captured"):
            ingested += 1
        else:
            skipped += 1
    return {"ok": True, "ingested": ingested, "deduplicated": skipped, "total": len(papers)}


def broadcast_beacon(target: str, beacon_papers: list[dict], pub_date: str) -> dict:
    """Emit NouGenMsg alert to fleet."""
    if not beacon_papers:
        return {"ok": True, "status": "noop"}

    exe = shutil.which("nougenmsg")
    if exe is None:
        candidate = Path.home() / ".nougen" / "bin" / ("nougenmsg.bat" if sys.platform == "win32" else "nougenmsg")
        if candidate.exists():
            exe = str(candidate)
        else:
            local_bin = Path.home() / ".local" / "bin" / "nougenmsg"
            if local_bin.exists():
                exe = str(local_bin)

    if exe is None:
        return {
            "ok": False,
            "status": "unavailable",
            "error": "nougenmsg is not on PATH",
        }

    msg_lines = [
        f"🚨 [ARXIV BEACON RADAR] {len(beacon_papers)} Breakthrough Papers for {pub_date}:",
    ]
    for i, p in enumerate(beacon_papers[:5], 1):
        reasons = ", ".join(p["reason_codes"]) if p["reason_codes"] else "high_priority"
        msg_lines.append(f"{i}. [{p['id']}] {p['title']} ({p['primary_category']} | {reasons})")
    msg_lines.append(f"View full queue: ~/.nougen/shards/radar/queues/beacon.json")

    cmd = [
        exe,
        f"@{target}" if not target.startswith("@") else target,
        "\n".join(msg_lines)
    ]
    _no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=20, creationflags=_no_window)
        if completed.returncode == 0:
            print(f"📡 Broadcast emitted to {target} via nougenmsg.")
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stderr": completed.stderr[-1000:] if completed.stderr else "",
        }
    except Exception as e:
        print(f"Warning: broadcast failed: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


def run_pipeline(mode: str = "reconcile", channels: list[str] = None, broadcast_target: str = "all") -> dict:
    channels = channels or ["cs"]
    recipe = load_route_recipe()
    cursor = load_cursor()
    
    all_papers = []
    seen_ids = set(cursor.get("seen_ids", []))
    new_seen_ids = set()
    latest_meta = {}

    for ch in channels:
        try:
            content, headers = fetch_arxiv_rss_conditional(ch, cursor)
            if headers.get("status") == 304 or not content:
                print(f"Channel '{ch}': Unchanged (HTTP 304).")
                continue
                
            cursor.setdefault("channels", {})[ch] = {
                "etag": headers.get("etag"),
                "last_modified": headers.get("last_modified"),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            
            root = ET.fromstring(content)
            channel_el = root.find("channel")
            if channel_el is not None:
                latest_meta = {
                    "title": channel_el.find("title").text or "",
                    "pubDate": channel_el.find("pubDate").text or "",
                }
                for item_el in channel_el.findall("item"):
                    p = parse_arxiv_item(item_el)
                    if p["id"]:
                        new_seen_ids.add(p["id"])
                        all_papers.append(p)
        except Exception as e:
            print(f"Error fetching channel '{ch}': {e}", file=sys.stderr)

    if not all_papers:
        print("No papers to process in this cycle.")
        return {"status": "noop", "papers_count": 0}

    # Defined here, not only in the reconcile-mode digest block: the broadcast below uses it in every mode,
    # and a sweep with a beacon + broadcast target crashed with UnboundLocalError.
    today_slug = datetime.datetime.now().strftime("%Y-%m-%d")

    print(f"📊 Processing {len(all_papers)} papers for {latest_meta.get('pubDate', 'today')}...")
    scored_papers = compute_percentiles(all_papers)
    lanes = route_papers(scored_papers, recipe)

    print(f"✔ Routing complete: {len(lanes['beacon'])} BEACON | {len(lanes['review'])} REVIEW | {len(lanes['shard'])} SHARD")

    # Persist queues
    QUEUES_DIR.mkdir(parents=True, exist_ok=True)
    (QUEUES_DIR / "beacon.json").write_text(json.dumps(lanes["beacon"], indent=2), encoding="utf-8")
    (QUEUES_DIR / "review.json").write_text(json.dumps(lanes["review"], indent=2), encoding="utf-8")

    # Ingest Beacon & Review papers into the 108K+ NouGen Substrate
    priority_papers = lanes["beacon"] + lanes["review"]
    print(f"⚡ Ingesting top {len(priority_papers)} papers into ~/.nougen/shards/...")
    ingest_res = ingest_lane_to_substrate(priority_papers)
    print(f"✔ Substrate Result: {ingest_res.get('ingested')} newly sharded, {ingest_res.get('deduplicated')} deduplicated.")

    # Save cursor with updated seen IDs
    cursor["seen_ids"] = list(seen_ids | new_seen_ids)[-10000:]
    save_cursor(cursor)

    today_slug = datetime.datetime.now().strftime("%Y-%m-%d")

    # Generate Daily Digest markdown if reconcile mode
    if mode == "reconcile":
        DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
        digest_file = DIGESTS_DIR / f"arxiv_digest_{today_slug}.md"
        
        digest_lines = [
            f"# 📡 arXiv Morning Radar Digest — {today_slug}",
            f"> **Announced**: {latest_meta.get('pubDate', 'Today')} | **Total Evaluated**: {len(all_papers)} papers",
            "",
            "## 🚨 Beacon Lane (Operator & Core Action Items)",
            "",
        ]
        for i, p in enumerate(lanes["beacon"], 1):
            reasons = ", ".join(p["reason_codes"])
            authors = ", ".join(p["authors"][:3]) + (" et al." if len(p["authors"]) > 3 else "")
            digest_lines.extend([
                f"### {i}. [{p['id']}] {p['title']}",
                f"- **Priority**: `p{p['priority_pct']}` | **Category**: `{p['primary_category']}` | **Reasons**: `{reasons}`",
                f"- **Authors**: {authors} | **Link**: [{p['link']}]({p['link']})",
                f"- **Abstract**: {p['abstract'][:250]}...",
                "",
            ])
            
        digest_lines.extend([
            "## 🔍 Review Lane (Specialist Queues)",
            "",
        ])
        for i, p in enumerate(lanes["review"][:15], 1):
            digest_lines.append(f"{i}. **[{p['id']}]** [{p['title']}]({p['link']}) (`{p['primary_category']}` | `p{p['priority_pct']}`)")
            
        digest_lines.append(f"\n*(Showing top 15 of {len(lanes['review'])} review papers. Full queue: `~/.nougen/shards/radar/queues/review.json`)*\n")
        digest_lines.append(f"---\n*Generated by Phoebus arXiv RSS Radar (Mode: {mode})*")
        
        digest_file.write_text("\n".join(digest_lines), encoding="utf-8")
        print(f"✔ Daily digest written to: {digest_file}")

    # Emit broadcast
    if broadcast_target and lanes["beacon"]:
        broadcast_beacon(broadcast_target, lanes["beacon"], latest_meta.get("pubDate", today_slug))

    return {
        "status": "success",
        "total": len(all_papers),
        "beacon_count": len(lanes["beacon"]),
        "review_count": len(lanes["review"]),
        "shard_count": len(lanes["shard"]),
        "ingested_to_substrate": ingest_res.get("ingested"),
    }


def main():
    parser = argparse.ArgumentParser(description="arXiv RSS Radar & Automated 3-Lane Route Engine.")
    parser.add_argument("--mode", choices=["sweep", "reconcile"], default="reconcile", help="Execution mode (hourly sweep vs 5:15 AM ET reconcile)")
    parser.add_argument("--channels", default="cs", help="Comma-separated channels (e.g. 'cs', 'cs,stat')")
    parser.add_argument("--broadcast", default="all", help="Target node to notify via nougenmsg (e.g. 'all', 'blade')")
    args = parser.parse_args()

    channels = [c.strip() for c in args.channels.split(",") if c.strip()]
    res = run_pipeline(mode=args.mode, channels=channels, broadcast_target=args.broadcast)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
