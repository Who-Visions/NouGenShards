"""Frozen engine sidecar entry point.

Bundled by PyInstaller into `nougen_engine-<triple>(.exe)` and shipped next to
the Tauri app. It is a thin, fail-safe shim around the real CLI: it forwards its
argv straight to `nougen_shards.cli.main()` (e.g. `search <q> --json`,
`status --json`, `stats --period week --json`) and prints the same trailing JSON
the dev path emits.

Contract with the Rust shell (src-tauri/src/lib.rs):
  - success  -> JSON document on stdout, exit 0
  - failure  -> human-readable reason on stderr, exit 1
The Rust side captures stderr and surfaces it; it never sees a raw traceback.
"""
import os
import sys

# Keep Unicode-bearing shard content from crashing the Windows console codec.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _ensure_importable():
    """Dev convenience: when run from source (not frozen), put repo `src` on the
    path. In the frozen exe `nougen_shards` is embedded and this is a no-op."""
    if getattr(sys, "frozen", False):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.abspath(os.path.join(here, "..", "..", "src"))
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)


def main() -> int:
    _ensure_importable()
    try:
        from nougen_shards.cli import main as cli_main
    except Exception as exc:  # noqa: BLE001 - report any import failure cleanly
        sys.stderr.write(f"engine import failed: {exc}\n")
        return 1

    try:
        cli_main()
    except SystemExit as exc:
        # argparse / cli use sys.exit; honor their code (None == success).
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
    except Exception as exc:  # noqa: BLE001 - never let a traceback hit stdout
        sys.stderr.write(f"engine error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
