"""Atomize cross-agent handoff notes into single-claim DOCTRINE shards.

Closes the second coverage gap from wargames/retrieval-quality.md: operational
knowledge (incidents, fixes, doctrine) accumulates in .handoffs/**/handoff_*.md
which semantic recall never federates. Same fleet mechanism as
atomize_journal_shards.py; capture() dedupes so re-runs are idempotent.
Dynamic per Rule 0.2: paths/models env-resolved with probes.
"""
import os
import re
import sys
import json
import glob
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("NOUGEN_VAULT_DIR", r"C:/Users/super/Watchtower/vault")

from nougen_shards.core import capture

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDOFF_DIR = os.environ.get("NOUGEN_HANDOFF_DIR", os.path.join(REPO, ".handoffs"))
OLLAMA_URL = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")
MAX_CLAIMS = int(os.environ.get("NOUGEN_ATOMIZE_MAX_CLAIMS", "8"))
BODY_CAP = int(os.environ.get("NOUGEN_ATOMIZE_BODY_CAP", "4000"))
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


def atomize(model, name, body):
    prompt = (
        f"The text below is an engineering session handoff note. Extract at most {MAX_CLAIMS} "
        "atomic, self-contained factual claims worth remembering permanently: incidents and their "
        "root causes, fixes and where they live, standing rules, named tools/commits and what they do. "
        "Each claim must stand alone (name systems explicitly, no pronouns pointing outside the claim) "
        "and cover ONE topic. Skip status chatter, dates-only lines, and empty sections. "
        'Output raw JSON ONLY: [{"title": "<short specific headline>", "claim": "<1-3 sentence fact>"}]. '
        "Output [] if nothing is worth keeping.\n\n"
        f"Handoff file: {name}\n\n{body[:BODY_CAP]}"
    )
    res = chat(model, prompt)
    m = re.search(r"\[\s*\{.*\}\s*\]", res, re.DOTALL)
    if not m:
        return []
    items = json.loads(m.group(0))
    return [i for i in items if isinstance(i, dict) and i.get("title") and i.get("claim")]


def main():
    files = sorted(glob.glob(os.path.join(HANDOFF_DIR, "**", "handoff_*.md"), recursive=True))
    if not files:
        print(json.dumps({"error": f"no handoff files under {HANDOFF_DIR}"}))
        return 1
    model = _resolve_model()
    print(f"model: {model}, files: {len(files)}", file=sys.stderr)
    done, claims_written, dupes, fails = 0, 0, 0, 0
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                body = f.read()
        except Exception:
            continue
        name = os.path.basename(path)
        done += 1
        try:
            claims = atomize(model, name, body)
        except Exception as e:
            fails += 1
            print(f"atomize failed ({name[:50]}): {e}", file=sys.stderr)
            continue
        for c in claims:
            ok = capture("DOCTRINE", c["title"].strip()[:200], c["claim"].strip(),
                         ["atomic", "handoff-derived"])
            claims_written += ok
            dupes += (not ok)
        print(f"[{done}/{len(files)}] {name[:60]} -> {len(claims)}", file=sys.stderr)
    print(json.dumps({"files": done, "atomic_claims_written": claims_written,
                      "duplicates": dupes, "failures": fails, "model": model}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
