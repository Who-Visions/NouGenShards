"""arXiv daily digest prototype (arxiv-evolution Move 2).

Fleet does the work: local/cloud ollama gemma triages one announce-day's shards
to the most NouGen-relevant papers, then summarizes each from its abstract ONLY.
Coach reviews output. Dynamic per Rule 0.2: everything env-resolved with probes.
"""
import os
import re
import sys
import json
import glob
import argparse
import urllib.request

OLLAMA_URL = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")
TOP_N = int(os.environ.get("NOUGEN_DIGEST_TOP_N", "10"))
TRIAGE_BATCH = int(os.environ.get("NOUGEN_DIGEST_TRIAGE_BATCH", "120"))
ABSTRACT_CAP = int(os.environ.get("NOUGEN_DIGEST_ABSTRACT_CAP", "1500"))
INTERESTS = os.environ.get(
    "NOUGEN_DIGEST_INTERESTS",
    "LLM agents, agent memory systems, RAG/retrieval, context compression, "
    "multi-agent orchestration, evals/benchmarks for agents, local/edge inference, "
    "knowledge distillation, tool use",
)


def _resolve_vault_root():
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return env
    try:
        with open(os.path.join(os.path.expanduser("~"), ".nougen", "config.json"), encoding="utf-8") as f:
            vd = json.load(f).get("vault_dir")
        if vd:
            return vd
    except Exception:
        pass
    return r"C:\Users\super\Watchtower\vault"


def _resolve_model():
    env = os.environ.get("NOUGEN_DIGEST_MODEL")
    if env:
        return env
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            models = [m["name"] for m in json.loads(r.read())["models"]]
        gemma = sorted(m for m in models if "gemma" in m.lower())
        if gemma:
            return gemma[-1]
        if models:
            return models[0]
    except Exception as e:
        print(f"model probe failed: {e}", file=sys.stderr)
    return "gemma4:12b"


def chat(model, prompt, timeout=600):
    payload = json.dumps({
        "model": model, "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def load_day_shards(vault, day):
    papers = []
    for path in glob.iglob(os.path.join(vault, "intelligence_shard_arxiv_*.md")):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if f"published_date: {day}" not in text:
            continue
        tm = re.search(r"^# (.+)$", text, re.MULTILINE)
        am = re.search(r"## Abstract\n(.*?)(?:\n---|\Z)", text, re.DOTALL)
        im = re.search(r"^arxiv_id: (.+)$", text, re.MULTILINE)
        papers.append({
            "id": (im.group(1).strip() if im else os.path.basename(path)),
            "title": tm.group(1).strip() if tm else "Untitled",
            "abstract": (am.group(1).strip() if am else "")[:ABSTRACT_CAP],
            "shard": os.path.basename(path),
        })
    return papers


def triage(model, papers):
    """Ask the fleet to pick TOP_N most relevant paper indexes; merge across batches."""
    picks = []
    for i in range(0, len(papers), TRIAGE_BATCH):
        batch = papers[i:i + TRIAGE_BATCH]
        listing = "\n".join(f"{i + j}: {p['title']}" for j, p in enumerate(batch))
        prompt = (
            f"You triage arXiv cs.AI papers for a team building: {INTERESTS}.\n"
            f"From the numbered titles below, output ONLY a JSON array of the {TOP_N} most relevant numbers, "
            f"most relevant first. No other text.\n\n{listing}"
        )
        res = chat(model, prompt)
        m = re.search(r"\[[\d,\s]*\]", res)
        if m:
            picks.extend(int(x) for x in json.loads(m.group(0)) if 0 <= int(x) < len(papers))
    # Final cut if multiple batches: re-rank the merged candidates by title.
    cand = [papers[i] for i in dict.fromkeys(picks)]
    if len(cand) > TOP_N:
        listing = "\n".join(f"{j}: {p['title']}" for j, p in enumerate(cand))
        res = chat(model, (
            f"Pick the {TOP_N} most relevant to: {INTERESTS}. "
            f"Output ONLY a JSON array of numbers, most relevant first.\n\n{listing}"
        ))
        m = re.search(r"\[[\d,\s]*\]", res)
        if m:
            cand = [cand[int(x)] for x in json.loads(m.group(0)) if 0 <= int(x) < len(cand)][:TOP_N]
    return cand[:TOP_N]


def summarize(model, paper):
    prompt = (
        "Compress ONLY the abstract below into at most 3 short sentences. "
        "Use no outside knowledge, add nothing not stated in the abstract.\n\n"
        f"Title: {paper['title']}\n\nAbstract: {paper['abstract']}"
    )
    return chat(model, prompt).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", required=True, help="announce day YYYY-MM-DD")
    args = ap.parse_args()

    vault = _resolve_vault_root()
    model = _resolve_model()
    print(f"model: {model}", file=sys.stderr)

    papers = load_day_shards(vault, args.day)
    print(f"papers on {args.day}: {len(papers)}", file=sys.stderr)
    if not papers:
        print(json.dumps({"error": f"no shards for {args.day}"}))
        return 1

    top = triage(model, papers)
    print(f"triage picked: {len(top)}", file=sys.stderr)

    lines = [f"# arXiv cs.AI Digest — {args.day}", "",
             f"*{len(papers)} papers announced; top {len(top)} selected for NouGen relevance "
             f"by {model}; summaries compress abstracts only.*", ""]
    for p in top:
        s = summarize(model, p)
        print(f"summarized {p['id']}", file=sys.stderr)
        lines += [f"## {p['title']}", f"- **arXiv:** {p['id']}  |  **shard:** `{p['shard']}`", s, ""]
    lines += ["---", f"*Full day: {len(papers)} shards match `published_date: {args.day}` in the vault.*"]

    out = os.path.join(vault, f"arxiv_digest_{args.day.replace('-', '')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(json.dumps({"digest": out, "papers": len(papers), "selected": len(top), "model": model}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
