#!/usr/bin/env python3
r"""Answer the question a clean-worktree test cannot: what is actually RUNNING?

On 2026-09-08 a redaction fix merged to main three times over and ran nowhere.
phoebus carried NINE copies of ``brain_scan/redaction.py`` and blade SIX; of the
fifteen, exactly one had the merged patterns, and it was not the one any live
process imported. Every node had verified the fix -- in a clean worktree, with
``print(module.__file__)``, correctly.

    print(module.__file__)   proves which file your TEST loaded.
    It says NOTHING about which file the SERVICE loads.

Those are different questions and only the second one protects anybody. This
script answers the second: for each matching process it reports the working
directory and PYTHONPATH the process itself is running under, resolves the
module the way that process would, and counts a marker in the file that wins.
Process inspection runs on Windows, Linux and macOS alike via psutil; without
psutil installed it falls back to ps/lsof, which is POSIX-only.

    python tools/which_tree.py --module nougen_shards.brain_scan.redaction \
        --marker 're\.compile' --expect 29 --proc app.py

Exit status is 1 if any live process resolves to a tree whose marker count
differs from --expect, so it can gate a deploy rather than decorate a report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

try:
    import psutil
except ImportError:  # pragma: no cover - exercised only where psutil is absent
    psutil = None


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              check=False).stdout
    except OSError:
        return ""


def _pids_psutil(pattern: str) -> list[tuple[int, str]]:
    found = []
    for proc in psutil.process_iter(["pid"]):
        try:
            cmd = " ".join(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if pattern in cmd and "which_tree" not in cmd:
            found.append((proc.pid, cmd.strip()))
    return found


def _pids_ps(pattern: str) -> list[tuple[int, str]]:
    out, found = _run(["ps", "-axo", "pid=,command="]), []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid, _, cmd = line.partition(" ")
        if pattern in cmd and "which_tree" not in cmd and pid.isdigit():
            found.append((int(pid), cmd.strip()))
    return found


def pids(pattern: str) -> list[tuple[int, str]]:
    """Every live process whose command line contains ``pattern``.

    psutil first when it is importable -- it is what makes this cross-platform
    at all, since ``ps``/``lsof`` do not exist on Windows. Falls back to ``ps``
    only when psutil is unavailable, so a box without it keeps the original
    behaviour rather than reporting nothing silently.
    """
    if psutil is not None:
        return _pids_psutil(pattern)
    return _pids_ps(pattern)


def cwd_of(pid: int) -> str | None:
    """Working directory of a live process, or None if unavailable.

    psutil.Process.cwd() works on Windows, Linux and macOS alike -- the
    lsof-based POSIX-only version this replaced is why this whole tool used to
    print "NO PROCESS matched" on Windows while the process it was looking for
    was plainly running: lsof does not exist there, so the old path always
    returned nothing, and an unsupported platform looked identical to a true
    negative. Falls back to lsof only when psutil is unavailable.
    """
    if psutil is not None:
        try:
            return psutil.Process(pid).cwd()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
    for line in _run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def pythonpath_of(pid: int) -> str | None:
    """PYTHONPATH from the process's OWN environment, not the shell's.

    This is the field that made the incident invisible: the node's cwd looked
    reasonable and its PYTHONPATH pointed somewhere else entirely.

    psutil.Process.environ() reads the target process's own environment block
    on Windows, Linux and macOS alike (same-user only -- AccessDenied for a
    process owned by someone else, which is reported as "unavailable", the
    same as every other unreadable case here, never guessed at). Falls back to
    ``ps eww`` only when psutil is unavailable.
    """
    if psutil is not None:
        try:
            return psutil.Process(pid).environ().get("PYTHONPATH")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
    for token in _run(["ps", "eww", str(pid)]).split():
        if token.startswith("PYTHONPATH="):
            return token[len("PYTHONPATH="):]
    return None


def resolve(module: str, roots: list[str]) -> list[str]:
    """Every file that could satisfy ``module`` under ``roots``, in order.

    The first is what wins. The rest are the shadows -- reported because a
    single count tells you nothing about how many other copies are one
    PYTHONPATH edit away from winning instead.
    """
    rel = os.path.join(*module.split(".")) + ".py"
    hits = []
    for root in roots:
        if not root:
            continue
        for candidate in (os.path.join(root, rel), os.path.join(root, "src", rel)):
            if os.path.isfile(candidate) and candidate not in hits:
                hits.append(candidate)
    return hits


def count(path: str, marker: str) -> int:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return len(re.findall(marker, handle.read()))
    except OSError:
        return -1


def ask_health(url: str, timeout: float = 30.0) -> dict:
    """Ask a node what redaction code it is RUNNING, over HTTP.

    This is the answer that works even when process inspection cannot run at
    all -- when psutil is unavailable and there is no ``ps``/``lsof`` either, or
    when the node in question is not reachable as a local process (a peer on
    the LAN, a Space behind the public edge).

    It is also the only method that survives the mistake this tool exists to
    catch. Importing the module and asking it -- the obvious portable
    alternative -- reports what THIS interpreter resolves, under THIS
    environment. That is a different question from what the service resolves,
    and answering the first while believing you answered the second is exactly
    how a redaction fix sat on main, verified by three nodes, running on none
    of them. Import-and-ask is correct only when run under the service's own
    interpreter and environment; a node's own health report is correct
    always, because the node computed it from the module it actually loaded.
    """
    # An explicit User-Agent is REQUIRED, not cosmetic. The default
    # "Python-urllib/3.x" is refused with HTTP 403 by the edge in front of
    # these nodes while curl gets 200 from the same URL in the same second
    # (measured 2026-09-08). A peer reported that 403 hours earlier and I
    # could not reproduce it -- because I reached for curl. The endpoint was
    # never down for either of us; it answers some clients and not others.
    req = urllib.request.Request(
        url.rstrip("/") + "/health",
        headers={"Accept": "application/json",
                 "User-Agent": "nougen-which-tree/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--module", required=True, help="dotted module path")
    ap.add_argument("--marker", required=True, help="regex counted in the file")
    ap.add_argument("--expect", type=int, help="required count; sets exit status")
    ap.add_argument("--proc", default="app.py", help="substring of the process command")
    ap.add_argument("--health", metavar="URL",
                    help="ask a node over HTTP instead of inspecting processes "
                         "(portable; the only method that works on Windows)")
    ap.add_argument("--fingerprint", metavar="HEX",
                    help="with --health: the redaction_fingerprint to require")
    args = ap.parse_args()

    if args.health:
        try:
            body = ask_health(args.health)
        except Exception as exc:
            print(f"{args.health}: health unreachable ({type(exc).__name__})",
                  file=sys.stderr)
            return 1
        # Named pattern_count, not count: this function also has a module-level
        # count() used by the --proc path below. Assigning to a name anywhere in
        # a function makes Python treat it as local for the WHOLE function, so a
        # local `count` here shadowed the function for the entire call and made
        # `n = count(path, args.marker)` in the --proc branch raise
        # UnboundLocalError on every real match -- caught only by hand, because
        # the test suite exercises --health and the empty---proc-match case, and
        # neither one reaches that line. Fixed 2026-09-08, found running this
        # tool for real against whoart's node instead of only against its tests.
        pattern_count = body.get("redaction_patterns")
        fingerprint = body.get("redaction_fingerprint")
        print(f"{args.health}")
        if pattern_count is None and fingerprint is None:
            # Absence is the diagnostic, not a gap in the check: a node that
            # publishes neither field is running code from before the fields
            # existed. Saying "unknown" here would hide a definite answer.
            print("  redaction fields ABSENT -> this node predates the "
                  "self-reporting change and is running older code")
            return 1
        print(f"  redaction_patterns    {pattern_count}")
        print(f"  redaction_fingerprint {fingerprint}")
        bad = False
        if args.expect is not None and pattern_count != args.expect:
            print(f"  EXPECTED {args.expect} patterns, node reports {pattern_count}")
            bad = True
        if args.fingerprint and fingerprint != args.fingerprint:
            print(f"  EXPECTED fingerprint {args.fingerprint}")
            bad = True
        print("FAIL" if bad else "OK")
        return 1 if bad else 0

    procs = pids(args.proc)
    if not procs:
        # Not a pass. Nothing was measured, and "no processes" reads exactly
        # like "all processes are fine" in a log.
        print(f"NO PROCESS matched {args.proc!r} -- nothing verified", file=sys.stderr)
        return 1

    bad = 0
    for pid, cmd in procs:
        cwd, ppath = cwd_of(pid), pythonpath_of(pid)
        print(f"\npid {pid}  {cmd[:70]}")
        print(f"  cwd         {cwd or '(unavailable)'}")
        print(f"  PYTHONPATH  {ppath or '(unset)'}")
        roots = (ppath.split(os.pathsep) if ppath else []) + ([cwd] if cwd else [])
        hits = resolve(args.module, roots)
        if not hits:
            print(f"  {args.module} NOT FOUND under this process's own roots")
            bad += 1
            continue
        for i, path in enumerate(hits):
            n = count(path, args.marker)
            tag = "WINS " if i == 0 else "shadow"
            flag = ""
            if i == 0 and args.expect is not None and n != args.expect:
                flag = f"   <-- EXPECTED {args.expect}, THIS PROCESS RUNS {n}"
                bad += 1
            print(f"  {tag} {path}  marker={n}{flag}")

    if args.expect is not None:
        print(f"\n{'FAIL' if bad else 'OK'}: "
              f"{len(procs) - bad}/{len(procs)} live process(es) run the expected tree")
        if not bad:
            # This is a claim about the FILE the process would resolve right
            # now, from a fresh read -- not proof the running process has that
            # code loaded. A long-lived process that started before the file
            # changed keeps whatever it imported at start; Python does not
            # hot-reload a module because its bytes changed on disk. Measured
            # on whoart 2026-09-08: this exact check reported "OK: 2/2" for a
            # process running 55 hours, because the file it would resolve was
            # edited in place 55 hours after that process imported it -- while
            # --health against the same process's own live self-report showed
            # the redaction fields ABSENT, i.e. code from before #280 existed.
            # "OK" here means the DEPLOY is correct, not that it has TAKEN
            # EFFECT. Use --health for that, against a process new enough to
            # have loaded today's file -- a restart is what makes them agree.
            print("NOTE: this verifies the code ON DISK, not that the listed "
                  "process(es) have RELOADED it. If none has restarted since "
                  "the file last changed, prefer --health against the running "
                  "service for what it actually has loaded.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
