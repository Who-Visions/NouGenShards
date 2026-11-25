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

def ngs_driver(args, timeout=120):
    """Run the NGS bench driver (a local C binary over the NGS prototype)
    and parse its JSON stdout. Returns the parsed dict, or an error dict."""
    out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        return {"error": (out.stderr or out.stdout)[:500]}
    try:
        return json.loads(out.stdout)
    except Exception:
        return {"error": "unparsable driver output", "raw": out.stdout[:500]}

def ngs_ingest(doc_path, title_prefix, tags, store_dir, driver, ns):
    """Fresh local NGS store for one doc: wipe the dir, then ingest the
    doc's ## sections as one atomic ngs_remember_many batch."""
    subprocess.run(["rm", "-rf", store_dir], timeout=30)
    return ngs_driver([driver, "ingest", "--store", store_dir, "--ns", ns,
                       "--doc", doc_path, "--title-prefix", title_prefix,
                       "--tags", ",".join(tags)])

def ngs_recall(query, k, token_budget, store_dir, driver, ns,
               min_confidence=None):
    """Recall from a local NGS store: keyword arm only (vec NULL), k hits,
    token_budget tokens. Returns the driver's JSON dict."""
    args = [driver, "recall", "--store", store_dir, "--ns", ns,
            "--query", query, "--k", str(k),
            "--token-budget", str(token_budget)]
    if min_confidence is not None:
        args += ["--min-confidence", str(min_confidence)]
    return ngs_driver(args)

def recall(query, candidates=10, top_k=5, context_budget=4000,
             min_term_len=5, doc_chars=None, title_prefix="", tag="",
             passage_chars=900):
    """Recall full shard text for a query.

    Contract — universal, dynamic, deterministic, hierarchical,
    heuristic, templatable:
    - Universal: no value in here names a document, a topic, or a
      model. Every tunable is a parameter with a default; the query,
      the document's title/tag, and the document's length arrive as
      arguments.
    - Dynamic: the context budget is derived at runtime from the
      document itself — budget = min(context_budget, doc_chars) — so
      recall can never feed the model more context than the raw
      document holds. The distinctive terms are derived from the
      query at runtime, not from a list.
    - Deterministic: the same query against the same grid returns the
      same context. The re-rank is pure counting; there is no
      randomness and no model call inside recall.
    - Hierarchical, six layers, each feeding the next:
      L1 search (the grid's own relevance, N candidates),
      L2 scope (prefer the document's own shards by title/tag),
      L3 fetch (get_shard each candidate for its full text),
      L4 re-rank (the DISTINCTIVE_TERM_COVERAGE heuristic, chunks;
      top_k is the CANDIDATE POOL, not the budget — widened 3 to 5
      after v6, when the chunk holding the duration sentence ranked
      4th and never reached the passage layer),
      L4b passage re-rank (the same heuristic, passages),
      L5 budget (ranked passages, joined, cut at the budget).
    - Heuristic, named DISTINCTIVE_TERM_COVERAGE: a chunk or passage
      scores (distinct query terms present, total occurrences),
      sorted descending. Coverage first, volume second. The earlier
      raw-count version failed on Plato: common terms (Plato, Egypt,
      Forms) appear in every chunk and swamped the distinctive ones
      (Sechnuphis, Heliopolis), so the chunk holding the answer —
      the duration and the teacher — ranked below the Forms chunks
      and the arm answered partially. Coverage fixed the chunk
      ranking, but v5 failed a different way: the budget cut the
      winning chunk BEFORE its answer sentence (the duration line
      sits at the end of the Plato chunk), so the arm saw the
      chunk's beginning and confused Pythagoras's twelve years with
      Plato's. L4b fixes that: rank PASSAGES, not whole chunks, so
      the budget carries the sentences that answer instead of the
      starts of long chunks. A passage is a paragraph, or a run of
      sentences up to passage_chars when a paragraph is longer.
    - Fallback, named DISTINCTIVE_QUERY_FALLBACK: the grid's search
      ranks generic-term matches above distinctive-term matches, so
      a broad recall query can return zero of the document's own
      shards (CGF v1: the query's generic words — gauge, matter,
      field, equation, state — matched old VeilVerse shards and the
      paper's 33 chunks ranked below the top 10). When L2 scoping
      finds fewer than 2 of the document's own shards, recall
      re-searches with the query's longest distinctive words only
      (top 4 by length, deterministic) and merges the hits. A
      distinctive query (Omega_CGF, Sechnuphis) finds the document;
      a broad one drowns it.
    - Templatable: this function is the reusable recall template.
      Any bench, test, or lane can call it with its own query and
      document; the bench below is one instantiation of it.
    """
    def search_once(q):
        rr = mcp_call("shards_search", {"query": q, "limit": candidates})
        out = ""
        for c in rr.get("content", []):
            if isinstance(c, dict) and c.get("text"):
                out += c["text"] + "\n"
        return out
    raw = search_once(query)
    query_used = query
    # L1/L2: parse (shard id, title) from the hit lines, then scope to
    # the document's own shards. The title is what the search output
    # shows ("**Plato in Egypt (bench) — Plato in Cyrene**"); get_shard's
    # text does not reliably carry it, so scope on the title here.
    def parse_hits(text):
        found = []
        for line in text.splitlines():
            m = re.search(r"shard:(\d+)@db(\d+).*?\*\*(.+?)\*\*", line)
            if m:
                pair = (int(m.group(1)), int(m.group(2)))
                if pair not in [p for p, _ in found]:
                    found.append((pair, m.group(3)))
        if not found:
            for m in re.finditer(r"shard:(\d+)@db(\d+)", text):
                pair = (int(m.group(1)), int(m.group(2)))
                if pair not in [p for p, _ in found]:
                    found.append((pair, ""))
        return found
    hits_meta = parse_hits(raw)
    def scoped_count(hits):
        if not (title_prefix or tag):
            return len(hits)
        return len([(p, t) for p, t in hits
                    if (title_prefix and title_prefix in t)
                    or (tag and tag in t)])
    # DISTINCTIVE_QUERY_FALLBACK: if the broad query found fewer than
    # 2 of the document's own shards, re-search with the query's
    # longest distinctive words only and merge the hits.
    if scoped_count(hits_meta) < 2:
        words = sorted({w for w in re.split(r"\W+", query)
                        if len(w) >= min_term_len},
                       key=lambda w: (-len(w), w.lower()))[:4]
        if words:
            fallback_q = " ".join(words)
            if fallback_q.lower() != query.lower():
                query_used = fallback_q
                extra = parse_hits(search_once(fallback_q))
                seen = {p for p, _ in hits_meta}
                hits_meta.extend([(p, t) for p, t in extra
                                  if p not in seen])
    if title_prefix or tag:
        scoped = [(p, t) for p, t in hits_meta
                  if (title_prefix and title_prefix in t)
                  or (tag and tag in t)]
        if len(scoped) >= 2:
            hits_meta = scoped
    # L3: fetch full text for each candidate.
    hits = []
    for (sid, db), _title in hits_meta[:candidates]:
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
    # L4: DISTINCTIVE_TERM_COVERAGE — (distinct terms present, total
    # occurrences), descending. Distinctive terms are the query's words
    # of at least min_term_len, which carry the question's specifics.
    terms = [w.lower() for w in re.split(r"\W+", query)
             if len(w) >= min_term_len]
    def coverage(t):
        low = t.lower()
        present = sum(1 for term in terms if term in low)
        volume = sum(low.count(term) for term in terms)
        return (present, volume)
    hits.sort(key=coverage, reverse=True)
    # L4b: passage re-rank. Split each of the top_k chunks into
    # passages (paragraphs; over-long paragraphs are re-split on
    # sentence boundaries into runs of at most passage_chars), score
    # each passage with the same coverage heuristic, rank descending.
    # The budget then carries the answering sentences, not the starts
    # of long chunks.
    def passages(text):
        out = []
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            if len(para) <= passage_chars:
                out.append(para)
                continue
            sents = re.split(r"(?<=[.!?])\s+", para)
            cur = ""
            for s in sents:
                if cur and len(cur) + 1 + len(s) > passage_chars:
                    out.append(cur)
                    cur = s
                else:
                    cur = (cur + " " + s) if cur else s
            if cur:
                out.append(cur)
        return out
    ranked = []
    for h in hits[:top_k]:
        ranked.extend(passages(h))
    ranked.sort(key=coverage, reverse=True)
    # L5: take ranked passages in order, whole, while they fit the
    # dynamic budget; a passage that does not fit is skipped so a
    # shorter one behind it can still land.
    budget = context_budget if doc_chars is None else min(context_budget, doc_chars)
    kept, used = [], 0
    for p in ranked:
        sep = 7 if kept else 0  # "\n\n---\n\n" between passages
        if used + sep + len(p) <= budget:
            kept.append(p)
            used += sep + len(p)
    ctx = "\n\n---\n\n".join(kept)
    return ([ctx] if ctx.strip() else []), query_used

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--question", default="")
    ap.add_argument("--recall-query", default="")
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--tag", default="bench")
    ap.add_argument("--title-prefix", default="Bench doc")
    ap.add_argument("--shard", action="store_true", help="shard the doc, then exit")
    ap.add_argument("--shards-first", action="store_true",
                    help="run the Shards arm before the raw arm (the smarter protocol)")
    ap.add_argument("--candidates", type=int, default=10,
                    help="recall L1: how many grid hits to consider")
    ap.add_argument("--top-k", type=int, default=5,
                    help="recall L5: how many re-ranked chunks to feed the model")
    ap.add_argument("--context-budget", type=int, default=4000,
                    help="recall L5: max context chars; the effective budget is "
                         "min(this, the document's own length)")
    ap.add_argument("--min-term-len", type=int, default=5,
                    help="recall L4: a query word counts as distinctive at this length")
    ap.add_argument("--passage-chars", type=int, default=900,
                    help="recall L4b: max chars per passage; longer paragraphs "
                         "are re-split on sentence boundaries")
    ap.add_argument("--recall-source", choices=["fleet", "ngs"],
                    default="fleet",
                    help="which recall engine feeds the answer arm: the fleet "
                         "NouGenShards grid (default) or a local NGS store")
    ap.add_argument("--ngs-driver",
                    default=os.path.expanduser(
                        "~/workspace/research-lab/bench/ngs-bench-driver"),
                    help="NGS arm: path to the compiled ngs-bench-driver binary")
    ap.add_argument("--ngs-store",
                    default=os.path.expanduser(
                        "~/workspace/research-lab/bench/ngs-store"),
                    help="NGS arm: parent dir for per-doc local NGS stores")
    ap.add_argument("--ngs-ns", default="bench",
                    help="NGS arm: namespace the facts are ingested under")
    ap.add_argument("--ngs-k", type=int, default=5,
                    help="NGS arm: ngs_recall k (max hits)")
    ap.add_argument("--ngs-token-budget", type=int, default=4000,
                    help="NGS arm: ngs_recall token_budget (engine estimate "
                         "is chars/4, so 4000 tokens is the same NUMBER as "
                         "the fleet's 4000-char budget, a different unit — "
                         "see the NGS arm's log note)")
    ap.add_argument("--skip-raw", action="store_true",
                    help="skip Arm A (raw Claude); the NGS arm runs alone and "
                         "is compared against raw totals from an earlier log")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if not args.shard and not args.question:
        ap.error("--question is required unless --shard is given")

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
        hits, query_used = recall(rq, candidates=args.candidates, top_k=args.top_k,
                      context_budget=args.context_budget,
                      min_term_len=args.min_term_len,
                      doc_chars=len(doc),
                      title_prefix=args.title_prefix, tag=args.tag,
                      passage_chars=args.passage_chars)
        ctx = hits[0] if hits else ""
        print(f"  recalled context: {len(ctx)} chars "
              f"(budget {min(args.context_budget, len(doc))})", flush=True)
        log["recalled_chars"] = len(ctx)
        log["recall"] = {"candidates": args.candidates, "top_k": args.top_k,
                         "context_budget": args.context_budget,
                         "effective_budget": min(args.context_budget, len(doc)),
                         "min_term_len": args.min_term_len,
                         "passage_chars": args.passage_chars,
                         "query": rq, "query_used": query_used,
                         "heuristic": "DISTINCTIVE_TERM_COVERAGE"}
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

    def run_ngs():
        """Arm N (Claude + NGS): the document is ingested once into a fresh
        local NGS store (per-doc dir under --ngs-store); every round only
        the engine's recalled facts go in the prompt. The engine's recall
        is local and free; only the Haiku answer calls cost. The engine
        returns whole facts (or title-only stubs when the token budget
        runs out); the context is the full bodies of the non-stub hits,
        joined the same way as the fleet arm. An abstention means the
        engine cleared no hit over min_confidence — the context is then
        empty and the model says so; that IS the engine's answer."""
        print("Arm N (Claude + NGS) ...", flush=True)
        slug = os.path.basename(args.doc)
        if slug.endswith(".md"):
            slug = slug[:-3]
        store_dir = os.path.join(args.ngs_store, slug)
        ing = ngs_ingest(args.doc, args.title_prefix,
                         [args.tag, "bench", "independent-test"],
                         store_dir, args.ngs_driver, args.ngs_ns)
        if "error" in ing:
            print(f"  NGS ingest failed: {ing['error']}", flush=True)
            log["ngs_ingest"] = ing
            return [{"error": ing["error"], "round": i}
                    for i in range(1, args.rounds + 1)]
        print(f"  NGS ingested {ing.get('ingested')} sections into "
              f"{store_dir}", flush=True)
        log["ngs_ingest"] = ing
        res = ngs_recall(rq, k=args.ngs_k,
                         token_budget=args.ngs_token_budget,
                         store_dir=store_dir, driver=args.ngs_driver,
                         ns=args.ngs_ns)
        if "error" in res:
            print(f"  NGS recall failed: {res['error']}", flush=True)
            log["ngs_recall"] = res
            return [{"error": res["error"], "round": i}
                    for i in range(1, args.rounds + 1)]
        hits = res.get("hits", [])
        full = [h for h in hits if not h.get("stub") and h.get("body")]
        stubs = [h for h in hits if h.get("stub")]
        ctx = "\n\n---\n\n".join(h["body"] for h in full)
        print(f"  NGS recalled {len(hits)} hits ({len(full)} full, "
              f"{len(stubs)} stub), {len(ctx)} chars, "
              f"tokens_used={res.get('tokens_used')}/"
              f"{res.get('tokens_budget')}, abstained={res.get('abstained')}, "
              f"arms_complete={res.get('arms_complete')}", flush=True)
        log["recalled_chars"] = len(ctx)
        log["recall"] = {
            "source": "ngs", "k": args.ngs_k,
            "token_budget": args.ngs_token_budget,
            "token_budget_unit": "engine tokens (chars/4 estimate); "
                "4000 tokens is the same NUMBER as the fleet's 4000-char "
                "budget but ~4x the chars. R4: the budget binds, not k -- "
                "hits are returned in rank order until it is spent, past k "
                "when it allows; a fact that does not fit full is skipped "
                "for a smaller one that does, and a title-only stub is "
                "returned only for the highest-ranked deferred facts "
                "needed to reach k.",
            "query": rq, "abstained": res.get("abstained"),
            "arms_complete": res.get("arms_complete"),
            "timed_out": res.get("timed_out"),
            "tokens_used": res.get("tokens_used"),
            "tokens_budget": res.get("tokens_budget"),
            "best_confidence": res.get("best_confidence"),
            "min_confidence": res.get("min_confidence"),
            "confidence_calibrated": res.get("confidence_calibrated"),
            "hits": [{"title": h.get("title"), "score": h.get("score"),
                      "confidence": h.get("confidence"),
                      "tokens": h.get("tokens"), "stub": h.get("stub")}
                     for h in hits],
        }
        recs = []
        for i in range(1, args.rounds + 1):
            prompt = (f"Recalled context from NGS:\n{ctx}\n\nQuestion: {q}\n"
                      f"Answer using only the recalled context above. Reply in under 200 words.")
            r = anth_call(prompt)
            r["round"] = i
            r["cost"] = cost(r)
            recs.append(r)
            print(f"  N round {i}: in={r.get('input')} read={r.get('cache_read')} "
                  f"write={r.get('cache_write')} out={r.get('output')} "
                  f"cost=${(r['cost'] or 0):.4f}", flush=True)
        return recs

    # Arms: the recall source selects the answer arm (fleet Shards or
    # local NGS); --skip-raw drops Arm A when its total already exists
    # in an earlier log. The fleet path below is untouched by the NGS arm.
    if args.recall_source == "ngs":
        recs_n = run_ngs()
        log["arms"]["ngs"] = recs_n
        recs_a = [] if args.skip_raw else run_raw()
        if recs_a:
            log["arms"]["raw"] = recs_a
    else:
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
    if args.recall_source == "ngs":
        tn = total(log["arms"]["ngs"])
        ta = total(log["arms"].get("raw", [])) if "raw" in log["arms"] else None
        log["totals"] = {"ngs": tn, "raw": ta,
                         "ratio": (ta / tn) if (ta and tn) else None,
                         "saved_pct": (100 * (1 - tn / ta)) if ta else None}
        print(f"\nTOTAL ngs: ${tn:.4f}" +
              (f" | raw: ${ta:.4f} | ratio {ta/tn:.1f}x | "
               f"saved {100*(1-tn/ta):.1f}%" if ta else " | raw: skipped"))
    else:
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
