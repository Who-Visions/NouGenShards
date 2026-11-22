# NouGen tester package: one mesh for ten repos

The tester package is ten repos: NouGenShards, NouGenRelay, NouGenMsg, NouGenCode,
nougendesign, NouGenTracker, NouGenOpen, nougen-fleet-mcp, NouGenClaude and
NouGenPortable. Each one runs alone. Installed side by side, any of them can call
any other's tools. A tester sees their own identity, never the fleet owner's.

## What was wrong

- Repos found each other by guessing paths (`~/The Observatory/...`,
  `C:\Users\<owner>\...`, `parents[3]`), so they only met on the owner's boxes.
- Identity was printed into code: node lists, default machine names and a
  default sender, so a tester's relay legs and messages carried the owner's names.
- Every repo kept its own copy of free-lane provider code and Keymaker discovery.
- There was no list of which tools each repo offers.

## The design

Three pieces. All are plain files, so every repo reads them the same way.

### 1. One runtime config: `mesh.json`

Lives in the runtime home (`NOUGEN_ROOT`, default `~/.nougen`). Schema:
`schemas/nougen-mesh.schema.json`. Every value resolves in this order:

1. environment (`NOUGEN_MACHINE`, `NOUGEN_AGENT`, `NOUGEN_FLEET_NODE`,
   `NOUGEN_<SERVICE>_URL`, `NOUGEN_<SERVICE>_PORT`, `NOUGEN_<REPO>_DIR`, ...),
2. `mesh.json`,
3. the files an existing fleet box already has (`fleet_hosts.json`,
   `endpoints.json`), so no box needs a migration,
4. the box itself (git config `nougen.machine` / `nougen.agent`, hostname),
5. `standalone` / none. A fresh clone only routes to itself.

`nougen-mesh setup` writes the file on first run from the tester's own box.

Other nodes are reached through the ingress: `<ingress>/<node>/<service>`,
or a node's own `endpoints` entry. With no ingress set, nothing remote is
tried, so a tester never reaches someone else's hosts by default.

Loopback ports: shards 4444, open 8765, msg 8766, open-mcp 8767, ollama 11434.

### 2. One tool list per repo: `nougen.tools.json`

At each repo root. Schema: `schemas/nougen-tools.schema.json`. A tool has a
transport:

- `mcp`: the tool the repo already serves over MCP, called in the repo's own
  interpreter. `nougen-mesh manifest <repo> <module:server>` generates these
  from the MCP server, so nothing is registered twice.
- `python`: a plain `module:function`.
- `cli`: an argv with `{arg}` slots.
- `http`: a path on the repo's service endpoint; the only kind that runs on
  another node.

### 3. Native to the `nougen` CLI

The `nougen` command from NouGenShards drives the whole package. The mesh code
is `src/nougen_shards/mesh.py` (stdlib only, Python 3.10+); each repo carries a
byte-identical copy as `nougen_mesh.py` so it works alone, and
`nougen mesh check-vendored <file>` catches drift.

```
nougen mesh install --dir ~/nougen --deps   # clone the ten repos side by side (sources: nougen.package.json)
nougen mesh setup --agent my-claude         # first run: this box's own identity into ~/.nougen/mesh.json
nougen whoami                               # machine, agent, node, wire v2 address
nougen mesh doctor                          # which repos are installed, which lack a manifest
nougen up                                   # start every declared service (or: nougen up open msg)
nougen mesh status                          # pid, url, answering?
nougen tools                                # every repo.tool on this box
nougen call open.nougen_ask prompt="hi"     # key=value args, or one JSON object
nougen call shards.recall_memory query=x --at <node>   # http tools only, through the ingress
nougen down                                 # stop what nougen up started, nothing else
```

Services are declared in each repo's `nougen.tools.json` under `services`
(argv, env with `{port}` filled from the mesh, `env_required`, health path).
A service whose required config is missing reports `needs_config` and does not
start: the Shards node will not run without the tester's own `NGS_NODE_TOKEN`.

Python callers use `mesh.call("repo.tool", {...})`. Messages use the wire v2
address from `mesh.self_address(lane)`: `lane[@node]`.

## Free lanes live in NouGenOpen

NouGenOpen holds every free lane: Hugging Face, OpenRouter, NVIDIA, Arli AI,
local Ollama, and Ollama Cloud when it is free again. Headers, keys, model lists
and run code stay there. Other repos call `open.*` tools (or Open's
OpenAI-compatible `/v1/chat/completions` on the open endpoint) instead of
carrying provider code, and Open logs each completion to NouGenTracker when it
is installed. Provider code found elsewhere, to move behind Open:

- Shards: `models_client.py`, `fleet_keys.py`, `key_usage.py`, `ollama_host.py`,
  `nvidia_nim.py`, `router.py`, `openrouter_mcp_client.py`, `tools/fleet.py`.
- Relay: `tools/relay_daemon.py` fleet_respond chain and the Ollama-only workers.
- Code: `discovery/waterflow.py`, `model_runner.py`, `fabric/engine.py`.
- Claude: `plan_exec` local tier has no executor yet; it calls Open.
- Tracker: the Ollama logging proxy is lane runtime and belongs in Open.

## Rollout, one small PR per repo

1. Shards: mesh module, schemas, this doc, Shards manifest (75 tools).
2. Open: Arli AI lane, no path guesses, MCP on its own port, usage to Tracker, manifest.
3. Msg, Relay, Tracker, Design, Code, Claude: replace printed identity with the
   mesh, add manifests.
4. fleet-mcp: reads node lists and front-door hosts from config, not code.
5. Bundle: `nougen mesh install` clones the ten repos side by side and
   `nougen mesh setup` writes the tester's own identity. The war-game,
   `python tools/tester_wargame.py --repos <dir>`, runs the package on a scratch
   home as a made-up identity: setup, whoami, doctor, tools, a read-only call
   in each repo that lists one, a remote call that must be refused with no
   ingress, and status. It fails on any owner name in the output.

## Testers download from R2, not GitHub

Testers never need access to the owner's GitHub. A fleet box packs each
repo's committed tree (no git history) into a tarball, scans every file for
leaked keys, and uploads the tarballs, a sha256 manifest and a standalone
installer to a private R2 bucket. Testers get one expiring link.

```
nougen mesh sync --repos ~/nougen            # fetch, pack each default branch, scan, upload what changed
nougen mesh share --days 7                   # prints one command for a tester, valid up to 7 days
```

The tester runs that one command; it downloads the installer, then each
tarball, checks every sha256 and unpacks the ten repos side by side.

- **Leak gate:** a repo with a secret-shaped value is refused and nothing of
  it is uploaded; the finding names the file, line, kind and a value id,
  never the value. Known fake keys in tests are listed by value id under
  `scan_allow` in `nougen.package.json`, so any new value still blocks.
- **Runtime data stays home:** per-repo `exclude` globs in
  `nougen.package.json` (Relay's handoffs, claims, acks, logs, fleet logs).
- **Settings, resolved at run time:** bucket `NOUGEN_R2_BUCKET` or
  `package.r2.bucket` in mesh.json; prefix `NOUGEN_R2_PREFIX` (default
  `packages/nougen-tester`); account `NOUGEN_R2_ACCOUNT_ID` or
  `CLOUDFLARE_ACCOUNT_ID`; keys `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`
  from the environment or Keymaker. A missing one is named exactly.
- **Schedule, no paid CI:** run the sync from a fleet box. cron:
  `*/30 * * * * cd ~/nougen/NouGenShards && .venv/bin/nougen mesh sync --repos ~/nougen >> ~/.nougen/sync.log 2>&1`;
  on a Mac, a launchd agent with `StartInterval` 1800 running the same command.
- Default branches ship, so a merge reaches testers on the next sync.

No merges, deploys or node restarts without the GM's yes.

## Before merging: settings an existing fleet box needs

Every repo now resolves identity and hosts at runtime, so a fleet box keeps
today's behaviour only once these are in its `~/.nougen/mesh.json` (or env):

- `nodes.<n>.machine` when a node's machine name differs from the node name
  (Tracker expected machines, relay routing).
- `nodes.<n>.endpoints` for each front door (`shards`, `msg`, `health`, ...),
  or the `ingress` URL; NouGenClaude reports `not_configured` without them.
- `nodes.<n>.keywords`, `coach`, `aliases` for relay keyword and coach routing.
- `relay_live.self`: extra legs the live relay daemon should not wake on
  (for example a connector's own legs).
- `models.code` / `NOUGEN_CODE_MODEL` to keep NouGenCode's local model;
  `paths.edge_ai` / `EDGE_AI_DIR` for the edge-Ai source.
- `NOUGEN_AGENT` in a lane's own MCP config where the lane name came from a plugin default.
- `NOUGEN_NODE_<N>_IP` for `cc_msg` LAN dials, `NOUGEN_MSG_URL` for the Muse connector.
- `NOUGEN_VAULT` for the vault folder (`NOUGEN_SHARDS_DIR` now means the Shards checkout).
- fleet-mcp: the new `wrangler.jsonc` vars ship with its code; check
  `wrangler secret list` for a clash with SHARD_PRIMARY_NAME, NOUGENMSG_APP_LANES
  or APP_KEY_MSG_TARGET before deploying.

Remote MCP tools (fleet-mcp's 58) are called with `"rpc": "tools/call"` over
http: set `NOUGEN_FLEET_MCP_URL` and `NOUGEN_FLEET_MCP_TOKEN`, then
`nougen call fleet-mcp.<tool> ...`.
