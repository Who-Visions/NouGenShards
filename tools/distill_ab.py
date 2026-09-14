#!/usr/bin/env python3
"""Detached A/B for the distillation lanes. Launch with pythonw so it outlives the
session and never flashes a console:

    Start-Process pythonw -ArgumentList 'tools\\distill_ab.py' -WindowStyle Hidden

1. runs the lanes-OFF baseline itself, before any sidecar write (no race with
   another process, and the A/B shares one golden set and one code state)
2. distils golden targets + the shards that outranked them (local e2b, resumable)
3. builds L2 scenes + L3 persona
4. re-runs the eval with the lanes ON and logs both overall MRR numbers

Log: analysis/recall_eval/distill_ab.log (plain text, Eastern times).
"""
from __future__ import annotations

import contextlib
import glob
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "analysis" / "recall_eval" / "distill_ab.log"
os.environ.setdefault("NOUGEN_VAULT_DIR", str(Path.home() / ".nougen" / "shards"))
os.environ["NOUGEN_QUERY_EMBED"] = "0"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


def log(msg: str) -> None:
    try:
        from zoneinfo import ZoneInfo
        stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%I:%M %p %Z").lstrip("0")
    except Exception:
        stamp = datetime.now().strftime("%I:%M %p")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {msg}\n")


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    import recall_eval  # noqa: E402  (after env is set)
    # Baseline runs HERE, lanes forced off per call, before any sidecar write, so
    # no other process can race it and the A/B shares one golden set and one code state.
    os.environ["NOUGEN_DISTILL_LANES"] = "0"
    log("baseline: eval with distill lanes OFF")
    with LOG.open("a", encoding="utf-8") as fh, contextlib.redirect_stdout(fh):
        base = recall_eval.run(recall_eval.GOLDEN, 10, True, 0.2, "*")
    os.environ["NOUGEN_DISTILL_LANES"] = "1"
    log(f"baseline overall MRR {base['overall']['mrr']} body R@10 {base['summary'].get('body', {}).get('recall@10')}")

    import distill_run  # noqa: E402  (after env is set)
    import recall_eval  # noqa: E402
    from nougen_shards import distill  # noqa: E402
    import coach  # noqa: E402
    c = coach.check()
    if not c["ok"]:
        log("STOP: coach gate refused: " + "; ".join(c["reasons"]))
        return 1
    with LOG.open("a", encoding="utf-8") as fh, contextlib.redirect_stdout(fh):
        keys = distill_run.keys_from_eval()
        log(f"distilling {len(keys)} shards (targets + hard negatives) on local e2b")
        distill_run.run(keys, None)
        log(f"scenes written: {distill.build_scenes(distill.connect(), distill_run.llm)}")
        persona = distill.build_persona(distill.connect(), distill_run.llm)
        log(f"persona: {(persona or 'none')[:200]!r}")
        log("A/B: eval with distill lanes ON")
        on = recall_eval.run(recall_eval.GOLDEN, 10, True, 0.2, "*")
    log(f"RESULT overall MRR {base['overall']['mrr']} -> {on['overall']['mrr']}; "
        f"body R@10 {base['summary'].get('body', {}).get('recall@10')} -> {on['summary'].get('body', {}).get('recall@10')}; "
        f"title R@10 {base['summary'].get('title', {}).get('recall@10')} -> {on['summary'].get('title', {}).get('recall@10')}; "
        f"p50 {base['latency_ms'].get('p50')} -> {on['latency_ms'].get('p50')} ms")
    log(json.dumps(distill.stats()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:  # a detached process must leave its cause behind
        log(f"CRASH {type(ex).__name__}: {ex}")
        raise
