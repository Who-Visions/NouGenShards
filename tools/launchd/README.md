# launchd bootstrap (macOS)

Copy the two `*_launch.sh` wrappers and the `*.plist.example` files, then:

1. Replace placeholders in each `.plist.example` and save it without the
   `.example` suffix into `~/Library/LaunchAgents/`:
   `__HOME__` (your home dir), `__NODE_NAME__` (this node's fleet name),
   `__NOUGEN_RELAY_DIR__` (your NouGenRelay clone).
2. The wrappers resolve every secret from the Keymaker vault at process
   start — secrets never live in a plist (plists sync and get backed up).
   Set `NOUGEN_SHARDS_REPO` if the wrapper is not run from inside the repo.
3. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist`

Other platforms: a systemd user unit or Windows Task Scheduler entry that
runs the same Python scripts with the same env vars.
