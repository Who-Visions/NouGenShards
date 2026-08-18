#!/bin/bash
# Launcher for the Kaedra local-model gateway on phoebus.
#
# Same contract as bin/ngs-node.sh: launchd gives us a near-empty environment,
# so config is loaded explicitly here and this stays the single entry point for
# both launchd and any manual start.
set -euo pipefail

REPO="/Users/kushboygroup/The Observatory/NouGen/nougenshards"
ENV_FILE="/Users/kushboygroup/The Observatory/.env"

# Read KAEDRA_* literally rather than sourcing — the fleet .env contains
# unquoted paths with spaces that word-split and fail the whole file under
# `set -e` (see the long note in ngs-node.sh).
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line; do
        case "$line" in
            KAEDRA_*=*)
                key="${line%%=*}"
                value="${line#*=}"
                value="${value%\"}"; value="${value#\"}"
                value="${value%\'}"; value="${value#\'}"
                export "$key=$value"
                ;;
        esac
    done < "$ENV_FILE"
fi

# Deny-by-default: an unauthenticated gateway would put a free GPU on a public
# hostname. Fail loudly in the launchd log instead of serving open.
if [ -z "${KAEDRA_GATEWAY_TOKEN:-}" ]; then
    echo "[FATAL] KAEDRA_GATEWAY_TOKEN unset — refusing to start an open model gateway." >&2
    exit 78  # EX_CONFIG
fi

exec /usr/bin/python3 "$REPO/ops/kaedra/kaedra_gateway.py"
