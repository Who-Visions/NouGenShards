"""arXiv weekly digest aggregator (arxiv-evolution Move 4).

Aggregates the week's daily digests (arxiv_digest_YYYYMMDD.md) into one weekly
intelligence shard. The fleet (local/cloud ollama gemma) does the synthesis;
input is the daily digests only — no outside knowledge.
Dynamic per Rule 0.2: vault/model/URL env-resolved with probes.
"""
import os
import re
import sys
import json
import glob
import argparse
import datetime
import urllib.request

OLLAMA_URL = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")


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


def chat(model, prompt, timeout=900):
    payload = json.dumps({
        "model": model, "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--week", help="ISO week like 2026-W28 (default: week containing today)")
    args = ap.parse_args()

    vault = _resolve_vault_root()
    model = _resolve_model()

    if args.week:
        year, wk = args.week.split("-W")
        monday = datetime.date.fromisocalendar(int(year), int(wk), 1)
    else:
        today = datetime.date.today()
        monday = datetime.date.fromisocalendar(*today.isocalendar()[:2], 1)
    iso = f"{monday.isocalendar()[0]}-W{monday.isocalendar()[1]:02d}"

    dailies = []
    for i in range(7):
        day = monday + datetime.timedelta(days=i)
        path = os.path.join(vault, f"arxiv_digest_{day.strftime('%Y%m%d')}.md")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                dailies.append(f.read())
    if not dailies:
        print(json.dumps({"error": f"no daily digests found for {iso}"}))
        return 1
    print(f"week {iso}: {len(dailies)} daily digests, model {model}", file=sys.stderr)

    prompt = (
        "You are compiling a weekly research intelligence brief from the daily arXiv digests below. "
        "Using ONLY the content provided (no outside knowledge), write:\n"
        "1. '## Themes of the week' — 3-5 bullet themes you observe across the days.\n"
        "2. '## Must-reads' — the 5 most important papers of the week; for each give the title, "
        "its arXiv id exactly as shown, and ONE sentence on why it matters.\n"
        "3. '## Radar' — 3 papers worth watching, title + arXiv id only.\n"
        "Keep the whole brief under 450 words. Do not invent papers or ids.\n\n"
        + "\n\n=====\n\n".join(dailies)
    )
    brief = chat(model, prompt).strip()

    created = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    content = f"""---
topic: arxiv_weekly_digest_{iso}
source: arxiv-evolution
category: INTELLIGENCE
created_at: {created}
model: {model}
daily_digests: {len(dailies)}
---

# arXiv cs.AI Weekly Intelligence — {iso}

{brief}

---
*Synthesized by {model} from {len(dailies)} daily digests (fleet lane, abstracts only).*
"""
    out = os.path.join(vault, f"intelligence_shard_arxiv_weekly_{iso.replace('-', '_')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print(json.dumps({"week": iso, "dailies": len(dailies), "shard": out, "model": model}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
