#!/usr/bin/env python3
"""Audit and roll out the NouGenMsg inline-body protocol across fleet copies.

WHY THIS EXISTS
---------------
Message bodies used to travel as scp'd file pointers instead of text. The
sender interpolated the body into an ssh shell string, so any body containing
a shell metacharacter was diverted to a file and only a pointer went inline --
and ordinary prose trips that on a single parenthesis or apostrophe. The fix
is `--text-b64`: the body rides as base64url, which no shell can reinterpret.

Rolling that out is not a one-file job. The fleet carries MANY divergent
copies of nougenmsg.py -- per-node clones, branch workspaces, vendored trees --
and a single stale sender keeps producing pointers for everyone. On 2026-09-05
three separate copies existed on one node alone, one of them two directories
deep under a path containing a space, which `find` never reached before timing
out while `mdfind` located it in seconds.

So the high-value operation is AUDIT: find every copy and say which ones speak
the protocol. Patching is secondary and deliberately conservative.

USAGE
-----
    # What copies exist here, and which are stale?
    python tools/nougenmsg_rollout.py audit
    python tools/nougenmsg_rollout.py audit --host phoebus

    # Patch one file (prints a diff and changes nothing without --write)
    python tools/nougenmsg_rollout.py patch path/to/tools/nougenmsg.py
    python tools/nougenmsg_rollout.py patch path/to/nougenmsg.py --write

A receiver patch is purely additive and anchor-based. A sender patch replaces
the emit_node region wholesale from a reference implementation, so it needs
--reference (default: this repo's own module) and always writes a .bak first.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANONICAL_SENDER = os.path.join(REPO_ROOT, "src", "nougen_shards", "nougenmsg.py")

# ---------------------------------------------------------------- receiver --

CAPS_BLOCK = '''    if "--capabilities" in sys.argv:
        # Probed over ssh by NouGenMsgBus.emit_node to decide whether this
        # receiver can take a base64 body inline instead of an scp'd file.
        print("nougenmsg-capabilities: text-b64")
        return

'''

PARSE_BLOCK = '''    forced_text = None
    if "--text-b64" in args:
        idx = args.index("--text-b64")
        if idx + 1 >= len(args):
            print("[!] Error: --text-b64 requires a value.")
            return
        encoded = args[idx + 1]
        try:
            padding = "=" * (-len(encoded) % 4)
            forced_text = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            print("[!] Error: invalid --text-b64 payload.")
            return
        args = [value for pos, value in enumerate(args)
                if pos not in (idx, idx + 1)]

'''

# Applied after the text is assembled, so it works whether the target builds
# `text` from positional args, from --stdin (phoebus), or both.
APPLY_BLOCK = '''    if forced_text is not None:
        text = forced_text
'''

PEERS_ANCHOR = '    if "--peers" in sys.argv'
CLEANED_ANCHOR = re.compile(r"^    cleaned_args = \[\]\n", re.M)
NOTEXT_ANCHOR = re.compile(r"^    if not text:\n", re.M)

# ------------------------------------------------------------------ sender --

SENDER_OLD_START = "    @classmethod\n    def emit_node("
# The fix adds _REMOTE_SCRIPTS / _TEXT_B64_SUPPORT / _SSH_OPTS / _ssh_capture /
# _supports_text_b64 AHEAD of emit_node. Starting the copied region at
# emit_node would port a body that calls helpers the target does not have.
SENDER_NEW_START = "    _REMOTE_SCRIPTS = {"
SENDER_END = "    @classmethod\n    def emit_fleet("


def classify(path, text):
    """receiver (the CLI), sender (the bus module), or neither."""
    if "NouGenMsgBus" in text and "def emit_node(" in text:
        return "sender"
    if "def main()" in text and "--peers" in text:
        return "receiver"
    return "unknown"


def status(text, kind):
    has_fix = "--text-b64" in text
    ships = "_ship_body" in text
    if kind == "sender":
        # A sender with neither is a leaner variant (phoebus's --stdin shape):
        # it cannot produce a pointer, so it was never part of the problem.
        if has_fix:
            return "OK"
        return "STALE" if ships else "n/a (no ship path)"
    if kind == "receiver":
        return "OK" if has_fix else "STALE"
    return "?"


# ------------------------------------------------------------------- audit --

def find_copies(host=None):
    """Locate nougenmsg.py copies. Uses the platform's indexed search where
    available -- a recursive walk is far too slow on these trees and silently
    truncates under a timeout, which is how a live stale copy stayed hidden."""
    if host:
        script = (
            'command -v mdfind >/dev/null 2>&1 && mdfind -name nougenmsg.py 2>/dev/null'
            ' || find "$HOME" -name "nougenmsg.py" -maxdepth 8 2>/dev/null'
        )
        out = ssh_capture(["ssh", "-n", "-o", "BatchMode=yes",
                           "-o", "ConnectTimeout=10", host, script], timeout=120)
        return [line.strip() for line in out.splitlines()
                if line.strip().endswith("nougenmsg.py")]

    roots = [REPO_ROOT, os.path.expanduser("~/.nougen")]
    found = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in {".git", "node_modules", "__pycache__",
                                        ".venv", "venv"}]
            if "nougenmsg.py" in filenames:
                found.append(os.path.join(dirpath, "nougenmsg.py"))
    return sorted(set(found))


def read_remote(host, path):
    return ssh_capture(["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                        host, f'cat "{path}"'], timeout=60)


def ssh_capture(argv, timeout):
    """Run ssh writing to a temp file, never a pipe.

    Windows OpenSSH blocks when its stdout is a pipe held by the parent:
    measured blade->whoart, `ssh whoart "echo hi"` times out at 20s with
    capture_output=True and returns in 0.5s writing to a file. scp is
    unaffected, which is what made this so confusing to diagnose.
    """
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".sshout")
    try:
        with os.fdopen(fd, "wb") as sink:
            subprocess.run(argv, stdout=sink, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, timeout=timeout)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, subprocess.SubprocessError):
        return ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def cmd_audit(args):
    copies = find_copies(args.host)
    if not copies:
        print("no nougenmsg.py copies found"
              + (f" on {args.host}" if args.host else ""))
        return 1

    where = args.host or "local"
    print(f"\n{len(copies)} copy(ies) on {where}\n")
    rows, stale = [], 0
    for path in copies:
        try:
            text = read_remote(args.host, path) if args.host else \
                open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            rows.append((path, "?", f"unreadable: {exc.strerror}"))
            continue
        if not text:
            rows.append((path, "?", "unreadable"))
            continue
        kind = classify(path, text)
        state = status(text, kind)
        if state == "STALE":
            stale += 1
        rows.append((path, kind, state))

    width = min(max((len(r[0]) for r in rows), default=20), 96)
    for path, kind, state in sorted(rows, key=lambda r: (r[2] != "STALE", r[0])):
        mark = "!!" if state == "STALE" else "  "
        print(f" {mark} {path[-width:]:<{width}}  {kind:<8} {state}")

    print()
    if stale:
        print(f"{stale} stale copy(ies). A stale SENDER emits file pointers for")
        print("everyone; a stale RECEIVER reads --capabilities as message text.")
        print("Patch with:  nougenmsg_rollout.py patch <file> --write")
    else:
        print("all copies speak the inline protocol")
    print("\nNote: a patched file on disk does NOT fix an already-running")
    print("process -- Python caches the module at import. Restart daemons.")
    return 0


# ------------------------------------------------------------------- patch --

def patch_receiver(text):
    changed = []
    if "import base64" not in text:
        text = text.replace("import sys\n", "import sys\nimport base64\n", 1)
        changed.append("import base64")
    if "--capabilities" not in text:
        if PEERS_ANCHOR not in text:
            return None, "no --peers anchor"
        text = text.replace(PEERS_ANCHOR, CAPS_BLOCK + PEERS_ANCHOR, 1)
        changed.append("--capabilities")
    if "--text-b64" not in text:
        m = CLEANED_ANCHOR.search(text)
        if not m:
            return None, "no cleaned_args anchor"
        text = text[:m.start()] + PARSE_BLOCK + text[m.start():]
        m2 = NOTEXT_ANCHOR.search(text)
        if not m2:
            return None, "no 'if not text:' anchor"
        text = text[:m2.start()] + APPLY_BLOCK + text[m2.start():]
        changed.append("--text-b64")
    return text, None if changed else "already patched"


def region(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def patch_sender(text, reference):
    if "--text-b64" in text:
        return None, "already patched"
    try:
        new_block = region(reference, SENDER_NEW_START, SENDER_END)
    except ValueError:
        return None, "reference lacks the fixed emit_node region"
    for required in ("_REMOTE_SCRIPTS", "_ssh_capture", "_supports_text_b64",
                     "--text-b64"):
        if required not in new_block:
            return None, f"reference block missing {required}"
    try:
        old_block = region(text, SENDER_OLD_START, SENDER_END)
    except ValueError:
        return None, "target lacks an emit_node..emit_fleet region"
    return text.replace(old_block, new_block, 1), None


def cmd_patch(args):
    path = args.path
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        print(f"cannot read {path}: {exc}")
        return 1

    kind = classify(path, text)
    if kind == "sender":
        try:
            reference = open(args.reference, encoding="utf-8").read()
        except OSError as exc:
            print(f"cannot read reference {args.reference}: {exc}")
            return 1
        patched, err = patch_sender(text, reference)
    elif kind == "receiver":
        patched, err = patch_receiver(text)
    else:
        print(f"{path}: not a nougenmsg receiver or sender")
        return 1

    if err and patched is None:
        print(f"{path}: {err}")
        return 0 if err == "already patched" else 1

    try:
        compile(patched, path, "exec")
    except SyntaxError as exc:
        print(f"{path}: patch produced invalid Python at line {exc.lineno}")
        return 1

    delta = len(patched) - len(text)
    if not args.write:
        print(f"{path}: {kind} would be patched ({delta:+d} bytes). "
              f"Re-run with --write to apply.")
        return 0

    backup = f"{path}.bak-{time.strftime('%Y%m%d')}"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(patched)
    print(f"{path}: {kind} patched ({delta:+d} bytes), backup {os.path.basename(backup)}")
    print("Restart any daemon importing this file -- the running process still "
          "holds the old module.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="find copies and report which are stale")
    audit.add_argument("--host", help="audit a remote fleet node over ssh")
    audit.set_defaults(func=cmd_audit)

    patch = sub.add_parser("patch", help="bring one copy up to the protocol")
    patch.add_argument("path")
    patch.add_argument("--write", action="store_true",
                       help="apply the change (default: dry run)")
    patch.add_argument("--reference", default=CANONICAL_SENDER,
                       help="fixed sender to copy emit_node from")
    patch.set_defaults(func=cmd_patch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
