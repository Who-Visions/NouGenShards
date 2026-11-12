# nougen-supervisor

Keeps every NouGen account on a computer online. One file, no window, no
Python, nothing to install. The join setup downloads it and runs
`nougen-supervisor install`; after that the person never touches it.

Every 30 seconds it checks each account's node (`/health` on its local port)
and tunnel (cloudflared's `/ready`) and restarts whatever stopped, waiting
longer between attempts when something keeps failing (5 seconds up to 5
minutes). A second account that joins on the same computer is picked up on the
next check.

## Commands

    nougen-supervisor install     start at sign-in, and start now (replaces an older build)
    nougen-supervisor status      one line per account; exit 0 = all up, 2 = something down, 1 = not running
    nougen-supervisor status -json
    nougen-supervisor uninstall   stop watching (running nodes are left on)
    nougen-supervisor version

`-base DIR` points it at a different folder of accounts. The default is the
join setup's folder: `%LOCALAPPDATA%\NouGen` on Windows, `~/.nougen-node`
elsewhere.

## What it reads

One folder per account under the base folder. An account is described by
`node.json`:

    {"id": "...", "port": 4444, "token": "...", "tunnel": "...", "url": "https://..."}

Computers that joined before the supervisor existed have a `run.ps1` or
`run.sh` instead; those are read too, so no one has to set up again. A folder
whose download never finished (no `NouGenShards/app.py`) is ignored.

## Safety

- The status endpoint listens on `127.0.0.1:47411` only and never returns a
  token or tunnel credential.
- Stopping it over that endpoint needs a header a web page cannot send across
  origins, and the `Host` must match, so a site open in a browser cannot take
  the nodes down.
- The tunnel credential is passed in the environment, not on the command
  line, where every other program could read it.
- If another program holds an account's port, it reports `port-busy` and
  leaves that program alone.

## Build and test

    go vet ./... && go test ./...
    go build -trimpath -ldflags "-s -w -H windowsgui -X main.version=1.2.0" -o nougen-supervisor.exe .

`-H windowsgui` is what keeps a console window from flashing at sign-in. Drop
it on macOS and Linux. Releases are built by `.github/workflows/supervisor.yml`
when a `supervisor-v*` tag is pushed; the join worker pins each file's SHA-256.
