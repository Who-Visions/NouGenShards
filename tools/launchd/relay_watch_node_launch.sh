#!/bin/bash
# launchd bootstrap for the relay watcher. Same pattern as
# nougenmsg_node_launch.sh: secrets from the Keymaker vault at process start
# so relay legs can go through the same judgment gate and owner-origin
# verifier as the network path, without any secret touching the plist.
#
# Environment (all optional):
#   NOUGEN_SHARDS_REPO      nougenshards checkout holding .venv and src/
#                           (default: two levels above this script)
#   NOUGEN_PYTHON           interpreter (default /usr/bin/python3)
#   NOUGEN_RELAYWATCH_SCRIPT path to relay_watch_node.py (default:
#                           ../relay_watch_node.py, else a sibling file)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${NOUGEN_SHARDS_REPO:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

resolve() {
    "$REPO/.venv/bin/python" -c "
import sys; sys.path.insert(0, '$REPO/src')
from nougen_shards import keymaker
print(keymaker.get_secret('$1') or '')
"
}

export KAEDRA_GATEWAY_TOKEN="$(resolve KAEDRA_GATEWAY_TOKEN)"
export NOUGEN_USER_ORIGIN_TOKEN="$(resolve NOUGEN_USER_ORIGIN_TOKEN)"

NODE_SCRIPT="${NOUGEN_RELAYWATCH_SCRIPT:-$SCRIPT_DIR/../relay_watch_node.py}"
[ -f "$NODE_SCRIPT" ] || NODE_SCRIPT="$SCRIPT_DIR/relay_watch_node.py"

exec "${NOUGEN_PYTHON:-/usr/bin/python3}" "$NODE_SCRIPT"
