#!/bin/sh
# macOS/Linux installer for the aiwithdav3 PR reviewer poll (install.ps1 is the Windows one).
# Copies the tool to ~/.nougen/bin/pr_reviewer and, on macOS, loads a LaunchAgent that polls every 20 minutes.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dst="$HOME/.nougen/bin/pr_reviewer"
mkdir -p "$dst"
cp -f "$here"/*.ts "$here"/*.py "$here/checklist.json" "$here/poll_task.pyw" "$dst/"
py=""
for c in "$HOME/Outpost/NouGen/.venv/bin/python" "$HOME/.nougen/src/nougenshards/.venv/bin/python"; do
  [ -x "$c" ] && { py=$c; break; }
done
[ -n "$py" ] || py=$(command -v python3)
[ "$(uname -s)" = Darwin ] || { echo "copied to $dst; schedule \"$py $dst/poll_task.pyw\" every 20 min with cron"; exit 0; }
label=com.nougen.prreviewer.aiwithdav3
plist="$HOME/Library/LaunchAgents/$label.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>$py</string><string>$dst/poll_task.pyw</string></array>
  <key>WorkingDirectory</key><string>$dst</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>StartInterval</key><integer>1200</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "loaded $label -> $py $dst/poll_task.pyw"
