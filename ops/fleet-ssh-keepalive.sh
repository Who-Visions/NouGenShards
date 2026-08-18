#!/bin/bash
# Fleet SSH lane keepalive.
#
# Holds a live ControlMaster socket open to each fleet box so every later
# `ssh blade ...` reuses it instead of paying a full handshake — and so a lane
# that drops (sleep, Wi-Fi flap, DHCP renewal) is re-dialled without anyone
# noticing it went away.
#
# Hosts are ALIASES from ~/.ssh/config, never addresses. Both boxes are on
# DHCP; a literal here would rot at the next lease exactly like the stale
# 192.168.1.0/24 firewall rule did. Resolution stays with mDNS.
#
# Managed by launchd as com.whovisions.fleetssh — see ops/launchd/.
set -u

HOSTS="${FLEET_SSH_HOSTS:-blade phoebus}"
LOG="${FLEET_SSH_LOG:-$HOME/.ssh/fleet-lane.log}"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

mkdir -p "$HOME/.ssh/sockets"

for h in $HOSTS; do
  # -O check asks an existing master whether it is alive; cheap and side-effect
  # free. Only dial when it reports no live socket.
  if ssh -O check "$h" 2>/dev/null; then
    continue
  fi
  # BatchMode: never block on a password prompt. A lane that needs a human is a
  # lane launchd cannot hold, and silently hanging here would wedge the agent.
  if ssh -o BatchMode=yes -o ConnectTimeout=10 -MNf "$h" 2>/dev/null; then
    log "lane up: $h"
  else
    log "lane DOWN: $h (unreachable, key not installed, or sshd off)"
  fi
done

# Keep the log from growing without bound — this runs every few minutes forever.
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2000 ]; then
  tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
