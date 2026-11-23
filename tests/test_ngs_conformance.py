"""Compile-time conformance harness for the NGS native engine header (PR 1199).

Engine-independent: compiles tests/ngs_conformance/header_contract.c against
ngs.h as C11 (pedantic, -Werror) and as C++. The header is located via
$NGS_HEADER_DIR or docs/memory-engine/; until the spec PR lands on main the
tests skip rather than fail.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests" / "ngs_conformance" / "header_contract.c"
HEADER_DIR = Path(os.environ.get("NGS_HEADER_DIR", ROOT / "docs" / "memory-engine"))

pytestmark = pytest.mark.skipif(
    not (HEADER_DIR / "ngs.h").is_file(), reason="ngs.h not on this branch yet (PR 1199)"
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


def test_header_alone_c11() -> None:
    _compile("cc", ["-std=c11", "-pedantic", "-x", "c", str(HEADER_DIR / "ngs.h")])
