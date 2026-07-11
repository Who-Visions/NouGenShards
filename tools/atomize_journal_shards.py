"""Atomize journal records into single-claim DOCTRINE shards (retrieval-quality H5).

Dense multi-topic journal records embed as muddy centroids and lose ranking to
sharp single-topic content. The fleet (ollama gemma) splits each record into
atomic, self-contained claims; each claim is captured as its own shard
(capture() dedupes). Proven mechanism: an atomic shard reaches vector-lane #1
and survives fusion via lane champions where its parent blob never surfaced.
Dynamic per Rule 0.2: paths/models env-resolved with probes.
"""
import os
import re
import sys
import json
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("NOUGEN_VAULT_DIR", r"C:/Users/super/Watchtower/vault")

from nougen_shards.core import capture, GLOBAL_DIR

OLLAMA_URL = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")
JOURNAL = os.environ.get("NOUGEN_JOURNAL_PATH", str(GLOBAL_DIR / "codex_memory_journal.jsonl"))
MAX_CLAIMS = int(os.environ.get("NOUGEN_ATOMIZE_MAX_CLAIMS", "8"))
CALL_TIMEOUT = int(os.environ.get("NOUGEN_ATOMIZE_TIMEOUT_S", "300"))


def _resolve_model():
    env = os.environ.get("NOUGEN_ATOMIZE_MODEL")
    if env:
        return env
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            models = [m["name"] for m in json.loads(r.read())["models"]]
        gemma = sorted(m for m in models if "gemma" in m.lower())
        if gemma:
            return gemma[-1]
    except Exception as e:
        print(f"model probe failed: {e}", file=sys.stderr)
    return "gemma4:12b"


def chat(model, prompt):
    payload = json.dumps({"model": model, "stream": False,
                          "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=CALL_TIMEOUT) as r:
        return json.loads(r.read())["message"]["content"]


def atomize(model, title, content):
    prompt = (
        f"Split the note below into at most {MAX_CLAIMS} atomic, self-contained factual claims. "
        "Each claim must stand alone (name the system/component explicitly, no pronouns referring "
        "outside the claim) and cover ONE topic only. Skip meta-commentary. Output raw JSON ONLY: "
        '[{"title": "<short specific headline>", "claim": "<1-3 sentence self-contained fact>"}]\n\n'
        f"Note title: {title}\n\nNote: {content[:4000]}"
    )
    res = chat(model, prompt)
    m = re.search(r"\[\s*\{.*\}\s*\]", res, re.DOTALL)
    items = json.loads(m.group(0) if m else res)
    return [i for i in items if isinstance(i, dict) and i.get("title") and i.get("claim")]


def main():
    if not os.path.isfile(JOURNAL):
        print(json.dumps({"error": f"journal missing: {JOURNAL}"}))
        return 1
    model = _resolve_model()
    print(f"model: {model}", file=sys.stderr)
    records, claims_written, dupes, fails = 0, 0, 0, 0
    with open(JOURNAL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            title = (rec.get("title") or "").strip()
            content = (rec.get("content") or "").strip()
            if not title or not content:
                continue
            records += 1
            try:
                claims = atomize(model, title, content)
            except Exception as e:
                fails += 1
                print(f"atomize failed ({title[:40]}): {e}", file=sys.stderr)
                continue
            tags = rec.get("tags") or []
            if isinstance(tags, str):
                tags = [t for t in tags.split(",") if t]
            for c in claims:
                ok = capture("DOCTRINE", c["title"].strip()[:200], c["claim"].strip(),
                             list(tags) + ["atomic"])
                claims_written += ok
                dupes += (not ok)
            print(f"[{records}] {title[:50]} -> {len(claims)} claims", file=sys.stderr)
    print(json.dumps({"records": records, "atomic_claims_written": claims_written,
                      "duplicates": dupes, "atomize_failures": fails, "model": model}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
