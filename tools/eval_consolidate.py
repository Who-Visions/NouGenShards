"""Frozen evaluator for the shard consolidation guard (nougen_shards.consolidate.consolidate).

    python tools/eval_consolidate.py            # score, verify the lock
    python tools/eval_consolidate.py --lock     # first run only: write the lock

The model only PROPOSES; consolidate() verifies. This eval measures the verifier, not a model:
for each fact it feeds every proposal kind through a scripted decider (add, none,
supersede_valid = a real neighbour, supersede_bogus = a hallucinated id) and checks the final
action that comes out. That is the guarantee the module claims: whatever the model says, the
final store action is one the rules allow.

Each check carries a tag:
  spec      the rule is stated in consolidate.py or tests/test_consolidate.py
  proposed  an invariant this eval proposes; the module does not enforce it yet

Both are reported separately. A failing "proposed" check is a gap, not a regression.

The fixture is frozen by sha256 (evals/consolidate_v1.lock.json). Dev is for revising the
guard; heldout is the gate. Shadow mode: reads only, a local model is not needed.

Exit codes: 0 pass, 1 a heldout "spec" check failed, 2 no lock file, 3 fixture changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nougen_shards.consolidate import consolidate  # noqa: E402

FIXTURE = ROOT / "evals" / "consolidate_v1.jsonl"
LOCK = ROOT / "evals" / "consolidate_v1.lock.json"
PROPOSALS = ("add", "none", "supersede_valid", "supersede_bogus")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proposal(kind: str, case: dict) -> dict:
    if kind == "add":
        return {"action": "ADD", "target_id": None, "reason": "scripted"}
    if kind == "none":
        return {"action": "NONE", "target_id": None, "reason": "scripted"}
    if kind == "supersede_valid":
        target = case.get("valid_target", case["neighbours"][0]["id"])
        return {"action": "SUPERSEDE", "target_id": target, "reason": "scripted"}
    if kind == "supersede_bogus":
        return {"action": "SUPERSEDE", "target_id": "999", "reason": "scripted"}
    raise ValueError(kind)


def final_of(result: dict) -> str:
    action = result["action"]
    if action in ("SUPERSEDE", "CONFLICT"):
        return f"{action}:{result.get('supersedes') or result.get('target')}"
    return action


def run(case: dict, kind: str) -> str:
    fixed = proposal(kind, case)
    result = consolidate(
        case["new_fact"],
        case["neighbours"],
        lambda _fact, _n: dict(fixed),
        new_status=case["new_status"],
    )
    return final_of(result)


def score(cases: list[dict]) -> dict:
    checks = []
    for c in cases:
        for kind in PROPOSALS:
            want = c["expect"][kind]
            got = run(c, kind)
            checks.append(
                {
                    "id": c["id"],
                    "proposal": kind,
                    "tag": c["tags"][kind],
                    "want": want,
                    "got": got,
                    "ok": got == want,
                }
            )
    by_tag: dict[str, list[bool]] = defaultdict(list)
    for ch in checks:
        by_tag[ch["tag"]].append(ch["ok"])
    return {
        "checks": len(checks),
        "accuracy": round(sum(ch["ok"] for ch in checks) / len(checks), 3) if checks else None,
        "by_tag": {
            t: {"n": len(v), "accuracy": round(sum(v) / len(v), 3)} for t, v in sorted(by_tag.items())
        },
        "failures": [ch for ch in checks if not ch["ok"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", action="store_true", help="write the sha256 lock (first run only)")
    args = ap.parse_args()

    digest = sha256(FIXTURE)
    if args.lock:
        LOCK.write_text(json.dumps({"fixture": FIXTURE.name, "sha256": digest}, indent=2) + "\n")
        print(f"locked {FIXTURE.name} at {digest}")
    elif not LOCK.exists():
        print("no lock file; run once with --lock", file=sys.stderr)
        return 2
    elif json.loads(LOCK.read_text())["sha256"] != digest:
        print("fixture changed since lock; refusing to score", file=sys.stderr)
        return 3

    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = {"fixture_sha256": digest[:12]}
    for split in ("dev", "heldout"):
        report[split] = score([r for r in rows if r["split"] == split])
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # The gate reads heldout only (AHL), and only "spec" checks: a failing
    # "proposed" check is a known gap, not a regression, so it stays informational.
    regressions = [f for f in report["heldout"]["failures"] if f["tag"] == "spec"]
    if regressions:
        ids = ", ".join(f"{f['id']}/{f['proposal']}" for f in regressions)
        print(f"heldout spec regression ({len(regressions)}): {ids}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
