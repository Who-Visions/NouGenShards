"""CLI shim; logic lives in nougen_shards.codex_status."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nougen_shards.codex_status import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
