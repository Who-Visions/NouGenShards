"""Run the existing Codex adapter without importing the vault application."""
import argparse
import importlib.util
import json
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "src" / "nougen_shards" / "codex_pipe.py"
spec = importlib.util.spec_from_file_location("codex_pipe_adapter", source)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "serve"])
    parser.add_argument("--thread")
    parser.add_argument("--executable")
    args = parser.parse_args()
    if args.action == "status":
        print(json.dumps(adapter.request({"op": "status"})))
    else:
        if not args.thread or not args.executable:
            parser.error("serve requires --thread and --executable")
        adapter.serve(args.thread, args.executable)
