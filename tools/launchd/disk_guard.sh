#!/bin/zsh
# Phoebus low-disk guard (launchd com.nougen.diskguard, every 5 min).
# Below 8 GB free: log who is holding space, clear only caches that rebuild themselves, notify.
# Never touches user files, models, vaults, repos or agent memory.
setopt null_glob  # an empty or missing cache dir must not abort the whole cleanup
LOG=~/.nougen/logs/disk_guard.log
mkdir -p ${LOG:h}
free_gb() { df -k /System/Volumes/Data | awk 'NR==2{printf "%d", $4/1048576}'; }
F=$(free_gb)
(( F >= 8 )) && exit 0
{
  print "== $(date '+%Y-%m-%d %I:%M %p %Z') free=${F}G"
  # The space here comes and goes in bursts (2026-11-06: 600 MB -> 36 GB in an hour), so record the holders.
  du -sh /private/tmp/* /private/var/folders/*/*/T ~/.ollama ~/.gemini ~/Library/Caches 2>/dev/null | sort -rh | head -8
  lsof -nP +L1 2>/dev/null | awk 'NR>1 && $7>500000000 {print "deleted-but-open", $1, $2, $7}' | head -5
} >> $LOG
rm -rf ~/Library/Caches/Homebrew/* ~/Library/Caches/Google/* ~/Library/Caches/com.openai.codex/* \
       ~/Library/Caches/electron/* ~/Library/Caches/com.anthropic.claudefordesktop.ShipIt/* /private/tmp/claude-501/nf-stream-* 2>/dev/null
npm cache clean --force >/dev/null 2>&1
find ~/Library/Logs -type f -mtime +7 -delete 2>/dev/null
A=$(free_gb)
print "   cleared caches, free=${A}G" >> $LOG
osascript -e "display notification \"Disk was at ${F} GB free, now ${A} GB. See ~/.nougen/logs/disk_guard.log\" with title \"Phoebus low disk\"" 2>/dev/null
