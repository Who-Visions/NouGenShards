"""Compile-time conformance harness for the NGS native engine header (PR 1199, draft 0.3.1 @ 685901a).

Engine-independent: compiles tests/ngs_conformance/header_contract.c against
ngs.h as C11 (pedantic, -Werror) and as C++. The header is located via
$NGS_HEADER_DIR or docs/memory-engine/; until the spec PR lands on main the
tests skip rather than fail.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests" / "ngs_conformance" / "header_contract.c"
_CANDIDATES = (ROOT / "engine" / "ngs" / "include", ROOT / "docs" / "memory-engine")
HEADER_DIR = Path(
    os.environ.get("NGS_HEADER_DIR")
    or next((d for d in _CANDIDATES if (d / "ngs.h").is_file()), _CANDIDATES[-1])
)
SPEC_CHECK_DIR = Path(
    os.environ.get("NGS_SPEC_CHECK_DIR", ROOT / "docs" / "memory-engine" / "check")
)

pytestmark = pytest.mark.skipif(
    not (HEADER_DIR / "ngs.h").is_file(),
    reason="ngs.h not on this branch yet (PR 1199)",
)


def _compile(compiler: str, args: list[str]) -> None:
    exe = shutil.which(compiler)
    if exe is None:
        pytest.skip(f"{compiler} not installed")
    proc = subprocess.run(
        [exe, "-fsyntax-only", "-Wall", "-Wextra", "-Werror", f"-I{HEADER_DIR}", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_header_contract_c11() -> None:
    _compile("cc", ["-std=c11", "-pedantic", "-x", "c", str(CONTRACT)])


def test_header_contract_cxx() -> None:
    _compile("c++", ["-std=c++11", "-x", "c++", str(CONTRACT)])


def test_spec_header_check_runs(tmp_path: Path) -> None:
    """Build and run the spec PR's own check/ngs_header_check.c when present."""
    src = next(
        (
            p
            for p in (
                HEADER_DIR / "check" / "ngs_header_check.c",
                SPEC_CHECK_DIR / "ngs_header_check.c",
            )
            if p.is_file()
        ),
        HEADER_DIR / "check" / "ngs_header_check.c",
    )
    if not src.is_file():
        pytest.skip("spec header check not present")
    exe = shutil.which("cc")
    if exe is None:
        pytest.skip("cc not installed")
    out = tmp_path / "ngs_header_check"
    build = subprocess.run(
        [
            exe,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{HEADER_DIR}",
            str(src),
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(out)], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr


BEHAVIOUR = ROOT / "tests" / "ngs_conformance" / "behaviour.c"
ENGINE_DIR = Path(os.environ.get("NGS_ENGINE_DIR", ROOT / "engine" / "ngs"))


def _amalgamation() -> Path | None:
    """The entry's single-file build: $NGS_AMALGAMATION, else engine/ngs/dist,
    built with the entry's own tool/amalgamate.py when not committed."""
    env = os.environ.get("NGS_AMALGAMATION")
    if env:
        return Path(env)
    dist = ENGINE_DIR / "dist" / "nougenshards.c"
    tool = ENGINE_DIR / "tool" / "amalgamate.py"
    if not dist.is_file() and tool.is_file():
        subprocess.run(
            [sys.executable, "-I", str(tool)],
            cwd=ENGINE_DIR,
            capture_output=True,
            check=False,
        )
    single = ENGINE_DIR / "src" / "nougenshards.c"
    return dist if dist.is_file() else (single if single.is_file() else None)


@pytest.mark.skipif(os.name == "nt", reason="file-damage checks use POSIX I/O")
def test_engine_behaviour_m1(tmp_path: Path) -> None:
    """Black-box M1 behaviour: every check in behaviour.c must PASS."""
    amalg = _amalgamation()
    if amalg is None:
        pytest.skip("no engine amalgamation on this branch")
    exe = shutil.which("cc")
    if exe is None:
        pytest.skip("cc not installed")
    binary = tmp_path / "behaviour"
    build = subprocess.run(
        [
            exe,
            "-std=c11",
            "-O1",
            "-w",
            f"-I{HEADER_DIR}",
            str(BEHAVIOUR),
            str(amalg),
            "-o",
            str(binary),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    run = subprocess.run(
        [str(binary), str(tmp_path / "db")],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    print(run.stdout)
    fails = [line for line in run.stdout.splitlines() if line.startswith("FAIL")]
    assert "SUMMARY" in run.stdout, (
        f"engine crashed (rc={run.returncode}):\n{run.stdout}{run.stderr}"
    )
    assert not fails, "\n".join(fails)


CRASH = ROOT / "tests" / "ngs_conformance" / "crash.c"


@pytest.mark.skipif(os.name == "nt", reason="crash injection uses fork and SIGKILL")
def test_engine_crash_injection(tmp_path: Path) -> None:
    """SIGKILL a writer mid-batch, repeatedly; acked facts survive, batches stay atomic."""
    amalg = _amalgamation()
    if amalg is None:
        pytest.skip("no engine amalgamation on this branch")
    exe = shutil.which("cc")
    if exe is None:
        pytest.skip("cc not installed")
    binary = tmp_path / "crash"
    build = subprocess.run(
        [
            exe,
            "-std=c11",
            "-O1",
            "-w",
            f"-I{HEADER_DIR}",
            str(CRASH),
            str(amalg),
            "-o",
            str(binary),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    rounds = os.environ.get("NGS_CRASH_ROUNDS", "30")
    seed = os.environ.get("NGS_CRASH_SEED", "1085")
    run = subprocess.run(
        [str(binary), str(tmp_path / "db"), rounds, seed],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    print(run.stdout)
    fails = [line for line in run.stdout.splitlines() if line.startswith("FAIL")]
    assert "SUMMARY" in run.stdout, (
        f"crash driver died (rc={run.returncode}):\n{run.stdout}{run.stderr}"
    )
    assert not fails, "\n".join(fails)
