"""CLI interface for NouGenTime; supports human and JSON output."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show canonical Eastern and UTC time.")
    parser.add_argument("--json", action="store_true", help="emit one machine-readable JSON object")
    parser.add_argument("--version", action="version", version=f"nougen-time {__version__}")
    args = parser.parse_args(argv)

    instant = now()
    if args.json:
        print(json.dumps(instant.to_dict(__version__), ensure_ascii=False, separators=(",", ":")))
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print("=" * 60)
        print("NouGenTime — Fleet Dynamic Temporal Anchor")
        print("=" * 60)
        print(f"  Dave Local (EDT/EST) : {instant.banner}")
        print(f"  Short Display        : {instant.display}")
        print(f"  Provenance Paired    : {instant.paired}")
        print(f"  Canonical UTC ISO    : {instant.utc_iso}")
        print(f"  Unix Timestamp (ns)  : {instant.unix_timestamp_ns}")
        print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
