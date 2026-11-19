"""Review-loop state for one PR: parse every prreview log (codex/agy) and say whether the loop is done.

    python tools/pr_reviewer/verdicts.py <owner/repo> <pr>     # or: prreview verdicts <owner/repo> <pr>

The loop is: review -> fix -> `prreview <repo> <pr> --agent agy --prior <latest log>` -> repeat until `done` (latest
verdict has no P1/P2 open). Logs live in ~/.nougen/research/reviews/<repo>-<pr>-<agent>-<YYYYMMDD-HHMM>.md.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

REVIEWS = pathlib.Path.home() / ".nougen" / "research" / "reviews"
NAME_RE = re.compile(r"^(?P<repo>.+)-(?P<pr>\d+)-(?P<agent>codex|agy|both)-(?P<stamp>\d{8}-\d{4})\.md$")
VERDICT_RE = re.compile(r"#(\d+)\s*\W+\s*(MERGE-WITH-NITS|MERGE|BLOCK)\b")
SEV_RE = re.compile(r"\*\*(P[123])\*\*")
STATUS_RE = re.compile(r"\*\*(NOT FIXED|FIXED)\*\*")


def parse_log(text: str, pr: int) -> dict:
    """Verdict for `pr`, counts of prior findings FIXED/NOT FIXED, and open findings by severity.

    Findings marked FIXED/NOT FIXED are the --prior checklist; any **P1/P2/P3** line that is not a FIXED line is open.
    """
    verdict = None
    for n, v in VERDICT_RE.findall(text):
        if int(n) == int(pr):
            verdict = v
    fixed = not_fixed = 0
    open_sev = {"P1": 0, "P2": 0, "P3": 0}
    for line in text.splitlines():
        st = STATUS_RE.search(line)
        if st:
            if st.group(1) == "FIXED":
                fixed += 1
                continue
            not_fixed += 1
        for sev in SEV_RE.findall(line):
            open_sev[sev] += 1
            break
    return {"verdict": verdict, "fixed": fixed, "not_fixed": not_fixed, "open": open_sev}


def loop_state(repo: str, pr: int, root: pathlib.Path = REVIEWS) -> dict:
    """All logs for repo#pr, oldest first, plus the loop decision from the newest log that carries a verdict."""
    short = repo.split("/")[-1]
    rows = []
    for p in sorted(root.glob(f"{short}-{int(pr)}-*.md")) if root.exists() else []:
        m = NAME_RE.match(p.name)
        if not m or int(m["pr"]) != int(pr):
            continue
        rows.append({"log": str(p), "agent": m["agent"], "stamp": m["stamp"],
                     **parse_log(p.read_text(encoding="utf-8", errors="replace"), pr)})
    rows.sort(key=lambda r: r["stamp"])
    latest = next((r for r in reversed(rows) if r["verdict"]), None)
    blocking = bool(latest) and (latest["verdict"] == "BLOCK" or latest["open"]["P1"] > 0
                                 or latest["open"]["P2"] > 0 or latest["not_fixed"] > 0)
    return {"repo": repo, "pr": int(pr), "rounds": rows, "latest": latest,
            "done": bool(latest) and not blocking,
            "next": ("merge (non-author lane)" if latest and not blocking else
                     f"fix, then: prreview {repo} {int(pr)} --agent agy --prior {latest['log']}" if latest else
                     f"prreview {repo} {int(pr)} --agent both")}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(json.dumps(loop_state(sys.argv[1], int(sys.argv[2])), indent=1))
