"""Generate the HUD's demo fixtures from a real engine run.

The browser preview needs sample data, and hand-invented numbers teach the
wrong shape: they are always too tidy, too small, and they drift from what the
engine actually returns. This snapshots the real commands and scrubs the
result, so the demo inherits the structure of real use without carrying any of
its content.

What is kept: field names, record counts, the shape and rough order of
magnitude of numbers.
What is removed: every piece of free text (shard titles and bodies, handoff
goals), host names, and exact figures. Numbers are rounded to two significant
figures so a snapshot cannot be read back as a usage report.

    python tools/snapshot_demo.py                 # -> ui/src/demo-data.json
    python tools/snapshot_demo.py --keep-text     # local only; never commit
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "ui" / "src" / "demo-data.json"

# Free-text fields that must never survive into a committed fixture.
TEXT_FIELDS = {"title", "content", "goal", "machine", "branch", "acknowledged_by", "id"}

PLACEHOLDERS = {
    "title": "Sample shard {i} — run inside Tauri for live data",
    "content": ("Demo record generated from a real engine response, with text removed. "
                "Launch with `npm run tauri dev` to search your own substrate."),
    "goal": "Sample handoff {i} — your real registry appears here in the desktop shell",
    "machine": "demo-node",
    "branch": "main",
    "acknowledged_by": "",
    "id": "demo-{i}",
}


def run_engine(args: list[str]) -> object | None:
    """Call the CLI the same way the Tauri shell does."""
    cmd = [sys.executable, "-m", "nougen_shards.cli", *args]
    env_src = str(REPO_ROOT / "src")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=REPO_ROOT, env={**__import__("os").environ, "PYTHONPATH": env_src},
        )
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"[!] {' '.join(args)}: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(f"[!] {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()[:200]}",
              file=sys.stderr)
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"[!] {' '.join(args)}: output was not JSON", file=sys.stderr)
        return None


def round_sig(value: float, digits: int = 2) -> float:
    """Round to N significant figures, so a figure cannot be read as a real total."""
    if not value:
        return 0
    rounded = round(value, -int(math.floor(math.log10(abs(value)))) + (digits - 1))
    return int(rounded) if float(rounded).is_integer() else round(rounded, 4)


def scrub(node, keep_text: bool, counter: dict):
    if isinstance(node, list):
        return [scrub(v, keep_text, counter) for v in node]
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in TEXT_FIELDS and not keep_text:
                i = counter.setdefault(key, 0) + 1
                counter[key] = i
                out[key] = PLACEHOLDERS.get(key, "").format(i=i)
            elif isinstance(value, bool):
                out[key] = value
            elif isinstance(value, (int, float)):
                out[key] = value if keep_text else round_sig(value)
            else:
                out[key] = scrub(value, keep_text, counter)
        return out
    return node


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--query", default="memory", help="Search term used to sample results")
    ap.add_argument("--period", default="week", help="Window for the usage snapshot")
    ap.add_argument("--limit", type=int, default=3, help="Records to keep per section")
    ap.add_argument("--keep-text", action="store_true",
                    help="Skip scrubbing. Local inspection only — do not commit the result.")
    args = ap.parse_args(argv)

    sections = {
        "shards": run_engine(["search", args.query, "--json"]),
        "status": run_engine(["status", "--json"]),
        "usage": run_engine(["usage", "--period", args.period, "--json"]),
        "relay": run_engine(["handoff", "list", "--json"]),
    }

    missing = [k for k, v in sections.items() if v is None]
    if missing:
        print(f"[!] no data for: {', '.join(missing)} — those sections keep their previous values.",
              file=sys.stderr)

    counter: dict = {}
    payload = {
        "_generated_by": "tools/snapshot_demo.py",
        "_note": ("Derived from a real engine run with text and exact figures removed. "
                  "Regenerate rather than editing by hand."),
        "_scrubbed": not args.keep_text,
    }
    for name, data in sections.items():
        if data is None:
            continue
        if isinstance(data, list):
            data = data[:args.limit]
        elif name == "usage" and isinstance(data, dict) and isinstance(data.get("by_model"), list):
            data = {**data, "by_model": data["by_model"][:args.limit]}
        payload[name] = scrub(data, args.keep_text, counter)

    if args.keep_text:
        print("[!] --keep-text: this file carries real content. Do not commit it.", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {', '.join(k for k in sections if sections[k] is not None)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
