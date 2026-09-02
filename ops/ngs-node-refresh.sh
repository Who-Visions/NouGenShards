#!/bin/bash
# Restart the NouGenShards node on a schedule, and record what the restart was
# worth.
#
# WHY THIS EXISTS: the node gets slower the longer it runs, with no matching
# growth in CPU or RSS. Measured on phoebus 2026-09-01 against the same query
# and the same 108k-shard vault:
#
#                        3-day-old process      fresh process
#   sequential recall    13.7 - 16.1 s          3.1 - 4.1 s
#   3 concurrent         63.0 s each            8.2 s each
#
# That is invisible to /health (25ms in both states) and to `ps` (103 min CPU
# over 3 days, 65MB RSS -- nothing wedged). It only shows up by timing a real
# recall. The fleet Worker's blade+phoebus fan-out gives this node a bounded
# peer budget, so a degraded node silently stops contributing its half of the
# corpus; keeping it fresh keeps it inside that budget.
#
# THIS IS A BAND-AID, NOT A FIX. The root cause is still unfound -- candidates
# are accumulated MCP session state, SQLite connection/statement cache growth
# across nine DBs plus history.db, or per-request structures never released.
# The before/after latencies logged here are the dataset for finding it: they
# record how fast the degradation actually accrues. Delete this script the day
# the leak is fixed, not before.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${NGS_NODE_LABEL:-com.whovisions.ngsnode}"
PORT="${NGS_PORT:-4444}"
LOG="$REPO/logs/ngs-node-refresh.log"
# The live node reads its token from the fleet .env two levels above the
# checkout. Derived, never hardcoded: an absolute path here would name the
# operator's disk layout in a public repo (tests/test_published_surface.py).
ENV_FILE="${NGS_ENV_FILE:-$(cd "$REPO/../.." && pwd)/.env}"
# Boot opens nine databases AND blocks on outbound calls to api.gradio.app
# (analytics + version check) before uvicorn binds, so cold start is network
# dependent and highly variable: measured at ~95s and ~250s on the same box
# hours apart. A 180s ceiling reported a healthy node as failed. Poll far past
# the worst observed time -- a restart that is merely slow must not be logged
# as a restart that failed.
BOOT_TIMEOUT="${NGS_BOOT_TIMEOUT:-420}"

mkdir -p "$REPO/logs"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

# Read NGS_NODE_TOKEN literally rather than sourcing: the fleet .env holds
# unquoted paths with spaces, and sourcing makes bash word-split and try to
# execute the fragment after the space (same reason bin/ngs-node.sh parses it
# by hand).
token=""
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line; do
        case "$line" in
            NGS_NODE_TOKEN=*)
                token="${line#*=}"
                token="${token%\"}"; token="${token#\"}"
                token="${token%\'}"; token="${token#\'}"
                ;;
        esac
    done < "$ENV_FILE"
fi

# Time one real recall. /health cannot answer this question -- it stayed at
# 25ms while recall sat at 16s, which is precisely why the degradation went
# unnoticed for three days.
measure() {
    [ -n "$token" ] || { echo "no-token"; return; }
    curl -s -o /dev/null --max-time 120 -w '%{time_total}' \
        -H "X-NGS-Token: $token" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -X POST "http://127.0.0.1:$PORT/mcp/" \
        -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"recall_memory","arguments":{"query":"node refresh latency probe","limit":5}}}' \
        2>/dev/null || echo "error"
}

before="$(measure)"
log "before=${before}s label=$LABEL"

launchctl kickstart -k "gui/$(id -u)/$LABEL"

up=""
for _ in $(seq 1 "$BOOT_TIMEOUT"); do
    if curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        up=yes
        break
    fi
    sleep 1
done

if [ -z "$up" ]; then
    # Loud, because a node that never came back is worse than a slow one: the
    # fan-out will report phoebus degraded on every read until someone looks.
    log "FAILED node did not answer /health within ${BOOT_TIMEOUT}s after restart"
    exit 1
fi

# Discard the first recall after a restart. It pays one-time cold costs (FTS
# and page cache, ollama's model load) that have nothing to do with the
# degradation being tracked, and comparing a cold number against the warm
# `before` would understate every restart's benefit.
measure >/dev/null
after="$(measure)"
log "after=${after}s (restarted ok)"
