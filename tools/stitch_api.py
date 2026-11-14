#!/usr/bin/env python3
"""Google Stitch API CLI & Client.

Connects to Google Stitch MCP Endpoint (https://stitch.googleapis.com/mcp)
using STITCH_API_KEY securely resolved via Keymaker.
Never dumps secrets into stdout or command traces.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

NOUGEN_SRC = Path(__file__).resolve().parents[1] / "src"
if NOUGEN_SRC.is_dir() and str(NOUGEN_SRC) not in sys.path:
    sys.path.insert(0, str(NOUGEN_SRC))

STITCH_ENDPOINT = "https://stitch.googleapis.com/mcp"


def _get_api_key() -> str:
    key = os.environ.get("STITCH_API_KEY", "").strip()
    if not key:
        try:
            from nougen_shards.keymaker import get_secret
            key = (get_secret("STITCH_API_KEY") or "").strip()
        except Exception:
            pass
    return key


def call_stitch(tool_name: str, arguments: dict | None = None) -> dict:
    """Call a Stitch tool over JSON-RPC."""
    key = _get_api_key()
    if not key:
        raise RuntimeError("STITCH_API_KEY not found in Keymaker vault or environment.")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Goog-Api-Key": key,
        "User-Agent": "NouGenStitchClient/1.0",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
    }
    req = urllib.request.Request(
        STITCH_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(f"Stitch Error {data['error'].get('code')}: {data['error'].get('message')}")
        result = data.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content[0], dict) and "text" in content[0]:
            try:
                return json.loads(content[0]["text"])
            except Exception:
                return {"text": content[0]["text"]}
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Stitch CLI (Keymaker-Grounded)")
    sub = parser.add_subparsers(dest="command", required=True)

    # list-projects
    sub.add_parser("projects", help="List all Stitch projects")

    # list-screens
    p_screens = sub.add_parser("screens", help="List screens in a project")
    p_screens.add_argument("project_id", help="Full project resource name (e.g. projects/2056801290244597492)")

    # get-screen
    p_screen = sub.add_parser("screen", help="Get screen metadata")
    p_screen.add_argument("screen_id", help="Full screen resource name")

    # generate-screen
    p_gen = sub.add_parser("generate", help="Generate a new screen from text prompt")
    p_gen.add_argument("project_id", help="Project ID")
    p_gen.add_argument("--prompt", required=True, help="Prompt describing the screen UI")

    args = parser.parse_args()

    try:
        if args.command == "projects":
            res = call_stitch("list_projects")
            projects = res.get("projects", [])
            print(f"Stitch Projects ({len(projects)}):")
            for p in projects:
                print(f"  • {p.get('title', 'Untitled')} [{p.get('name')}] (Updated: {p.get('updateTime', 'n/a')})")

        elif args.command == "screens":
            res = call_stitch("list_screens", {"projectId": args.project_id})
            screens = res.get("screens", [])
            print(f"Screens in {args.project_id} ({len(screens)}):")
            for s in screens:
                print(f"  • {s.get('title', 'Untitled')} [{s.get('name')}]")

        elif args.command == "screen":
            res = call_stitch("get_screen", {"screenId": args.screen_id})
            print(json.dumps(res, indent=2))

        elif args.command == "generate":
            res = call_stitch("generate_screen_from_text", {"projectId": args.project_id, "prompt": args.prompt})
            print(json.dumps(res, indent=2))

    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
