"""
NouGenShards: Hardening & Verification Orchestrator.
System Audit: Verification of Pylint quality standards and test pass rate.
"""
import os
import subprocess
import sys
from pathlib import Path

# Anchor to this file's directory (the repo root) so paths resolve no matter
# where the script is invoked from. A prior relative Path("NouGenShards") pointed
# at a nonexistent nested dir, making every check a silent no-op.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "nougen_shards"
TESTS = ROOT / "tests"

FILES_TO_HARDEN = [
    SRC / "core.py",
    SRC / "cli.py",
    SRC / "models_client.py",
    SRC / "keymaker.py",
    SRC / "history.py",
    SRC / "federation.py",
    SRC / "nougen_context.py",
    SRC / "nougen_sandbox.py"
]

def run_command(cmd, env=None):
    # cmd is an argv list run with shell=False — no shell parsing, no injection surface.
    print(f"[*] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, shell=False, capture_output=True, text=True, env=env)
    return result

def verify_system():
    print("--- [VERIFY] System Integrity ---")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(SRC.parent), env.get("PYTHONPATH", "")])
    res = run_command([sys.executable, "-m", "pytest", str(TESTS)], env=env)
    print(res.stdout)
    if res.returncode != 0:
        print(f"[!] TEST FAILURE:\n{res.stderr}")
    return res.returncode == 0

def pylint_harden(file_path):
    print(f"--- [HARDEN] Pylint: {file_path} ---")
    # Using a simple check; a full 10/10 requires iterative fixes which usually
    # require LLM reasoning per line. Here we just report.
    res = run_command([sys.executable, "-m", "pylint", str(file_path)])
    print(res.stdout)
    return res.returncode == 0

def main():
    print("[*] NOUGENSHARDS AUTONOMOUS HARDENING")

    ok = True

    # Cycle 1: Verification — the test suite must pass.
    if verify_system():
        print("[+] Baseline verified.")
    else:
        print("[-] Baseline test suite FAILED.")
        ok = False

    # Cycle 2: Pylint reporting per file.
    for f in FILES_TO_HARDEN:
        if not pylint_harden(f):
            ok = False

    # Honest exit status: only report success when every check actually passed.
    if ok:
        print("\n[+] SYSTEM HARDENING COMPLETE. All checks passed.")
        return 0
    print("\n[!] SYSTEM HARDENING INCOMPLETE. One or more checks failed above.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
