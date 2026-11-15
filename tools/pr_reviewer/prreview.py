"""prreview: independent, read-only PR reviews by other agents, with the verdict extracted.

    prreview rsi status|evolve|rollback <v>   (the aiwithdav3 RSI loop)
    prreview verdicts <owner/repo> <pr>        (review-loop state: done? next command)
    prreview reverse owner/repo[:pats] ...     (fleet reads donor code, extracts mechanisms)
    prreview <owner/repo> <pr> [<pr> ...] [--focus "..."] [--prior FILE] [--agent codex|agy|both]

- Runs Codex (`codex exec --yolo`) and/or Antigravity (`agy --dangerously-skip-permissions -p`)
  READ-ONLY: the prompt forbids merge/push/comment/edit. stdin is closed (Codex otherwise hangs
  forever on "Reading additional input from stdin").
- Falls back: if Codex hits its usage limit, Antigravity runs instead (and vice versa).
- --prior FILE: a previous report; the reviewer must mark each old finding FIXED / NOT FIXED.
- Writes the full log to ~/.nougen/research/reviews/<repo>-<prs>-<agent>-<stamp>.md and prints
  only the verdict lines (MERGE / MERGE-WITH-NITS / BLOCK + P1/P2/P3 findings).
--post (or --agent aiwithdav3): the posting lane. Runs ~/.nougen/bin/pr_reviewer/review.ts, which reviews
  on the free lanes (fallback to local e2b, then agy), has a second lane supervise, and POSTS a GitHub review
  as aiwithdav3, once per head SHA. It never merges.
Exit: 0 if every PR is MERGE or MERGE-WITH-NITS, 1 if any BLOCK, 2 if no verdict came back.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import shutil
import subprocess
import sys

OUT = pathlib.Path.home() / ".nougen" / "research" / "reviews"
LIMIT_RE = re.compile(r"usage limit|rate limit|quota", re.I)
KEEP_RE = re.compile(r"(MERGE-WITH-NITS|\bMERGE\b|\bBLOCK\b|NOT FIXED|\bFIXED\b|\*\*P[123]\b|^\s*\d+\.\s+\*\*|Overall)", re.I)


def prompt(repo, prs, focus, prior):
    p = (f"Read-only code review of GitHub PR(s) {repo} " + ", ".join(f"#{n}" for n in prs) +
         f". Use `gh pr diff <n> -R {repo}` and `gh pr view <n> -R {repo}`. Do NOT merge, push, comment, approve, "
         "or edit any file: review only. For EACH PR: a verdict line `#<n> — MERGE | MERGE-WITH-NITS | BLOCK`, then "
         "numbered findings `**P1|P2|P3** — file:line: problem. Fix: one line.` Reproduce a finding when you can. "
         "End with one line starting `Overall:`.")
    if focus:
        p += f" Focus: {focus}"
    if prior:
        p += ("\nA previous review reported the findings below. For each one say FIXED or NOT FIXED with file:line "
              "evidence, then list any NEW issue:\n" + pathlib.Path(prior).read_text(encoding="utf-8", errors="replace")[-6000:])
    return p


def run(agent, cwd, text, timeout):
    cmd = (["codex", "exec", "--yolo", text] if agent == "codex"
           else ["agy", "--dangerously-skip-permissions", "--print-timeout", f"{timeout}s", "-p", text])
    # No shell: through cmd.exe the whole command line is capped at 8191
    # characters, so a re-review prompt that carries the prior report was cut
    # off and the agent returned nothing (2026-11-11, exit 4, empty log).
    # CreateProcess takes 32767; resolve the .cmd/.exe shim and call it directly.
    exe = shutil.which(cmd[0])
    if not exe:
        return f"[prreview] {agent} is not installed"
    cmd = [exe] + cmd[1:]
    if sys.platform == "win32" and exe.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/d", "/s", "/c"] + cmd  # shims still need cmd; keep the prompt short below
    if sum(len(c) + 3 for c in cmd) > 32000:
        return f"[prreview] prompt too long for one command line ({sum(len(c) for c in cmd)} chars); shorten --prior"
    try:
        r = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout + 60,
                           encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        return (e.stdout or "") + f"\n[prreview] {agent} timed out after {timeout}s"
    except FileNotFoundError:
        return f"[prreview] {agent} is not installed"


def verdict_lines(log):
    seen, out = set(), []
    for line in log.splitlines():
        s = line.strip()
        if s and KEEP_RE.search(s) and s not in seen and not s.startswith(("Read-only code review", "A previous review")):
            seen.add(s)
            out.append(s[:300])
    return out


def rsi(argv):
    """prreview rsi status|evolve|rollback <v>: the aiwithdav3 RSI loop, via review.ts."""
    here = pathlib.Path(__file__).resolve().parent
    script = here / "review.ts" if (here / "review.ts").exists() else pathlib.Path.home() / ".nougen" / "bin" / "pr_reviewer" / "review.ts"
    bun = shutil.which("bun") or str(pathlib.Path.home() / ".bun" / "bin" / "bun.exe")
    return subprocess.run([bun, str(script), "rsi", *(argv or ["status"])], stdin=subprocess.DEVNULL).returncode


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "rsi":
        return rsi(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in ("verdicts", "reverse"):
        here = pathlib.Path(__file__).resolve().parent
        return subprocess.run([sys.executable, str(here / f"{sys.argv[1]}.py"), *sys.argv[2:]], stdin=subprocess.DEVNULL).returncode
    ap = argparse.ArgumentParser(prog="prreview")
    ap.add_argument("repo")
    ap.add_argument("prs", nargs="+", type=int)
    ap.add_argument("--focus", default="")
    ap.add_argument("--prior")
    ap.add_argument("--agent", default="codex", choices=["codex", "agy", "both", "aiwithdav3"])
    ap.add_argument("--post", action="store_true", help="also post a real review as aiwithdav3")
    ap.add_argument("--cwd", default=str(pathlib.Path.home()))
    ap.add_argument("--timeout", type=int, default=1500)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    text = prompt(a.repo, a.prs, a.focus, a.prior)
    if a.agent == "aiwithdav3":
        return post_reviews(a.repo, a.prs)
    agents = ["codex", "agy"] if a.agent == "both" else [a.agent]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    worst = 2
    for agent in agents:
        log = run(agent, a.cwd, text, a.timeout)
        if LIMIT_RE.search(log[-2000:]) and a.agent != "both":
            other = "agy" if agent == "codex" else "codex"
            print(f"[prreview] {agent} hit a usage limit; falling back to {other}")
            agent, log = other, run(other, a.cwd, text, a.timeout)
        path = OUT / f"{a.repo.split('/')[-1]}-{'-'.join(map(str, a.prs))}-{agent}-{stamp}.md"
        path.write_text(log, encoding="utf-8")
        lines = verdict_lines(log)
        print(f"\n== {agent} ({path}) ==")
        print("\n".join(lines[-40:]) if lines else "(no verdict found; read the full log)")
        joined = " ".join(lines).upper()
        if "BLOCK" in joined:
            worst = max(worst if worst != 2 else 0, 1)
        elif "MERGE" in joined:
            worst = 0 if worst == 2 else worst
    if a.post:
        post_reviews(a.repo, a.prs)
    return worst


def post_reviews(repo, prs):
    """Posting lane: aiwithdav3 review via the Bun reviewer. 0 if every PR posted or was already reviewed."""
    here = pathlib.Path(__file__).resolve().parent
    script = here / "review.ts" if (here / "review.ts").exists() else pathlib.Path.home() / ".nougen" / "bin" / "pr_reviewer" / "review.ts"
    bun = shutil.which("bun") or str(pathlib.Path.home() / ".bun" / "bin" / "bun.exe")
    rc = 0
    for n in prs:
        r = subprocess.run([bun, str(script), "review", repo, str(n)], stdin=subprocess.DEVNULL, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=3600)
        tail = "\n".join((r.stdout or r.stderr or "").strip().splitlines()[-8:])
        print(f"\n== aiwithdav3 #{n} ==\n{tail}")
        rc = max(rc, r.returncode)
    return rc


if __name__ == "__main__":
    sys.exit(main())
