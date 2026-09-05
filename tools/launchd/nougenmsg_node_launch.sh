#!/bin/bash
# launchd bootstrap for the NouGenMsg node receiver.
#
# Resolves every secret from the Keymaker vault at process start, then execs
# the portable receiver. The receiver itself stays stdlib-only and
# secret-free; the plist stays secret-free too. Only this wrapper touches
# Keymaker, and the values live in one process's environment for its
# lifetime — never on disk in plaintext, never in a synced/backed-up plist.
#
# Environment (all optional):
#   NOUGEN_SHARDS_REPO   nougenshards checkout holding .venv and src/
#                        (default: two levels above this script, i.e. the
#                        repo root when run from tools/launchd/)
#   NOUGEN_PYTHON        interpreter for the receiver (default /usr/bin/python3)
#   NOUGEN_MSGNODE_SCRIPT path to nougenmsg_node.py (default: ../nougenmsg_node.py
#                        relative to this script, else a sibling file)
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

# Bus token: opt-in receiver auth. User-origin token: strictly higher value
# than the bus token — a valid signature bypasses the content gate — so it is
# resolved here exactly like the others and never handled anywhere the bus
# token is not.
export NOUGEN_AGY_MSG_TOKEN="$(resolve NOUGEN_AGY_MSG_TOKEN)"
export KAEDRA_GATEWAY_TOKEN="$(resolve KAEDRA_GATEWAY_TOKEN)"
export NOUGEN_USER_ORIGIN_TOKEN="$(resolve NOUGEN_USER_ORIGIN_TOKEN)"

NODE_SCRIPT="${NOUGEN_MSGNODE_SCRIPT:-$SCRIPT_DIR/../nougenmsg_node.py}"
[ -f "$NODE_SCRIPT" ] || NODE_SCRIPT="$SCRIPT_DIR/nougenmsg_node.py"

exec "${NOUGEN_PYTHON:-/usr/bin/python3}" "$NODE_SCRIPT"
