"""Run or inspect the NouGen Codex named-pipe adapter."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nougen_shards.codex_pipe import request, serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["serve", "status"])
    parser.add_argument("--thread")
    parser.add_argument("--executable")
    args = parser.parse_args()
    if args.action == "status":
        try:
            print(json.dumps(request({"op": "status"}), indent=2))
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "offline", "error": str(exc)}))
            sys.exit(1)
    else:
        if not args.thread or not args.executable:
            parser.error("serve requires --thread and --executable")
        serve(args.thread, args.executable)
