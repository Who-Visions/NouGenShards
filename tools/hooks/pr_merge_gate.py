#!/usr/bin/env python3
"""pr_merge_gate: refuse a merge while a reviewer's latest word is CHANGES_REQUESTED.

Born from two misses on 2026-11-22 (NouGenClaude #4, NouGenShards #1169): a PR was squash-merged
on CI/mergeState alone while an aiwithdav3 CHANGES_REQUESTED was the latest review. This reads the
live review state first, in its own command, and only then (with --merge) calls gh.

usage: pr_merge_gate.py OWNER/REPO PR [--merge] [--allow-red-check NAME ...]
exit 0 = clear (and merged when --merge), 1 = blocked, 2 = could not read state (never merge on 2).
Nothing is hardcoded: required-check names come from the PR itself; --allow-red-check is explicit.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def gh(*args: str) -> str:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"gh exited {out.returncode}")
    return out.stdout


def threads_unresolved(repo: str, pr: int) -> int:
    owner, name = repo.split("/", 1)
    query = ("query($o:String!,$n:String!,$p:Int!){repository(owner:$o,name:$n){pullRequest(number:$p)"
             "{reviewThreads(first:100){nodes{isResolved}}}}}")
    raw = gh("api", "graphql", "-f", f"query={query}", "-F", f"o={owner}", "-F", f"n={name}", "-F", f"p={pr}")
    nodes = json.loads(raw)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    return sum(1 for n in nodes if not n["isResolved"])


def evaluate(repo: str, pr: int, allow_red: set[str]) -> tuple[list[str], list[str]]:
    data = json.loads(gh("pr", "view", str(pr), "--repo", repo, "--json",
                         "state,isDraft,headRefOid,mergeStateStatus,reviewDecision,reviews,statusCheckRollup"))
    blocks: list[str] = []
    notes: list[str] = []
    if data["state"] != "OPEN":
        blocks.append(f"state is {data['state']}, not OPEN")
    if data["isDraft"]:
        blocks.append("PR is a draft")
    head = data["headRefOid"]
    latest: dict[str, dict] = {}
    for review in sorted(data["reviews"], key=lambda r: r.get("submittedAt") or ""):
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[review["author"]["login"]] = review
    for who, review in latest.items():
        at = (review.get("commit") or {}).get("oid", "")[:7]
        if review["state"] == "CHANGES_REQUESTED":
            blocks.append(f"{who} CHANGES_REQUESTED at {at} is that reviewer's latest word")
        elif review["state"] == "APPROVED" and at != head[:7]:
            notes.append(f"{who} approved at {at}, head is {head[:7]}: read the delta before merging")
    if data["reviewDecision"] not in ("APPROVED", "", None):
        blocks.append(f"reviewDecision is {data['reviewDecision']}")
    if not any(r["state"] == "APPROVED" for r in latest.values()):
        blocks.append("no standing approval from a non-author reviewer")
    if data["mergeStateStatus"] in ("DIRTY", "BEHIND", "BLOCKED"):
        blocks.append(f"mergeStateStatus is {data['mergeStateStatus']}")
    for check in data["statusCheckRollup"] or []:
        name = check.get("name") or check.get("context") or "?"
        verdict = check.get("conclusion") or check.get("state") or ""
        if verdict in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED") and name not in allow_red:
            blocks.append(f"check {name} is {verdict}")
    open_threads = threads_unresolved(repo, pr)
    if open_threads:
        blocks.append(f"{open_threads} unresolved review thread(s)")
    return blocks, notes


def main() -> int:
    ap = argparse.ArgumentParser(prog="pr_merge_gate")
    ap.add_argument("repo")
    ap.add_argument("pr", type=int)
    ap.add_argument("--merge", action="store_true", help="squash-merge when clear")
    ap.add_argument("--allow-red-check", action="append", default=[],
                    help="a check name known to be red for a non-code reason (e.g. billing)")
    args = ap.parse_args()
    try:
        blocks, notes = evaluate(args.repo, args.pr, set(args.allow_red_check))
    except Exception as exc:  # fail closed: unreadable state is never a green light
        print(f"UNREADABLE: {exc}")
        return 2
    for note in notes:
        print(f"note: {note}")
    if blocks:
        for block in blocks:
            print(f"BLOCKED: {block}")
        return 1
    print("CLEAR")
    if args.merge:
        gh("pr", "merge", str(args.pr), "--repo", args.repo, "--squash")
        print("MERGED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
