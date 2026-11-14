#!/bin/bash
# Kill runaway `log show` children of Antigravity's language_server before
# they starve the shard node.
#
# WHY THIS EXISTS: 2026-09-05 ~01:00-06:20Z, Antigravity's `language_server`
# fanned out one `log show --predicate ... EXEBOX ID ...` sandbox-audit query
# per event, and at least 26 of them never exited -- each pinned at ~25-30%
# CPU for 15-90+ minutes. That drove `load average` to 367 on an 8-core box.
# com.whovisions.ngsnode runs as launchd ProcessType=Background (PRI 4), so at
# that load it never got scheduled: the process showed up in `ps`, was
# listening on :4444 (confirmed via `lsof`), but produced zero log output and
# answered no request for 4+ hours -- a wedged node that looked alive to every
# surface-level check. Only a direct curl + log-staleness check caught it.
# Recovery needed killing the `log show` children AND a `launchctl kickstart
# -k` of the node; neither alone was sufficient.
#
# This does NOT fix Antigravity's fan-out (root cause is in a closed-source
# app, out of reach). It bounds the blast radius: any `log show` process still
# running past AGE_LIMIT_S is presumed stuck (a real single-predicate query
# against the unified log completes in seconds, not minutes) and is killed.
# Read-only diagnostic queries have no state, so killing one loses nothing.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$REPO/logs/phoebus-logshow-guard.log"
AGE_LIMIT_S="${PHOEBUS_LOGSHOW_AGE_LIMIT_S:-120}"

mkdir -p "$REPO/logs"
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

# etime as HH:MM:SS or MM:SS or DD-HH:MM:SS -> seconds. `ps etime` has no
# stable single format across those, so parse the colon-separated tail
# ourselves rather than trust a fixed field width.
etime_to_seconds() {
    local etime="$1" days=0 rest="$1" secs=0 mult=1
    if [[ "$etime" == *-* ]]; then
        days="${etime%%-*}"
        rest="${etime#*-}"
    fi
    IFS=':' read -ra parts <<< "$rest"
    for ((i = ${#parts[@]} - 1; i >= 0; i--)); do
        secs=$((secs + 10#${parts[i]} * mult))
        mult=$((mult * 60))
    done
    echo $((secs + days * 86400))
}

killed=0
# `ps -ax -o pid,ppid,etime,command` once, not once per candidate: this box
# runs hundreds of processes and a per-PID `ps` call in a loop would itself
# add to the load this guard exists to relieve.
while IFS= read -r line; do
    pid="$(awk '{print $1}' <<< "$line")"
    ppid="$(awk '{print $2}' <<< "$line")"
    etime="$(awk '{print $3}' <<< "$line")"
    comm="$(cut -d' ' -f4- <<< "$line")"

    [[ "$comm" == *"log show"* ]] || continue
    # Only Antigravity's language_server lane -- never touch a `log show`
    # someone is running by hand at a terminal.
    parent_comm="$(ps -p "$ppid" -o comm= 2>/dev/null || true)"
    [[ "$parent_comm" == *"language_server"* ]] || continue

    age="$(etime_to_seconds "$etime")"
    if [ "$age" -ge "$AGE_LIMIT_S" ]; then
        if kill "$pid" 2>>"$LOG"; then
            log "killed pid=$pid ppid=$ppid age=${age}s cmd=${comm:0:120}"
            killed=$((killed + 1))
        fi
    fi
done < <(ps -ax -o pid,ppid,etime,command | awk '$0 ~ /log show/ && $0 !~ /awk/')

if [ "$killed" -gt 0 ]; then
    log "guard pass complete: killed=$killed load=$(sysctl -n vm.loadavg)"
fi
