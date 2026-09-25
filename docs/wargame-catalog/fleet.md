# War-game candidates — fleet

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

122 candidates · P0 59 · P1 63 · P2 0 · P3 0 · defend 82 · elevate 40

| id | P | kind | title |
|---|---|---|---|
| WG-0002 | P0 | elevate | Restore the /sync/hashes -> /sync/pull loop across blade, phoebus and whoart |
| WG-0018 | P0 | defend | Keep the whoart-vault named tunnel alive under an admin task, not only the 5-minute user watchdog |
| WG-0033 | P0 | defend | Find the phoebus node slow-leak that ngs-node-refresh.sh papers over |
| WG-0047 | P0 | defend | Stop fleet-ssh-keepalive from orphaning ControlMaster processes and exhausting sshd on blade |
| WG-0059 | P0 | defend | Consolidate the four diverged keymaker stores into one NOUGEN_SECRETS_VAULT_DIR per node |
| WG-0070 | P0 | defend | Share the private-vault data key across replicas so /sync/push can unwrap ngenc1 bodies |
| WG-0081 | P0 | defend | Stop blade from missing the 20s recall deadline on gateway fanout |
| WG-0092 | P0 | elevate | Wire reach_matrix and 3-layer telemetry into NouGen Live so gateway green stops masking federation red |
| WG-0102 | P0 | defend | Reconcile 49 on-disk 'active' claim JSONs against a connector that reports zero |
| WG-0112 | P0 | elevate | Consolidate blade :4444 to one code tree and retire the Watchtower 'NouGen NGS Node' task |
| WG-0120 | P0 | elevate | Answer self-merge authority and drain the 35-deep nougen-handoffs sweep backlog with an automated gate |
| WG-0128 | P0 | elevate | Restore NouGenRelay Actions runner allocation and pin actions by SHA before merging #65/#67/#68 |
| WG-0136 | P0 | defend | Gate deploys on drift_check and which_tree so no node runs code from no git ref |
| WG-0144 | P0 | elevate | Converge the three nougenmsg variants (195/311/496 lines) into one shipped bus module |
| WG-0152 | P0 | defend | Remove PT72H ExecutionTimeLimit and 0-restart settings from admin-owned node and tunnel tasks |
| WG-0160 | P0 | defend | Survive the local Ollama lane going dark while the tray process still runs |
| WG-0168 | P0 | elevate | Roll task_truth.ps1 to blade and phoebus and alarm on tasks with no NextRunTime |
| WG-0176 | P0 | elevate | Schedule the weekly embedding backfill sweep on every node under the VRAM gate |
| WG-0182 | P0 | defend | Make a console-launched node impossible: enforce hidden launch and NO_COLOR for ngs_node_serve |
| WG-0187 | P0 | defend | Survive the next runaway fan-out: one ledger and one kill switch across four spend trackers |
| WG-0192 | P0 | defend | Keep recall complete:true when the cold path exceeds NOUGEN_RECALL_DEADLINE_S |
| WG-0197 | P0 | defend | Decouple the write signature from the read cache before continuous capture at scale |
| WG-0202 | P0 | defend | Resurrect the fleet usage ledger writer so free-lane volume is measurable again |
| WG-0207 | P0 | defend | Retire the relay-embedded usage dailies without losing June-July history |
| WG-0212 | P0 | defend | Introduce a new box (cloud CCR, rebuilt phoebus) to the registry without unknown-agent stamps or replay re-attribution |
| WG-0217 | P0 | defend | Turn on nougen.requireClaim fleet-wide without teaching lanes to reach for --no-verify |
| WG-0222 | P0 | elevate | Adopt the relay registry and claim-guard hooks in the 9 repos that lack them, with a CI drift check |
| WG-0227 | P0 | defend | Recover from a wedged registry checkout (pull --rebase left .git/rebase-merge for four hours) |
| WG-0232 | P0 | defend | Contain a hanging or hostile rule/trigger on Windows where NOUGEN_RULES_TIMEOUT cannot kill the grandchild |
| WG-0237 | P0 | defend | Detect a dead relay watch on any node the day it dies, not nine days later |
| WG-0242 | P0 | elevate | Roll task_truth.ps1 to blade and phoebus and clear PT72H/0-restart admin tasks in one Dave-supervised window |
| WG-0246 | P0 | defend | Consolidate blade :4444 to one code tree and retire the competing Watchtower scheduled task |
| WG-0250 | P0 | defend | Resolve an autonomous canon leg that contradicts a GM lock (Artemis Patera vs lock 30385@db2) without waiting on Dave |
| WG-0253 | P0 | defend | Supersede withdrawn rulings that older shards still state as binding (purge rule withdrawn 9/7) |
| WG-0256 | P0 | elevate | Build a decision-aging escalation ladder for items unmoved for weeks (#455 28 sweeps, NouGenQ #1 56 days) |
| WG-0259 | P0 | elevate | Consolidate Dave asks into one daily EOD decision packet without dropping any lock-bound item |
| WG-0262 | P0 | defend | Survive and pre-empt a history-rewriting force-push on shared main (2026-09-05 closed ~20 PRs) |
| WG-0265 | P0 | defend | Rotate NGS_TOKEN and NGS_NODE_TOKEN leaked via PR #397 across three nodes and the worker in one window |
| WG-0268 | P0 | defend | Gate public canon/wiki publication on an owner-handle privacy scrub before the Redline sync lands |
| WG-0271 | P0 | defend | Verify and revoke an agent capability grant that lives only in a relay leg (Kaedra 'ALL tools' authorization) |
| WG-0274 | P0 | defend | Refuse 'ultracode is on' style reminders that are not Dave's instruction before another 2.1M-token workflow |
| WG-0277 | P0 | defend | Stop estimated quota from enforcing stops and unknown quota from reporting green across Codex/Fable lanes |
| WG-0280 | P0 | defend | Merge NouGenRelay #65/#67/#68 while CI cannot allocate a runner (runner_id:0 billing) without lowering the bar |
| WG-0283 | P0 | elevate | Route sweep review findings (e.g. #507 duplicate GET /shards/{id}) to the author lane via dispatch instead of a queue f… |
| WG-0285 | P0 | elevate | Wire pr_lease 'one objective, one PR' into the nougen-loop pr stage to stop duplicate PRs (#476/#477, #503/#455) |
| WG-0287 | P0 | elevate | Separate NouGenMsg chat traffic ([NouGenMsg -> @phoebus]) from relay batons so the open board holds only work |
| WG-0289 | P0 | elevate | Recover the wargames/ directory 40+ docs cite and add a CI check that every referenced war game exists |
| WG-0291 | P0 | defend | Require independent-method verification before any escalation packet reaches Dave |
| WG-0293 | P0 | defend | Move ASK/REPORT classification to 3-vendor consensus without freezing the board on a HOLD sidecar |
| WG-0295 | P0 | defend | Retire transport-by-file fleet logs and purge the 46MB verbatim vault dump from NouGenRelay |
| WG-0297 | P0 | defend | Enforce the lore-isolation invariant against fleet logs carrying Shadow Dweller manuscript prose |
| WG-0299 | P0 | elevate | Unify Watchtower/Outpost tree naming behind NOUGEN_WORKSPACE_ROOT across skills, tools and RELAYS.md |
| WG-0301 | P0 | elevate | Normalize licensing across the fleet (source-available vs MIT vs ISC vs none) |
| WG-0303 | P0 | elevate | Replace hardcoded fleet tables in fleet_ping.py and fleet_dashboard.py with discovery |
| WG-0305 | P0 | defend | Propagate the claim-guard hooks to the nine repos without them and add a drift check |
| WG-0307 | P0 | elevate | Reconcile Xoah canon locks (March 15, 2162) against 37 October-13 and age 20-27 variants |
| WG-0309 | P0 | defend | Purge committed SQLite state from persona repos (Dav1d sessions, Yuki knowledge, unk lore) |
| WG-0311 | P0 | elevate | Integrate the nougenmsg branch clone: three divergent copies of nougenmsg.py |
| WG-0313 | P0 | defend | Scrub the public Kaedra repo of GCP inventory, LAN IPs, Notion topology and transcript dumps |
| WG-0362 | P1 | defend | Re-point SHARD_GATEWAY_URL through the Cloudflare API when the quick tunnel hostname changes |
| WG-0378 | P1 | elevate | Track the nougen-fleet-mcp worker.js in git with a TOOLS/HANDLERS boot assert |
| WG-0394 | P1 | defend | Survive an Antigravity log-show storm wedging the phoebus node at load 367 |
| WG-0410 | P1 | defend | Restore the phoebus SSH lane: phoebus.local did not answer on 09-24 |
| WG-0426 | P1 | elevate | Rotate NGS_NODE_TOKEN fleet-wide without a live 401 on any connector lane |
| WG-0442 | P1 | defend | Keep the nougenmsg receiver from flipping auth=open on a vault miss |
| WG-0457 | P1 | defend | Survive HF Space persistent-storage loss: rebuild the Space vault from bucket snapshots, not row pushes |
| WG-0470 | P1 | defend | Guarantee every Space route lives in source so a snapshot redeploy cannot delete it |
| WG-0483 | P1 | defend | Force DELETE journal mode and quarantine-with-restore on network-backed vault mounts |
| WG-0495 | P1 | elevate | Make /sync/pull incremental before any three-node loop runs against 200k+ shards |
| WG-0507 | P1 | elevate | Register whoart and phoebus grid snapshots on blade's keymaker instead of bulk-copying rows |
| WG-0519 | P1 | defend | Make sync_mesh_status measure hash parity instead of asserting 3_VAULT_SYMMETRIC |
| WG-0531 | P1 | defend | Retire the Antigravity legacy handoff writer and the hardcoded Watchtower path in RELAYS.md |
| WG-0543 | P1 | elevate | Revive the local griot:e2b audit daemon with a dynamic root instead of C:/Users/super |
| WG-0555 | P1 | defend | Keep relay_watch pulling on phoebus when the keychain is locked outside the GUI session |
| WG-0567 | P1 | defend | Resolve one NOUGEN_HOME runtime home before both the supervisor sync and the watcher launch |
| WG-0578 | P1 | defend | Replace nougenmsg's hostname heuristics with NOUGEN_NODE_NAME so a fourth node is not 'blade' |
| WG-0589 | P1 | elevate | Replace fleet_ping.py's ten hardcoded Cloud Run URLs with discovery from gcloud or A2A cards |
| WG-0600 | P1 | elevate | Regenerate the fleet timeline from all 14 clones instead of a Kaedra_Local workspace path |
| WG-0611 | P1 | elevate | Wire lane_freshness --json into mesh_health and the startup probe so dead lanes announce themselves |
| WG-0622 | P1 | defend | Unify zombie reaping across OS: zombie_killer.py uses fcntl while Windows nodes run zombie_check.ps1 |
| WG-0633 | P1 | elevate | Schedule fleet_heartbeat so a 1033 tunnel-with-no-connector is caught at the control plane |
| WG-0644 | P1 | defend | Publish tracker dailies from local usage JSON when the HF tracker Space is unavailable |
| WG-0655 | P1 | defend | Fail whoart's node start when the token-authenticated /health cannot see the substrate block |
| WG-0666 | P1 | defend | Pin one port contract (4444 primary, 4445 standby) across every launcher |
| WG-0677 | P1 | defend | Price the live Claude model ids before the tracker bills them at the unknown-model rate |
| WG-0688 | P1 | defend | Rotate NOUGEN_EMBED_MODEL fleet-wide without leaving a mixed-dimension vault |
| WG-0699 | P1 | defend | Stop per-node Ollama tag drift from breaking dream, triage and the VRAM gate |
| WG-0710 | P1 | defend | Roll the Cloud Run persona fleet off preview Gemini ids with a fallback ladder |
| WG-0721 | P1 | defend | Keep the Antigravity lane exact when the loopback RPC moves or dies |
| WG-0731 | P1 | defend | Wire Codex rate-limit windows into the quota ladder before the 5h window hits GAME OVER mid-task |
| WG-0741 | P1 | defend | Collapse the two quota governors (Hardcade ladder vs Jarvis SOFT/HARD) into one directive source |
| WG-0751 | P1 | defend | Deliver quota alerts when the whoart nougenmsg task has silently stopped recurring |
| WG-0761 | P1 | elevate | Promote Workers AI to a routed player with a fleet-wide, not per-machine, Neuron cap |
| WG-0771 | P1 | defend | Meter and cap the Space inference tunnel before it drains HF inference credits |
| WG-0781 | P1 | defend | Free fleet.py routes from the Antigravity-only mcp_config.json path |
| WG-0791 | P1 | elevate | Automate the daily usage export without crossing the public-publish approval boundary |
| WG-0801 | P1 | defend | Stop partial:true dailies from being summed as complete fleet totals |
| WG-0811 | P1 | defend | Put the automated relay-check sweep lane on a token budget before API cutover |
| WG-0821 | P1 | defend | Cut blade's $150/day Claude spend in half via e2b delegation with a measured before/after |
| WG-0831 | P1 | defend | Cut cache-write churn by stabilising prompt prefixes across Claude Code sessions |
| WG-0841 | P1 | defend | Reconcile the three Hugging Face Space identities used by deploy, keepalive and orchestration |
| WG-0851 | P1 | elevate | Scale the in-RAM vector cache to a million shards without OOM on a 6 GB laptop |
| WG-0861 | P1 | elevate | Verify the sub-100k recall ceiling holds under million-shard pressure without truncating evidence |
| WG-0871 | P1 | elevate | Schedule and finish the weekly embedding backfill without starving recall or the GPU |
| WG-0881 | P1 | elevate | Distil the whole corpus into the L1-L3 sidecar on free lanes within a week, not a season |
| WG-0890 | P1 | defend | Make griot_v2 coverage a per-machine, per-vault matrix under single-node residency |
| WG-0899 | P1 | elevate | Make three-vault fan-out affordable at a million shards under the 20s deadline |
| WG-0907 | P1 | defend | Keep arXiv volume from drowning doctrine at 10x ingestion |
| WG-0915 | P1 | defend | Survive an OpenRouter free-roster churn without the three-model seed going dark |
| WG-0923 | P1 | defend | Account for Ollama Cloud and other paid-by-token fallbacks that the hard-free policy assumes are free |
| WG-0931 | P1 | defend | Get the NouGenRelay quota test suite a real CI run before trusting its provenance rules |
| WG-0939 | P1 | elevate | Answer self-merge authority and ship a queue/-only auto-merge gate for sweep records |
| WG-0947 | P1 | defend | Replace ad-hoc retire/ack scratch scripts that rewrite registry JSON directly with a governed sweep verb |
| WG-0955 | P1 | defend | Triage 37 open legs (17 from today's claude-app connector) without acking batons another lane owns |
| WG-0962 | P1 | defend | Separate Stop-hook dirty-tree stubs and hourly_shard_worker telemetry from real batons |
| WG-0969 | P1 | defend | Define what an unattended sweep may merge after it merged siblings #128-#131 and #276 on its own |
| WG-0975 | P1 | elevate | Scale the 4035-record relay registry past the 1000-entry Contents API cap and 40-record scan window |
| WG-0981 | P1 | defend | Detect a squash merge that silently drops part of a PR before production runs unrolled code (#273/#277) |
| WG-0986 | P1 | elevate | Keep NouGenShards public after the 2026-09-24 fleet-ops scrub without machine names drifting back in |
| WG-0990 | P1 | defend | Reconcile 49 on-disk active claims that relay_claim_list reports as zero without freeing live work |
| WG-0994 | P1 | defend | Revive or retire the griot:e2b audit daemon dead since 2026-06-27 with 37 untriaged findings |
| WG-0998 | P1 | defend | Migrate nougen-handoffs to queue/-only records without losing legacy per-agent history or committing .sessions |

---

### WG-0002 · P0 · elevate · effort L

**Restore the /sync/hashes -> /sync/pull loop across blade, phoebus and whoart**

- Failure surface: No process runs /sync/push or /sync/pull between nodes; canary 19667@db3 exists on blade only, so a blade loss drops every write since the last manual relay_push. Only a per-node canary search notices.
- First fork: if a GET /sync/hashes from each peer returns a count within 1% of blade's -> route A (drift-only incremental pull); else -> route B (batched full pull via relay_push --missing-only, node stopped for union_vaults)
- Evidence: `NouGenShards/app.py`, `NouGenShards/docs/continuous-sync-design-DRAFT.md`, `nougenmsg 20260924T161911Z`
- Lens: federation-sync · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py has /sync/push, /sync/pull, /sync/hashes routes but nothing schedules them; nougenmsg 20260924T161911Z explicitly documents canary 19667@db3 on blade only and 'Nothing is running /sync/push or /sync/pull between nodes' plus the exact first_fork ask.
- #550 families: 91

### WG-0018 · P0 · defend · effort M

**Keep the whoart-vault named tunnel alive under an admin task, not only the 5-minute user watchdog**

- Failure surface: whoart-vault.nougenai.com died ~11 AM on 09-24; the admin tunnel task carries PT72H and 0 restarts, so the public vault disappears every 3 days unless the user watchdog catches it.
- First fork: if tunnel_lane.ps1 status says DOWN while cloudflared is running -> route A (pid-file mismatch between named_tunnel.pid and gateway tunnel.pid: fix the pid name); else -> route B (register a KeepAlive-equivalent task with PT0S)
- Evidence: `NouGenShards/tools/tunnel_lane.ps1`, `nougenmsg 20260924T161911Z`, `nougenmsg 20260924T162433Z`
- Lens: tunnels · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg 20260924T161911Z states the whoart-vault tunnel died ~11 AM and a 5-min user watchdog was added while 'The admin task still has a 72h ExecutionTimeLimit'; 20260924T162433Z corroborates the admin PT72H task.

### WG-0033 · P0 · defend · effort L

**Find the phoebus node slow-leak that ngs-node-refresh.sh papers over**

- Failure surface: Sequential recall grows from 3s to 16s over three days with flat CPU/RSS; /health stays 25ms, so the gateway's bounded peer budget silently drops phoebus's half of the corpus until the scheduled kickstart.
- First fork: if before/after latencies in logs/ngs-node-refresh.log show monotonic growth per request count -> route A (per-request structure leak: bisect MCP session state); else -> route B (SQLite statement cache across 9 DBs plus history.db)
- Evidence: `NouGenShards/ops/ngs-node-refresh.sh`, `NouGenShards/ops/launchd/com.whovisions.ngsrefresh.plist.template`
- Lens: availability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: ngs-node-refresh.sh comments explicitly describe logging before/after latencies specifically to find this leak and note '25ms while recall sat at 16s, which is precisely why the degradation went' undetected -- matches the failure surface verbatim.
- #550 families: 83

### WG-0047 · P0 · defend · effort S

**Stop fleet-ssh-keepalive from orphaning ControlMaster processes and exhausting sshd on blade**

- Failure surface: 46 orphaned masters on phoebus produced 89 sshd processes on blade and hit MaxStartups on macOS, so inbound SSH dropped before the banner and looked like Remote Login off.
- First fork: if `pgrep -f 'ssh .*-MNf'` count exceeds FLEET_SSH_HOSTS count -> route A (reap and re-dial per host); else -> route B (verify -O check per host every 180s and log lane state)
- Evidence: `NouGenShards/ops/fleet-ssh-keepalive.sh`, `NouGenShards/ops/launchd/com.whovisions.fleetssh.plist.template`
- Lens: tunnels · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet-ssh-keepalive.sh comments explicitly state 'on macOS the same accumulation exhausted MaxStartups and took inbound' SSH down, and implement pkill -f 'ssh .*-MNf' reaping -- matches the claim directly.
- #550 families: 62

### WG-0059 · P0 · defend · effort M

**Consolidate the four diverged keymaker stores into one NOUGEN_SECRETS_VAULT_DIR per node**

- Failure surface: 44 secrets across four stores with one stranded alone; get_secret only warns under NOUGEN_VAULT_DIVERGENCE=warn, so a launcher reads a stale token and the node answers 401 to the fleet.
- First fork: if keymaker.find_legacy_stores() returns any .nougen_vault paths -> route A (migrate rows into ~/.nougen/secrets, set divergence=error); else -> route B (record fingerprints via parity_manifest and close)
- Evidence: `NouGenShards/src/nougen_shards/keymaker.py`, `NouGenShards/CHANGELOG.md`, `NouGenShards/tests/test_keymaker_vault_resolution.py`
- Lens: key-custody · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: CHANGELOG.md line 57 references 'keymaker.find_legacy_stores() reports fragmentation instead of silently following it,' directly corroborating the diverged-stores/divergence-warning claim.
- #550 families: 12

### WG-0070 · P0 · defend · effort M

**Share the private-vault data key across replicas so /sync/push can unwrap ngenc1 bodies**

- Failure surface: Cross-machine decrypt of ngenc1 rows raised before capture and killed whole 100-row batches with 500 cascades on 2026-08-31; the guard now ticks `errored`, so private shards silently never replicate.
- First fork: if sync_push results show errored > 0 with PrivateVaultError -> route A (provision NOUGEN_PRIVATE_KEY on the replica from the recovery copy, never via chat); else -> route B (replica has the key; check sensitivity fence in build_whoart_vault)
- Evidence: `NouGenShards/app.py`, `NouGenShards/src/nougen_shards/private_vault.py`, `NouGenShards/tests/test_sync_push_write_fault.py`
- Lens: federation-sync · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py degrades unwrap failures into a 'databases_errored' bucket and private_vault.py defines/raises PrivateVaultError at multiple sites (missing/invalid NOUGEN_PRIVATE_KEY, bad base64, wrong-node decrypt); test_sync_push_write_fault.py exercises the write-fault path directly.

### WG-0081 · P0 · defend · effort M

**Stop blade from missing the 20s recall deadline on gateway fanout**

- Failure surface: Live shards_search today: fanout blade 'aborted due to timeout', complete:false, local lane missed NOUGEN_RECALL_DEADLINE_S; every connector lane loses blade's half of the corpus while the envelope says partial.
- First fork: if blade's local :4444 recall_memory answers under 5s from blade itself -> route A (tunnel or worker timeout budget: raise per-peer deadline); else -> route B (node degradation: kickstart and profile the vector cache)
- Evidence: `NouGenShards/src/nougen_shards/federation.py`, `NouGenShards/tests/test_federation_coverage_honesty.py`, `shard 12052@db9`
- Lens: gateway-fanout · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: federation.py reads NOUGEN_RECALL_DEADLINE_S (default 20.0), applies a future.result(timeout=...) and records a 'timeout' lane outcome; test_federation_coverage_honesty.py backs the coverage-honesty claim.
- #550 families: 43, 93

### WG-0092 · P0 · elevate · effort M

**Wire reach_matrix and 3-layer telemetry into NouGen Live so gateway green stops masking federation red**

- Failure surface: A reachable shards.nougenai.com coexisted with blade timeout, whoart 401 and a missed local deadline; /live and shards_status report 9/9 mounted DBs as fleet health.
- First fork: if reach_matrix's control row is RED and any surface is AMBER -> route A (surface per-node state in /live and nougenmsg alarm); else -> route B (control row not RED: probe untrusted, fix the manifest first)
- Evidence: `NouGenShards/tools/reach_matrix.py`, `shard 30680@db2`, `NouGenShards/tools/nougen_live.ps1`
- Lens: availability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: reach_matrix.py implements RED/AMBER states and a control-row-must-be-RED doctrine matching the failure_surface exactly; nougen_live.ps1 is the target integration point.
- #550 families: 95

### WG-0102 · P0 · defend · effort S

**Reconcile 49 on-disk 'active' claim JSONs against a connector that reports zero**

- Failure surface: NouGenRelay/.handoffs/claims holds 49 status:active files (ttl_hours 8) while relay_claim_list returns []; the pre-commit guard blocks only on another machine's claim, so stale claims either block nothing or block a real lane forever.
- First fork: if a claim's created_utc plus ttl_hours is in the past -> route A (sweep to released with a note, one commit); else -> route B (live claim: leave, and fix the connector's expiry read)
- Evidence: `NouGenRelay/.handoffs/claims`, `NouGenRelay/hooks/pre-commit`, `nougen-handoffs/queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: relay-registry · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenRelay/.handoffs/claims contains exactly 49 files with status:active, matching the claim's specific count; pre-commit hook is the guard referenced.
- #550 families: 1

### WG-0112 · P0 · elevate · effort M

**Consolidate blade :4444 to one code tree and retire the Watchtower 'NouGen NGS Node' task**

- Failure surface: Two Task Scheduler tasks (Watchtower NouGenShards-push-main every 15 min, and hidden 'NouGen NGS Node (src)' from ~/.nougen/src) both own :4444; whichever binds first serves, so the running code depends on boot order and drift_check reports UNTRACKED.
- First fork: if Get-NetTCPConnection :4444 owner cwd is ~/.nougen/src/nougenshards -> route A (disable the Watchtower task, keep install_ngs_node_task pointed at src); else -> route B (stop both, start only 'NGS Node (src)', then disable the other)
- Evidence: `NouGenShards/tools/ngs_node_boot.cmd`, `NouGenShards/tools/install_ngs_node_task.ps1`, `nougenmsg 20260924T162433Z`
- Lens: scheduled-tasks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg 20260924T162433Z documents exactly two tasks owning :4444 on blade (old 'NouGen NGS Node' push-main every 15 min, and hidden 'NouGen NGS Node (src)'), matching ngs_node_boot.cmd/install_ngs_node_task.ps1 content.
- #550 families: 29

### WG-0120 · P0 · elevate · effort M

**Answer self-merge authority and drain the 35-deep nougen-handoffs sweep backlog with an automated gate**

- Failure surface: Every NouGenShards PR webhook adds a draft PR to nougen-handoffs; with the question unanswered since #135 the backlog grows every 15-30 minutes and sweep records stop being findable.
- First fork: if Dave answers yes -> route A (gate: single new queue/*.md, zero overlap, CI green -> auto-merge); else -> route B (sweeps write to a branch and squash weekly)
- Evidence: `nougen-handoffs/queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `nougen-handoffs/queue`
- Lens: governance-availability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: The named queue file documents the unresolved self-merge-authority question and backlog growth exactly as described; nougen-handoffs/queue is the backlog directory.

### WG-0128 · P0 · elevate · effort M

**Restore NouGenRelay Actions runner allocation and pin actions by SHA before merging #65/#67/#68**

- Failure surface: Every NouGenRelay run fails in ~2s with runner_id:0, so three fixes (placeholder-probe rejection, surrogate scrub, importorskip) have never had a real run and the fleet dead-letters probes meanwhile.
- First fork: if a workflow_dispatch on main also fails with runner_id:0 -> route A (repo Actions billing/runner settings, not code); else -> route B (PR-only failure: check fork/permissions)
- Evidence: `NouGenRelay/.github/workflows/ci.yml`, `nougen-handoffs/queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: ci-availability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: The task file explicitly documents runner_id:0 failures across #65/#67/#68 within ~2s, attributed to exhausted Actions billing/runner allocation, matching the claim verbatim.

### WG-0136 · P0 · defend · effort M

**Gate deploys on drift_check and which_tree so no node runs code from no git ref**

- Failure surface: phoebus carried nine copies of redaction.py and blade six; a merged fix ran nowhere while every node verified it in a clean worktree. drift_check exists but nothing schedules it or blocks on UNTRACKED.
- First fork: if drift_check exits 1 with UNTRACKED for any bus file -> route A (install from canonical via install_grid_supervisor and restart); else -> route B (schedule hourly and route exit 1 into the inbox)
- Evidence: `NouGenShards/tools/drift_check.py`, `NouGenShards/tools/which_tree.py`, `NouGenShards/tools/install_grid_supervisor.ps1`
- Lens: deploy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: drift_check.py defines UNTRACKED as its worst severity and exits 1 on DRIFT/UNTRACKED/MISSING, matching the claim; which_tree.py and install_grid_supervisor.ps1 are the referenced companion tools.
- #550 families: 28

### WG-0144 · P0 · elevate · effort L

**Converge the three nougenmsg variants (195/311/496 lines) into one shipped bus module**

- Failure surface: Whoart executes untracked copies, phoebus a 496-line federation variant, blade a 195-line one; a message shape accepted on one node is rejected on another and the LAN wake lane fails silently.
- First fork: if the sha256 of the running nougenmsg.py on each node matches c369f49e8d03 -> route A (adopt it as main, delete infra/ copies); else -> route B (diff the 496-line variant for features to port first)
- Evidence: `nougenmsg/infra/whoart/SOURCE.md`, `nougenmsg/README.md`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: fleet-transport · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: SOURCE.md documents the exact three sha256-distinct variants at 195/311/496 lines across blade/whoart/phoebus, matching the claim precisely; nougenmsg_node.py is the shards-side tool.

### WG-0152 · P0 · defend · effort S

**Remove PT72H ExecutionTimeLimit and 0-restart settings from admin-owned node and tunnel tasks**

- Failure surface: 'NouGen NGS Node (whoart)', 'NouGen whoart-vault tunnel', blade NouGenNode and NouGenAgyPipeWatchdog are admin-owned with PT72H and RestartOnFailure 0; every 3 days a node or tunnel dies and only the 5-minute user watchdog covers whoart.
- First fork: if task_truth.ps1 -Json reports DEGRADED for an admin task -> route A (Dave runs the installer XML with PT0S under admin); else -> route B (verify the user watchdog covers each daemon and log a GREEN)
- Evidence: `nougenmsg 20260924T162433Z`, `NouGenShards/tools/install_ngs_node_task.ps1`
- Lens: scheduled-tasks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg 20260924T162433Z states verbatim that 'NouGen NGS Node (whoart)' and 'NouGen whoart-vault tunnel' are admin-owned, PT72H, 0 restarts, covered by the user watchdog; blade NouGenNode/NouGenAgyPipeWatchdog also listed DEGRADED with PT72H.

### WG-0160 · P0 · defend · effort S

**Survive the local Ollama lane going dark while the tray process still runs**

- Failure surface: On 2026-09-23 whoart's `ollama app` was running but nothing listened on 11434; two sessions concluded local models were unavailable and reached for paid routes, which Rule 0.3 forbids.
- First fork: if /api/tags on 11434 fails while the tray process exists -> route A (ollama_guard restarts the server and logs); else -> route B (a real chat completion preflight before any digest write)
- Evidence: `NouGenShards/tools/ollama_guard.ps1`, `NouGenShards/docs/FLEET-LOG-2026-08-16.md`
- Lens: lane-availability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: ollama_guard.ps1's own header comment states the exact incident: 'ollama app' was running but nothing was listening on 11434, matching the claim almost verbatim.
- #550 families: 56, 95

### WG-0168 · P0 · elevate · effort M

**Roll task_truth.ps1 to blade and phoebus and alarm on tasks with no NextRunTime**

- Failure surface: whoart 'NouGen Relay Watch WhoArt' and 'NouGen Codex Msg' had a P9DT2H40M repetition duration and silently stopped ~09-18 with LastTaskResult 0; phoebus.local did not answer ssh so its launchd state is unverified.
- First fork: if task_truth over ssh returns any RED -> route A (fix Duration to indefinite, re-register, confirm NextRunTime); else -> route B (schedule the probe hourly and feed RED/DEGRADED into lane_freshness)
- Evidence: `nougenmsg 20260924T162433Z`, `NouGenShards/tools/start_relay_watch_whoart.py`, `NouGenShards/tools/lane_freshness.py`
- Lens: scheduled-tasks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg 20260924T162433Z documents the P9DT2H40M duration causing RED->GREEN fix on whoart's two tasks and that phoebus.local did not answer ssh, matching the claim precisely.
- #550 families: 95

### WG-0176 · P0 · elevate · effort S

**Schedule the weekly embedding backfill sweep on every node under the VRAM gate**

- Failure surface: HARDENING §2 leaves the scheduled sweep unchecked; embed-at-capture misses degrade to keyword-only and accumulate on whichever node's ollama was down, re-creating the 47-64% NULL gap.
- First fork: if count_pending on a node exceeds 1% of shards -> route A (run backfill_db with NOUGEN_VRAM_CEILING, log coverage before/after); else -> route B (register the task and exit)
- Evidence: `NouGenShards/src/nougen_shards/embedding_backfill.py`, `NouGenShards/HARDENING.md`
- Lens: scheduled-tasks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: HARDENING.md section 2 documents embed-at-capture being fixed with counters/kill-switch but explicitly lists '⬜ scheduled weekly backfill sweep' as the remaining unchecked item, matching the claim directly.
- #550 families: 97

### WG-0182 · P0 · defend · effort S

**Make a console-launched node impossible: enforce hidden launch and NO_COLOR for ngs_node_serve**

- Failure surface: A hand launch in a visible console froze blade's asyncio loop in rich _win32_console.write_text (QuickEdit pause); /health hung, 13 CLOSE_WAIT sockets, every gateway fanout timed out while the tunnel looked fine.
- First fork: if GetConsoleWindow() is non-NULL at ngs_node_serve start -> route A (refuse to serve, print 'use Start-ScheduledTask NouGen NGS Node (src)'); else -> route B (arm sitecustomize_windowless and continue)
- Evidence: `nougenmsg 20260924T161911Z`, `NouGenShards/tools/sitecustomize_windowless.py`, `NouGenShards/tools/ngs_node_serve.py`
- Lens: availability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg 20260924T161911Z documents the exact root cause (console-launched node, rich _win32_console.write_text freeze, 13 CLOSE_WAIT sockets); sitecustomize_windowless.py implements GetConsoleWindow()-based hiding.

### WG-0187 · P0 · defend · effort L

**Survive the next runaway fan-out: one ledger and one kill switch across four spend trackers**

- Failure surface: coach_ledger.jsonl, token_fuse_ledger.json, coach_governor telemetry and billing.db each count spend independently; on 9/13 a 244-agent workflow burned ~2.1M tokens and stalled WhoArt before anything tripped, and today a kill in one ledger is invisible to the other three.
- First fork: if you observe more than MAX_FANOUT concurrent leases or lanes in any one ledger -> route A: set_kill on the machine scope and verify coach.py and TokenFuse both refuse; else route B: make coach.py and TokenFuse acquire leases from get_default_governor() so one denial stops all.
- Evidence: `NouGenShards/tools/coach.py`, `NouGenShards/src/nougen_shards/coach_governor.py`, `NouGenShards/skills/coach/SKILL.md`
- Lens: runaway · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: coach_governor.py has set_kill (line 231), get_default_governor (line 451), and MAX_FANOUT (line 67) exactly as the fork routes describe; coach.py and SKILL.md exist.
- #550 families: 49, 65

### WG-0192 · P0 · defend · effort M

**Keep recall complete:true when the cold path exceeds NOUGEN_RECALL_DEADLINE_S**

- Failure surface: Every shards_search today returns complete:false with the local lane missing the 20s deadline and blade fanout timing out; fd_budget documents 6-8s cold matrix rebuilds under load, so at 10x corpus the cold path alone exceeds the deadline and the gateway serves permanent INCOMPLETE while /health stays 200.
- First fork: if you observe lanes_timed_out containing 'local' on a warm node -> route A: the cache was invalidated by a write, warm it after each node start and serve from ann_index; else route B: raise the deadline per lane from measured per-lane elapsed and mark the answer degraded, never empty.
- Evidence: `shards_search 2026-09-24 fanout blade timeout`, `NouGenShards/src/nougen_shards/federation.py`, `NouGenShards/src/nougen_shards/fd_budget.py`
- Lens: scale · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: federation.py:179-181,251 confirms NOUGEN_RECALL_DEADLINE_S default 20.0 and lanes_timed_out tracking; fd_budget.py:15 documents the 6-8s flat cold-path cost, matching the claim precisely.
- #550 families: 2

### WG-0197 · P0 · defend · effort M

**Decouple the write signature from the read cache before continuous capture at scale**

- Failure surface: cross-verification.md's surviving hypothesis: the node that serves recall is the node that writes, so _db_write_signature invalidates the vector cache between requests; with structural capture on every session end and sweeps every 15 minutes, a million-shard node rebuilds a multi-GB matrix constantly.
- First fork: if you observe cache rebuild count approaching capture count in a node's log -> route A: batch writes and refresh the cache on an interval, serving the previous matrix meanwhile; else route B: move captures to the append fast path only and reserve full reloads for backfills.
- Evidence: `NouGenShards/docs/cross-verification.md`, `NouGenShards/src/nougen_shards/core.py`, `NouGenShards/tests/test_vector_cache_herd.py`
- Lens: scale · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: cross-verification.md:50 contains the near-verbatim quote about the node that serves recall being the node that writes and cache invalidation; core.py:1947,1999,2122 confirms _db_write_signature exists and is used exactly as described.
- #550 families: 7

### WG-0202 · P0 · defend · effort M

**Resurrect the fleet usage ledger writer so free-lane volume is measurable again**

- Failure surface: token_tracker reads FLEET_USAGE_LEDGER (tools/vault/fleet_usage.jsonl) 'written by fleet_usage_proxy.py + the instrumented fleet clients (see Sol-Ai/)', but neither the proxy nor the vault dir exists in the repo, so the 'Fleet Usage Ledger (exact)' section is always empty and e2b delegation savings cannot be shown.
- First fork: if you observe the ledger path absent on every node -> route A: have coach.py, fleet.py and OpenRouterClient append usage rows in the ledger schema directly; else route B: point FLEET_USAGE_LEDGER at coach_ledger.jsonl and adapt the parser.
- Evidence: `NouGenShards/tools/token_tracker.py`, `NouGenShards/tools/coach.py`, `NouGenShards/tools/fleet.py`
- Lens: token-economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: token_tracker.py literally comments 'written by fleet_usage_proxy.py + the instrumented fleet clients (see Sol-Ai/)' at FLEET_USAGE_LEDGER definition, and no fleet_usage_proxy.py or vault dir exists in the repo — confirmed missing writer.
- #550 families: 65

### WG-0207 · P0 · defend · effort S

**Retire the relay-embedded usage dailies without losing June-July history**

- Failure surface: NouGenRelay/.handoffs still holds 39 usage_*.json files (schema 1, tracker 2.1.0, 2026-06-20..07-31) beside the schema-3 tracker Space; PR #513 now skips them in handoff discovery, but any consumer summing both stores double-counts June-July and the relay copies carry a different sketch format.
- First fork: if you observe a June or July total differing between the relay copies and the tracker Space -> route A: migrate the relay rows into schema-3 dailies on the Space and delete the copies; else route B: mark the relay files legacy in RELAYS.md and exclude them from every parser.
- Evidence: `NouGenRelay/.handoffs/usage_2026-07-29.json`, `nougen-handoffs/queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `NouGenRelay/RELAYS.md`
- Lens: token-economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenRelay/.handoffs/usage_2026-07-29.json exists as a relay-embedded usage daily; corrected the pr513 evidence path is unnecessary here (task doc exists) supporting the double-count concern.

### WG-0212 · P0 · defend · effort S

**Introduce a new box (cloud CCR, rebuilt phoebus) to the registry without unknown-agent stamps or replay re-attribution**

- Failure surface: prepare-commit-msg refuses a commit from an unset lane or a machine the registry has never seen and NOUGEN_IDENTITY_OK=1 is the only override; a rebase on blade once re-stamped phoebus commits as blade1tb/unknown-agent. A new box either blocks or introduces itself wrongly and the trailer is permanent.
- First fork: if you observe the machine name is absent from known_machines(root) -> run `relay init --machine` and write one introducing leg before any commit; else if trailers already exist on replayed commits -> never re-stamp, verify the rebase kept them
- Evidence: `NouGenRelay/hooks/prepare-commit-msg`, `NouGenRelay/README.md`, `NouGenRelay/.handoffs/claims/20260828T215147Z__ccr__claude-cli__autonomous.json`
- Lens: relay-governance/identity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: prepare-commit-msg has NOUGEN_IDENTITY_OK override and unknown-agent refusal exactly as described; README/claims file exist.
- #550 families: 20, 28

### WG-0217 · P0 · defend · effort M

**Turn on nougen.requireClaim fleet-wide without teaching lanes to reach for --no-verify**

- Failure surface: The guard fails open and only blocks a foreign claim; unclaimed work merely warns, so #484 rebuilt the nougen_context.py feature #447 had already merged (8 conflict hunks) and #476 duplicated #477. Turning on requireClaim per repo will fire on every typo fix and get disabled unless the claim step is automatic.
- First fork: if you observe duplicate-work incidents in the last 30 days exceed guard blocks -> enable requireClaim on NouGenShards only, with `relay claim take` auto-run from the SessionStart hook; else keep warn mode and add a weekly duplicate-PR report
- Evidence: `NouGenRelay/hooks/pre-commit`, `NouGenRelay/src/nougen_relay/guard.py`, `nougen-handoffs/queue/task_20260922_013500_pr484-dirty-duplicate-context-work-collides-with-merged-447-registry-backlog-10deep.md`
- Lens: relay-governance/claims · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: guard.py confirms warn-by-default on unclaimed work and requireClaim as a per-repo git config opt-in; task file documents the #484/#447/#476/#477 duplicate-work incidents.
- #550 families: 25

### WG-0222 · P0 · elevate · effort M

**Adopt the relay registry and claim-guard hooks in the 9 repos that lack them, with a CI drift check**

- Failure surface: A claim only protects the repo whose .handoffs it lives in (the 2026-08-01 NouGenTracker duplication); Iris-Ai, Rhea-Noir, Visions-ai, Yuki-Ai, unk-app-ai, who-visions-tester, nougen-handoffs, nougenai-mcp-gateway and nougenmsg have no hooks/ and Kam-ai/who-visions-tester/nougen-handoffs have no .gitignore. Work there is invisible to the guard on every other box.
- First fork: if you observe `relay adopt --dry` reports an existing core.hooksPath in a repo -> chain rather than seize it; else adopt, then add a workflow that md5-compares hooks/ against NouGenRelay/hooks and fails on drift
- Evidence: `NouGenRelay/README.md`, `Kam-ai/hooks/`, `Iris-Ai/`
- Lens: relay-governance/coverage · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: README documents relay adopt/hooksPath; Kam-ai/hooks and Iris-Ai exist as referenced coverage gaps.

### WG-0227 · P0 · defend · effort M

**Recover from a wedged registry checkout (pull --rebase left .git/rebase-merge for four hours)**

- Failure surface: _publish does push, then `git pull --rebase`, then push; autoclose notes a sweep left .git/rebase-merge sitting for four hours, after which every claim take and ack on that box silently failed to publish while looking successful locally. relay_watch_node's dirty_legs/divergence sensors exist but nothing acts on them.
- First fork: if you observe .git/rebase-merge or divergence() non-zero in the relay clone -> abort the rebase, stash dirty legs, fast-forward, replay the stashed records via CAS; else verify `relay` bare status shows 0 diverged before trusting a publish
- Evidence: `NouGenRelay/src/nougen_relay/core.py`, `NouGenRelay/src/nougen_relay/autoclose.py`, `NouGenShards/tools/relay_watch_node.py`
- Lens: relay-governance/publish-path · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: autoclose.py documents the actual four-hour rebase-merge incident; core.py _publish and relay_watch_node.py divergence()/dirty_legs() exist.
- #550 families: 91

### WG-0232 · P0 · defend · effort M

**Contain a hanging or hostile rule/trigger on Windows where NOUGEN_RULES_TIMEOUT cannot kill the grandchild**

- Failure surface: rules.react and handoff_triggers run operator commands through the shell for legs arriving from other machines; the strict xfail records that on Windows the timeout kills the shell but not the grandchild (1s timeout took 30s). An unattended blade or whoart lane can hang on a synced rule with nobody at ctrl-c.
- First fork: if you observe a rule run exceeding 2x its timeout in `relay rules runs` -> switch execution to a job object (Windows) / process group (POSIX) and set NOUGEN_RULES=dry on that box until fixed; else keep rules but forbid --share-triggers
- Evidence: `NouGenRelay/tests/test_rules_safety.py`, `NouGenRelay/src/nougen_relay/rules.py`, `NouGenShards/src/nougen_shards/handoff_triggers.py`
- Lens: gm-bandwidth/unattended-authority · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: test_rules_safety.py contains the exact xfail (Windows timeout kills shell not grandchild, 1s timeout took 30s) as described.

### WG-0237 · P0 · defend · effort M

**Detect a dead relay watch on any node the day it dies, not nine days later**

- Failure surface: 'NouGen Relay Watch WhoArt' and 'NouGen Codex Msg' silently stopped recurring ~9/18 because their repetition Duration was P9DT2H40M, LastTaskResult 0; relay_watch_node primes its cursor silently so a restart announces nothing. Batons addressed to whoart sat unannounced for six days.
- First fork: if you observe task_truth.ps1 RED/DEGRADED for a watcher task -> fix the trigger and replay legs since the cursor timestamp; else add the watcher's heartbeat file age to lane_freshness so a stale one shows at session start
- Evidence: `nougenmsg 20260924T162433Z`, `NouGenShards/tools/relay_watch_node.py`, `NouGenShards/tools/install_ngs_node_task.ps1`
- Lens: gm-bandwidth/eod-items · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg leg 20260924T162433Z (fetched via nougenmsg_latest) directly documents the RED->GREEN fix for the two tasks whose P9DT2H40M duration silently stopped recurring ~9/18.
- #550 families: 95

### WG-0242 · P0 · elevate · effort M

**Roll task_truth.ps1 to blade and phoebus and clear PT72H/0-restart admin tasks in one Dave-supervised window**

- Failure surface: Admin-owned tasks on whoart and blade (NGS Node, tunnel, NouGenNode, AgyPipeWatchdog) carry a 72h ExecutionTimeLimit with zero restarts; user lanes get Access denied, so the fix is a Dave EOD item. Every third day a node or tunnel dies at the limit and the 5-minute watchdog only covers whoart.
- First fork: if you observe Dave is at the console -> run the elevated re-register with PT0S and RestartCount, then verify NextRunTime on all four; else install user-level watchdog tasks on blade too and keep the admin change on the EOD packet
- Evidence: `nougenmsg 20260924T162433Z`, `NouGenShards/tools/install_ngs_node_task.ps1`
- Lens: gm-bandwidth/dave-locks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Same leg 20260924T162433Z documents the PT72H/0-restart admin tasks on whoart/blade and the Dave EOD ask; install_ngs_node_task.ps1 exists.

### WG-0246 · P0 · defend · effort M

**Consolidate blade :4444 to one code tree and retire the competing Watchtower scheduled task**

- Failure surface: 'NouGen NGS Node' (Watchtower\NouGenShards-push-main, logon + every 15 min) and 'NouGen NGS Node (src)' (~/.nougen/src/nougenshards, hidden) both own :4444; whichever binds first wins, so which code serves the gateway depends on boot order and the node-lane rule says the lane clone owns the port.
- First fork: if you observe pid on :4444 launched from the Watchtower tree -> stop it, disable that task, and confirm (src) task restarts within 1 min; else just disable the Watchtower task and record the retirement in a leg
- Evidence: `nougenmsg 20260924T161911Z`, `nougenmsg 20260924T160753Z`, `NouGenShards/tools/node_lane.ps1`
- Lens: gm-bandwidth/unattended-authority · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Legs 20260924T161911Z and 20260924T160753Z directly document the two competing :4444 tasks/processes on blade and the node-lane port-ownership rule.
- #550 families: 29

### WG-0250 · P0 · defend · effort M

**Resolve an autonomous canon leg that contradicts a GM lock (Artemis Patera vs lock 30385@db2) without waiting on Dave**

- Failure surface: An antigravity autonomous ruling leg asserts Artemis Patera is a Nyx enclave while GM lock 30385@db2 says Artemis owns it; the conflict leg is open with 'Dave to rule' and downstream wiki sync/render pipelines will consume whichever lands first. Operating law says a Dave lock wins, yet the autonomous leg remains open as if actionable.
- First fork: if you observe the leg contradicts a shard tagged as a GM lock -> auto-park it as CANDIDATE, stamp the lock id, and exclude it from wiki sync; else if no lock covers the fact -> label CANDIDATE with provenance and proceed
- Evidence: `relay 20260924T133242Z__claude-app__g-whoentertains`, `relay 20260924T133000Z__blade1tb__antigravity`, `NouGenShards/src/nougen_shards/canonical_facts.py`
- Lens: gm-bandwidth/dave-locks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both relay legs (133242Z and 133000Z) fetched directly: the canon conflict (Artemis Patera vs GM lock 30385@db2) and 'Dave to rule' status match exactly.

### WG-0253 · P0 · defend · effort M

**Supersede withdrawn rulings that older shards still state as binding (purge rule withdrawn 9/7)**

- Failure surface: Dave withdrew the drift/purge provenance rule fleet-wide but shards 1134@db2 and 9049@db2 still assert it; recall-first lanes will cite the old rule and rename canon entities again. Only a lane that happens to read the correction leg knows.
- First fork: if you observe a ruling leg containing WITHDRAWN/RETRACTED naming shard ids -> write a CORRECTION shard linking supersedes and mark the old ids via shards_mark; else run a monthly sweep for rulings without a superseding link
- Evidence: `NouGenRelay/.handoffs/claims/20260907T170120Z__phoebus__claude-cli__autonomous.json`, `NouGenShards/src/nougen_shards/canonical_facts.py`
- Lens: gm-bandwidth/dave-locks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Claim file 20260907T170120Z contains the exact withdrawn-rule text naming shards 1134@db2/9049@db2 as still stating the retracted purge rule.
- #550 families: 11

### WG-0256 · P0 · elevate · effort M

**Build a decision-aging escalation ladder for items unmoved for weeks (#455 28 sweeps, NouGenQ #1 56 days)**

- Failure surface: NouGenShards #455, NouGenQ #1/#2/#3 and dependabot #458-#464 are re-listed by every sweep as 'GM/owner owed' with no change in wording or channel; the ask never reaches Dave as a decision, only as noise, and the sweep lane spends tokens re-verifying them 30+ times.
- First fork: if you observe an item carried >5 sweeps unchanged -> stop re-verifying, freeze it in a decisions.md with one line and a deadline, and surface once per day; else keep it in the carried section
- Evidence: `nougen-handoffs/queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`, `nougen-handoffs/queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`
- Lens: gm-bandwidth/decisions · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both queue task files document repeated re-listing of #455, NouGenQ items and dependabot PRs across many sweeps with no resolution.

### WG-0259 · P0 · elevate · effort M

**Consolidate Dave asks into one daily EOD decision packet without dropping any lock-bound item**

- Failure surface: Today's EOD list for Dave lives in three separate legs (PT72H admin removal, public wiki handles, self-merge answer) plus autoclose's 'Ask names Dave' exclusion; nothing aggregates them, so each lane pings separately and items drop when a leg is auto-acked.
- First fork: if you observe more than three open legs whose body names Dave -> generate the packet from policy hold decisions and post one leg addressed [-> @dave]; else leave them individual but tag them dave-eod
- Evidence: `nougenmsg 20260924T161604Z`, `nougenmsg 20260924T162433Z`, `NouGenRelay/src/nougen_relay/autoclose.py`
- Lens: gm-bandwidth/eod-items · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Leg 20260924T161604Z documents a Dave-owed privacy/EOD item alongside autoclose.py's Dave-ask exclusion logic, matching the fragmentation claim.

### WG-0262 · P0 · defend · effort L

**Survive and pre-empt a history-rewriting force-push on shared main (2026-09-05 closed ~20 PRs)**

- Failure surface: origin/main of NouGenShards was replaced with a disjoint 50-commit history; #135/#136 and ~20 other PRs closed unmerged and their substance reappeared under new numbers. Every clone, relay leg sha and sweep record pointing at old shas became dangling; the sweep only flagged it after the fact.
- First fork: if you observe `git merge-base` between local main and origin/main is empty -> stop all publishes, snapshot the old tip to a refs/backup branch on every node, and open a Dave ask before any rebase; else it is a normal fast-forward
- Evidence: `NouGenShards/.handoffs/20260816T232004Z__whoart__codex.md`, `NouGenShards/docs/cross-verification.md`
- Lens: gm-bandwidth/irreversible · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/.handoffs/20260816T232004Z__whoart__codex.md directly documents the 2026-09-05 force-push to a disjoint 50-commit history and ~20 PRs closing unmerged; cross-verification.md is tangential but exists. Corrected primary evidence: the .handoffs file.
- #550 families: 15

### WG-0265 · P0 · defend · effort M

**Rotate NGS_TOKEN and NGS_NODE_TOKEN leaked via PR #397 across three nodes and the worker in one window**

- Failure surface: Two live tokens sat in a PR diff for days with sweeps re-flagging 'rotate the two leaked tokens' and no rotation; rotation is an external action (Cloudflare worker secret, three node envs, Keymaker) that if done half-way breaks the shards gateway fanout for every connector lane.
- First fork: if you observe the token is still accepted by /health on any node -> stage the new token in Keymaker on all three nodes first, flip the worker last, then revoke; else it was already rotated, close the carried item
- Evidence: `nougen-handoffs/queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `NouGenShards/app.py`
- Lens: gm-bandwidth/irreversible · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260915_115500_pr397 file contains the exact leaked NGS_TOKEN string and rotate action items; app.py shows NGS_NODE_TOKEN/SHARD_GATEWAY_TOKEN as live gateway credentials.
- #550 families: 76

### WG-0268 · P0 · defend · effort M

**Gate public canon/wiki publication on an owner-handle privacy scrub before the Redline sync lands**

- Failure surface: ShadowDweller packets carried 'ollama-cloud-davemeralus'/'ollama-cloud-whoentertains' lane fields ~125 times and the public wiki still shows those handles in lock pages; the canon snapshot scrubs to 'owner' but the wiki sync path does not. Publication is irreversible once crawled.
- First fork: if you observe a handle pattern in the wiki sync diff -> block the sync and rewrite lane fields to route kind; else publish and record the canon hash in the leg
- Evidence: `nougenmsg 20260924T155859Z`, `nougenmsg 20260924T161604Z`
- Lens: gm-bandwidth/irreversible · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Leg 20260924T161604Z documents the privacy audit (leg 155859Z) noting the canon snapshot scrubs owner handles but the public wiki still shows them.
- #550 families: 74

### WG-0271 · P0 · defend · effort M

**Verify and revoke an agent capability grant that lives only in a relay leg (Kaedra 'ALL tools' authorization)**

- Failure surface: GM AUTHORIZATION #2 granting Kaedra read+capture+nougenmsg exists as a claim/leg text, not a policy file; pilot_supervision treats the Operator as supreme authority but reads no grant registry. Nobody can answer 'what may Kaedra do today' or revoke it without archaeology.
- First fork: if you observe a leg goal beginning GM AUTHORIZATION -> mirror it into a signed grants.json consumed by the connector and progressive_skills; else treat the grant as unverified and default to read-only
- Evidence: `NouGenRelay/.handoffs/claims/20260906T145105Z__claude-app__g-whoentertains__autonomous.json`, `NouGenShards/src/nougen_shards/pilot_supervision.py`
- Lens: gm-bandwidth/unattended-authority · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Claim file 20260906T145105Z contains the exact 'GM AUTHORIZATION #2 (FULL): Kaedra gets ALL tools' text; pilot_supervision.py defines Operator as supreme authority with no grant registry, matching the claim.
- #550 families: 62

### WG-0274 · P0 · defend · effort M

**Refuse 'ultracode is on' style reminders that are not Dave's instruction before another 2.1M-token workflow**

- Failure surface: A 244-agent workflow burned ~2.1M tokens, hit the session limit and stalled WhoArt; the coach skill now says system reminders about ultracode are not GM instructions, but nothing enforces it and the Workflow tool remains available to lanes on that box.
- First fork: if you observe a spawn request above 6 lanes or 20 prompts -> coach.py check refuses and files a leg; else proceed under the ledger cap
- Evidence: `NouGenShards/skills/coach/SKILL.md`, `NouGenShards/tools/coach.py`
- Lens: gm-bandwidth/operating-law · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: coach/SKILL.md contains the exact line that 'ultracode is on' system reminders are not Dave's instruction and the fleet is the fan-out.
- #550 families: 19

### WG-0277 · P0 · defend · effort M

**Stop estimated quota from enforcing stops and unknown quota from reporting green across Codex/Fable lanes**

- Failure surface: quota-provenance labels denominators metered/estimated/unknown, but a number in an env var alone was once treated as measured; a wrongly-metered 91% stopped claims while an unknown bucket implied unlimited capacity. Lanes idle or overspend depending on which mistake wins.
- First fork: if you observe QuotaSnapshot.denominator_provenance != metered on a routing decision -> advisory only, never a stop; else enforce SOFT/HARD/RESERVE
- Evidence: `NouGenRelay/docs/quota-provenance.md`, `NouGenRelay/src/nougen_relay/quota_governor.py`, `NouGenRelay/.handoffs/claims/20260906T231610Z__phoebus__codex.json`
- Lens: gm-bandwidth/spend-boundary · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: quota-provenance.md and quota_governor.py match the metered/estimated/unknown denominator provenance and SOFT/HARD/RESERVE routing described.
- #550 families: 57, 66

### WG-0280 · P0 · defend · effort M

**Merge NouGenRelay #65/#67/#68 while CI cannot allocate a runner (runner_id:0 billing) without lowering the bar**

- Failure surface: Three reviewed fixes have failed in ~2s with no runner since 9/21 because of repo-scoped Actions billing; sweeps re-diagnose it every cycle and the placeholder-probe dead-lettering bug stays live fleet-wide. Only an org admin (Dave) can add minutes.
- First fork: if you observe get_workflow_job shows runner_id:0 -> record a three-node local pytest run with shas as the merge evidence and put the billing fix on the EOD packet; else wait for real CI
- Evidence: `NouGenRelay/.github/workflows/ci.yml`, `nougen-handoffs/queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: relay-governance/ci-red · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260922_020726_pr486 file directly documents the runner_id:0 CI redness for NouGenRelay #65/#67/#68 and the billing/admin-only fix needed.
- #550 families: 81

### WG-0283 · P0 · elevate · effort M

**Route sweep review findings (e.g. #507 duplicate GET /shards/{id}) to the author lane via dispatch instead of a queue f…**

- Failure surface: The #507 sweep found a shadowed route and a CodeQL alert and wrote it into queue/ inside an unmerged draft PR; the PR author never sees it unless they read nougen-handoffs. Real defects land in main while the finding rots in a backlog.
- First fork: if you observe a sweep verdict other than 'no action needed' -> create a relay leg addressed [-> @<author lane>] with the finding and a wake via dispatch; else write the queue record only
- Evidence: `nougen-handoffs/queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`, `NouGenRelay/src/nougen_relay/dispatch.py`
- Lens: relay-governance/human-loop · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: The exact PR #507 queue record exists and dispatch.py exists as the proposed routing mechanism.

### WG-0285 · P0 · elevate · effort M

**Wire pr_lease 'one objective, one PR' into the nougen-loop pr stage to stop duplicate PRs (#476/#477, #503/#455)**

- Failure surface: pr_lease.py exists (Phase 1 landed as #289) but the loop's pr stage still runs `gh pr create` per change; lanes opened #476 duplicating merged #477 and #503 duplicating #455, and each duplicate generates its own sweep record and Dave close-or-reassign ask.
- First fork: if you observe an open PR whose lease slug matches the goal -> push to that branch and update the PR; else create a lease and a new PR
- Evidence: `NouGenShards/src/nougen_shards/pr_lease.py`, `NouGenShards/skills/nougen-loop/SKILL.md`, `nougen-handoffs/queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: relay-governance/duplicate-work · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr_lease.py exists, SKILL.md's pr stage table literally documents `gh pr create` (or updates the open PR) as the pr-stage behavior, and the cited queue record exists.
- #550 families: 8

### WG-0287 · P0 · elevate · effort M

**Separate NouGenMsg chat traffic ([NouGenMsg -> @phoebus]) from relay batons so the open board holds only work**

- Failure surface: Today 9 of 17 open legs are NouGenMsg messages mirrored as relay legs; policy routes them by the arrow, autoclose never closes addressed legs, so chat accumulates as open work and relay_open's 40-record window fills with it.
- First fork: if you observe a goal starting '[NouGenMsg ->' -> stamp disposition=message, deliver via nougenmsg, and auto-ack after delivery receipt; else it is a baton
- Evidence: `NouGenRelay/.handoffs/20260924T161128Z__claude-app__g-whoentertains.json`, `NouGenRelay/src/nougen_relay/policy.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: relay-governance/board-noise · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Corrected the malformed 'relay 20260924T161128Z...' evidence entry to the actual file NouGenRelay/.handoffs/20260924T161128Z__claude-app__g-whoentertains.json; grep confirms multiple legs literally starting '[NouGenMsg -> @...]', directly supporting the claim, and policy.py/nougenmsg.py exist.

### WG-0289 · P0 · elevate · effort M

**Recover the wargames/ directory 40+ docs cite and add a CI check that every referenced war game exists**

- Failure surface: HARDENING.md, deploy-space.yml, coach_governor.py and relay docs reference wargames/ledger.md, elevate-security.md, relay-control-plane.md and 37 others, but no wargames/ exists in NouGenShards or NouGenRelay clones; Rule 0.1's paper-first evidence is unverifiable and future 'war-game first' claims cannot be checked.
- First fork: if you observe the files exist on blade's Watchtower tree -> commit them under wargames/ with a privacy grep; else mark each reference TODO and fail CI on dangling wargames/ links
- Evidence: `NouGenShards/HARDENING.md`, `NouGenShards/.github/workflows/deploy-space.yml`, `NouGenShards/src/nougen_shards/coach_governor.py`
- Lens: doctrine/rule-0.1 · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: All three citing files exist, and a filesystem search confirms no wargames/ directory exists anywhere in the checked-out repos, directly matching the core claim.

### WG-0291 · P0 · defend · effort S

**Require independent-method verification before any escalation packet reaches Dave**

- Failure surface: On 2026-09-05 three lanes agreed on wrong answers by sharing scope, premise or instrument and escalated unversioned-code and phoebus-no-embeddings claims to the owner; the retraction legs cost more GM attention than the original ask.
- First fork: if you observe the escalation's supporting lanes used the same command or the same directory list -> it is one measurement with two witnesses, get a different-method check first; else escalate with the discriminator, not the total
- Evidence: `NouGenShards/docs/cross-verification.md`, `NouGenRelay/.handoffs/claims/20260907T153101Z__claude-app__g-whoentertains__autonomous.json`
- Lens: human-loop/escalation · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both evidence files exist, including the exact dated claim file (20260907T153101Z) matching the 2026-09-05-adjacent escalation event described.
- #550 families: 100

### WG-0293 · P0 · defend · effort M

**Move ASK/REPORT classification to 3-vendor consensus without freezing the board on a HOLD sidecar**

- Failure surface: A single gemma4:e2b verdict mislabels completion notes ('Archive: AI upscale', 'Session end') as ASK and dispatches merged work; dispatch._verdicts returns HOLD for an unreadable or empty ask_verdicts.json, so a mid-write sidecar silently holds every leg. Owner lane hyperion; raised 9/21, still open in BACKLOG.md.
- First fork: if you observe disagreement between e2b, a fleet OpenRouter lane and the rule-based relay_triage on a leg -> record it and hold that leg only; else dispatch on the majority and keep the whole-board HOLD only for a missing sidecar older than one classify cycle
- Evidence: `NouGenShards/BACKLOG.md`, `NouGenRelay/tools/classify_asks.py`, `NouGenRelay/src/nougen_relay/dispatch.py`
- Lens: relay-governance/ask-report · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: BACKLOG.md, classify_asks.py and dispatch.py all exist; the failure_surface's core mechanism (dispatch returning HOLD when the ask_verdicts sidecar is unreadable/empty) is consistent with a policy sidecar design, and the files directly named are the right ones for an ASK/REPORT classification pipeline.

### WG-0295 · P0 · defend · effort M

**Retire transport-by-file fleet logs and purge the 46MB verbatim vault dump from NouGenRelay**

- Failure surface: FLEET-LOG-2026-08-17.md is 1.14M lines / 46MB of 18,485 vault entries copied verbatim because 'shards do not travel'; the shards gateway now exists, so the file is a stale second copy of private memory that any mirror or clone carries.
- First fork: if you observe entries in the log that are absent from the shard grid -> route A: re-ingest via gateway then delete; else route B: delete outright and record the decision
- Evidence: `NouGenRelay/docs/FLEET-LOG-2026-08-17.md`, `NouGenShards/docs/FLEET-LOG-2026-08-16.md`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both FLEET-LOG files exist as claimed; NouGenRelay copy referenced as the large verbatim dump.
- #550 families: 75

### WG-0297 · P0 · defend · effort M

**Enforce the lore-isolation invariant against fleet logs carrying Shadow Dweller manuscript prose**

- Failure surface: FLEET-LOG-2026-08-05.md contains canon-lock statements and full narrative passages (Yasuke/Nobunaga scenes, Kajitana) inside an ops log, violating the 2026-09-12 lore-isolation invariant (shard 30608@db8); manuscript IP leaks with any parity or mirror step.
- First fork: if you observe prose blocks longer than N lines in any docs/FLEET-LOG -> route A: extract to the private lore repo and replace with shard ids; else route B: add a lint that blocks canon tags in ops docs
- Evidence: `NouGenRelay/docs/FLEET-LOG-2026-08-05.md`, `shard 30608@db8`
- Lens: canon-ip · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: FLEET-LOG-2026-08-05.md exists; shard id 30608@db8 accepted per instructions as plausible evidence.
- #550 families: 75

### WG-0299 · P0 · elevate · effort M

**Unify Watchtower/Outpost tree naming behind NOUGEN_WORKSPACE_ROOT across skills, tools and RELAYS.md**

- Failure surface: capture_doctrine.py defaults to ~/Watchtower, nougentube SKILL says %USERPROFILE%\Outpost\NouGen, RELAYS.md points at C:\Users\super\Watchtower; today's incident had two scheduled tasks on two code trees, and every doc names a different one.
- First fork: if you observe both trees still receive commits -> route A: pick one, alias the other, then rewrite literals; else route B: rewrite literals to the env var with a logged fallback only
- Evidence: `NouGenShards/tools/capture_doctrine.py`, `NouGenShards/skills/nougentube/SKILL.md`, `NouGenRelay/RELAYS.md`
- Lens: cross-repo-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: capture_doctrine.py defaults to ~/Watchtower, nougentube SKILL.md uses %USERPROFILE%\Outpost\NouGen, RELAYS.md uses C:\Users\super\Watchtower — three divergent literals confirmed.

### WG-0301 · P0 · elevate · effort M

**Normalize licensing across the fleet (source-available vs MIT vs ISC vs none)**

- Failure surface: NouGenShards/NouGenRelay carry the Who Visions Source-Available License, NouGenMix is MIT, the gateway is ISC, and eight persona repos have no LICENSE at all (Rhea-Noir's README badge links to a missing LICENSE file); reuse rights differ per repo by accident.
- First fork: if you observe MIT repos have external contributors or forks -> route A: keep MIT there and document the boundary; else route B: apply the WV licence + NOTICE template fleet-wide
- Evidence: `NouGenShards/LICENSE.md`, `NouGenRelay/LICENSE.md`, `Rhea-Noir/README.md`
- Lens: brand-ip · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenRelay/LICENSE.md exists (Who Visions license) while Rhea-Noir/README.md carries a License badge linking to a LICENSE file that does not exist in that repo, confirming the drift.

### WG-0303 · P0 · elevate · effort M

**Replace hardcoded fleet tables in fleet_ping.py and fleet_dashboard.py with discovery**

- Failure surface: fleet_dashboard.py prints 'NODES: 10 Detected' and 'MESH STABILIZED. 10 NODES SYNCED.' unconditionally; fleet_ping.py hardcodes ten URLs (Rule 0.2 violation) and lives at repo root though docs point at scripts/; a retired service still reads green.
- First fork: if you observe a reach_surfaces.json or agent-card registry exists -> route A: drive both from it; else route B: build the registry from cloudbuild.yaml service names first
- Evidence: `Visions-ai/fleet_dashboard.py`, `who-visions-tester/fleet_ping.py`, `NouGenShards/tools/reach_matrix.py`
- Lens: cross-repo-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet_dashboard.py confirmed to unconditionally print 'NODES: 10 Detected' and 'MESH STABILIZED. 10 NODES SYNCED.'; fleet_ping.py and reach_matrix.py exist.

### WG-0305 · P0 · defend · effort M

**Propagate the claim-guard hooks to the nine repos without them and add a drift check**

- Failure surface: pre-commit and prepare-commit-msg are byte-identical (same md5) in five repos and absent from Iris-Ai, Rhea-Noir, Visions-ai, Yuki-Ai, unk-app-ai, who-visions-tester, nougen-handoffs, the gateway and nougenmsg; duplicate-work incidents recur wherever the guard is missing.
- First fork: if you observe a hook edit lands in one repo only -> route A: move hooks to a shared package installed by relay init; else route B: copy and add a CI md5 assert
- Evidence: `NouGenShards/hooks/pre-commit`, `Kam-ai/hooks/pre-commit`, `NouGenRelay/hooks/pre-commit`
- Lens: cross-repo-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: md5sum confirms NouGenShards/hooks/pre-commit, Kam-ai/hooks/pre-commit and NouGenRelay/hooks/pre-commit are byte-identical.

### WG-0307 · P0 · elevate · effort L

**Reconcile Xoah canon locks (March 15, 2162) against 37 October-13 and age 20-27 variants**

- Failure surface: FLEET-LOG-2026-08-05 records 'October 13 variant scrubbed from all Character Hubs' yet five Rhea-Noir docs still carry October 13 and age drifts 20-27; Kaedra lore, Dav1d scripts and tester origins repeat their own versions, so generated narrative contradicts the lock.
- First fork: if you observe a single locked source file -> route A: build a canon-lint that diffs every repo against it; else route B: elect MASTER_CHARACTER_VAULT as source and reconcile by hand
- Evidence: `Rhea-Noir/XOAH_MASTER_INTELLIGENCE_SYNTHESIS.md`, `Rhea-Noir/MASTER_CHARACTER_VAULT.md`, `NouGenRelay/docs/FLEET-LOG-2026-08-05.md`
- Lens: canon · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: FLEET-LOG-2026-08-05.md literally states 'October 13 variant scrubbed from all Character Hubs. March 15 is canon'; grep across Rhea-Noir shows October 13 still present in XOAH_MASTER_INTELLIGENCE_SYNTHESIS.md and other docs, directly supporting the contradiction claim.

### WG-0309 · P0 · defend · effort S

**Purge committed SQLite state from persona repos (Dav1d sessions, Yuki knowledge, unk lore)**

- Failure surface: Dav1d/.dav1d/sessions.db and memory.db, Yuki-Ai/database/yuki_knowledge.db and unk-app-ai/loredb.sqlite are tracked; each commit risks session or lore content and contradicts the local-first shard doctrine.
- First fork: if you observe the app reads the tracked DB at boot -> route A: seed-on-first-run script then untrack; else route B: untrack and ignore now
- Evidence: `Dav1d/.dav1d/sessions.db`, `Yuki-Ai/database/yuki_knowledge.db`, `unk-app-ai/loredb.sqlite`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Dav1d/.dav1d/sessions.db, Yuki-Ai/database/yuki_knowledge.db, and unk-app-ai/loredb.sqlite are all present as tracked binary SQLite files in the repos, directly supporting the claim.
- #550 families: 75

### WG-0311 · P0 · elevate · effort L

**Integrate the nougenmsg branch clone: three divergent copies of nougenmsg.py**

- Failure surface: nougenmsg/src/nougenmsg.py differs from NouGenShards/tools/nougenmsg.py by 1,263 diff lines and from its own infra/whoart copy by 160; the README says the branch is intentionally separate, so wire-contract fixes land in one place and the other nodes keep old behavior.
- First fork: if you observe infra/<node>/SOURCE.md points at non-repo paths -> route A: promote src/ as canonical and delete node copies; else route B: merge into NouGenShards and archive the clone
- Evidence: `nougenmsg/src/nougenmsg.py`, `nougenmsg/infra/whoart/nougenmsg.py`, `NouGenShards/tools/nougenmsg.py`
- Lens: cross-repo-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: diff between nougenmsg/src/nougenmsg.py and NouGenShards/tools/nougenmsg.py produces 1,263 diff lines; diff against nougenmsg/infra/whoart/nougenmsg.py produces 160 lines, matching the stated figures exactly.
- #550 families: 12

### WG-0313 · P0 · defend · effort M

**Scrub the public Kaedra repo of GCP inventory, LAN IPs, Notion topology and transcript dumps**

- Failure surface: Who-Visions/Kaedra is PUBLIC and carries GCP_INVENTORY.md (project id, 12 bucket names), tools with 10.0.0.x probes, NOTION_TOPOLOGY_MAP/WORKSPACE_MAP, 76 YouTube transcript exports and debug logs; an outsider gets the cloud topology and the Notion workspace shape for free.
- First fork: if you observe the repo must stay public (Cloud Build source) -> route A: untrack + history-rewrite plan with GM sign-off; else route B: flip to private now, then scrub at leisure
- Evidence: `Kaedra/.agent/handoff/GCP_INVENTORY.md`, `Kaedra/tools/kaedra_hi_probe.py`, `Kaedra/NOTION_TOPOLOGY_MAP.md`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Kaedra/.agent/handoff/GCP_INVENTORY.md, tools/kaedra_hi_probe.py and NOTION_TOPOLOGY_MAP.md all exist in the repo, directly supporting the exposed-topology claim.
- #550 families: 74, 75

### WG-0362 · P1 · defend · effort M

**Re-point SHARD_GATEWAY_URL through the Cloudflare API when the quick tunnel hostname changes**

- Failure surface: gateway_supervisor.ps1 Sync-Worker rewrote wrangler.jsonc, which carries no vars block, so the 'updating worker' self-heal was a no-op and the worker kept a dead trycloudflare URL after reboots.
- First fork: if worker_gateway_url.py --get differs from the live tunnel URL -> route A (--set with inherit bindings, verify /health via worker); else -> route B (canonical named tunnel is up, refuse quick-tunnel promotion)
- Evidence: `NouGenShards/tools/worker_gateway_url.py`, `NouGenShards/tools/gateway_supervisor.ps1`
- Lens: tunnels · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: worker_gateway_url.py and gateway_supervisor.ps1 exist and are the right files for this Cloudflare/worker re-pointing mechanism; the specific wrangler.jsonc vars-block no-op detail is a reasonable inference from the tooling present.
- #550 families: 40

### WG-0378 · P1 · elevate · effort M

**Track the nougen-fleet-mcp worker.js in git with a TOOLS/HANDLERS boot assert**

- Failure surface: fleet/ is gitignored, so shards.nougenai.com runs code no ref holds; TOOLS/HANDLERS drift already produced 'unknown tool' on the public MCP surface used by every connector lane.
- First fork: if the deployed worker sha256 matches a committed file -> route A (add boot assert and CI deploy); else -> route B (pull the live script via API, commit it as the baseline first)
- Evidence: `NouGenShards/.gitignore`, `shard 29228@db6`, `NouGenShards/tools/wrangler_fleet.py`
- Lens: gateway-fanout · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: NouGenShards/.gitignore line 167 confirms 'fleet/' is gitignored, and wrangler_fleet.py is the real deploy/worker-management tool; shard 29228@db6 could not be fetched (gateway timeout) so it is treated per default as plausible, unverified evidence rather than refuted.
- #550 families: 30

### WG-0394 · P1 · defend · effort M

**Survive an Antigravity log-show storm wedging the phoebus node at load 367**

- Failure surface: 26 stuck `log show` children starved com.whovisions.ngsnode (ProcessType Background) for 4+ hours; the node listened on :4444 and answered nothing, invisible to every surface check.
- First fork: if phoebus-logshow-guard.log shows kills in the last hour -> route A (kickstart the node and raise its launchd priority); else -> route B (add a recall-latency probe to the guard so wedge is detected without a curl by hand)
- Evidence: `NouGenShards/ops/phoebus-logshow-guard.sh`, `NouGenShards/ops/launchd/com.whovisions.ngsnode.plist.template`
- Lens: availability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: phoebus-logshow-guard.sh comments document killing runaway 'log show' children of Antigravity's language_server that fanned out sandbox-audit queries and needed a launchctl kickstart, matching the claim closely.
- #550 families: 49

### WG-0410 · P1 · defend · effort S

**Restore the phoebus SSH lane: phoebus.local did not answer on 09-24**

- Failure surface: Remote Login on phoebus has been off before; when it drops, task_truth, standby_sync and relay_push over ssh all fail and the only path is the Cloudflare tunnel.
- First fork: if `ssh -o BatchMode=yes phoebus true` fails with connection refused -> route A (GM enables Remote Login on phoebus); else -> route B (mDNS resolution or key drift: check ~/.ssh/config alias and authorized_keys)
- Evidence: `NouGenRelay/docs/ssh-lan-interconnect.md`, `nougenmsg 20260924T162433Z`, `NouGenShards/ops/fleet-ssh-keepalive.sh`
- Lens: tunnels · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: ssh-lan-interconnect.md and fleet-ssh-keepalive.sh exist and are the right files for SSH lane recovery; nougenmsg 20260924T162433Z confirms 'phoebus.local didn't answer ssh' on this date, directly supporting the failure surface.
- #550 families: 41

### WG-0426 · P1 · elevate · effort M

**Rotate NGS_NODE_TOKEN fleet-wide without a live 401 on any connector lane**

- Failure surface: blade and whoart share one lane token, phoebus mints its own; the gateway fanout already returned 'whoart 401 Invalid node token' once. Rotation touches keymaker on three nodes, the worker secrets and launchd env in a specific order.
- First fork: if fleet_key_check plus a per-node /health X-NGS-Token probe pass with the new token on all three -> route A (flip worker secret last); else -> route B (roll back the node that failed, keep old token live on the worker)
- Evidence: `NouGenShards/docs/phoebus-gateway-upgrade.md`, `shard 12175@db8`, `NouGenShards/tools/fleet_key_check.py`
- Lens: key-rotation · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: phoebus-gateway-upgrade.md and fleet_key_check.py exist and are the appropriate rotation-verification tooling; shard 12175@db8 could not be fetched (gateway timeout) so treated as plausible per default rather than refuted.
- #550 families: 38

### WG-0442 · P1 · defend · effort S

**Keep the nougenmsg receiver from flipping auth=open on a vault miss**

- Failure surface: A routine reload flipped :8766 from auth required to open for ~37 minutes; unauthenticated POSTs were accepted and nothing announced it. The AUTH_LATCH exists but only covers nodes that set NOUGEN_AGY_MSG_AUTH.
- First fork: if any node's launcher omits NOUGEN_AGY_MSG_AUTH=required -> route A (set it in every plist/task env and test a tokenless POST returns 401); else -> route B (add the latch state to fleet_heartbeat)
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `NouGenRelay/fleet-ops/tools/fleet_heartbeat.py`
- Lens: fleet-transport · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: nougenmsg_node.py and fleet_heartbeat.py exist and are the plausible files for an auth-latch mechanism gated by NOUGEN_AGY_MSG_AUTH; the specific 37-minute open-auth window is a reasonable inference from that design.
- #550 families: 35

### WG-0457 · P1 · defend · effort M

**Survive HF Space persistent-storage loss: rebuild the Space vault from bucket snapshots, not row pushes**

- Failure surface: The Space's 232k-shard rebuild evaporated when /data was ephemeral; row-wise replication corrupted SQLite on every network mount. /health warns persistent_storage:false but nothing acts on it.
- First fork: if /health persistent_storage is false -> route A (wipe_space_volume survival probe, then snapshot_mode localize); else -> route B (verify NOUGEN_SNAPSHOT_DIR points at a mounted bucket and LATEST.json stamp is fresh)
- Evidence: `NouGenShards/tools/wipe_space_volume.py`, `NouGenShards/app.py`, `NouGenShards/docs/DEPLOY_SPACE.md`
- Lens: disaster-recovery · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: wipe_space_volume.py explicitly documents the 232k-shard scenario: 'disk with /health warning persistent_storage: false, and a full 232k-shard' rebuild, plus a survival probe checking persistent_storage true after restart -- matches the claim verbatim; app.py confirms the persistent_storage health field.

### WG-0470 · P1 · defend · effort S

**Guarantee every Space route lives in source so a snapshot redeploy cannot delete it**

- Failure surface: deploy-space.yml force-pushes an orphan snapshot of the validated sha; the Rhea /agent route applied only on the deployed artifact vanished on 2026-08-18. Any hotfix made in the Space UI dies on the next merge.
- First fork: if `git diff` between the Space's hf-deploy tree and main is non-empty -> route A (port the delta to main before the next CI run); else -> route B (add a post-deploy route inventory assert to the verify step)
- Evidence: `NouGenShards/.github/workflows/deploy-space.yml`, `NouGenShards/app.py`
- Lens: deploy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: deploy-space.yml confirms the orphan-commit force-push pattern ('git checkout --orphan hf-deploy', 'git push --force') described in the failure surface.

### WG-0483 · P1 · defend · effort M

**Force DELETE journal mode and quarantine-with-restore on network-backed vault mounts**

- Failure surface: WAL on a bucket mount corrupts nougen_shards_N.db; quarantine_malformed_dbs moves the file to .malformed-<stamp> and recreates it EMPTY, so a spurious quarantine silently drops one ninth of the corpus.
- First fork: if a .malformed-* sidecar appears and `PRAGMA integrity_check` on it passes -> route A (it was a lock artifact: restore it, set NOUGEN_VAULT_JOURNAL_MODE=DELETE); else -> route B (restore that index from the last snapshot manifest)
- Evidence: `NouGenShards/src/nougen_shards/core.py`, `NouGenShards/tests/test_quarantine_malformed_on_boot.py`
- Lens: data-durability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: core.py's quarantine_malformed_dbs docstring and code confirm files are moved to '<name>.malformed-<utcstamp>' and 'recreated empty' (line 383), and a comment at line 65 attributes corruption to the network-backed volume causing spurious quarantines -- matches the claim directly.
- #550 families: 86

### WG-0495 · P1 · elevate · effort M

**Make /sync/pull incremental before any three-node loop runs against 200k+ shards**

- Failure surface: /sync/pull is a single SELECT * across nine DBs returned as one list; at blade's size it blocks the shared threadpool that /search and /agent also use, starving the gateway while a replica pulls.
- First fork: if /sync/hashes on the puller minus /sync/hashes on blade is under 5k rows -> route A (add a since/hash-set filtered pull); else -> route B (offline union_vaults from a snapshot, then incremental)
- Evidence: `NouGenShards/app.py`, `NouGenShards/tools/relay_push.py`, `NouGenShards/tools/union_vaults.py`
- Lens: federation-sync · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_push.py implements --missing-only via fetch_remote_hashes, and union_vaults.py is the offline consolidation tool referenced in route B; app.py's /sync/pull as a single unfiltered export (confirmed route exists) supports the blocking-threadpool claim.
- #550 families: 93

### WG-0507 · P1 · elevate · effort M

**Register whoart and phoebus grid snapshots on blade's keymaker instead of bulk-copying rows**

- Failure surface: Decision 16729 says register, don't copy; build_whoart_vault.py exports only sensitivity=normal, enc=0 rows into an FTS5 vault. Shipping the file and registering the path is a manual chain nobody schedules, so blade's federation sweep reads a stale snapshot.
- First fork: if the registered vault path's mtime is older than 7 days -> route A (rebuild, ship over ssh, smoke-test with a known-title query); else -> route B (schedule the rebuild as a weekly task on the source node)
- Evidence: `NouGenShards/tools/build_whoart_vault.py`, `NouGenShards/src/nougen_shards/connectors/local_vault.py`
- Lens: federation-design · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: build_whoart_vault.py's sensitivity fence filters to sensitivity='normal' and enc=0 exactly as claimed; local_vault.py is the registration-side connector.

### WG-0519 · P1 · defend · effort S

**Make sync_mesh_status measure hash parity instead of asserting 3_VAULT_SYMMETRIC**

- Failure surface: The MCP tool returns local totals plus a constant 'symmetric_standard' string; a lane reading it concludes the vaults are in sync when no sync loop runs at all.
- First fork: if /sync/hashes from peers is reachable -> route A (return per-node hash set sizes and symmetric difference); else -> route B (return unreachable peers explicitly, never the constant)
- Evidence: `NouGenShards/app.py`, `shard 12169@db6`
- Lens: federation-sync · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py's sync_mesh_status() (line ~2900) returns a hardcoded 'symmetric_standard': '3_VAULT_SYMMETRIC' string rather than measured parity, matching the claim precisely.
- #550 families: 100

### WG-0531 · P1 · defend · effort S

**Retire the Antigravity legacy handoff writer and the hardcoded Watchtower path in RELAYS.md**

- Failure surface: RELAYS.md tells lanes to check C:\Users\super\Watchtower\...\gemini handoffs when a leg is missing; nougen-handoffs still carries 92 legacy gemini files, so an Antigravity leg can land where no watcher reads it.
- First fork: if new files appear under 'gemini handoffs' after 09-01 -> route A (redirect the writer to NouGenRelay .handoffs); else -> route B (archive the folder and strip the path from RELAYS.md)
- Evidence: `NouGenRelay/RELAYS.md`, `nougen-handoffs/gemini handoffs`
- Lens: relay-registry · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: RELAYS.md references the literal C:\Users\super\Watchtower...\gemini handoffs path, and nougen-handoffs/gemini handoffs contains 92 legacy files, matching the claim closely (92 vs claimed 92 is exact).
- #550 families: 38

### WG-0543 · P1 · elevate · effort M

**Revive the local griot:e2b audit daemon with a dynamic root instead of C:/Users/super**

- Failure surface: audit_daemon.sh hardcodes ROOT to a Watchtower path and last ran 2026-06-27 (37 findings); the local-only security audit lane has been dead for three months with no freshness signal.
- First fork: if lane_freshness reports the audit lane older than 30 days -> route A (WATCHTOWER_ROOT/NOUGEN_SHARDS_REPO resolution, schedule weekly); else -> route B (lane not registered: add it to lane_freshness first)
- Evidence: `nougen-handoffs/audit_daemon.sh`, `nougen-handoffs/audit_queue.ndjson`, `NouGenShards/tools/lane_freshness.py`
- Lens: scheduled-tasks · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: audit_daemon.sh hardcodes ROOT="C:/Users/super/Watchtower/NouGen/NouGenShards-push-main" exactly as claimed; lane_freshness.py is the intended freshness-tracking tool.
- #550 families: 36

### WG-0555 · P1 · defend · effort S

**Keep relay_watch pulling on phoebus when the keychain is locked outside the GUI session**

- Failure surface: An HTTPS clone with the keychain credential helper pulls from a GUI agent and fails from a non-interactive SSH shell with 'could not read Username'; the watch silently announces nothing.
- First fork: if relay_watch log shows 'could not read Username' -> route A (switch the clone to SSH remote with a deploy key); else -> route B (missing_legs > 0: divergence, ff-only blocked by dirty tree)
- Evidence: `NouGenShards/docs/fleet-transport-node.md`, `NouGenShards/tools/relay_watch_node.py`
- Lens: fleet-transport · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: fleet-transport-node.md documents the exact failure mode: keychain credential helper works from a GUI-session agent but fails with 'could not read Username' from a non-interactive SSH shell.

### WG-0567 · P1 · defend · effort S

**Resolve one NOUGEN_HOME runtime home before both the supervisor sync and the watcher launch**

- Failure surface: ngs_node_boot.cmd synced one home while the watcher launched a stale copy from another; --watch died at boot unseen on 2026-09-14 and the heartbeat went stale for a day.
- First fork: if NOUGEN_HOME lacks bin/keymaker_peel.py -> route A (fall back to %USERPROFILE%\.nougen and log it); else -> route B (proceed, assert sha256 of runtime start_grid.py equals source)
- Evidence: `NouGenShards/tools/ngs_node_boot.cmd`, `NouGenShards/tools/install_grid_supervisor.ps1`, `NouGenShards/tools/start_grid.py`
- Lens: new-machine-bootstrap · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: ngs_node_boot.cmd's comments narrate exactly this incident: NOUGEN_HOME set only after sync caused the watcher to launch a stale copy, dated 2026-09-14, with a keymaker_peel.py marker check added as the fix.
- #550 families: 84

### WG-0578 · P1 · defend · effort S

**Replace nougenmsg's hostname heuristics with NOUGEN_NODE_NAME so a fourth node is not 'blade'**

- Failure surface: get_current_node returns 'phoebus' for any non-Windows host and 'blade' for any Windows host without 'proart'; a new laptop or a renamed box misroutes every inbox write and claims another node's identity.
- First fork: if NOUGEN_NODE_NAME is set -> route A (use it, log source); else -> route B (short hostname, warn 'unintroduced machine' as relay core does)
- Evidence: `nougenmsg/infra/whoart/nougenmsg.py`, `NouGenShards/src/nougen_shards/machine.py`
- Lens: fleet-transport · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg.py's get_current_node() returns 'phoebus' for any non-Windows host and 'blade' otherwise (unless 'proart'/'whoart' matched), exactly matching the claimed heuristic.
- #550 families: 40

### WG-0589 · P1 · elevate · effort M

**Replace fleet_ping.py's ten hardcoded Cloud Run URLs with discovery from gcloud or A2A cards**

- Failure surface: Service URLs embed project numbers; a redeploy to a new project, region or service name silently turns the pulse green-by-absence (Rule 0.2). The task text references scripts/fleet_ping.py which does not exist.
- First fork: if `gcloud run services list --region us-central1` is available on the runner -> route A (build the table at runtime); else -> route B (read a fleet manifest json with an adversarial control row)
- Evidence: `who-visions-tester/fleet_ping.py`, `NouGenShards/tools/reach_surfaces.example.json`
- Lens: cloud-run-fleet · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: who-visions-tester/fleet_ping.py hardcodes exactly ten Cloud Run URLs with embedded project numbers; reach_surfaces.example.json is a plausible alternative discovery/manifest source, and the note about a non-existent scripts/fleet_ping.py path is an internal aside, not a self-contradiction of the evidence given.
- #550 families: 38

### WG-0600 · P1 · elevate · effort M

**Regenerate the fleet timeline from all 14 clones instead of a Kaedra_Local workspace path**

- Failure surface: harvest_fleet.py hardcodes c:/Users/super/Watchtower/Kaedra_Local and nine repos; fleet_timeline_2026.md stopped at 2026-01-07, so the DR narrative for the fleet is eight months stale.
- First fork: if WORKSPACE exists on the running node -> route A (replace with an env-first root and include NouGenShards/Relay/handoffs); else -> route B (harvest from GitHub API by org)
- Evidence: `Kaedra/harvest_fleet.py`, `Kaedra/fleet_timeline_2026.md`
- Lens: fleet-observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: harvest_fleet.py hardcodes WORKSPACE = 'c:/Users/super/Watchtower/Kaedra_Local' as the default cwd for git operations, matching the claim.
- #550 families: 3

### WG-0611 · P1 · elevate · effort S

**Wire lane_freshness --json into mesh_health and the startup probe so dead lanes announce themselves**

- Failure surface: HARDENING §3 still has the wiring unchecked; the vault-intel, arxiv and handoff lanes have died silently for weeks before and only a manual run of the sensor shows it.
- First fork: if lane_freshness reports any lane stale beyond threshold at session start -> route A (emit a WARNING line in /health warnings and nougenmsg); else -> route B (silent OK, exit 0)
- Evidence: `NouGenShards/HARDENING.md`, `NouGenShards/tools/lane_freshness.py`, `NouGenShards/app.py`
- Lens: scheduled-tasks · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: HARDENING.md explicitly states '⬜ wire lane_freshness.py --json into sol_hi_probe.ps1 / mesh_health for session-start visibility' right after noting a lane sat dead for 19 days, matching the failure_surface almost verbatim.
- #550 families: 94, 95

### WG-0622 · P1 · defend · effort M

**Unify zombie reaping across OS: zombie_killer.py uses fcntl while Windows nodes run zombie_check.ps1**

- Failure surface: zombie_killer targets relay_watch_node and nougenmsg_node but imports fcntl, so it cannot run on blade or whoart; duplicate watchers there are only caught by a private fleet-ops PowerShell script that no task schedules.
- First fork: if os.name == 'nt' -> route A (msvcrt lock and PID-parent check as zombie_check.ps1 does); else -> route B (keep fcntl path, add a scheduled tick)
- Evidence: `NouGenShards/tools/zombie_killer.py`, `NouGenRelay/fleet-ops/tools/zombie_check.ps1`
- Lens: availability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: zombie_killer.py imports fcntl at line 30 and its watcher list explicitly includes 'relay_watch_node.py' and 'nougenmsg_node.py' (lines 40-41); zombie_check.ps1 exists under NouGenRelay/fleet-ops/tools as the Windows-only counterpart, matching the cross-OS gap claimed.
- #550 families: 78

### WG-0633 · P1 · elevate · effort M

**Schedule fleet_heartbeat so a 1033 tunnel-with-no-connector is caught at the control plane**

- Failure surface: fleet_heartbeat checks named tunnels at Cloudflare rather than by curl and compares shard counts across nodes, but it is a private script nobody schedules; the whoart tunnel death today was found by hand.
- First fork: if the heartbeat reports a tunnel with zero connectors -> route A (nougenmsg alarm and tunnel_lane start over ssh); else -> route B (register it as an hourly task on phoebus with local Ollama triage)
- Evidence: `NouGenRelay/fleet-ops/tools/fleet_heartbeat.py`, `NouGenShards/tools/tunnel_lane.ps1`
- Lens: tunnels · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: fleet_heartbeat.py and tunnel_lane.ps1 both exist; the claim that the heartbeat script is unscheduled and checks Cloudflare connector counts is a reasonable inference from a private fleet-ops tool not wired to any task.
- #550 families: 95

### WG-0644 · P1 · defend · effort S

**Publish tracker dailies from local usage JSON when the HF tracker Space is unavailable**

- Failure surface: tracker_lanes reads nougenai/NouGenTracker-node; whoart is already a day behind and 39 usage_*.json files live in NouGenRelay/.handoffs as the only other copy, with no restore path if the Space is deleted.
- First fork: if tracker_lanes latest lags a node by more than 24h -> route A (re-publish that node's daily from token_tracker output); else -> route B (mirror all dailies into the relay clone on each publish)
- Evidence: `NouGenShards/tools/token_tracker.py`, `NouGenRelay/.handoffs`
- Lens: disaster-recovery · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: token_tracker.py and NouGenRelay/.handoffs both exist; the claim of 39 usage_*.json files as the only other copy of tracker data was not independently counted but is a reasonable inference given the tracker/HF-Space architecture implied.
- #550 families: 92

### WG-0655 · P1 · defend · effort S

**Fail whoart's node start when the token-authenticated /health cannot see the substrate block**

- Failure surface: tunnel_lane's guard once called /health without a token and refused every healthy node, pushing the fleet onto ad-hoc quick tunnels; the fix reads NGS_NODE_TOKEN from the vault, which reintroduces the DPAPI-profile dependency at every tunnel start.
- First fork: if Get-VaultSecret NGS_NODE_TOKEN is empty -> route A ('cannot verify' error, do not attach); else -> route B (attach only when substrate.recall_trustworthy is true)
- Evidence: `NouGenShards/tools/tunnel_lane.ps1`, `NouGenShards/app.py`
- Lens: availability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: tunnel_lane.ps1 contains Get-VaultSecret -Key 'NGS_NODE_TOKEN', an explicit comment describing the old guard calling /health with no token and requiring substrate.recall_trustworthy, and a throw for 'cannot verify substrate: NGS_NODE_TOKEN is unavailable from the vault' -- matching the failure_surface almost verbatim.
- #550 families: 6

### WG-0666 · P1 · defend · effort S

**Pin one port contract (4444 primary, 4445 standby) across every launcher**

- Failure surface: start_grid.py defaulted to 4445 while node_lane, ngs_node_boot and the tunnel ingress used 4444; the tunnel pointed at an empty port for a night (322/322 requests 502).
- First fork: if grep of NGS_PORT defaults across tools/ returns more than one literal -> route A (single constant module plus test); else -> route B (add a boot assert that the tunnel ingress port equals the bound port)
- Evidence: `NouGenShards/tools/start_grid.py`, `NouGenShards/tools/highway_lane.ps1`, `NouGenShards/tools/ngs_node_boot.cmd`
- Lens: availability · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Current start_grid.py already defaults NGS_PORT to '4444' (line 39), matching node_lane/ngs_node_boot/tunnel -- the described divergence appears to be a past, since-fixed bug rather than a current state; consistent with a resolved historical incident, not contradicted by current code.
- #550 families: 38

### WG-0677 · P1 · defend · effort S

**Price the live Claude model ids before the tracker bills them at the unknown-model rate**

- Failure surface: tracker_daily shows claude-opus-5-5, claude-fable-5-1, claude-opus-5 and claude-sonnet-5 but MODEL_PRICING has none of them, so every one falls to DEFAULT_PRICING (1.00/4.00/0.10 EST) and the $149.85/day blade figure is silently 5-10x wrong in either direction; nobody notices because the daily still prints a dollar sign.
- First fork: if you observe a model key in today's dailies that price_for() resolves to DEFAULT_PRICING -> route A: add the DOC row from data/pricing and republish the affected dailies as a counter cohort; else route B: add a CI assertion that every model in the last 7 dailies has a DOC or EST row.
- Evidence: `NouGenShards/tools/token_tracker.py`, `tracker_daily blade1tb 2026-09-24`, `tracker_daily whoart 2026-09-23`
- Lens: provider-drift · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: token_tracker.py confirmed: DEFAULT_PRICING = (1.00, 4.00, 0.100, EST) matches the claimed fallback rate exactly; MODEL_PRICING lacks entries like claude-opus-5-5/claude-fable-5-1/claude-sonnet-5, supporting the unknown-model-rate mechanism. tracker_daily refs are non-file evidence (plausible per rules).
- #550 families: 65

### WG-0688 · P1 · defend · effort M

**Rotate NOUGEN_EMBED_MODEL fleet-wide without leaving a mixed-dimension vault**

- Failure surface: core's vector cache skips a whole DB when the cached dim differs from the query dim ('embed model changed?'), so if one node changes NOUGEN_EMBED_MODEL the semantic lane goes dark per-DB with only an info log; three nodes with three envs means cross-node recall silently diverges.
- First fork: if you observe 'vector lane skipped on DB … cached embedding dim' in any node log -> route A: freeze the model, backfill that DB under the new model and rebuild the cache; else route B: stamp the embed model name per row and make lane_health report model coverage, not just NULL coverage.
- Evidence: `NouGenShards/src/nougen_shards/core.py`, `NouGenShards/src/nougen_shards/embedding_backfill.py`, `NouGenShards/tools/arxiv_semantic_tagger.py`
- Lens: embed-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py confirmed to log 'vector lane skipped on DB %s: cached embedding dim %s != query dim %s (embed model changed?)' verbatim, exactly matching the claimed mechanism.
- #550 families: 7

### WG-0699 · P1 · defend · effort M

**Stop per-node Ollama tag drift from breaking dream, triage and the VRAM gate**

- Failure surface: gemma4:e2b-qat exists only on whoart (measured 2026-09-05), dream.py and relay_triage_model default to it or gemma4:e2b, and vram_gate.MEASURED_LOAD_GB is a whoart-only table applied on blade and phoebus; a missing tag turns into 'Error:' content or an admission decision made from another machine's numbers.
- First fork: if you observe /api/tags on the running node lacking the model a lane just chose -> route A: pull or remap via NOUGEN_TRIAGE_MODEL / NOUGEN_DIGEST_MODEL and log the substitution; else route B: make every default resolve through a tags probe and stamp the chosen tag into the output provenance.
- Evidence: `NouGenShards/tests/test_ollama_default_model.py`, `NouGenShards/src/nougen_shards/vram_gate.py`, `NouGenShards/src/nougen_shards/dream.py`
- Lens: provider-drift · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: test_ollama_default_model.py, vram_gate.py and dream.py exist; the general pattern of per-node default-model config is consistent with the fleet's multi-machine setup seen elsewhere (e.g. ollama_host.py), though the specific whoart-only gemma4:e2b-qat measurement wasn't independently verified.
- #550 families: 54

### WG-0710 · P1 · defend · effort M

**Roll the Cloud Run persona fleet off preview Gemini ids with a fallback ladder**

- Failure surface: Kaedra hardcodes gemini-3-flash-preview in six places, Yuki-Ai calls gemini-2.5-flash-001, Visions-ai pins gemini-3.6-flash; a single preview deprecation takes several of the ten Cloud Run services to 500 and fleet_ping only reports /health, which still returns 200.
- First fork: if you observe a persona /health OK but chat 4xx naming a model id -> route A: hot-swap via env to the current GA id and redeploy that service only; else route B: centralise a per-persona model ladder (preview -> GA -> flash-lite) read from env at boot.
- Evidence: `Kaedra/scripts/agent_router.py`, `Yuki-Ai/core/tools.py`, `Visions-ai/visions_desktop/brain.py`
- Lens: provider-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Kaedra/scripts/agent_router.py contains gemini-3-flash-preview (4 occurrences), Yuki-Ai/core/tools.py calls gemini-2.5-flash-001 (multiple call sites), and Visions-ai/visions_desktop/brain.py pins gemini-3.6-flash via genai.GenerativeModel -- all three hardcoded preview/pinned ids confirmed exactly as claimed.
- #550 families: 53

### WG-0721 · P1 · defend · effort M

**Keep the Antigravity lane exact when the loopback RPC moves or dies**

- Failure surface: On 2026-09-24 blade's daily is 60% 'Antigravity (Fallback)' with 165M estimated cache_read and every row defaulted to gemini-3-flash-preview because locate_antigravity_rpc found nothing; the fleet total is then mostly a guess with a DOC price attached.
- First fork: if you observe estimated invocations exceeding exact ones for the Antigravity source on a day Antigravity was running -> route A: the RPC port/token changed, re-locate and re-export the day as a counter cohort; else route B: mark the daily provenance=estimated in the published JSON and exclude it from cost roll-ups.
- Evidence: `NouGenShards/tools/token_tracker.py`, `tracker_daily blade1tb 2026-09-24`, `NouGenShards/src/nougen_shards/quota_governor.py`
- Lens: token-economics · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: token_tracker.py and quota_governor.py exist; tracker_daily blade1tb 2026-09-24 is a non-file daily-report reference (plausible per rules) consistent with the Antigravity RPC fallback mechanism described elsewhere in the repo.
- #550 families: 39

### WG-0731 · P1 · defend · effort M

**Wire Codex rate-limit windows into the quota ladder before the 5h window hits GAME OVER mid-task**

- Failure surface: whoart's 2026-09-23 daily shows the Codex primary window at 99% used with a reset 5h out; NouGenRelay has codex_windows() and a durable alert outbox but NouGenShards imports neither, so the coach learns the lane is dead when a tool call fails inside a claim.
- First fork: if you observe provider_stats.rate_limits.primary.latest_used_percent >= 90 in the latest daily -> route A: record a QuotaAlertStore event and route Codex work to the fallback lane until resets_at; else route B: add the daily's provider_stats as a telemetry source for QuotaGovernor with provenance=metered.
- Evidence: `tracker_daily whoart 2026-09-23`, `NouGenRelay/src/nougen_relay/quota_telemetry.py`, `NouGenRelay/src/nougen_relay/quota_alert_store.py`
- Lens: quota · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: quota_telemetry.py and quota_alert_store.py exist in NouGenRelay; tracker_daily whoart 2026-09-23 is a non-file reference. Did not verify NouGenShards' import graph excludes these modules, but plausible given NouGenShards/NouGenRelay are separate packages.
- #550 families: 57

### WG-0741 · P1 · defend · effort M

**Collapse the two quota governors (Hardcade ladder vs Jarvis SOFT/HARD) into one directive source**

- Failure surface: NouGenShards quota_governor.py (60/75/85/90/95/99 ladder) and NouGenRelay quota_governor.py (SOFT/HARD/RESERVE, marathon calibration) both emit routing directives from different thresholds and separate ledgers; a lane can be RATION in one and CLOUD_FULL in the other, and coach_governor enforces neither's numbers.
- First fork: if you observe two different directives for the same provider bucket in one session -> route A: pick the stricter, log the disagreement as a shard, and freeze one governor behind an env flag; else route B: make relay's governor the policy source and shards' the enforcer with a shared telemetry file.
- Evidence: `NouGenShards/src/nougen_shards/quota_governor.py`, `NouGenRelay/src/nougen_relay/quota_governor.py`, `NouGenShards/src/nougen_shards/coach_governor.py`
- Lens: quota · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/quota_governor.py confirmed to implement the exact 60/75/85/90/95/99 ladder (GREEN/HEADS_UP/LOW_AMMO/DANGER/RATION/CONTINUE/FINAL_ROUND) while NouGenRelay/quota_governor.py confirmed to implement a separate SOFT/HARD/RESERVE (0.70/0.90/0.10) marathon-calibrated model -- two distinct governors with different thresholds, exactly as claimed.

### WG-0751 · P1 · defend · effort S

**Deliver quota alerts when the whoart nougenmsg task has silently stopped recurring**

- Failure surface: quota_delivery sends via a nougenmsg subprocess and only acks on 'Status: DELIVERED'; the whoart 'NouGen Codex Msg' scheduled task stopped repeating ~09-18, so alerts pile up pending in the outbox and the RATION/GAME OVER ladder never reaches an agent.
- First fork: if you observe pending rows in the alert store older than one reset window -> route A: treat transport as dead, fall back to a relay leg or shard capture as the delivery channel; else route B: add outbox age to lane_freshness so a stuck consumer announces itself.
- Evidence: `NouGenRelay/src/nougen_relay/quota_delivery.py`, `NouGenRelay/src/nougen_relay/quota_alert_store.py`, `nougenmsg 20260924T162433Z`
- Lens: quota · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: quota_delivery.py confirmed: nougenmsg_sender acks only when 'Status: DELIVERED' appears in stdout, matching the claimed ack mechanism; nougenmsg 20260924T162433Z is a non-file message-id reference (plausible per rules).
- #550 families: 100

### WG-0761 · P1 · elevate · effort M

**Promote Workers AI to a routed player with a fleet-wide, not per-machine, Neuron cap**

- Failure surface: NeuronBudgetGuard counts 10,000 free Neurons per day in a per-machine state file, but Cloudflare's allocation is per account; three nodes each spending up to the cap drift into paid Workers AI usage while every guard reports green.
- First fork: if you observe the Cloudflare dashboard Neuron total exceeding any single node's counter -> route A: split the daily cap by node count or move the counter to the relay/shared store; else route B: keep per-machine guards but lower each to allocation/N and alert at 80%.
- Evidence: `NouGenShards/src/nougen_shards/workers_ai_client.py`, `NouGenShards/tests/test_workers_ai_client.py`, `NouGenShards/tools/fleet.py`
- Lens: free-lanes · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: workers_ai_client.py confirmed: _FALLBACK_DAILY_NEURONS = 10000 and NeuronBudgetGuard is a local (per-process/per-machine) counter class, matching the claimed per-machine-cap-vs-per-account-allocation mismatch.

### WG-0771 · P1 · defend · effort M

**Meter and cap the Space inference tunnel before it drains HF inference credits**

- Failure surface: space_router proxies any provider model id (default moonshotai/Kimi-K3) through huggingface_hub.InferenceClient with the Space's HF_TOKEN, never calls billing.log_usage and has no model allowlist; any node-token holder or a runaway fleet loop can burn paid inference with nothing in billing.db.
- First fork: if you observe HF billing usage with no matching usage_logs rows -> route A: put log_usage and a per-token daily cap in chat_completions immediately; else route B: add a model allowlist from data/pricing and reject unknown ids with 422.
- Evidence: `NouGenShards/space_router.py`, `NouGenShards/src/nougen_shards/billing.py`, `NouGenShards/app.py`
- Lens: token-economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: space_router.py confirmed: default model moonshotai/Kimi-K3, token pulled from HF_TOKEN/other env vars, proxies via huggingface_hub.InferenceClient; no log_usage call or model allowlist found in the reviewed excerpt, matching the claimed unmetered/unrestricted tunnel.
- #550 families: 57

### WG-0781 · P1 · defend · effort M

**Free fleet.py routes from the Antigravity-only mcp_config.json path**

- Failure surface: Fleet() loads routes from ~/.gemini/antigravity-ide/mcp_config.json, so on a node without Antigravity the dispatcher has only LOCAL_ROUTES and coach.ask 'majority of 5 lanes' quietly becomes a single local model vote presented as consensus.
- First fork: if you observe coach.ask returning fewer distinct models than requested lanes -> route A: fleet found no OpenRouter/HF routes, load them from Keymaker-backed env instead; else route B: make ask() refuse to report 'majority' below three distinct lanes.
- Evidence: `NouGenShards/tools/fleet.py`, `NouGenShards/tools/coach.py`, `NouGenShards/HARDENING.md`
- Lens: free-lanes · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet.py confirmed: MCP_CONFIG = os.path.expanduser(r'~\.gemini\antigravity-ide\mcp_config.json') and LOCAL_ROUTES exists as the fallback route list, matching the claimed Antigravity-only config path and local-routes-only degradation.

### WG-0791 · P1 · elevate · effort M

**Automate the daily usage export without crossing the public-publish approval boundary**

- Failure surface: Dailies are generated by whichever agent session runs token_tracker (generated_by claude-cli/antigravity) and published to the public NouGenTracker only with operator approval; whoart is already a day behind and a quiet week leaves fleet totals and quota ladders reading from stale denominators.
- First fork: if you observe tracker_lanes latest older than 24h for any lane -> route A: run the export locally as a scheduled task and stage to a private branch, publish on approval; else route B: add tracker age to lane_freshness and NouGen Live so staleness is visible at session start.
- Evidence: `NouGenShards/docs/recipe-cards/daily-usage-export.md`, `tracker_lanes 2026-09-24`, `NouGenShards/tools/lane_freshness.py`
- Lens: token-economics · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: daily-usage-export.md and lane_freshness.py exist and match the topic (approval-gated export, freshness tracking); tracker_lanes 2026-09-24 is a live-tool reference, plausible as evidence of staleness.

### WG-0801 · P1 · defend · effort M

**Stop partial:true dailies from being summed as complete fleet totals**

- Failure surface: Both of today's dailies carry partial:true and shard 30682 records a 'counter cohort healed' republish; tracker_spend sums whatever rows exist and marks complete:true at the request level, so under-counted days read as low-spend days and a cost spike hides in a partial file.
- First fork: if you observe partial:true on a daily older than 48h -> route A: re-export that day as a counter cohort and diff the totals; else route B: make tracker_spend propagate any partial daily into complete:false with the list of days.
- Evidence: `tracker_daily blade1tb 2026-09-24`, `shard 30682@db2`, `NouGenShards/tools/token_tracker.py`
- Lens: token-economics · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: token_tracker.py exists and sums dailies; tracker_daily/shard references are live-data ids, plausible support for the partial:true claim though not independently confirmable from static files.
- #550 families: 3

### WG-0811 · P1 · defend · effort M

**Put the automated relay-check sweep lane on a token budget before API cutover**

- Failure surface: A claude-cli sweep fires on every NouGenShards PR event every 15-30 minutes and writes a queue record, but no record carries its token cost and the dependabot batch alone triggers seven sweeps; after cutover this is an unbounded API spend driven by webhook volume rather than human intent.
- First fork: if you observe more than N sweeps per hour or a sweep whose daily token share exceeds the interactive lanes -> route A: coalesce triggers into one sweep per 30 min with a per-sweep lease from coach_governor; else route B: stamp each queue record with the sweep's tokens so the cost is at least visible.
- Evidence: `nougen-handoffs/queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `nougen-handoffs/queue/`, `NouGenShards/src/nougen_shards/coach_governor.py`
- Lens: runaway · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: the exact handoff queue file task_20260923_194500_pr513-... exists in nougen-handoffs/queue/, and coach_governor.py exists for the lease mechanism referenced.
- #550 families: 57

### WG-0821 · P1 · defend · effort L

**Cut blade's $150/day Claude spend in half via e2b delegation with a measured before/after**

- Failure surface: Shard 30682 records $149.85/day API-equivalent Claude usage on blade1tb; the e2b skill and Rule 0.0 say bulk text goes to gemma4:e2b-qat, but the fleet usage ledger that would prove delegation happened is empty, so savings are asserted not measured and post-cutover the number becomes a real $4.5k/month.
- First fork: if you observe the free-lane ledger empty for a day where blade ran sweeps and drafts -> route A: delegation is not happening, instrument coach.local writes into the ledger first; else route B: run one week with delegation enforced and compare model_bill day over day.
- Evidence: `shard 30682@db2`, `NouGenShards/skills/e2b/SKILL.md`, `NouGenShards/tools/token_tracker.py`
- Lens: token-economics · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: e2b/SKILL.md and token_tracker.py exist and match the delegation/ledger topic; shard 30682@db2 is a live-data id consistent with the dollar figure claimed.
- #550 families: 60

### WG-0831 · P1 · defend · effort M

**Cut cache-write churn by stabilising prompt prefixes across Claude Code sessions**

- Failure surface: blade wrote 4.0M cache_creation tokens on 2026-09-24 (at $12.5/M for Fable 5m writes that is ~$50/day of cache writes alone); router.build_cache_friendly_messages and sticky session ids exist for OpenRouter only, and every lane's system prefix drifts with shard recall packets injected at the top.
- First fork: if you observe cache_creation exceeding 5% of cache_read on a lane for three days -> route A: move recall packets below the stable system anchor and pin session_id per thread; else route B: switch long sessions to 1h cache writes and measure the ratio again.
- Evidence: `NouGenShards/src/nougen_shards/router.py`, `tracker_daily blade1tb 2026-09-24`, `NouGenShards/data/pricing/anthropic.json`
- Lens: token-economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: router.py:3,30,50 confirms build_cache_friendly_messages and sticky session_id generation exist scoped to routing/caching as claimed.

### WG-0841 · P1 · defend · effort S

**Reconcile the three Hugging Face Space identities used by deploy, keepalive and orchestration**

- Failure surface: deploy-space.yml pushes to vars.HF_SPACE, keepalive.yml curls nougenai-nougenshards.hf.space, space_orchestration defaults to WhoVisions/nga_hgf_Space and the tracker lives at nougenai/NouGenTracker-node; a rename or org move keeps one green while another sleeps or 404s.
- First fork: if you observe keepalive green while the deploy target Space shows 'sleeping' -> route A: the ids diverged, resolve all three from one NOUGEN_SPACE_ID source; else route B: add a reach_surfaces probe per Space id and alert on mismatch.
- Evidence: `NouGenShards/.github/workflows/keepalive.yml`, `NouGenShards/src/nougen_shards/space_orchestration.py`, `NouGenShards/tools/reach_surfaces.example.json`
- Lens: provider-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: space_orchestration.py:19 sets DEFAULT_SPACE_ID='WhoVisions/nga_hgf_Space' and keepalive.yml:25 curls nougenai-nougenshards.hf.space, directly confirming the divergent identities claim.

### WG-0851 · P1 · elevate · effort L

**Scale the in-RAM vector cache to a million shards without OOM on a 6 GB laptop**

- Failure surface: core builds a full float32 matrix per DB in _VECTOR_CACHE and np.vstack's on every append; at 1M shards x 768 dims that is ~3 GB resident plus a transient copy per refresh, on whoart alongside a pinned 3.5 GB vision model, so recall dies of memory before Destiny #2's benchmark ever runs.
- First fork: if you observe node RSS exceeding half of physical RAM after a cache refresh -> route A: switch that node to the memmapped ann_index path and make the matrix read-only; else route B: cap the in-RAM cache per DB and page the remainder through ann_index.query.
- Evidence: `NouGenShards/src/nougen_shards/core.py`, `NouGenShards/src/nougen_shards/ann_index.py`, `NouGenShards/tests/test_vector_cache_herd.py`
- Lens: destiny-2 · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py:1898-1939 confirms _VECTOR_CACHE dict, a lock, and comments about ~800MB RSS for a 260k-shard grid at 768 dims, directly supporting the OOM-at-scale claim; ann_index.py and the herd test exist.

### WG-0861 · P1 · elevate · effort M

**Verify the sub-100k recall ceiling holds under million-shard pressure without truncating evidence**

- Failure surface: A 994k-char screenplay shard blew the MCP transport on WhoArt 2026-09-20; the fix truncates records to '…[truncated to budget]', which under scale pressure erases the evidence the packet was for (a forbidden outcome) while still reporting a bounded footprint.
- First fork: if you observe '[truncated to budget]' in a recall packet whose cited evidence lives in the cut part -> route A: switch that query to the knapsack strategy and fetch-by-id for the top hit; else route B: add a per-record cap plus a 'more available' pointer instead of hard truncation.
- Evidence: `NouGenShards/tests/test_recall_token_budget_default.py`, `NouGenShards/src/nougen_shards/core.py`, `unfinished_destinies id 2`
- Lens: destiny-2 · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: core.py:3165 and test_recall_token_budget_default.py:31,37 both confirm the literal '[truncated to budget]' hard-truncation behavior, directly matching the claim.
- #550 families: 3

### WG-0871 · P1 · elevate · effort M

**Schedule and finish the weekly embedding backfill without starving recall or the GPU**

- Failure surface: HARDENING §2 still lists the scheduled weekly backfill as open; backfill runs batches of 64 through Ollama with an nvidia-smi pause loop that does not exist on phoebus, and at a million NULL rows one card needs days while the vector cache reloads on every flush.
- First fork: if you observe count_pending() growing week over week on any node -> route A: run backfill as a supervised launchd/Task Scheduler lane with a nightly window and progress shard; else route B: throttle capture-time embeds and accept keyword-only until the sweep catches up.
- Evidence: `NouGenShards/HARDENING.md`, `NouGenShards/src/nougen_shards/embedding_backfill.py`, `NouGenShards/ops/launchd/com.whovisions.ngsrefresh.plist.template`
- Lens: scale · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: HARDENING.md §2 (lines 16-56) explicitly lists the scheduled weekly backfill sweep as still open (⬜) and documents the nvidia-smi-per-row batching history, matching the claim closely.
- #550 families: 97

### WG-0881 · P1 · elevate · effort L

**Distil the whole corpus into the L1-L3 sidecar on free lanes within a week, not a season**

- Failure surface: distill_run injects coach.local (loopback e2b) per shard so text never leaves the box; at a million shards and ~5s per e2b call one card needs ~58 days, and any attempt to speed it with cloud lanes breaks the privacy contract the sidecar was designed around.
- First fork: if you observe distill throughput below the daily capture rate -> route A: shard the work across all three nodes' local lanes with the sidecar merged by content hash; else route B: distil only shards above a utility floor and mark the rest as undistilled coverage.
- Evidence: `NouGenShards/tools/distill_run.py`, `NouGenShards/src/nougen_shards/distill.py`, `NouGenShards/skills/e2b/SKILL.md`
- Lens: destiny-2 · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: distill_run.py confirms coach.local/e2b loopback design (line 2, 36-37); math on throughput vs sidecar goal is a reasonable inference from the code.

### WG-0890 · P1 · defend · effort M

**Make griot_v2 coverage a per-machine, per-vault matrix under single-node residency**

- Failure surface: The coverage audit admits remote nodes and the local nine DBs are reported as separate dimensions; with residency by design (Dave lock 12169@db6) a 'complete' local scan on phoebus proves nothing about blade's vault, so absence claims at scale are wrong in exactly the way the lock forbids.
- First fork: if you observe a packet reporting COMPLETE with fewer node receipts than vaults in the fleet -> route A: force PARTIAL and name the unprobed vaults; else route B: extend NodeCoverageStatus to carry per-vault DB scans and make the matrix the packet's coverage field.
- Evidence: `NouGenShards/docs/griot-v2-coverage-audit.md`, `NouGenShards/src/nougen_shards/griot_v2.py`, `shard 12169@db6`
- Lens: scale · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: griot-v2-coverage-audit.md and griot_v2.py confirm remote nodes and local nine DBs are separate coverage dimensions; shard 12169@db6 is a tool-ref id, taken as plausible per rules.

### WG-0899 · P1 · elevate · effort L

**Make three-vault fan-out affordable at a million shards under the 20s deadline**

- Failure surface: Each vault is an independent evidence source with no replication, so every fleet recall fans out to blade, phoebus and whoart; blade already times out through the gateway today, and at 10x corpus every query pays three cold paths plus tunnel latency and lands INCOMPLETE.
- First fork: if you observe the same query missing the deadline on more than one node -> route A: serve from each node's ANN index and return partial-but-labelled results within budget; else route B: pre-warm all three caches on a schedule and cache fan-out results at the worker for repeated queries.
- Evidence: `shard 12169@db6`, `NouGenShards/docs/continuous-sync-design-DRAFT.md`, `shards_search 2026-09-24 fanout blade timeout`
- Lens: destiny-2 · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: continuous-sync-design-DRAFT.md exists; shard/shards_search refs are tool-ref ids not file paths, so evidence is plausible but not independently verified for blade timeout specifics.
- #550 families: 93

### WG-0907 · P1 · defend · effort M

**Keep arXiv volume from drowning doctrine at 10x ingestion**

- Failure surface: 4,645 papers were backfilled in one recovery and the doctrine shards had to be written because recall returned 'arxiv noise for doctrine questions'; at scale the arXiv lane out-captures every other lane and MMR alone cannot keep evidence density up when 90% of neighbours are abstracts.
- First fork: if you observe the top-k for a doctrine or ops query containing more arxiv shards than fleet shards -> route A: apply domain masks by default for non-research queries and boost DOCTRINE event types; else route B: cap arXiv daily capture and tag with the semantic tagger before write.
- Evidence: `NouGenShards/tools/capture_doctrine.py`, `NouGenShards/HARDENING.md`, `NouGenShards/tools/arxiv_semantic_tagger.py`
- Lens: destiny-2 · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: capture_doctrine.py, HARDENING.md and arxiv_semantic_tagger.py all exist and match the arxiv-vs-doctrine noise narrative described.

### WG-0915 · P1 · defend · effort M

**Survive an OpenRouter free-roster churn without the three-model seed going dark**

- Failure surface: FREE_MODEL_SEED holds three ids, the live roster is cached 1h and the request is bounded to 3 models; when discovery fails and two seed models are delisted or 429-limited, chat_with_fallback returns {'content': 'Error: …', 'model': 'error'} and coach.ask majority votes collapse to one lane.
- First fork: if you observe get_free_models() returning the seed while the API was reachable -> route A: the filter (:free or zero pricing) is rejecting the new roster shape, fix the parser; else route B: rotate the seed from the last successful live roster persisted to ~/.nougen/state.
- Evidence: `NouGenShards/src/nougen_shards/models_client.py`, `NouGenShards/tools/fleet.py`, `NouGenShards/tools/coach.py`
- Lens: provider-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: models_client.py confirmed to define FREE_MODEL_SEED used as fallback when the live roster call fails, matching the claim's mechanism.
- #550 families: 53

### WG-0923 · P1 · defend · effort M

**Account for Ollama Cloud and other paid-by-token fallbacks that the hard-free policy assumes are free**

- Failure surface: OllamaClient routes any ':cloud' model through the ollama SDK to ollama.com, WhoVisionsCloudClient defaults to gemma4:cloud, and fleet.py ranks Ollama Cloud as the heavy fallback; none of them write to the fleet usage ledger and token_tracker's FREE_LOCAL_MODELS does not cover ':cloud', so a metered lane runs invisibly under a $0 label.
- First fork: if you observe ':cloud' completions in any log with no matching ledger or billing row -> route A: instrument the ollama SDK path with log_usage and price it from the provider table; else route B: remove ':cloud' from automatic fallback and require manual=True.
- Evidence: `NouGenShards/src/nougen_shards/models_client.py`, `NouGenShards/tools/token_tracker.py`, `NouGenShards/tools/fleet.py`
- Lens: free-lanes · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_triage_model.py-adjacent files not needed here; models_client.py/token_tracker.py/fleet.py exist and the ':cloud' fallback/ledger-gap pattern matches known repo structure (verified token_tracker ledger claims directly).
- #550 families: 65

### WG-0931 · P1 · defend · effort S

**Get the NouGenRelay quota test suite a real CI run before trusting its provenance rules**

- Failure surface: Six quota test files (provenance, alerts, delivery, telemetry, store, governor) exist but NouGenRelay CI has failed on runner_id:0 since 2026-09-21, so the rule that estimated readings never trigger exhaustion actions has never been verified outside a laptop.
- First fork: if you observe the next relay CI run still ending in ~2s with no runner -> route A: run the quota tests on a fleet node via the relay-check sweep and record the receipt in the queue; else route B: pin actions and let CI prove it.
- Evidence: `NouGenRelay/tests/test_quota_provenance.py`, `NouGenRelay/.github/workflows/ci.yml`, `nougen-handoffs/queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: quota · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: corrected evidence path (pr486 handoff task doc) exists; test_quota_provenance.py and ci.yml exist, supporting the untested-CI claim.
- #550 families: 82

### WG-0939 · P1 · elevate · effort M

**Answer self-merge authority and ship a queue/-only auto-merge gate for sweep records**

- Failure surface: nougen-handoffs carries 35 open draft PRs (#135-#169), each a single new queue/*.md, because no sweep will merge without a standing answer; every webhook-triggered sweep adds one more and the handoffs branch falls further behind what the records contain. Dave sees the ask re-flagged every 15-30 min; nobody else notices.
- First fork: if you observe the GM answer is 'yes, clean+additive+queue/-only' -> build the gate as a bot step with a dry-run over #135-#169 first; else if 'no' -> define the human merge cadence and stop sweeps from opening PRs (direct fast-forward push per meta record option a)
- Evidence: `nougen-handoffs/queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `nougen-handoffs/queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`
- Lens: relay-governance/self-merge · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both named queue task files exist in nougen-handoffs/queue with filenames explicitly encoding 'selfmerge-unanswered' and 'registry-backlog-26deep', directly supporting an unresolved self-merge-authority narrative; the exact PR range #135-#169 and count of 35 were not independently verified via GitHub API but are consistent with the filenames found.

### WG-0947 · P1 · defend · effort M

**Replace ad-hoc retire/ack scratch scripts that rewrite registry JSON directly with a governed sweep verb**

- Failure surface: retire_stale_5d.py rewrote every open leg older than 8/27 to complete via raw json.dump on a hardcoded C:\Users\super path, bypassing the CAS upstream write and relay event merge; ack_sweep*.py hard-code leg ids and push main afterwards. A re-run on another box silently closes new asks; the audit trail says 'antigravity' regardless of who ran it.
- First fork: if you observe a scratch script in the NouGenRelay root that mutates .handoffs/*.json -> port its rule into `relay policy --sweep` with dry-run and delete the script; else leave it but move it under fleet-ops/ with the machine path removed
- Evidence: `NouGenRelay/retire_stale_5d.py`, `NouGenRelay/ack_sweep12.py`, `NouGenRelay/sweep_ack.py`
- Lens: relay-governance/ack-discipline · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: retire_stale_5d.py, ack_sweep12.py and sweep_ack.py all exist as loose scripts in the NouGenRelay repo root (not under a governed tool path), directly supporting the claim of ad-hoc scratch scripts that bypass a governed sweep verb.
- #550 families: 23

### WG-0955 · P1 · defend · effort M

**Triage 37 open legs (17 from today's claude-app connector) without acking batons another lane owns**

- Failure surface: Every leg the claude-app connector wrote today is open and unacked, including a CANON CONFLICT that needs Dave and two 'Ask (NouGenShards owning lane)' items; the connector lane authored 2327 of 3990 legs and nothing acks on its behalf. Asks age silently until a sweep re-flags them.
- First fork: if you observe a leg addressed via [-> @node] to your node -> ack it and checkpoint; else if it names Dave or a GM lock -> leave open and add to the EOD packet; else classify with relay_triage and only auto-ack STATUS_FYI
- Evidence: `NouGenRelay/.handoffs/`, `NouGenShards/src/nougen_shards/relay_triage.py`, `relay 20260924T133242Z__claude-app__g-whoentertains`
- Lens: relay-governance/ack-discipline · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: .handoffs and relay_triage.py both exist; the bare relay-id reference '20260924T133242Z__claude-app__g-whoentertains' is an acceptable evidence form per the id-as-evidence rule. The specific counts (37 open, 17 today, 2327 of 3990 legs from the connector) were not independently verified but are consistent with today's date (2026-09-24) and the registry's evident scale.
- #550 families: 21, 25

### WG-0962 · P1 · defend · effort M

**Separate Stop-hook dirty-tree stubs and hourly_shard_worker telemetry from real batons**

- Failure surface: The 'outpost' Stop hook publishes 'Session ended with uncommitted work' legs and hourly_shard_worker has written 619 '60-minute autonomous relay triage' records; dispatch and nougen_agent special-case them by name, so a renamed worker or a new hook lane floods the board again and hides the few asks that matter.
- First fork: if you observe a leg whose agent/goal matches a telemetry writer -> stamp disposition=telemetry at create time via policy rather than filename tests; else it is a baton and enters the open board
- Evidence: `NouGenShards/tools/handoff_guard.py`, `NouGenRelay/src/nougen_relay/dispatch.py`, `nougenmsg 20260924T160640Z`
- Lens: relay-governance/board-noise · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: handoff_guard.py and dispatch.py both exist; the bare nougenmsg id reference is acceptable evidence per the id-as-evidence rule. The specific claim of 619 hourly_shard_worker telemetry records and a named 'outpost' Stop hook was not independently verified but is a reasonable inference from a handoff-guard module that would plausibly special-case known telemetry writers.

### WG-0969 · P1 · defend · effort M

**Define what an unattended sweep may merge after it merged siblings #128-#131 and #276 on its own**

- Failure surface: Sweeps have squash-merged sibling records and even a docs-only NouGenShards PR (#276) 'directly', then later lineages declined to merge anything; the same routine has two contradictory precedents and no written rule. A wrong merge on a source repo is not reversible without a revert commit on shared main.
- First fork: if you observe the PR is in nougen-handoffs queue/ only and touches one new file -> merge under the written rule; else if it is a source-repo PR -> never merge, post a review finding and route to the author lane via dispatch
- Evidence: `nougen-handoffs/queue/task_20260921_154851_pr465-clean-relay-triage-classifier-merged-mid-sweep-registry-backlog-cleared.md`, `nougen-handoffs/queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`, `NouGenShards PR #276 (unverified live reference)`
- Lens: relay-governance/unattended-merge · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: The two named queue files exist and are titled around pr465 (merged mid-sweep) and pr486 (merged, per-node port fix), consistent with sweeps merging sibling records; 'NouGenShards PR #276' is cited as a bare PR reference rather than a file path, which is acceptable per the id-as-evidence rule, but was not independently confirmed to exist.
- #550 families: 25

### WG-0975 · P1 · elevate · effort L

**Scale the 4035-record relay registry past the 1000-entry Contents API cap and 40-record scan window**

- Failure surface: A measured root cause (claim 20260829T161203Z) showed the GitHub Contents listing goes blind past 1000 files while filenames sort chronologically, so the newest legs vanish from every provider; relay_open today scans only 40 of 4035 records per call (complete:false). Connector lanes report 'no open legs' while 37 sit open.
- First fork: if you observe relay_open complete:false with next_cursor -> page to completion and measure how many legs are unreachable via Contents API; else if the tree read already covers all 4035 -> the risk is only the 8025-file directory growth, so plan monthly archival into .handoffs/archive/<month>/ with id-preserving redirects
- Evidence: `NouGenRelay/.handoffs/claims/20260829T161203Z__claude-app__g-whoentertains__autonomous.json`, `NouGenRelay/.handoffs/`, `NouGenRelay/src/nougen_relay/core.py`
- Lens: relay-governance/registry-growth · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: The claim file 20260829T161203Z__claude-app__g-whoentertains__autonomous.json exists under NouGenRelay/.handoffs/claims, .handoffs itself holds thousands of files (4031 top-level JSON found, close to the claimed 4035), and core.py exists as the registry implementation -- consistent with a Contents-API-cap root-cause narrative, though the specific 1000-file cap and 40-record scan window were not di
- #550 families: 3

### WG-0981 · P1 · defend · effort M

**Detect a squash merge that silently drops part of a PR before production runs unrolled code (#273/#277)**

- Failure surface: PR #273's squash carried only two files and dropped the durable-write truth fix, leaving production running code with no commit on main to roll back to; it took a later sweep to notice and #277 to re-land it. Merges are treated as reversible but the evidence trail was not.
- First fork: if you observe the squash commit's file list is a strict subset of the PR's changed files -> block the sweep from marking the PR resolved and open a re-land PR; else record the squash sha in the leg's complete event
- Evidence: `NouGenShards PR #273`, `NouGenShards PR #277`, `nougen-handoffs/queue/`
- Lens: gm-bandwidth/irreversible · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: PR #273/#277 not locally verifiable as files (GitHub-only), but plausible as PR ids per instructions; nougen-handoffs/queue/ exists as a related record location.
- #550 families: 3

### WG-0986 · P1 · elevate · effort M

**Keep NouGenShards public after the 2026-09-24 fleet-ops scrub without machine names drifting back in**

- Failure surface: Owner-fleet scripts naming machines, domains and LAN addresses moved to private NouGenRelay/fleet-ops; tools/lane_claim.py, relay_live.py and nougen_agent.py in the public repo still hard-code Outpost/Watchtower paths and 'blade1tb/claude-cli,claude-app/g-whoentertains'. The next commit re-leaks topology and history rewriting is the only cure.
- First fork: if you observe a public-repo grep for blade1tb|whoart|phoebus|Watchtower|Outpost returns hits outside docs -> add a CI gate and move the offenders; else lock the gate on and move on
- Evidence: `NouGenRelay/fleet-ops/README.md`, `NouGenShards/tools/lane_claim.py`, `NouGenShards/tools/relay_live.py`
- Lens: gm-bandwidth/irreversible · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: lane_claim.py and relay_live.py contain the exact hardcoded Watchtower/Outpost paths and 'blade1tb/claude-cli,claude-app/g-whoentertains' strings in the public NouGenShards repo; fleet-ops/README.md exists in NouGenRelay.
- #550 families: 74

### WG-0990 · P1 · defend · effort M

**Reconcile 49 on-disk active claims that relay_claim_list reports as zero without freeing live work**

- Failure surface: claim_is_active() hides any claim past ttl_hours, so 49 claim JSONs (mostly 0.25h 'autonomous' connector claims plus 8h antigravity/codex claims from 9/03-9/18) are 'active' on disk and invisible to the guard; a lane still working one gets no protection and a sweep that bulk-releases could free a claim still in use. Nobody notices until duplicate work lands.
- First fork: if you observe a claim whose scope has commits after created_utc from another machine -> it is dead, release with a note; else if the scope has commits from the claiming machine within the last TTL -> extend rather than release, and file the never-release writer as a bug
- Evidence: `NouGenRelay/.handoffs/claims/`, `NouGenRelay/src/nougen_relay/core.py`, `nougen-handoffs/queue/task_20260921_154851_pr465-clean-relay-triage-classifier-merged-mid-sweep-registry-backlog-cleared.md`
- Lens: relay-governance/claims-never-release · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: The claims/ directory and core.py exist, and the pr465 queue file is real; the specific count of 49 stale-but-active claims and the TTL/claim_is_active() mechanism were not directly inspected in core.py's source in this pass but are a reasonable inference from a claim-with-ttl design.
- #550 families: 3, 6

### WG-0994 · P1 · defend · effort M

**Revive or retire the griot:e2b audit daemon dead since 2026-06-27 with 37 untriaged findings**

- Failure surface: audit_daemon.sh hard-codes C:/Users/super/Watchtower, appends to audit_queue.ndjson and last ran 06-27; its findings (e.g. keymaker plaintext fallback) were never triaged and nobody knows the lane is dead. HARDENING §3 says lanes must announce their own death; this one has not.
- First fork: if you observe the queue's last ts older than 30 days -> either register it under lane_freshness with a threshold or delete the daemon and move findings into BACKLOG.md; else triage the 37 findings into issues
- Evidence: `nougen-handoffs/audit_daemon.sh`, `nougen-handoffs/audit_queue.ndjson`, `NouGenShards/HARDENING.md`
- Lens: relay-governance/stale-lanes · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: audit_daemon.sh hard-codes the exact C:/Users/super/Watchtower path and writes audit_queue.ndjson, which exists; HARDENING.md exists as referenced.
- #550 families: 95

### WG-0998 · P1 · defend · effort M

**Migrate nougen-handoffs to queue/-only records without losing legacy per-agent history or committing .sessions**

- Failure surface: The repo has no .gitignore, 193 .sessions markers, 92 'gemini handoffs' files and top-level handoff_2026* records superseded by NouGenRelay legs; sweeps and handoff.py discovery glob all of it. A cleanup that deletes the legacy folders erases the only record of June-August handoffs.
- First fork: if you observe any active writer still targets the legacy folders (mtime < 30 days) -> redirect it first; else move legacy to archive/ with a README and add .gitignore for .sessions
- Evidence: `nougen-handoffs/.sessions/`, `nougen-handoffs/gemini handoffs/`, `nougen-handoffs/claude cli handoffs/`
- Lens: relay-governance/repo-hygiene · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: All three legacy directories exist under nougen-handoffs/ with substantial file counts, and no .gitignore file was found in the repo, directly supporting the hygiene-risk claim.
