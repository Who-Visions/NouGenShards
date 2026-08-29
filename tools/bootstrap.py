"""One command that takes a clean clone of NouGenShards to a working state.

Leg 20260829T045810Z: the stack must be reproducible clean-room from the public
repo. It was not. Project doctrine tells every agent to run
`.\\.venv\\Scripts\\python.exe`, but nothing in the repo ever created that venv --
so a fresh clone failed at the first documented command, and the failure looked
like a broken "shell runner" rather than a missing bootstrap step. That is the
gap this closes.

Deliberately dependency-free: it runs on a stock interpreter before anything is
installed, which is the whole point of a bootstrap.

    python tools/bootstrap.py            # create venv, install, verify
    python tools/bootstrap.py --check    # verify only, mutate nothing
    python tools/bootstrap.py --json     # machine-readable report

Exit code is 0 only when every REQUIRED step passes, so CI can gate on it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"

# Secret separation contract. Names only -- this file must never read, print or
# persist a secret VALUE. Bootstrap reports presence so an operator can see what
# is missing without the value ever entering a log, a terminal, or an agent's
# context window.
SECRETS = {
    "OPENROUTER_API_KEY": "OpenRouter :free lane (Rhea's default brain)",
    "NGS_INFERENCE_TOKENS": "HF Inference router keys, comma-separated (Kimi lane)",
    "NOUGEN_RELAY_GITHUB_TOKEN": "relay baton read/write",
    "NGS_NODE_TOKEN": "node auth for the deployed Space",
}
OPTIONAL_SECRETS = {
    "NOUGEN_OLLAMA_CLOUD_KEYS": "Ollama Cloud fallback lane (dormant if unset)",
    "HF_TOKEN": "fallback for NGS_INFERENCE_TOKENS",
}


def venv_python() -> Path:
    """Interpreter path inside the venv, per-platform."""
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, **kw)


def step(report: list, name: str, ok: bool, detail: str = "", required: bool = True) -> bool:
    report.append({"step": name, "ok": ok, "required": required, "detail": detail})
    return ok


def ensure_venv(report: list, check_only: bool) -> bool:
    if venv_python().exists():
        return step(report, "venv", True, str(venv_python()))
    if check_only:
        return step(report, "venv", False, "missing (.venv not created; run without --check)")
    proc = run([sys.executable, "-m", "venv", str(VENV)])
    if proc.returncode != 0:
        return step(report, "venv", False, proc.stderr.strip()[:200])
    return step(report, "venv", True, f"created {venv_python()}")


def ensure_install(report: list, check_only: bool) -> bool:
    py = venv_python()
    if not py.exists():
        return step(report, "install", False, "no venv interpreter")
    probe = run([str(py), "-c", "import nougen_shards; print(nougen_shards.__version__)"])
    if probe.returncode == 0:
        return step(report, "install", True, f"nougen_shards {probe.stdout.strip()}")
    if check_only:
        return step(report, "install", False, "nougen_shards not importable")
    # `.[test]`, not `.`: the test extra pins pytest-asyncio, and without it 10
    # async tests fail on a fresh clone in a way that reads like broken code
    # rather than an incomplete install. A bootstrap that cannot produce a green
    # suite has not finished bootstrapping.
    proc = run([str(py), "-m", "pip", "install", "-q", "-e", ".[test]"])
    if proc.returncode != 0:
        proc = run([str(py), "-m", "pip", "install", "-q", "-e", "."])
    if proc.returncode != 0:
        return step(report, "install", False, proc.stderr.strip()[:200])
    probe = run([str(py), "-c", "import nougen_shards; print(nougen_shards.__version__)"])
    return step(report, "install", probe.returncode == 0, probe.stdout.strip() or probe.stderr[:200])


def verify_cli(report: list) -> bool:
    py = venv_python()
    if not py.exists():
        return step(report, "cli", False, "no venv interpreter")
    proc = run([str(py), "-m", "nougen_shards.cli", "--help"])
    return step(report, "cli", proc.returncode == 0,
                "nougen_shards.cli --help" if proc.returncode == 0 else proc.stderr.strip()[:200])


def is_configured(name: str, env=None) -> bool:
    """Presence WITHOUT ever binding the value.

    Reading the variable pulls the credential into this process even when only
    its NAME is printed. CodeQL flags that as clear-text logging of sensitive
    information and is right to: the value has no reason to exist here at all,
    so a membership test is both the smaller answer and the whole answer. A
    variable that is set but empty counts as configured -- that is a
    misconfiguration to fix at the source, not something worth reading a
    secret to detect.
    """
    return name in (os.environ if env is None else env)


def verify_secrets(report: list) -> None:
    """Presence only. A missing secret is NOT a bootstrap failure.

    A clean-room clone must build and run its test suite with no credentials at
    all; secrets are deployment configuration, not build inputs. Conflating the
    two is what makes a stack look irreproducible when it is merely unconfigured.
    """
    for name, why in SECRETS.items():
        step(report, f"secret:{name}", is_configured(name), why, required=False)
    for name, why in OPTIONAL_SECRETS.items():
        step(report, f"secret:{name}", is_configured(name), f"optional - {why}", required=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="verify only; mutate nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args()

    report: list = []
    ensure_venv(report, args.check)
    ensure_install(report, args.check)
    verify_cli(report)
    verify_secrets(report)

    required_ok = all(r["ok"] for r in report if r["required"])

    # CodeQL raises py/clear-text-logging-sensitive-data on the three prints
    # below, and this repo's default-setup code scanning does not honor inline
    # suppressions, so they must be dismissed in the Security tab by an owner.
    # It is a name heuristic, not a real finding: what reaches stdout is
    # the NAME of an environment variable ("OPENROUTER_API_KEY"), which is
    # published in .env.example and the README, and the taint is inherited only
    # because SECRETS' keys contain KEY/TOKEN. No value is read anywhere in this
    # file -- is_configured() uses membership, and an AST test in
    # tests/test_repro_smoke.py fails the build if os.environ.get ever returns.
    if args.json:
        print(json.dumps({"ok": required_ok, "root": str(ROOT), "steps": report},
                         indent=2))
    else:
        for r in report:
            mark = "ok  " if r["ok"] else ("FAIL" if r["required"] else "--  ")
            print(f"[{mark}] {r['step']:<34} {r['detail']}")
        print()
        if required_ok:
            print(f"Bootstrap OK. Interpreter: {venv_python()}")
            missing = [n for n in SECRETS if not is_configured(n)]
            if missing:
                print("Unconfigured (deployment only, not needed to build or test): "
                      + ", ".join(missing))
        else:
            print("Bootstrap FAILED - see FAIL rows above.")
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
