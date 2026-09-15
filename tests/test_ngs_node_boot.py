"""tools/ngs_node_boot.cmd must sync and launch the SAME supervisor copy.

2026-09-14: the boot script ran install_grid_supervisor.ps1 before it set
NOUGEN_HOME, so with a different NOUGEN_HOME in the user environment the sync
refreshed one home while the watcher launched a stale copy from another, and
the --watch loop died at boot with no trace. The ordering checks are static
so they run on any CI runner; the resolution block is also executed through
cmd.exe where one exists.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BOOT = Path(__file__).resolve().parent.parent / "tools" / "ngs_node_boot.cmd"
SETS_HOME = re.compile(r'\bset\s+"?NOUGEN_HOME=', re.IGNORECASE)


def _code_lines():
    lines = []
    for raw in BOOT.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.lower().startswith("rem") or s.startswith("::"):
            continue
        lines.append(s)
    return lines


def _index(lines, needle):
    for i, s in enumerate(lines):
        if needle in s:
            return i
    raise AssertionError(f"{needle!r} not found in {BOOT.name}")


def test_home_is_resolved_before_the_supervisor_sync():
    lines = _code_lines()
    sync = _index(lines, "install_grid_supervisor.ps1")
    assigns = [i for i, s in enumerate(lines) if SETS_HOME.search(s)]
    assert assigns, "boot script never resolves NOUGEN_HOME"
    late = [lines[i] for i in assigns if i > sync]
    assert not late, f"NOUGEN_HOME reassigned after the sync (install and launch fork): {late}"


def test_launch_runs_the_copy_the_sync_refreshed():
    lines = _code_lines()
    sync = _index(lines, "install_grid_supervisor.ps1")
    launch = _index(lines, "--watch")
    assert sync < launch
    assert "%NOUGEN_HOME%\\bin\\start_grid.py" in lines[launch]


def test_configured_home_is_validated_not_blindly_trusted():
    text = "\n".join(_code_lines())
    assert 'exist "%NOUGEN_HOME%\\%NGS_HOME_MARKER%"' in text


def _resolution_block():
    lines = BOOT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, s in enumerate(lines) if "set \"NGS_HOME_MARKER=" in s)
    end = next(i for i, s in enumerate(lines)
               if s.strip() == 'if not defined NOUGEN_HOME set "NOUGEN_HOME=%NGS_HOME_FALLBACK%"')
    return lines[start:end + 1]


def _resolve(tmp_path, env_home):
    script = tmp_path / "resolve.cmd"
    body = ["@echo off", "setlocal", *_resolution_block(), "echo HOME=%NOUGEN_HOME%"]
    # LF bytes on purpose: the checked-in script is stored LF-only.
    script.write_bytes(("\n".join(body) + "\n").encode("utf-8"))
    env = dict(os.environ)
    env["USERPROFILE"] = str(tmp_path / "profile")
    env.pop("NGS_HOME_MARKER", None)
    env.pop("NOUGEN_HOME", None)
    if env_home is not None:
        env["NOUGEN_HOME"] = str(env_home)
    out = subprocess.run(["cmd.exe", "/d", "/c", str(script)], env=env,
                         capture_output=True, text=True, timeout=30)
    homes = [ln[5:] for ln in out.stdout.splitlines() if ln.startswith("HOME=")]
    assert out.returncode == 0 and homes, (out.returncode, out.stdout, out.stderr)
    return homes[-1].strip(), out.stderr


needs_cmd = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe only on Windows")


@needs_cmd
def test_valid_configured_home_is_kept(tmp_path):
    home = tmp_path / "runtime home"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "keymaker_peel.py").write_text("", encoding="utf-8")
    resolved, err = _resolve(tmp_path, home)
    assert resolved == str(home)
    assert not err.strip()


@needs_cmd
def test_home_without_keymaker_falls_back_and_says_so(tmp_path):
    bare = tmp_path / "not a runtime home"
    bare.mkdir()
    resolved, err = _resolve(tmp_path, bare)
    assert resolved == str(tmp_path / "profile" / ".nougen")
    assert "lacks" in err


@needs_cmd
def test_unset_home_uses_the_per_user_default(tmp_path):
    resolved, _ = _resolve(tmp_path, None)
    assert resolved == str(tmp_path / "profile" / ".nougen")
