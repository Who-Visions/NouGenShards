#!/bin/bash
# Render and load the fleet launchd agents for THIS operator.
#
# The plists must carry absolute paths -- launchd has no HOME, no PATH and no
# cwd. But an absolute path in the repo names the operator and the layout of
# their disk on a public surface, which tests/test_published_surface.py rejects
# on sight. So the repo ships templates and this renders them locally.
#
# Idempotent: re-run after moving the checkout or changing the watched hosts.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/Library/LaunchAgents"
mkdir -p "$DEST" "$HOME/.ssh/sockets"

for t in "$REPO"/ops/launchd/*.plist.template; do
  [ -e "$t" ] || continue
  name="$(basename "$t" .template)"
  sed -e "s#__REPO__#$REPO#g" -e "s#__HOME__#$HOME#g" "$t" > "$DEST/$name"
  plutil -lint "$DEST/$name" >/dev/null
  launchctl unload "$DEST/$name" 2>/dev/null || true
  launchctl load "$DEST/$name"
  echo "loaded $name"
done
