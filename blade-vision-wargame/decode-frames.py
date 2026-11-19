#!/usr/bin/env python3
"""Decode the base64 frame files pushed via GitHub (binary JPGs cannot travel
on the snapshot-push route) and verify them against test-set/manifest.json.

Run ON Blade, from the folder that holds test-set/ :

  python decode-frames.py

What it does:
  1. For every *.jpg.b64 under test-set/frames-congress and
     test-set/frames-military, writes the decoded *.jpg next to it.
  2. Verifies each decoded file's sha256 against manifest.json.
  3. Prints OK/FAIL per frame and exits non-zero if anything fails.

Stdlib only. No network, no writes outside this folder.
"""
import base64
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEST_SET = HERE / "test-set"


def main() -> int:
    manifest = json.loads((TEST_SET / "manifest.json").read_text())
    failures = 0
    total = 0
    for set_name, sub in (("congress", "frames-congress"),
                          ("military", "frames-military")):
        for fr in manifest[set_name]["frames"]:
            total += 1
            b64_path = TEST_SET / sub / (fr["file"] + ".b64")
            jpg_path = TEST_SET / sub / fr["file"]
            try:
                raw = base64.b64decode(b64_path.read_bytes())
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"FAIL {set_name}/{fr['file']}: cannot decode: {exc}")
                failures += 1
                continue
            jpg_path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            if digest != fr["sha256"]:
                print(f"FAIL {set_name}/{fr['file']}: sha256 mismatch "
                      f"(got {digest[:12]}..., want {fr['sha256'][:12]}...)")
                failures += 1
            else:
                print(f"OK   {set_name}/{fr['file']}")
    print(f"decoded {total - failures}/{total} frames, {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
