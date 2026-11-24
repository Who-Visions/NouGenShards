#!/usr/bin/env python3
"""Independent benchmark: raw Claude vs Claude+Shards on one document.

Arm A (raw): every round, the full document text goes in the prompt.
  The prompt is cached the documented way (--cache-prompt), so the raw
  arm gets its best legitimate case (the receipt's ladder behaviour).
Arm B (shards): the document is sharded once (see --shard); every round
  only the recalled shards go in the prompt.

Model: claude-haiku-5-5 (the small lookup helper), both arms.
Prices (list, per MTok — the receipt's assumed prices):
  Haiku in $1, out $5, cache read $0.10, cache write $2.
Usage is read from the Anthropic client JSON envelope per call.
Writes a JSON log to --out and prints a summary table.
"""
import argparse, json, re, subprocess, sys, os

ANTH = os.path.expanduser("~/workspace/custom-connectors/custom.anthropic/bin/client.py")
MCP = os.path.expanduser("~/workspace/custom-connectors/custom.nougenshards/bin/client.py")
MODEL = "claude-haiku-5-5"
PRICE = {"in": 1.0, "out": 5.0, "read": 0.10, "write": 2.0}  # $ per MTok

def anth_call(prompt, max_tokens=1000):
    # Thinking is set explicitly (--effort low) per the calling skill:
    # Haiku 5.5 thinks at its own default otherwise and can burn the
    # whole max_tokens budget on thinking, leaving no visible answer.
    # --no-thinking is NOT used: Haiku 5.5 rejects it with a 400.
    out = subprocess.run(
        [sys.executable, ANTH, "message", "--model", MODEL,
         "--prompt", prompt, "--cache-prompt", "--effort", "low",
         "--max-tokens", str(max_tokens), "--timeout", "60"],
        capture_output=True, text=True, timeout=90)
    if out.returncode != 0:
        return {"error": (out.stderr or out.stdout)[:300]}
    try:
        d = json.loads(out.stdout)
    except Exception:
        return {"error": "unparsable envelope", "raw": out.stdout[:300]}
    u = d.get("usage", {}) or {}
    return {
        "input": u.get("input_tokens", 0),
        "cache_write": u.get("cache_creation_input_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "stop": d.get("stop_reason"),
        "text": (d.get("text") or "")[:1200],
    }

def cost(r):
    if "error" in r:
        return None
    return (r["input"] * PRICE["in"] + r["output"] * PRICE["out"]
            + r["cache_read"] * PRICE["read"]
            + r["cache_write"] * PRICE["write"]) / 1e6

def mcp_call(tool, args):
    with open("/tmp/bench-mcp-args.json", "w") as f:
        json.dump(args, f)
    out = subprocess.run(
        [sys.executable, MCP, "call-tool", "--name", tool,
         "--arguments-file", "/tmp/bench-mcp-args.json"],
        capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return {"error": (out.stderr or out.stdout)[:300]}
    try:
        return json.loads(out.stdout)
    except Exception:
        return {"raw": out.stdout[:2000]}

def shard_doc(path, title_prefix, tags):
    text = open(path).read()
    # Split on ## section headers; keep the header with its chunk.
    parts = re.split(r"(?m)^## ", text)
    chunks = []
    if parts[0].strip():
        chunks.append(("Intro", parts[0]))
    for p in parts[1:]:
        head, _, body = p.partition("\n")
        chunks.append((head.strip(), "## " + p))
    ids = []
    for head, chunk in chunks:
        if len(chunk.strip()) < 200:
            continue
        r = mcp_call("shards_capture", {
            "title": f"{title_prefix} — {head}",
            "content": chunk.strip()[:6000],
            "tags": tags,
        })
        ids.append({"section": head, "result": r})
        print(f"  captured [{head}]: {str(r)[:200]}", flush=True)
    return ids

def recall(query, limit=5, title_prefix="", tag=""):
    """Recall full shard text for a query — source-scoped and token-budgeted.

    What the benchmark proved was broken:
    - The search returns the whole grid's matches, so a query about one
      document also pulls pointer shards and other tests' shards (noise).
    - Full-text recall of the top 5 hits then feeds the model MORE context
      than the raw document (2,376-2,858 tokens vs 858-1,480), so the
      Shards arm costs more than raw and answers from messier context.
    - The top-5 by keyword relevance missed the chunk holding the answer
      on Plato (duration + teacher), so the arm answered partially.

    The fix, in this client:
    1. Source-scope: prefer shards belonging to the document being asked
       about (title prefix / tag match). Fall back to unfiltered hits only
       if fewer than two source shards match.
    2. Take the top 3, not 5.
    3. Token-budget the context: cap the joined text at 4,000 chars
       (~1,000 tokens) so recall can never feed the model more than the
       raw document on a small doc.
    4. Re-rank the scoped hits client-side by overlap with the query's
       distinctive terms, so the chunk holding the answer outranks
       same-document chunks that merely share common words. (The grid
       search ranks by its own relevance; on Plato it ranked the Forms
       chunks above the chunk holding the duration + teacher.)
    """
    r = mcp_call("shards_search", {"query": query, "limit": limit})
    raw = ""
    for c in r.get("content", []):
        if isinstance(c, dict) and c.get("text"):
            raw += c["text"] + "\n"
    # Parse (shard id, title) from the hit lines. The title is what the
    # search output shows ("**Plato in Egypt (bench) — Plato in Cyrene**");
    # get_shard's text does not reliably carry it, so scope on the title
    # here, before fetching full text.
    hits_meta = []
    for line in raw.splitlines():
        m = re.search(r"shard:(\d+)@db(\d+).*?\*\*(.+?)\*\*", line)
        if m:
            pair = (int(m.group(1)), int(m.group(2)))
            if pair not in [p for p, _ in hits_meta]:
                hits_meta.append((pair, m.group(3)))
    if not hits_meta:
        for m in re.finditer(r"shard:(\d+)@db(\d+)", raw):
            pair = (int(m.group(1)), int(m.group(2)))
            if pair not in [p for p, _ in hits_meta]:
                hits_meta.append((pair, ""))
    # Source-scope: prefer shards whose title belongs to the document.
    if title_prefix or tag:
        scoped = [(p, t) for p, t in hits_meta
                  if (title_prefix and title_prefix in t)
                  or (tag and tag in t)]
        if len(scoped) >= 2:
            hits_meta = scoped
    hits = []
    for (sid, db), _title in hits_meta[:limit]:
        g = mcp_call("get_shard", {"shard_id": sid, "db": db})
        t = ""
        if isinstance(g, dict):
            for c in g.get("content", []):
                if isinstance(c, dict) and c.get("text"):
                    t += c["text"] + "\n"
            if not t and g.get("raw"):
                t = g["raw"]
        if t.strip():
            hits.append(t.strip())
    # Re-rank by overlap with the query's distinctive terms (words of
    # length 5+, which carry the question's specifics — Sechnuphis,
    # Heliopolis, Sharbaugh, Kailin — rather than common words).
    terms = [w.lower() for w in re.split(r"\W+", query) if len(w) >= 5]
    def score(t):
        low = t.lower()
        return sum(low.count(term) for term in terms)
    hits.sort(key=score, reverse=True)
    # Top 3, token-budgeted at 4,000 chars.
    ctx = "\n\n---\n\n".join(hits[:3])[:4000]
    return [ctx] if ctx.strip() else []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--recall-query", default="")
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--tag", default="bench")
    ap.add_argument("--title-prefix", default="Bench doc")
    ap.add_argument("--shard", action="store_true", help="shard the doc, then exit")
    ap.add_argument("--shards-first", action="store_true",
                    help="run the Shards arm before the raw arm (the smarter protocol)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.shard:
        print(f"Sharding {args.doc} ...")
        ids = shard_doc(args.doc, args.title_prefix,
                        [args.tag, "bench", "independent-test"])
        print(f"Captured {len(ids)} chunks.")
        return

    doc = open(args.doc).read()
    q = args.question
    rq = args.recall_query or q
    log = {"doc": args.doc, "question": q, "model": MODEL,
           "prices": PRICE, "rounds": args.rounds, "arms": {},
           "order": "shards-first" if args.shards_first else "raw-first"}

    def run_raw():
        print("Arm A (raw Claude) ...", flush=True)
        recs = []
        for i in range(1, args.rounds + 1):
            prompt = (f"Document:\n{doc}\n\nQuestion: {q}\n"
                      f"Answer using only the document above. Reply in under 200 words.")
            r = anth_call(prompt)
            r["round"] = i
            r["cost"] = cost(r)
            recs.append(r)
            print(f"  A round {i}: in={r.get('input')} read={r.get('cache_read')} "
                  f"write={r.get('cache_write')} out={r.get('output')} "
                  f"cost=${(r['cost'] or 0):.4f}", flush=True)
        return recs

    def run_shards():
        print("Arm B (Claude + Shards) ...", flush=True)
        hits = recall(rq, limit=10,
                      title_prefix=args.title_prefix, tag=args.tag)
        ctx = "\n\n---\n\n".join(hits)[:4000]
        print(f"  recalled {len(hits)} shard(s), {len(ctx)} chars of context", flush=True)
        log["recalled_chars"] = len(ctx)
        log["recalled_shards"] = len(hits)
        recs = []
        for i in range(1, args.rounds + 1):
            prompt = (f"Recalled context from NouGenShards:\n{ctx}\n\nQuestion: {q}\n"
                      f"Answer using only the recalled context above. Reply in under 200 words.")
            r = anth_call(prompt)
            r["round"] = i
            r["cost"] = cost(r)
            recs.append(r)
            print(f"  B round {i}: in={r.get('input')} read={r.get('cache_read')} "
                  f"write={r.get('cache_write')} out={r.get('output')} "
                  f"cost=${(r['cost'] or 0):.4f}", flush=True)
        return recs

    # The smarter protocol: Shards first, raw second. Same questions, two rounds.
    if args.shards_first:
        recs_b = run_shards()
        recs_a = run_raw()
    else:
        recs_a = run_raw()
        recs_b = run_shards()
    log["arms"]["raw"] = recs_a
    log["arms"]["shards"] = recs_b

    def total(recs):
        return sum((r.get("cost") or 0) for r in recs)
    ta, tb = total(recs_a), total(recs_b)
    log["totals"] = {"raw": ta, "shards": tb,
                     "ratio": (ta / tb) if tb else None,
                     "saved_pct": (100 * (1 - tb / ta)) if ta else None}
    print(f"\nTOTAL raw: ${ta:.4f} | shards: ${tb:.4f} | "
          f"ratio {ta/tb:.1f}x | saved {100*(1-tb/ta):.1f}%")
    if args.out:
        json.dump(log, open(args.out, "w"), indent=2)
        print(f"Log: {args.out}")

if __name__ == "__main__":
    main()
