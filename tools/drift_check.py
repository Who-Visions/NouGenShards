#!/usr/bin/env python3
"""Detect when a node's RUNNING bus code has drifted from the canonical repo.

Both fleet nodes spent a night running core code that existed in no git ref:
one in an uncommitted working-tree file, the other in a directory outside any
branch. Nothing alerted, and it was found by hand hours later. This is the
check that would have caught it inside one poll.

For each watched component it compares the sha256 of the file the node is
actually RUNNING against the same path on the canonical branch, and reports
one of:

    MATCH     running bytes equal the canonical bytes
    DRIFT     both exist and differ
    UNTRACKED the running file has no canonical counterpart at all (the worst
              case, because there is nothing to fall back to)
    MISSING   canonical has it, this node does not run it

Read-only. It never edits, fetches destructively, or writes to the repo. On
request it drops one message into the node's inbox so an existing watcher can
surface drift without knowing anything about git.

Environment (env first, then a probe, then a documented fallback):
    NOUGEN_BUS_DIR        single directory this node runs its bus files from
                          (preferred; shared with the manifest generator)
    NOUGEN_SHARDS_REPO    repo holding the canonical tools/ (default: probe)
    NOUGEN_DRIFT_BRANCH   canonical ref (default: origin/HEAD, else origin/main)
    NOUGEN_DRIFT_MAP      "runtime_path=canonical_path" entries, os.pathsep
                          separated, to add or override the default map
    NOUGEN_AGY_INBOX      inbox directory (default ~/.nougen/agy_inbox)

Exit status: 0 all MATCH, 1 any DRIFT/UNTRACKED/MISSING, 2 cannot determine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()

# Canonical paths this tool watches by default. The runtime side is normally
# NOUGEN_BUS_DIR (one directory per node); these per-file candidates are only
# a fallback for a node that has not set it, and are deliberately generic
# rather than describing any particular machine's layout.
WATCHED = ["tools/nougenmsg_node.py", "tools/relay_watch_node.py",
           "tools/_agy_live_delivery.py", "tools/parity_manifest.py",
           "tools/drift_check.py"]
DEFAULT_MAP = [([".nougen/bin/" + Path(c).name], c) for c in WATCHED]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_root() -> Path:
    raw = os.environ.get("NOUGEN_SHARDS_REPO", "").strip()
    candidates = [Path(raw)] if raw else []
    candidates += [Path.cwd(), HOME / "NouGenShards"]
    for c in candidates:
        if (c / ".git").exists():
            return c
    raise SystemExit("[drift] no NouGenShards clone found; set NOUGEN_SHARDS_REPO")


def canonical_ref(root: Path) -> str:
    raw = os.environ.get("NOUGEN_DRIFT_BRANCH", "").strip()
    if raw:
        return raw
    head = _git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return head or "origin/main"


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                           text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _remote_of(root: Path, ref: str) -> str:
    """The remote-tracking ref for ``ref``, so "behind" is measurable.

    For a local branch this is its upstream; for a ref that is already
    remote-tracking it is itself, in which case nothing can be behind it.
    """
    if ref.startswith("origin/"):
        return ref
    upstream = _git(root, "rev-parse", "--abbrev-ref", "{}@{{upstream}}".format(ref))
    return upstream or "origin/" + ref


def canonical_bytes(root: Path, ref: str, path: str):
    """Bytes of ``path`` at ``ref``, or None when it does not exist there."""
    try:
        r = subprocess.run(["git", "-C", str(root), "show", "{}:{}".format(ref, path)],
                           capture_output=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def pull_health(root: Path, ref: str):
    """Can this clone still fast-forward, and what would stop it?

    A watcher that pulls on a timer goes QUIETLY BLIND when the pull starts
    failing: it logs a reason nobody reads and keeps announcing only what it
    already has, which looks identical to a quiet period. Two causes, both
    seen in this fleet:

    * a MODIFIED TRACKED file that upstream later touches, which makes
      --ff-only refuse. Locally-modified state that is also synced upstream is
      the trap, and the file need not be touched yet for the clone to be armed.
    * a HEAD that is no longer an ancestor of the canonical ref at all, so no
      fast-forward is possible regardless of working-tree state.

    Reported as rows so a blind watcher can announce its own blindness rather
    than looking healthy while it stops learning anything new.
    """
    rows = []
    modified = [ln[3:] for ln in _git(root, "status", "--porcelain").splitlines()
                if ln[:2].strip() and not ln.startswith("??")]
    if modified:
        rows.append(("PULL-RISK", str(root), "", "",
                     "{} modified TRACKED file(s); an upstream touch to any of them makes "
                     "--ff-only refuse. First: {}".format(len(modified), ", ".join(modified[:3]))))
    ancestor = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", "HEAD", ref],
        capture_output=True, timeout=60)
    if ancestor.returncode != 0:
        rows.append(("PULL-BLOCKED", str(root), "", "",
                     "HEAD is not an ancestor of {}; no fast-forward is possible and a "
                     "polling watcher here has already stopped learning".format(ref)))
    return rows


def build_map():
    """Canonical path -> runtime candidates, with env entries OVERRIDING.

    Keyed on the CANONICAL path, so a mapped entry replaces the default's
    runtime side rather than adding a second row for the same file. Appending
    produced six rows for three files on a repointed node: three ghost MISSING
    from the retired default location and three MATCH from the real one. Two
    verdicts for one component is worse than either verdict alone, because a
    watcher cannot tell which to believe.
    """
    pairs = {}
    order = []
    for runtimes, canon in DEFAULT_MAP:
        pairs[canon] = list(runtimes)
        order.append(canon)
    for entry in [e for e in os.environ.get("NOUGEN_DRIFT_MAP", "").split(os.pathsep)
                  if e.strip()]:
        if "=" not in entry:
            continue
        runtime, canon = (x.strip() for x in entry.split("=", 1))
        if canon not in pairs:
            order.append(canon)
        pairs[canon] = [runtime]  # replaces, never appends
    return [(pairs[c], c) for c in order]


def bus_dir():
    """Where this node RUNS its bus files from, if it has a single location.

    Preferred over the per-file candidate list, and shared with the manifest
    generator so both tools answer "where does this node run from" the same
    way. It also removes a whole class of false alarm: after a node repoints
    to a deployment clone and retires its old copies, a stale per-file map
    reports MISSING for files that were merely moved. A ghost, not drift.
    """
    raw = os.environ.get("NOUGEN_BUS_DIR", "").strip()
    return Path(raw) if raw else None


def resolve_runtime(candidates, canon_path: str):
    running_dir = bus_dir()
    if running_dir is not None:
        # canonical "tools/x.py" runs as "<NOUGEN_BUS_DIR>/x.py"
        p = running_dir / Path(canon_path).name
        return p if p.is_file() else None
    for c in candidates:
        p = Path(c) if os.path.isabs(c) else HOME / c
        if p.is_file():
            return p
    return None


def check(refresh: bool = False):
    root = repo_root()
    ref = canonical_ref(root)
    if refresh:
        _git(root, "fetch", "--quiet", "origin")
    rows = []
    # A deployment clone that is BEHIND its remote is itself drift: the node is
    # running yesterday's canonical rather than today's, and every per-file
    # comparison below would agree with a reference that is already wrong.
    behind = _git(root, "rev-list", "--count", "{}..{}".format(ref, _remote_of(root, ref)))
    if behind.isdigit() and int(behind) > 0:
        rows.append(("STALE", ref, "", "", "{} commit(s) behind {}; every comparison "
                     "below is against an out-of-date reference"
                     .format(behind, _remote_of(root, ref))))
    rows.extend(pull_health(root, ref))
    for candidates, canon_path in build_map():
        runtime = resolve_runtime(candidates, canon_path)
        canon = canonical_bytes(root, ref, canon_path)
        if runtime is None and canon is None:
            continue
        if runtime is None:
            rows.append(("MISSING", canon_path, "", sha(canon)[:16], "canonical exists, not running here"))
        elif canon is None:
            rows.append(("UNTRACKED", canon_path, sha(runtime.read_bytes())[:16], "",
                         "running from {} but absent at {}".format(runtime, ref)))
        else:
            r_hash, c_hash = sha(runtime.read_bytes()), sha(canon)
            state = "MATCH" if r_hash == c_hash else "DRIFT"
            rows.append((state, canon_path, r_hash[:16], c_hash[:16], str(runtime)))
    return root, ref, rows


def announce(rows, ref):
    bad = [r for r in rows if r[0] != "MATCH"]
    if not bad:
        return None
    inbox = Path(os.environ.get("NOUGEN_AGY_INBOX", "").strip()
                 or HOME / ".nougen" / "agy_inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    summary = "; ".join("{} {}".format(s, p) for s, p, *_ in bad)
    msg = {"type": "live_message", "sender": "drift-check", "target": "local",
           "priority": "high", "timestamp": time.time(),
           "text": ("DRIFT: {} bus component(s) differ from {} -- {}. Running code that "
                    "is not in the canonical branch cannot be reviewed and does not "
                    "survive the disk. Reconcile before shipping anything else."
                    .format(len(bad), ref, summary))}
    path = inbox / "msg_{}_drift-check.json".format(int(time.time() * 1000))
    path.write_text(json.dumps(msg, indent=2), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--announce", action="store_true",
                    help="drop a DRIFT message into the inbox when anything differs")
    # Fetching is the DEFAULT, learned by this tool reporting a false alarm on
    # its own first run: against a stale local origin/main it called two files
    # UNTRACKED ("canonical has no such file") when the truth was DRIFT
    # ("canonical has it and it differs"). A drift checker that misreports when
    # its reference is stale is the exact class of bug it exists to catch.
    ap.add_argument("--no-fetch", dest="fetch", action="store_false", default=True,
                    help="compare against the local ref as-is, without refreshing "
                         "(faster, but a stale ref produces false UNTRACKED rows)")
    ap.add_argument("--quiet", action="store_true", help="only print non-MATCH rows")
    args = ap.parse_args()

    try:
        root, ref, rows = check(refresh=args.fetch)
    except SystemExit:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        print("[drift] cannot determine: {}".format(exc))
        return 2
    if not rows:
        print("[drift] nothing to compare; check NOUGEN_DRIFT_MAP")
        return 2
    print("[drift] repo={} ref={}".format(root, ref))
    for state, canon, r_hash, c_hash, note in rows:
        if args.quiet and state == "MATCH":
            continue
        print("  {:9s} {:34s} running={:16s} canonical={:16s} {}".format(
            state, canon, r_hash or "-", c_hash or "-", note))
    if args.announce:
        written = announce(rows, ref)
        if written:
            print("[drift] announced to {}".format(written.name))
    return 0 if all(r[0] == "MATCH" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
