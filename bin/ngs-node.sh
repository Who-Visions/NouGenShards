#!/bin/bash
# Launcher for the NouGenShards node on phoebus.
#
# launchd starts processes with a near-empty environment and no shell profile,
# so the node's secrets have to be loaded explicitly here rather than inherited.
# Keep this the single entry point: the launchd plist calls this script, and so
# should any manual start, so both paths get identical config.
set -euo pipefail

REPO="/Users/kushboygroup/The Observatory/NouGen/nougenshards"
ENV_FILE="/Users/kushboygroup/The Observatory/.env"

# Load NGS_* config (token, port, HUD credentials) without echoing values.
#
# Deliberately NOT `source` — the fleet .env holds unquoted paths with spaces
# (e.g. the Firebase adminsdk credential under "The Observatory/"), and sourcing
# makes bash word-split them and try to EXECUTE the fragment after the space.
# That fails the whole file under `set -e` and the node never starts. Read the
# keys we need literally instead, so unrelated lines can never break the launch.
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line; do
        case "$line" in
            NGS_*=*|NOUGEN_*=*)
                key="${line%%=*}"
                value="${line#*=}"
                # Strip one layer of surrounding quotes if present.
                value="${value%\"}"; value="${value#\"}"
                value="${value%\'}"; value="${value#\'}"
                export "$key=$value"
                ;;
        esac
    done < "$ENV_FILE"
fi

# Deny-by-default: without a token the data API returns 503 and /mcp returns
# 503, which looks like a broken tunnel rather than a config error. Fail loudly
# here instead so the cause shows up in the launchd log.
if [ -z "${NGS_NODE_TOKEN:-}" ]; then
    echo "[FATAL] NGS_NODE_TOKEN unset — refusing to start an unauthenticated node." >&2
    exit 78  # EX_CONFIG
fi

cd "$REPO"

# Bind loopback only. Public reach is the cloudflared tunnel's job; binding to
# 0.0.0.0 would additionally expose the node to everything on 10.0.0.x.
export NGS_HOST="127.0.0.1"
export NGS_PORT="${NGS_PORT:-4444}"

exec ./.venv/bin/python app.py
