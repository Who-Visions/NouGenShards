"""node_lane.ps1 must tell its own node from one started by another checkout.

Exercises tools/node_lane_repo.ps1 through PowerShell; skipped where no
PowerShell is installed.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "tools" / "node_lane_repo.ps1"
SHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(SHELL is None, reason="PowerShell not installed")


def ps(expr: str) -> str:
    script = f". '{LIB}'; {expr}"
    out = subprocess.run([SHELL, "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def repo_of(cmdline: str) -> str:
    literal = "'" + cmdline.replace("'", "''") + "'"
    return ps(f"$r = Get-RepoFromCommandLine {literal}; "
              "if ($r) { $r } else { '<none>' }")


def test_launcher_venv_names_its_checkout():
    cmd = r'"C:\Users\x\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\python.exe" tools\ngs_node_serve.py'
    assert repo_of(cmd) == r"C:\Users\x\Watchtower\NouGen\NouGenShards-push-main"


def test_unquoted_uvicorn_venv_path():
    cmd = r"C:\Users\x\Watchtower\NouGenShards\.venv\Scripts\python.exe -m uvicorn app:app --port 4444"
    assert repo_of(cmd) == r"C:\Users\x\Watchtower\NouGenShards"


def test_base_interpreter_has_no_repo():
    cmd = r'"C:\Users\x\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn app:app'
    assert repo_of(cmd) == "<none>"


def test_same_repo_ignores_case_slashes_and_trailing_separator():
    assert ps(r"Test-SameRepo 'C:\A\NouGenShards-push-main\' 'c:/a/nougenshards-push-main'") == "True"


def test_dev_checkout_is_not_the_main_checkout():
    assert ps(r"Test-SameRepo 'C:\A\NouGenShards' 'C:\A\NouGenShards-push-main'") == "False"


def test_missing_repo_is_never_the_same():
    assert ps(r"Test-SameRepo '' 'C:\A\NouGenShards'") == "False"
