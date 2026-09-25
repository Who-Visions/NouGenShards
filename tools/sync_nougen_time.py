"""Sync or check the generated NouGenTime mirror in the sibling Relay repo."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PACKAGE_FILES = ("README.md", "__init__.py", "__main__.py", "core.py")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relay-root", type=Path, help="NouGenRelay checkout (defaults to sibling checkout)")
    parser.add_argument("--check", action="store_true", help="report drift without copying files")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "src" / "nougen_time"
    relay_root = (args.relay_root or repo_root.parent / "NouGenRelay").expanduser().resolve()
    target = relay_root / "src" / "nougen_time"
    test_source = repo_root / "tests" / "test_nougen_time.py"
    test_target = relay_root / "tests" / "test_nougen_time.py"
    if not source.is_dir():
        print(f"canonical NouGenTime source is missing: {source}", file=sys.stderr)
        return 2
    if not (relay_root / ".git").exists() and not (relay_root / "pyproject.toml").exists():
        print(f"NouGenRelay checkout is missing: {relay_root}", file=sys.stderr)
        return 2

    mismatches = [name for name in PACKAGE_FILES if not (target / name).is_file()
                  or (source / name).read_bytes() != (target / name).read_bytes()]
    if not test_target.is_file() or test_source.read_bytes() != test_target.read_bytes():
        mismatches.append("tests/test_nougen_time.py")
    if args.check:
        if mismatches:
            print("NouGenTime mirror drift: " + ", ".join(mismatches), file=sys.stderr)
            return 1
        print("NouGenTime Relay mirror matches canonical source.")
        return 0

    target.mkdir(parents=True, exist_ok=True)
    for name in PACKAGE_FILES:
        shutil.copyfile(source / name, target / name)
    test_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(test_source, test_target)
    print(f"Synced {len(PACKAGE_FILES)} package files and the test suite to {relay_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
