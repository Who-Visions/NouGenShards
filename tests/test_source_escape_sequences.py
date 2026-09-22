"""Every shipped module must compile without invalid-escape warnings.

Python 3.12 reports an unknown escape such as ``"\\p"`` as a SyntaxWarning
(3.11 used DeprecationWarning) and a future release turns it into a
SyntaxError. Some escapes are also silently wrong today: ``"\\a"`` in a
Windows pipe path compiles to a BEL character. Compiling each source file
with warnings recorded catches both before a user's interpreter does.
"""

from __future__ import annotations

import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"


def _package_sources() -> list[Path]:
    packages = [p for p in SRC.iterdir() if (p / "__init__.py").is_file()]
    return sorted(f for pkg in packages for f in pkg.rglob("*.py"))


def _escape_warnings(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile(source, str(path), "exec")
    return [
        f"{path.relative_to(REPO_ROOT)}:{w.lineno}: {w.message}"
        for w in caught
        if issubclass(w.category, (SyntaxWarning, DeprecationWarning))
        and "escape sequence" in str(w.message)
    ]


def test_src_packages_are_discovered():
    assert _package_sources(), f"no packages found under {SRC}"


def test_no_invalid_escape_sequences_in_src():
    offenders = [msg for path in _package_sources() for msg in _escape_warnings(path)]
    assert not offenders, "invalid escape sequences:\n" + "\n".join(offenders)
