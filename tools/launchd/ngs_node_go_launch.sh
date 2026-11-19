#!/bin/bash
# Launcher for the NouGenShards node with the Go front (go/ngsnode).
#
# The Go binary owns the node's port. It serves the routes that have been
# ported and proxies the rest to the Python app, which it starts as a worker
# on a loopback port and restarts if it dies. Same config loading as the
# Python-only launcher, so swapping launchers changes nothing else.
#
# Build the binary once per update:
#   (cd "$CLONE/go/ngsnode" && go build -o "$HOME/.nougen/bin/ngsnode" .)
set -euo pipefail

CLONE="${NGS_NODE_CLONE:-$HOME/.nougen/src/nougenshards}"
BIN="${NGS_NODE_GO_BIN:-$HOME/.nougen/bin/ngsnode}"
PY="$CLONE/.venv/bin/python"
ENV_FILE="${NGS_NODE_ENV_FILE:-$HOME/The Observatory/.env}"

# Load NGS_*/NOUGEN_* config without echoing values. Deliberately NOT `source`:
# the fleet .env holds unquoted paths with spaces, and sourcing makes bash
# word-split them and try to execute the fragment after the space.
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line; do
        case "$line" in
            NGS_*=*|NOUGEN_*=*)
                key="${line%%=*}"
                value="${line#*=}"
                value="${value%\"}"; value="${value#\"}"
                value="${value%\'}"; value="${value#\'}"
                export "$key=$value"
                ;;
        esac
    done < "$ENV_FILE"
fi

if [ -z "${NGS_NODE_TOKEN:-}" ]; then
    echo "[FATAL] NGS_NODE_TOKEN unset — refusing to start an unauthenticated node." >&2
    exit 78  # EX_CONFIG
fi
if [ ! -x "$BIN" ]; then
    echo "[FATAL] $BIN is missing — build it: (cd $CLONE/go/ngsnode && go build -o $BIN .)" >&2
    exit 78
fi

export NOUGEN_VAULT_DIR="${NOUGEN_VAULT_DIR:-$HOME/.nougen/shards}"
export NOUGEN_WARMUP="${NOUGEN_WARMUP:-1}"
# PYTHONPATH goes on sys.path before site-packages .pth entries, which is what
# makes the clone's package win over another checkout's editable install.
export PYTHONPATH="$CLONE/src${PYTHONPATH:+:$PYTHONPATH}"
cd "$CLONE"

RESOLVED="$("$PY" -c 'import nougen_shards; print(nougen_shards.__file__)')"
case "$RESOLVED" in
    "$CLONE"/*) echo "[ok] nougen_shards from clone: $RESOLVED" ;;
    *) echo "[FATAL] import isolation failed — nougen_shards resolved to $RESOLVED" >&2
       exit 78 ;;
esac
echo "[ok] vault: $NOUGEN_VAULT_DIR"

# The front listens where the node always has; the worker's port is picked by
# the front and passed to app.py as NGS_PORT.
# NGS_FRONT_PORT overrides the listen port for a side-by-side trial run.
exec "$BIN" -listen "127.0.0.1:${NGS_FRONT_PORT:-${NGS_PORT:-4444}}" -vault "$NOUGEN_VAULT_DIR" -- "$PY" app.py
