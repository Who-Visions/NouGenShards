# nougen-supervisor

Keeps every NouGen tenant node on a Windows computer running: no console window, no dependency on
an agent session, and nothing to install besides the one `.exe`.

## What it does
- Discovers nodes from the files the join setup writes under `%LOCALAPPDATA%\NouGen`:
  `run.ps1` (older single install) and `<handle>\run.ps1` (one folder per account). An optional
  `public.txt` next to each holds the node's `https://` address. Folders are re-read every 30 s, so a
  new account is picked up live.
- Local `/health` down: starts `uv run --python 3.11 app.py` with that node's environment.
- Local up but the public address is not 200: starts that node's `cloudflared` tunnel.
- Restarts back off exponentially (240 s node / 60 s tunnel base, 30 min cap). A hung node, or a
  tunnel that runs but does not serve for ~3 min, is killed as a process tree and started again.
- Children start with `CREATE_NO_WINDOW`. One instance at a time: it holds `127.0.0.1:4499`, which
  also serves `GET /status` (JSON: version, per-node up/down, pids, restart counts; never tokens).
- Log: `%LOCALAPPDATA%\NouGen\supervisor.log` (`log/slog` text, rotated at 2 MB).

## Build and test
```
./build.sh 1.2.0-20261111                       # needs Go
BUILD_HOST=user@host BUILD_DIR=C:/path ./build.sh 1.2.0-20261111   # build on another Windows box
```
`go vet`, `go test` (6 tests, Windows only) and a `-H=windowsgui` build.

## Install
Copy `nougen-supervisor.exe` to `%LOCALAPPDATA%\NouGen\`, set the per-user autostart value
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\NouGen-Supervisor` to its quoted path, and remove
the per-node `NouGen*` Run values the join setup created. Start it detached (not as a child of a
terminal or agent shell), for example with `nodes.ps1 restart-supervisor`.

## nodes.ps1
`status | restart <name> | restart-supervisor | log [lines]`. It starts the supervisor through WMI
so it never inherits the caller's job object.

## Known gaps
- Runs at user login, not as a Windows service.
- Recovery after a full reboot has not been verified.
- The join setup does not yet write `public.txt` or install the supervisor.
