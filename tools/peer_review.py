#!/usr/bin/env python3
"""Peer review a PR as the aiwithdav3 GitHub account (see skills/peer-review/SKILL.md).

    peer_review.py show <PR> [--repo OWNER/NAME]
    peer_review.py approve <PR> --body "evidence"
    peer_review.py request-changes <PR> --body "reason"
    peer_review.py comment <PR> --body "note"

The reviewer token comes from the Keymaker (GITHUB_TOKEN_AIWITHDAV3) and is only
ever handed to `gh pr review` / `gh pr view`. This tool cannot merge.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

KEY_NAME = "GITHUB_TOKEN_AIWITHDAV3"
REVIEWER = "aiwithdav3"
DEFAULT_REPO = "Who-Visions/NouGenShards"
PASSING = {"SUCCESS", "SKIPPED", "NEUTRAL"}


def reviewer_token() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from nougen_shards import keymaker

    token = keymaker.get_secret(KEY_NAME)
    if not token:
        raise SystemExit(f"{KEY_NAME} is not in the Keymaker on this machine.")
    return token


def gh(args, token=None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    return subprocess.run(["gh", *args], env=env, capture_output=True, text=True)


def pr_state(pr: int, repo: str) -> dict:
    r = gh(["pr", "view", str(pr), "--repo", repo, "--json",
            "title,author,state,mergeStateStatus,reviewDecision,statusCheckRollup,url"])
    if r.returncode:
        raise SystemExit(r.stderr.strip())
    return json.loads(r.stdout)


def failing_checks(state: dict) -> list:
    out = []
    for c in state.get("statusCheckRollup") or []:
        result = c.get("conclusion") or c.get("state") or c.get("status")
        if result not in PASSING:
            out.append(f"{c.get('name') or c.get('context')}={result}")
    return out


def unresolved_threads(pr: int, repo: str) -> int:
    owner, name = repo.split("/", 1)
    q = ('query($o:String!,$n:String!,$p:Int!){repository(owner:$o,name:$n){pullRequest(number:$p)'
         '{reviewThreads(first:100){nodes{isResolved}}}}}')
    r = gh(["api", "graphql", "-f", f"query={q}", "-f", f"o={owner}", "-f", f"n={name}",
            "-F", f"p={pr}", "--jq",
            "[.data.repository.pullRequest.reviewThreads.nodes[]|select(.isResolved|not)]|length"])
    return int(r.stdout.strip() or 0) if r.returncode == 0 else -1


def check_review_allowed(state: dict, action: str, body: str) -> None:
    """Refuse a review that can't be honest. Raises SystemExit with the reason."""
    if not body.strip():
        raise SystemExit("A review needs a body with the evidence you checked.")
    if state.get("state") != "OPEN":
        raise SystemExit(f"PR is {state.get('state')}, not open.")
    if (state.get("author") or {}).get("login") == REVIEWER:
        raise SystemExit(f"{REVIEWER} wrote this PR; it cannot review it.")
    if action == "approve":
        bad = failing_checks(state)
        if bad:
            raise SystemExit("Not approving while checks are not passing: " + ", ".join(bad))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["show", "approve", "request-changes", "comment"])
    ap.add_argument("pr", type=int)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--body", default="")
    a = ap.parse_args(argv)

    state = pr_state(a.pr, a.repo)
    if a.action == "show":
        print(f"#{a.pr} {state['title']}  ({state['url']})")
        print(f"author={state['author']['login']} state={state['state']} "
              f"merge={state['mergeStateStatus']} review={state['reviewDecision'] or '-'}")
        bad = failing_checks(state)
        print("checks: " + ("all passing" if not bad else "NOT passing: " + ", ".join(bad)))
        print(f"unresolved threads: {unresolved_threads(a.pr, a.repo)}")
        return 0

    check_review_allowed(state, a.action, a.body)
    r = gh(["pr", "review", str(a.pr), "--repo", a.repo, f"--{a.action}", "--body", a.body],
           token=reviewer_token())
    if r.returncode:
        print(r.stderr.strip(), file=sys.stderr)
        return r.returncode
    after = pr_state(a.pr, a.repo)
    print(f"#{a.pr} {a.action} as {REVIEWER}: review={after['reviewDecision']} merge={after['mergeStateStatus']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
