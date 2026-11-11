#!/usr/bin/env python3
"""Smoke test for nougen_remote.py's live auth + tool-bridge surface.

Written after a live incident (2026-11-07): the Google-auth unification and
the /api/v1/tools/<name> bridge silently vanished from the source on disk
with no matching commit diff - discovered only because the Android app
threw "unauthorized" on relay_open/reach_state, then took a long git
archaeology session to pin down. This script turns that into a 10-second
check: run it any time something feels off, after a Dream Lane run, or
before trusting droid.nougenai.com for a debugging session.

Checks both layers independently, so a source-level regression and a
server-level regression (old process, not restarted) are distinguishable:
  1. Source on disk still defines the auth/bridge functions (static check).
  2. The live server (through droid.nougenai.com) actually serves them
     (dynamic check) - static-pass + dynamic-fail means "edit it, didn't
     restart the server"; static-fail means "the file itself regressed".

Usage: python tools/verify_remote_bridge.py [--token TOKEN]
Exit code 0 = all checks passed, 1 = at least one failed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REMOTE_PY = Path(__file__).resolve().parent / "nougen_remote.py"
DROID_ORIGIN = os.environ.get("NOUGEN_DROID_ORIGIN", "https://droid.nougenai.com")

REQUIRED_SOURCE_MARKERS = [
    "_google_id_token_valid",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_ALLOWED_EMAILS",
    "/api/v1/tools/",
    "kaedra_tools",
]


def check_source() -> list[str]:
    failures = []
    if not REMOTE_PY.exists():
        return [f"{REMOTE_PY} does not exist"]
    text = REMOTE_PY.read_text(encoding="utf-8")
    for marker in REQUIRED_SOURCE_MARKERS:
        if marker not in text:
            failures.append(f"source missing required marker: {marker!r}")
    return failures


_UA = {"User-Agent": "nougen-verify-remote-bridge/1.0"}


def _get(url: str, timeout: float = 10.0) -> tuple[int, str]:
    # Cloudflare's bot-fight blocks bare urllib (no User-Agent at all) even
    # with the droid.nougenai.com page rule's security_level=essentially_off -
    # curl and the Worker's own fetch() both send a UA and pass fine, only
    # Python's default urllib request got a 403 here.
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pylint: disable=broad-except
        return -1, str(exc)


def _post(url: str, token: str, body: dict, timeout: float = 15.0) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={**_UA, "Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pylint: disable=broad-except
        return -1, str(exc)


def check_live(token: str | None) -> list[str]:
    failures = []
    status, _ = _get(f"{DROID_ORIGIN}/api/v1/health")
    if status != 200:
        failures.append(f"GET /api/v1/health -> {status} (expected 200, droid down or unreachable)")
        return failures  # nothing else will work either

    if not token:
        failures.append("no token given (--token or NOUGEN_REMOTE_TOKEN) - skipped live auth/bridge checks")
        return failures

    status, body = _post(f"{DROID_ORIGIN}/api/v1/tools/fleet_whoami", token, {})
    if status != 200:
        failures.append(f"POST /api/v1/tools/fleet_whoami -> {status}: {body[:200]} "
                         "(bridge missing/broken, or token stale)")

    status, body = _post(f"{DROID_ORIGIN}/api/v1/tools/relay_open", token, {"limit": 1})
    if status != 200:
        failures.append(f"POST /api/v1/tools/relay_open -> {status}: {body[:200]} "
                         "(this exact endpoint regressed once already - 2026-11-07)")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", default=os.environ.get("NOUGEN_REMOTE_TOKEN", ""))
    parser.add_argument("--source-only", action="store_true", help="skip live network checks")
    args = parser.parse_args()

    failures = check_source()
    print(f"[source] {'OK' if not failures else 'FAIL'} - {REMOTE_PY}")
    for f in failures:
        print(f"  - {f}")

    if not args.source_only:
        live_failures = check_live(args.token or None)
        print(f"[live]   {'OK' if not live_failures else 'FAIL'} - {DROID_ORIGIN}")
        for f in live_failures:
            print(f"  - {f}")
        failures += live_failures

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} issue(s))")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
