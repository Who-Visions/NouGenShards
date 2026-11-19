"""GitHub over SSH for this machine: status, setup, test, undo.

    python tools/github_ssh.py status   # key, agent rule, remotes, live auth
    python tools/github_ssh.py setup    # add global https->ssh rewrite, then test
    python tools/github_ssh.py test     # ssh -T + ls-remote through the rewrite
    python tools/github_ssh.py undo     # remove the global rewrite
    python tools/github_ssh.py repos [DIR]  # transport of every repo one level under DIR

Never prints private key material. Exit 0 = healthy, 1 = something to fix.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REWRITE_KEY = "url.git@github.com:.insteadOf"
REWRITE_VAL = "https://github.com/"
PROBE_REPO = "https://github.com/Who-Visions/NouGenRelay.git"
SSH_DIR = Path.home() / ".ssh"
TIMEOUT = 30


def run(*cmd: str, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                           env={**os.environ, **env} if env else None)
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
    """ls-remote an https URL and prove it actually went over ssh.

    GIT_TRACE shows the transport git spawned; credential prompts are disabled so an
    https fallback cannot quietly succeed through the token helper.
    """
    code, out = run("git", "-c", "credential.helper=", "ls-remote", PROBE_REPO, "HEAD",
                    env={"GIT_TRACE": "1", "GIT_TERMINAL_PROMPT": "0"})
    via_ssh = bool(re.search(r"run_command: .*\bssh\b.*git@github\.com", out))
    sha = next((l.split()[0] for l in out.splitlines() if l.endswith("\tHEAD")), "")
    if code == 0 and sha and via_ssh:
        return True, f"{sha[:12]} via ssh"
    if code == 0 and sha:
        return False, f"{sha[:12]} but over https - rewrite not in effect"
    return False, out.splitlines()[-1][:120] if out else f"exit {code}"


def transport(url: str, rewrite: bool) -> str:
    if url.startswith(("git@github.com:", "ssh://git@github.com/")):
        return "ssh"
    if url.startswith(REWRITE_VAL):
        return "ssh via rewrite" if rewrite else "https"
    return "other"


def remotes() -> list[str]:
    code, out = run("git", "remote", "-v")
    if code != 0:
        return []
    return sorted({l.split()[0] + " " + l.split()[1] for l in out.splitlines() if l.strip()})


def helpers() -> list[str]:
    """Credential helpers git would still run for https://github.com/ (none run over ssh)."""
    code, out = run("git", "config", "--get-urlmatch", "credential.helper", REWRITE_VAL)
    return [h for h in out.splitlines() if h.strip()] if code == 0 else []


def status() -> int:
    ok_auth, msg = auth()
    on = rewrite_on()
    print(f"keys        : {', '.join(keys()) or 'NONE in ~/.ssh'}")
    print(f"auth        : {'OK' if ok_auth else 'FAIL'} - {msg}")
    print(f"https->ssh  : {'on (global)' if on else 'off'}")
    for h in helpers():
        note = "idle while the rewrite is on" if on else "ACTIVE on every https push/pull"
        print(f"cred helper : {h}  [{note}]")
    for r in remotes():
        print(f"remote      : {r}  [{transport(r.split()[1], on)}]")
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
        code, out = run("git", "config", "--global", "--add", REWRITE_KEY, REWRITE_VAL)
        if code != 0 or not rewrite_on():
            print(f"could not set the rewrite: {out or code}")
            return 1
    print("https->ssh rewrite on")
    return test()


def undo() -> int:
    # Remove only our value; other aliases under the same key stay.
    code, out = run("git", "config", "--global", "--unset-all", REWRITE_KEY,
                    "^" + re.escape(REWRITE_VAL) + "$")
    print("rewrite removed" if code == 0 else f"nothing to remove ({out or code})")
    return 0


def repos(root: str | None = None) -> int:
    """One level deep only - never walk a whole tree like Outpost."""
    base = Path(root) if root else Path.cwd().parent
    on = rewrite_on()
    bad = 0
    for d in sorted(p for p in base.iterdir() if (p / ".git").exists()):
        code, out = run("git", "-C", str(d), "remote", "-v")
        urls = sorted({l.split()[1] for l in out.splitlines() if l.strip()}) if code == 0 else []
        for u in urls or ["(no remote)"]:
            t = transport(u, on) if urls else "-"
            bad += t == "https"
            print(f"{t:16} {d.name:28} {u}")
    print(f"{bad} github https remote(s) not covered" if bad else "all github remotes use ssh")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    cmds = {"status": status, "test": test, "setup": setup, "undo": undo}
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "repos":
        return repos(argv[2] if len(argv) > 2 else None)
    if cmd not in cmds:
        print(__doc__)
        return 2
    return cmds[cmd]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
