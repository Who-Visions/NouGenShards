#!/usr/bin/env python3
"""Diagnose a NouGenMsg link between two fleet nodes.

WHY THIS EXISTS
---------------
When bodies arrive as `NouGenMsg body <id> shipped to ~/.nougen/msg-<id>.md`
instead of as text, there are several independent causes and they look
identical from the outside. Working them out by hand on 2026-09-05 took most
of an hour and two of them are genuinely counter-intuitive:

1. STALE RECEIVER -- does not understand `--text-b64`, so the sender's probe
   comes back empty and the link pins itself to the pointer path forever.
   Tell-tale: the receiver delivers a message whose text is `--capabilities`.

2. THE PIPE TRAP -- Windows OpenSSH blocks when its stdout is a pipe held by
   the parent process. Measured blade->whoart:

       capture_output=True   ssh whoart "echo hi"  ->  20.0s TimeoutExpired
       stdout=<file handle>  ssh whoart "echo hi"  ->   0.5s rc=0

   It is the pipe, not the command: a bare `echo hi` hangs identically, with
   or without -n. scp is never affected -- which is exactly why bodies shipped
   fine on a link where every ssh dispatch timed out, and why this reads as a
   messaging bug rather than a transport one.

3. STALE PROCESS -- the file on disk is patched but a daemon imported the old
   module hours ago and Python cached it. Nothing on disk will show this.

Check 2 is the one worth running before blaming anything else.

USAGE
-----
    python tools/nougenmsg_doctor.py --host blade
    python tools/nougenmsg_doctor.py --host blade --peer whoart
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time

SSH_OPTS = ["-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]

REMOTE_SCRIPTS = {
    "blade": "python %USERPROFILE%/Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py",
    "whoart": "python %USERPROFILE%/Outpost/NouGen/tools/nougenmsg.py",
}
DEFAULT_REMOTE_SCRIPT = "python3 ~/.nougen/tools/nougenmsg.py"

# Every character _refuse_if_shell_unsafe diverts. A body containing any of
# them took the pointer path before --text-b64 existed, which is why ordinary
# prose -- one apostrophe, one parenthesis -- was enough to trip it.
CANARY = """parens (Coach), apostrophe's, "quotes", 100% & <brackets>; $(id) `x` | ; ?"""


def run(argv, timeout, use_pipe=False):
    """Run a command, returning (seconds, output, timed_out).

    Defaults to a temp file rather than a pipe -- see THE PIPE TRAP above.
    use_pipe=True is offered only so the doctor can demonstrate the failure.
    """
    started = time.time()
    if use_pipe:
        try:
            res = subprocess.run(argv, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 stdin=subprocess.DEVNULL, timeout=timeout)
            return time.time() - started, (res.stdout or res.stderr or ""), False
        except subprocess.TimeoutExpired:
            return time.time() - started, "", True
        except OSError as exc:
            return time.time() - started, f"{type(exc).__name__}: {exc}", False

    fd, path = tempfile.mkstemp(suffix=".out")
    try:
        with os.fdopen(fd, "wb") as sink:
            subprocess.run(argv, stdout=sink, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, timeout=timeout)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return time.time() - started, fh.read(), False
    except subprocess.TimeoutExpired:
        return time.time() - started, "", True
    except OSError as exc:
        return time.time() - started, f"{type(exc).__name__}: {exc}", False
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def clean(text):
    noise = ("post-quantum", "store now", "openssh.com", "may need to be upgraded")
    return "\n".join(line for line in text.splitlines()
                     if line.strip() and not any(n in line for n in noise))


def check(label, ok, detail):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if detail:
        for line in str(detail).splitlines()[:4]:
            print(f"         {line[:100]}")
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", required=True,
                        help="node to run the checks FROM (ssh target)")
    parser.add_argument("--peer",
                        help="node to reach from --host; omit to check --host itself")
    parser.add_argument("--timeout", type=float, default=25.0)
    args = parser.parse_args(argv)

    target = args.peer or args.host
    script = REMOTE_SCRIPTS.get(target, DEFAULT_REMOTE_SCRIPT)
    failures = 0

    print(f"\nNouGenMsg doctor: {args.host}"
          + (f" -> {args.peer}" if args.peer else "") + "\n")

    # 1. reachability
    secs, out, timed_out = run(["ssh", *SSH_OPTS, args.host, "echo ok"], args.timeout)
    if not check(f"ssh reaches {args.host} ({secs:.1f}s)",
                 not timed_out and "ok" in out, clean(out) if timed_out else ""):
        print("\n  Cannot reach the host; nothing else is meaningful.")
        return 1

    # 2. the pipe trap, demonstrated rather than assumed
    if args.peer:
        inner = f'ssh {" ".join(SSH_OPTS)} {args.peer} "echo hi"'
        file_secs, file_out, file_to = run(
            ["ssh", *SSH_OPTS, args.host, inner], args.timeout)
        pipe_secs, _, pipe_to = run(
            ["ssh", *SSH_OPTS, args.host, inner], args.timeout, use_pipe=True)
        check(f"{args.host} -> {args.peer} via file handle ({file_secs:.1f}s)",
              not file_to and "hi" in file_out, clean(file_out) if file_to else "")
        if pipe_to and not file_to:
            print(f"  [WARN] same call through a PIPE timed out at {pipe_secs:.1f}s")
            print("         This link is subject to the pipe trap. Any caller using")
            print("         capture_output=True will hang and silently fall back to")
            print("         the scp pointer path. Use a file handle (_ssh_capture).")
        elif not pipe_to:
            print(f"  [ ok ] pipe path also fine here ({pipe_secs:.1f}s)")

    # 3. does the receiver speak the protocol
    probe = f"{script} --capabilities"
    argv_probe = (["ssh", *SSH_OPTS, args.host, f'ssh {" ".join(SSH_OPTS)} {args.peer} "{probe}"']
                  if args.peer else ["ssh", *SSH_OPTS, args.host, probe])
    secs, out, timed_out = run(argv_probe, args.timeout)
    advertises = "text-b64" in out
    if not check(f"{target} advertises text-b64 ({secs:.1f}s)", advertises,
                 clean(out)[:200] if not advertises else ""):
        failures += 1
        if "--capabilities" in out:
            print("         The receiver echoed the flag back as MESSAGE TEXT --")
            print("         it predates --capabilities. Patch it:")
            print(f"         nougenmsg_rollout.py patch <its tools/nougenmsg.py> --write")
        elif timed_out:
            print("         Probe timed out. If the file-handle check above passed,")
            print("         suspect a slow interpreter start rather than the link.")

    # 4. stale copies anywhere on the host
    audit = ('command -v mdfind >/dev/null 2>&1 && mdfind -name nougenmsg.py 2>/dev/null'
             ' || find "$HOME" -name nougenmsg.py -maxdepth 8 2>/dev/null')
    secs, out, _ = run(["ssh", *SSH_OPTS, args.host, audit], args.timeout)
    paths = [p.strip() for p in out.splitlines() if p.strip().endswith("nougenmsg.py")]
    if paths:
        print(f"  [info] {len(paths)} nougenmsg.py copy(ies) on {args.host}; a single")
        print(f"         stale SENDER emits pointers for the whole fleet. Audit with:")
        print(f"         nougenmsg_rollout.py audit --host {args.host}")

    print()
    if failures:
        print(f"{failures} check(s) failed.")
    else:
        print("Link speaks the inline protocol.")
        print("If pointers persist anyway, a running daemon still holds the old")
        print("module in memory -- patching disk does not fix an import. Restart it.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
