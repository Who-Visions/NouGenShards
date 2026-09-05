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

## Secrets are read once, at process start

The wrappers resolve `NOUGEN_AGY_MSG_TOKEN`, `KAEDRA_GATEWAY_TOKEN` and
`NOUGEN_USER_ORIGIN_TOKEN` from the vault when the process launches, and the
receiver/watcher read them from the environment at import. A token added to
the vault **after** a daemon started is invisible to it until that daemon is
restarted (`launchctl kickstart -k gui/$(id -u)/<label>`).

This bites at exactly one moment: provisioning the owner-origin token for
the first time. Provision it, restart both daemons, then test — a signed
message that does not verify on a daemon that was already running is not a
broken scheme, it is a stale process.

Other platforms: a systemd user unit or Windows Task Scheduler entry that
runs the same Python scripts with the same env vars.
