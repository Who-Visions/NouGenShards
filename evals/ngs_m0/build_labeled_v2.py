"""NGS M0: labeled set v2 = v1 gold + hand-written paraphrase queries.

Same gold shards and no-answer items as v1; only the answerable queries change,
so v1 vs v2 isolates how much of a score came from lexical overlap.

Usage: python evals/ngs_m0/build_labeled_v2.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    v1 = json.loads((HERE / "labeled_v1.json").read_text(encoding="utf-8"))
    para = json.loads((HERE / "paraphrases_v1.json").read_text(encoding="utf-8"))["queries"]
    answerable = [i for i in v1["items"] if i["kind"] == "answerable"]
    if len(para) != len(answerable):
        raise SystemExit(f"paraphrases ({len(para)}) != answerable items ({len(answerable)}): labeled_v1 changed")
    items = []
    for it, q in zip(answerable, para):
        items.append({**it, "query": q, "v1_query": it["query"]})
    items += [i for i in v1["items"] if i["kind"] == "no_answer"]
    body = {
        **{k: v for k, v in v1.items() if k not in ("items", "items_sha256", "counts", "name", "bias_note")},
        "name": "ngs-m0-labeled-v2",
        "bias_note": ("answerable queries are hand-written paraphrases (see paraphrases_v1.json note): "
                      "less lexical overlap than v1, but written by an author who had read the gold shards"),
        "items": items,
    }
    body["items_sha256"] = hashlib.sha256(
        json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    body["counts"] = {"answerable": len(answerable), "no_answer": len(items) - len(answerable)}
    out = HERE / "labeled_v2.json"
    out.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "counts": body["counts"], "sha256": body["items_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
