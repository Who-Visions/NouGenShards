"""Reverse-engineer donor repos' CODE on the free fleet and extract self-improvement mechanisms.

    python tools/pr_reviewer/reverse.py owner/repo[:pat1,pat2] [...] [--out DIR] [--lanes 2]

Pulls the core source (via `gh api`, .py/.ts, tests excluded) of each repo, splits it into CHUNK-char pieces and sends
every piece to `--lanes` independent fleet routes (NouGen/tools/fleet.py, max_tokens=2048). Raw answers land in
<out>/fleet_raw.json for a coach to review; nothing is ported automatically.

Trap (2026-11-15): 24k-char prompts make every free route fail with "budget exhausted"; keep chunks <= 7k.
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess
import sys

CHUNK = 7000
PER_REPO = 21000
FLEET = pathlib.Path(r"C:\Users\super\Outpost\NouGen\tools")
ASK = ("You are reverse-engineering a self-improving AI system's SOURCE CODE for an LLM PR-reviewer whose RSI loop "
       "versions a weighted checklist, scores findings as held/dismissed from the author's later push, and adopts a new "
       "version only past a holdout gate. Extract ONLY mechanisms actually implemented in the code below (cite file and "
       "function): (1) candidate generation, (2) scoring/selection, (3) anti-reward-hacking or drift guards, "
       "(4) archive/parent selection, (5) memory/playbook add/merge/prune. Give a 1-3 line port for each. Reply as JSON: "
       '{"repo":..,"mechanisms":[{"name":..,"where":..,"how":..,"port":..}]}\n\nRepo: ')


def chunks(text: str, size: int = CHUNK, limit: int = PER_REPO) -> list[str]:
    """Fixed-size pieces of at most `limit` chars total; empty text gives no pieces."""
    text = text[:limit]
    return [text[i:i + size] for i in range(0, len(text), size)]


def parse_target(t: str) -> tuple[str, list[str]]:
    """'owner/repo:pat1,pat2' -> ('owner/repo', ['pat1','pat2']); no patterns = every source file."""
    repo, _, pats = t.partition(":")
    if repo.count("/") != 1 or any(p in (".", "..", "") for p in repo.split("/")):
        raise ValueError(f"bad repo {t!r}")
    return repo, [p for p in pats.split(",") if p]


def _gh(*a: str) -> str:
    return subprocess.run(["gh", "api", *a], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=60, stdin=subprocess.DEVNULL).stdout


def sources(repo: str, pats: list[str]) -> str:
    meta = json.loads(_gh(f"repos/{repo}") or "{}")
    tree = json.loads(_gh(f"repos/{repo}/git/trees/{meta.get('default_branch', 'main')}?recursive=1") or "{}").get("tree", [])
    paths = [t["path"] for t in tree if t.get("type") == "blob" and t["path"].endswith((".py", ".ts"))
             and "test" not in t["path"] and (not pats or any(p in t["path"] for p in pats))]
    buf = ""
    for p in sorted(paths, key=len)[:12]:
        c = json.loads(_gh(f"repos/{repo}/contents/{p}") or "{}").get("content")
        if c:
            buf += f"\n### {p}\n" + base64.b64decode(c).decode("utf-8", "replace")[:6000]
        if len(buf) > PER_REPO:
            break
    return buf


def main() -> int:
    ap = argparse.ArgumentParser(prog="reverse")
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--out", default=str(pathlib.Path.home() / ".nougen" / "research" / "reverse"))
    ap.add_argument("--lanes", type=int, default=2)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    prompts, keys = [], []
    for t in a.targets:
        repo, pats = parse_target(t)
        for piece in chunks(sources(repo, pats)):
            for _ in range(max(1, a.lanes)):
                prompts.append(ASK + repo + "\n" + piece); keys.append(repo)
    if not prompts:
        print(json.dumps({"error": "no source found"})); return 2
    sys.path.insert(0, str(FLEET))
    from fleet import Fleet  # noqa: E402
    f = Fleet(); f.probe(verbose=False)
    try:
        f.diversify()
    except Exception:
        pass
    res = f.map(prompts, max_tokens=2048)
    rows = [{"repo": k, "result": x if isinstance(x, (str, dict)) else str(x)} for k, x in zip(keys, res)]
    ok = sum(1 for r in rows if "FAILED" not in str(r["result"])[:80])
    (out / "fleet_raw.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"out": str(out / "fleet_raw.json"), "calls": len(rows), "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
