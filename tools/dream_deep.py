"""Deep-dream cycle (wargames/dream-harder.md): real SFT pairs + LLM invariants.

Dreams over what we've got: top high-utility DB shards + the week's digest
picks. Local gemma writes grounded QA pairs (to get the e-models ready for
LoRA burn-in) and compiles semantic invariants into semantic_knowledge.
Volume runs on the Stadium (local ollama); every knob env-resolved (Rule 0.2).
Thermally tolerant: per-call failures are counted and skipped, never fatal.
"""
import os
import re
import sys
import json
import glob
import time
import argparse
import datetime
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("NOUGEN_VAULT_DIR", r"C:/Users/super/Watchtower/vault")

import nougen_shards.core as core
import nougen_shards.dream as dream_mod

OLLAMA_URL = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")
SFT_TOP = int(os.environ.get("NOUGEN_DEEP_SFT_TOP", "200"))
INV_TOP = int(os.environ.get("NOUGEN_DEEP_INV_TOP", "60"))
CONTENT_CAP = int(os.environ.get("NOUGEN_DEEP_CONTENT_CAP", "3000"))
CALL_TIMEOUT = int(os.environ.get("NOUGEN_DEEP_CALL_TIMEOUT_S", "300"))
SFT_OUT = os.environ.get("NOUGEN_DEEP_SFT_OUT", "dream_sft_deep.jsonl")


def _models():
    with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
        return [m["name"] for m in json.loads(r.read())["models"]]


def _resolve_volume_model():
    env = os.environ.get("NOUGEN_DREAM_LOCAL_MODEL")
    if env:
        return env
    try:
        models = _models()
        for pref in ("gemma4:12b",):
            if pref in models:
                return pref
        gemma = sorted(m for m in models if "gemma" in m.lower() and "cloud" not in m.lower())
        if gemma:
            return gemma[0]
        gemma_any = sorted(m for m in models if "gemma" in m.lower())
        if gemma_any:
            return gemma_any[-1]
    except Exception as e:
        print(f"volume-model probe failed: {e}", file=sys.stderr)
    return "gemma4:12b"


def chat(model, prompt):
    payload = json.dumps({"model": model, "stream": False,
                          "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=CALL_TIMEOUT) as r:
        return json.loads(r.read())["message"]["content"]


def parse_json_array(text):
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return json.loads(text)


def load_digest_picks(vault):
    """Papers selected by the daily digests: (title, abstract, shard filename)."""
    picks = []
    for dpath in glob.iglob(os.path.join(vault, "arxiv_digest_*.md")):
        with open(dpath, encoding="utf-8") as f:
            dtext = f.read()
        for m in re.finditer(r"\*\*shard:\*\* `([^`]+)`", dtext):
            spath = os.path.join(vault, m.group(1))
            if not os.path.exists(spath):
                continue
            with open(spath, encoding="utf-8") as f:
                stext = f.read()
            tm = re.search(r"^# (.+)$", stext, re.MULTILINE)
            am = re.search(r"## Abstract\n(.*?)(?:\n---|\Z)", stext, re.DOTALL)
            if tm and am:
                picks.append({"title": tm.group(1).strip(),
                              "content": am.group(1).strip()[:CONTENT_CAP],
                              "source": m.group(1)})
    seen, uniq = set(), []
    for p in picks:
        if p["source"] not in seen:
            seen.add(p["source"])
            uniq.append(p)
    return uniq


def gen_sft_pairs(model, item):
    prompt = (
        "From the content below, write exactly 2 question-answer training pairs a practitioner "
        "might ask about it. Ground every answer ONLY in the content — no outside knowledge. "
        "Output raw JSON ONLY, schema: "
        '[{"instruction": "<question>", "output": "<answer>"}]\n\n'
        f"Title: {item['title']}\n\nContent: {item['content'][:CONTENT_CAP]}"
    )
    pairs = parse_json_array(chat(model, prompt))
    return [p for p in pairs if isinstance(p, dict) and p.get("instruction") and p.get("output")]


def gen_invariants(model, item):
    prompt = (
        "Extract the core verified claims from the content below as structured facts. "
        "Output raw JSON ONLY, schema: "
        '[{"subject": "<system/method/entity>", "predicate": "<strict factual claim about it>"}]\n'
        "Only claims actually stated in the content. Empty array if none.\n\n"
        f"Title: {item['title']}\n\nContent: {item['content'][:CONTENT_CAP]}"
    )
    invs = parse_json_array(chat(model, prompt))
    return [i for i in invs if isinstance(i, dict) and i.get("subject") and i.get("predicate")]


def upsert_invariants(invs, domain_key, db_index=1):
    conn = core.get_connection(db_index)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    n = 0
    try:
        for inv in invs:
            conn.execute("""
                INSERT INTO semantic_knowledge (subject, predicate, domain_key, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(subject, predicate) DO UPDATE SET
                    confidence_score = confidence_score + 0.1,
                    updated_at = excluded.updated_at
            """, (inv["subject"].strip(), inv["predicate"].strip(), domain_key, ts))
            n += 1
        conn.commit()
    finally:
        conn.close()
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sft-top", type=int, default=SFT_TOP)
    ap.add_argument("--inv-top", type=int, default=INV_TOP)
    ap.add_argument("--skip-picks", action="store_true",
                    help="skip digest picks (already dreamed in a prior pass)")
    args = ap.parse_args()

    vault = str(core.GLOBAL_DIR)
    model = _resolve_volume_model()
    print(f"volume model: {model}", file=sys.stderr)

    picks = [] if args.skip_picks else load_digest_picks(vault)
    top_shards = [
        {"title": s["title"], "content": (s["content"] or "")[:CONTENT_CAP], "source": f"db:{s['id']}"}
        for s in dream_mod.fetch_high_utility_shards(limit=args.sft_top)
        if s.get("content")
    ]
    print(f"digest picks: {len(picks)}, top-utility shards: {len(top_shards)}", file=sys.stderr)

    stats = {"sft_items": 0, "sft_pairs": 0, "sft_parse_fail": 0,
             "inv_items": 0, "inv_rows": 0, "inv_parse_fail": 0, "call_errors": 0}

    sft_path = os.path.join(vault, SFT_OUT)
    t0 = time.time()
    with open(sft_path, "a", encoding="utf-8") as f:
        for item in picks + top_shards:
            try:
                pairs = gen_sft_pairs(model, item)
                if not pairs:
                    stats["sft_parse_fail"] += 1
                    continue
                for p in pairs:
                    f.write(json.dumps({"instruction": p["instruction"], "output": p["output"],
                                        "source": item["source"]}) + "\n")
                stats["sft_items"] += 1
                stats["sft_pairs"] += len(pairs)
            except json.JSONDecodeError:
                stats["sft_parse_fail"] += 1
            except Exception as e:
                stats["call_errors"] += 1
                print(f"sft call failed ({item['source']}): {e}", file=sys.stderr)
            f.flush()

    for item in picks + top_shards[:args.inv_top]:
        try:
            invs = gen_invariants(model, item)
            if not invs:
                stats["inv_parse_fail"] += 1
                continue
            stats["inv_rows"] += upsert_invariants(invs, domain_key="dream-deep")
            stats["inv_items"] += 1
        except json.JSONDecodeError:
            stats["inv_parse_fail"] += 1
        except Exception as e:
            stats["call_errors"] += 1
            print(f"inv call failed ({item['source']}): {e}", file=sys.stderr)

    stats["minutes"] = round((time.time() - t0) / 60, 1)
    stats["sft_file"] = sft_path
    stats["model"] = model
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
