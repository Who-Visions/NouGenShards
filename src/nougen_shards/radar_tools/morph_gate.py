#!/usr/bin/env python3
r"""Morph gate: turn a candidate's key claims into typed evidence by checking the paper body.

    morph_gate.py 2609.34785 '55\\.0\\\\?%[^.]{0,40}75\\.0' '600 human-reviewed'

Each claim is a regex that must match the paper's own LaTeX (tools/arxiv_paper.py).
All found   -> evidence_type "paper_body"    (NouGenMorph verifiability ceiling 0.8)
Any missing -> evidence_type "abstract_only" (ceiling 0.4) and the missing claims listed.
Body unavailable (PDF-only, fetch failure) -> "abstract_only" with the reason; never a pass.

Write claims ANCHORED on words, not bare numbers: '75\.0' also matches unrelated table cells,
while 'self-improved model reaches 75\.0' says what the number is. (BEHAVE taught this: its
'55.0 -> 73.3' sentence is RL training; the self-improvement result 55.0 -> 75.0 is elsewhere.)

Output is a JSON row shaped like nougen_morph MorphEvidence, so it can be passed straight in.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("arxiv_paper", Path(__file__).resolve().parent / "arxiv_paper.py")
ap = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("arxiv_paper", ap)
_spec.loader.exec_module(ap)


def gate(ref: str, claims: list[str]) -> dict:
    if not claims:
        raise ValueError("a gate needs at least one claim to check")
    aid = ap.normalize_id(ref)
    found, missing, where = [], [], {}
    try:
        for c in claims:
            hits = ap.claim(aid, c)
            (found if hits else missing).append(c)
            if hits:
                where[c] = hits[0][:240]
        reason = None
    except Exception as e:  # noqa: BLE001 - any failure to read the body is a non-pass
        found, missing, reason = [], list(claims), f"{type(e).__name__}: {e}"
    ok = not missing
    return {
        "source": f"arXiv:{aid}",
        "claim": "; ".join(claims),
        "confidence": round(len(found) / len(claims), 3),
        "evidence_type": "paper_body" if ok else "abstract_only",
        "provenance": "nougen-radar morph_gate: regex over e-print LaTeX body",
        "found": found,
        "missing": missing,
        "context": where,
        "body_unavailable": reason,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("ref")
    p.add_argument("claims", nargs="+", help="regex per key claim; all must appear in the body")
    a = p.parse_args()
    row = gate(a.ref, a.claims)
    print(json.dumps(row, indent=2))
    return 0 if row["evidence_type"] == "paper_body" else 1


if __name__ == "__main__":
    raise SystemExit(main())
