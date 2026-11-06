"""GitHub over SSH for this machine: status, setup, test, undo.

    python tools/github_ssh.py status   # key, agent rule, remotes, live auth
    python tools/github_ssh.py setup    # add global https->ssh rewrite, then test
    python tools/github_ssh.py test     # ssh -T + ls-remote through the rewrite
    python tools/github_ssh.py undo     # remove the global rewrite

Never prints private key material. Exit 0 = healthy, 1 = something to fix.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REWRITE_KEY = "url.git@github.com:.insteadOf"
REWRITE_VAL = "https://github.com/"
PROBE_REPO = "https://github.com/Who-Visions/NouGenRelay.git"
SSH_DIR = Path.home() / ".ssh"
TIMEOUT = 30


def run(*cmd: str) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 99, str(e)


def keys() -> list[str]:
    return sorted(p.name for p in SSH_DIR.glob("*.pub")) if SSH_DIR.exists() else []


def rewrite_on() -> bool:
    code, out = run("git", "config", "--global", "--get-all", REWRITE_KEY)
    return code == 0 and REWRITE_VAL in out.splitlines()


def auth() -> tuple[bool, str]:
    # GitHub exits 1 on success because it refuses a shell; judge by the text.
    _, out = run("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                 "-o", "ConnectTimeout=15", "-T", "git@github.com")
    ok = "successfully authenticated" in out
    return ok, out.splitlines()[-1] if out else "(no output)"


def probe() -> tuple[bool, str]:
    code, out = run("git", "ls-remote", PROBE_REPO, "HEAD")
    return code == 0 and len(out.split()) >= 1, out[:120]


def remotes() -> list[str]:
    code, out = run("git", "remote", "-v")
    if code != 0:
        return []
    return sorted({l.split()[0] + " " + l.split()[1] for l in out.splitlines() if l.strip()})


def status() -> int:
    ok_auth, msg = auth()
    on = rewrite_on()
    print(f"keys        : {', '.join(keys()) or 'NONE in ~/.ssh'}")
    print(f"auth        : {'OK' if ok_auth else 'FAIL'} - {msg}")
    print(f"https->ssh  : {'on (global)' if on else 'off'}")
    for r in remotes():
        tag = "ssh" if "git@" in r else ("ssh via rewrite" if on and "https://github.com/" in r else "https")
        print(f"remote      : {r}  [{tag}]")
    return 0 if ok_auth and on else 1


def test() -> int:
    ok_auth, msg = auth()
    ok_probe, out = probe()
    print(f"ssh -T      : {'OK' if ok_auth else 'FAIL'} - {msg}")
    print(f"ls-remote   : {'OK' if ok_probe else 'FAIL'} - {out}")
    return 0 if ok_auth and ok_probe else 1


def setup() -> int:
    if not keys():
        print("no public key in ~/.ssh - run: ssh-keygen -t ed25519, then add the .pub at github.com/settings/ssh/new")
        return 1
    if not rewrite_on():
        run("git", "config", "--global", "--add", REWRITE_KEY, REWRITE_VAL)
    print("https->ssh rewrite on")
    return test()


def undo() -> int:
    code, out = run("git", "config", "--global", "--unset-all", REWRITE_KEY)
    print("rewrite removed" if code == 0 else f"nothing to remove ({out or code})")
    return 0


def main(argv: list[str]) -> int:
    cmds = {"status": status, "test": test, "setup": setup, "undo": undo}
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd not in cmds:
        print(__doc__)
        return 2
    return cmds[cmd]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
