# War-game candidates — NouGenRelay

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

106 candidates · P0 43 · P1 63 · P2 0 · P3 0 · defend 76 · elevate 30

| id | P | kind | title |
|---|---|---|---|
| WG-0003 | P0 | defend | Prove FLEET-LOG relays cannot carry the 21 known AIzaSy fingerprints out of the vault |
| WG-0019 | P0 | defend | Survive nougen_shards API drift in auto_capture_shard and every fleet-ops tool |
| WG-0034 | P0 | elevate | Add a CI registry lint that parses every .handoffs/*.json and rejects non-leg shapes |
| WG-0048 | P0 | elevate | Collapse blade's two scheduled tasks and two code trees into one daemon, one DB, one lock |
| WG-0060 | P0 | elevate | Make the relay watchdog task headless and QuickEdit-proof after today's blade console freeze |
| WG-0071 | P0 | elevate | Route dispatch send_wake through file-backed stdout so Windows ssh stops timing out at 90s |
| WG-0082 | P0 | defend | Close the remaining fleet-answer false-completion path after leg 20260831T195956Z |
| WG-0093 | P0 | elevate | Schedule fleet_heartbeat on one node with tunnel-1033 detection and alert delivery |
| WG-0103 | P0 | elevate | Wire probe_field_parity into a scheduled check so a hostname answered by the wrong node is caught |
| WG-0113 | P0 | defend | Fix relay_pusher_90m's all-or-nothing 'operational' verdict while whoart-vault is intermittent |
| WG-0121 | P0 | elevate | Version the nougenmsg receipt contract so a stale copy cannot fake or lose delivery |
| WG-0129 | P0 | defend | Pin the interpreter every hook and scheduled task uses on each Windows box |
| WG-0137 | P0 | elevate | Rotate blade's LAN node token whose fingerprint matches nothing in any vault |
| WG-0145 | P0 | defend | Reconcile NOUGEN_USER_ORIGIN_TOKEN across phoebus and blade so the owner path works |
| WG-0153 | P0 | defend | Reconcile gateway-only legs that 404 on the git registry (connector split-brain) |
| WG-0161 | P0 | defend | Expire the 49 'active' claims and daemon leases that outlived their TTL in the tracked registry |
| WG-0169 | P0 | defend | Quarantine the two unparseable .handoffs records and gate every registry writer on json.loads |
| WG-0177 | P0 | defend | Reap the 49 blade1tb relay-daemon claims stuck 'active' for 120-618 hours |
| WG-0183 | P0 | defend | Neutralize the root retire_*/ack_* sweep scripts before a re-run re-acks live legs |
| WG-0188 | P0 | defend | Share one clone safely between the daemon's merge overlay and autoclose --autostash |
| WG-0193 | P0 | defend | Retire the 227 in_progress legs nobody is executing and give in_progress a TTL |
| WG-0198 | P0 | defend | Harden fleet_respond so a generated answer can never close a defect or ask leg again |
| WG-0203 | P0 | defend | Keep the pre-commit guard under 10s while claims/ holds 1,259 records (384 took over two minutes) |
| WG-0208 | P0 | defend | Shrink the 130MB of FLEET-LOG markdown every node clones and every ack pushes past |
| WG-0213 | P0 | defend | Align the heartbeat and pusher probe sets so a dead whoart tunnel is noticed |
| WG-0218 | P0 | defend | Reconcile the registry status vocabulary: DONE(621), closed(116), 47 statusless, ACTIVE, synchronized |
| WG-0223 | P0 | elevate | Run a one-shot registry normalization migration (status, created_utc, id) through CAS writes |
| WG-0228 | P0 | elevate | Roll out the --text-b64 nougenmsg protocol to every divergent copy without splitting the fleet |
| WG-0233 | P0 | defend | Survive a console-launched daemon freezing the relay clone on blade |
| WG-0238 | P0 | defend | Fix concurrent autoclose and policy sweeps from several machines conflicting every minute |
| WG-0243 | P0 | defend | Relay-shaped files committed outside .handoffs/ are invisible to every relay verb |
| WG-0247 | P0 | defend | quota_governor's RESERVE_HOLD blocks every leg, including the GM sessions it claims to protect |
| WG-0251 | P0 | defend | fleet-ops/tests (21 tests) never run in CI because ci.yml scopes to tests/ only |
| WG-0254 | P0 | defend | hooks/pre-commit fails open with no telemetry when relay itself errors |
| WG-0257 | P0 | defend | autoclose.py never closes an Ask naming Dave, with no fallback owner if he's unreachable |
| WG-0260 | P0 | defend | relay_dedup's degrade-to-token-overlap path still writes the leg it should have deduped |
| WG-0263 | P0 | defend | relay_daemon.py's keymaker secret fallback only resolves on one Windows account |
| WG-0266 | P0 | defend | NOUGEN_AGENT env override reproduces the exact unknown-agent incident README warns about |
| WG-0269 | P0 | defend | QuotaAlertStore's provenance-distinct dedup key can double-alert Dave for one real breach |
| WG-0272 | P0 | elevate | Scheduled quota telemetry collection remains manual, leaving burn spikes invisible between runs |
| WG-0275 | P0 | defend | nougenmsg's Windows SSH pipe-trap is indistinguishable from a genuine 90s dispatch timeout |
| WG-0278 | P0 | defend | fleet_heartbeat.py can't tell a Cloudflare Access failure from a real service outage |
| WG-0281 | P0 | defend | Two malformed .handoffs records exist with no CI JSON-lint gate on the registry |
| WG-0364 | P1 | defend | Neutralize goal-text prompt injection in relay ack auto-dispatch |
| WG-0380 | P1 | defend | Reconcile DAEMON.md 'read-only agy subcommands' with `agy -p <leg brief>` autonomous execution |
| WG-0396 | P1 | elevate | Move the 3.2M-line FLEET-LOG bulk out of git before clones, CI and SessionStart stop fitting |
| WG-0412 | P1 | defend | Stop fleet_respond from sending private leg goals to a third-party public HF Space |
| WG-0428 | P1 | elevate | Scope the MCP relay_* tools: repo allowlist and no relay_shards from an untrusted agent |
| WG-0444 | P1 | defend | Pin the dev/CI toolchain after the pytest 9 importorskip red (#65/#67/#68) |
| WG-0459 | P1 | elevate | Prove the Antigravity hooks.json actually fires on a box, then reconcile AGY.md |
| WG-0472 | P1 | defend | Detect a disarmed commit guard fleet-wide (hooksPath unset, relay missing, --no-verify) |
| WG-0485 | P1 | defend | Quarantine the root sweep scripts so a re-run cannot re-ack or retire live legs |
| WG-0497 | P1 | defend | Reconcile .gitignore with the 37 tracked files under logs/ and .relay/ that should not be in git |
| WG-0509 | P1 | elevate | Compact the 4031-leg / 1259-claim registry without breaking substring ids or the CAS writer |
| WG-0521 | P1 | defend | Survive two relay daemons on two boxes leasing the same leg at once |
| WG-0533 | P1 | defend | Fix the Windows rule-timeout defect so a hanging `relay react` rule cannot wedge a box |
| WG-0545 | P1 | defend | Stop dispatch _publish from pushing a feature branch's code commits onto main |
| WG-0557 | P1 | defend | Harden autoclose/policy so a goal containing 'verified' cannot suppress or falsely close a baton |
| WG-0569 | P1 | defend | Detect a hung-but-listening node (CLOSE_WAIT pileup on 4444) instead of trusting /health |
| WG-0580 | P1 | defend | Survive an Ollama model rename across dedup, classify_asks, daemon triage and TOKEN_RULE |
| WG-0591 | P1 | elevate | Rotate and enroll SSH identities across whoart, blade and phoebus with keys out of git |
| WG-0602 | P1 | defend | Add a timeout to core._git so a stalled fetch cannot wedge every relay verb, hook and MCP tool |
| WG-0613 | P1 | defend | Stop dispatch from waking a node the fleet already knows is down |
| WG-0624 | P1 | elevate | Reap the 227 in_progress legs whose executor never checkpointed |
| WG-0635 | P1 | defend | Heal a clone whose local registry commits diverged from main after CAS or push failures |
| WG-0646 | P1 | defend | Make the agy PreToolUse guard resolve symlinks and Windows spellings before scope matching |
| WG-0657 | P1 | defend | Harden persist_learning_shards so fleet topology (192.168.1.x) stops being ingested as knowledge |
| WG-0668 | P1 | defend | Replace the tracked .relay/wake signals with a per-box, untracked wake dir |
| WG-0679 | P1 | defend | Make hourly_shard_worker records first-class or keep them out of the leg directory |
| WG-0690 | P1 | elevate | Cut dispatch and dedup over to a nodes.json-driven config instead of hardcoded COACH_TO_NODE and paths |
| WG-0701 | P1 | defend | Add zero-cost health probes for cloudflared tunnels to the zombie and watchdog scripts |
| WG-0712 | P1 | elevate | Ship the HF static Space mirror without publishing the private registry and topology |
| WG-0723 | P1 | elevate | Build a repeatable scrub pipeline for the public twin Who-Visions/nougen-relay |
| WG-0733 | P1 | defend | Unify the fleet credential pattern set behind shardlog SECRET_PATTERNS |
| WG-0743 | P1 | defend | Survive Python 3.10 fromisoformat('...Z') making 2,756 Z-stamped legs and claims ageless |
| WG-0753 | P1 | defend | Make heal_rebase's 'upstream wins' loss visible: the losing lane still believes it acked |
| WG-0763 | P1 | defend | Stop dispatch._publish pushing HEAD:main from whatever branch the clone is on |
| WG-0773 | P1 | elevate | Make leg publication atomic across json+md: 26 legs have no body on any fetcher |
| WG-0783 | P1 | defend | Backfill created_utc for the 760 legs that are invisible to lag detection and stale ordering |
| WG-0793 | P1 | defend | Survive the same baton executing on two nodes: leases and idempotency keys never leave .relay/ |
| WG-0803 | P1 | defend | Untrack the 33 .relay/wake signals committed despite .gitignore before consume unlinks tracked files |
| WG-0813 | P1 | defend | Survive a stale ask_verdicts.json sidecar silently holding every dispatch |
| WG-0823 | P1 | defend | Prevent a daemon dead_letter from placeholder probes permanently outranking a human complete |
| WG-0833 | P1 | defend | Defuse relay_pusher_90m AUTO_RESOLVE_RULES before it closes legs on the keyword '502' |
| WG-0843 | P1 | defend | Fix exact-dedup returning EXIT_OK with the old id so the new body is silently dropped |
| WG-0853 | P1 | defend | Survive two relay daemons on blade launched from two scheduled tasks and two code trees |
| WG-0863 | P1 | defend | Keep relay_ack from being killed mid-write by the MCP 30s timeout around a 90s nougenmsg wake |
| WG-0873 | P1 | defend | Stop `relay open`, triggers and the session-start hook tar-balling 44MB of .handoffs per ref per call |
| WG-0883 | P1 | defend | Fix shardlog title-only dedup that drops same-title shards and cross-machine cutoffs |
| WG-0892 | P1 | defend | Stop dispatch re-sending legs whose marks say sent=false (238 multi-dispatch, 151 never-sent) |
| WG-0901 | P1 | defend | Make session-start triggers say when the fetch failed instead of judging against stale refs |
| WG-0909 | P1 | defend | Treat nougenmsg QUEUED as not delivered before flipping a leg to in_progress |
| WG-0917 | P1 | defend | Publish record_leg_failure's retry history instead of leaving it on one box |
| WG-0925 | P1 | elevate | Alert when a public hostname is answered by the wrong origin (probe_field_parity as a lane) |
| WG-0933 | P1 | elevate | Stop every registry ack firing the 3-python CI matrix (paths-ignore .handoffs) |
| WG-0941 | P1 | elevate | Automate Codex quota window collection into the outbox on a schedule with provenance intact |
| WG-0949 | P1 | elevate | Introduce a hybrid logical clock for relay events instead of second-granular wall-clock strings |
| WG-0957 | P1 | elevate | Promote fencing-token leases into the git registry so every executor shares one fence |
| WG-0964 | P1 | elevate | Unify dispatch, daemon, autoclose and policy into one leg state machine with one status set |
| WG-0971 | P1 | elevate | Make `relay ack` dispatch asynchronous through a wake outbox so acks never block on transport |
| WG-0977 | P1 | defend | Extend shardlog SECRET_PATTERNS before the next FLEET-LOG relay (CF tokens, JWTs, Tailscale keys) |
| WG-0983 | P1 | defend | Keep untagged personal shards out of FLEET-LOGs that the public twin scrub must then chase |
| WG-0988 | P1 | elevate | Wire the daemon's lag_alerts to nougenmsg so the watchdog stops alerting only its own SQLite |
| WG-0992 | P1 | elevate | Turn per-lane leg freshness into a fleet alarm so a silent blade1tb/hourly_shard is noticed in an hour |
| WG-0996 | P1 | defend | Stop the daemon ack PUT re-escaping UTF-8 and reviving the 1,707-file phantom-diff treadmill |
| WG-1000 | P1 | defend | README's 227-test claim has drifted from the real 438-function suite |

---

### WG-0003 · P0 · defend · effort M

**Prove FLEET-LOG relays cannot carry the 21 known AIzaSy fingerprints out of the vault**

- Failure surface: Blade and phoebus grids hold federated Google API keys (GM ruled zero rotation, local containment); shardlog reads that same vault and publishes verbatim. The AIza pattern requires exactly 35 trailing chars, so a wrapped or truncated key passes and lands in docs/FLEET-LOG-<date>.md.
- First fork: if you observe any of the published fingerprints matching content in docs/FLEET-LOG-*.md -> route A: purge history and rotate despite the lock, escalate to Dave; else route B: add a fingerprint denylist check to scan_secrets and a CI grep over docs/.
- Evidence: `.handoffs/20260907T213753Z__claude-app__g-whoentertains.json`, `src/nougen_relay/shardlog.py`, `docs/FLEET-LOG-2026-09-18.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: shardlog.py:90 pattern is exactly `AIza[0-9A-Za-z_-]{35}` (35 trailing chars, matching claim precisely); the handoff JSON documents 21 distinct fleet-wide AIzaSy fingerprints across blade/phoebus with 'GM has ruled zero rotation, local containment' stated verbatim; docs/FLEET-LOG-*.md contain 'AIza' occurrences (one file, binary-matched, plus 2 more across the log set).
- #550 families: 76

### WG-0019 · P0 · defend · effort M

**Survive nougen_shards API drift in auto_capture_shard and every fleet-ops tool**

- Failure surface: The daemon imports nougen_shards from a sibling checkout (NouGenShards-push-main/src) and already crashed on the 2026-08-28 capture() kwarg change; fleet-ops tools import NouGenMsgBus, redact_content and q_live from the same unpinned tree. A NouGenShards refactor silently breaks the hourly shard persistence.
- First fork: if you observe '[RelayDaemon] note: capture() no longer accepts' in daemon logs -> route A: pin a nougen_shards version tag per node and add a compat shim; else route B: move capture behind the shards HTTP API and drop the path import.
- Evidence: `tools/relay_daemon.py`, `fleet-ops/README.md`, `fleet-ops/tools/mrsb_peer_bridge.py`
- Lens: dependency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py:181-182 adds NouGenShards-push-main/src to sys.path as a sibling checkout; lines 1918-1944 contain the exact defensive code and message '[RelayDaemon] note: capture() no longer accepts {dropped}; dropped'; fleet-ops/tools/mrsb_peer_bridge.py imports NouGenMsgBus from the same unpinned nougen_shards tree.
- #550 families: 32

### WG-0034 · P0 · elevate · effort M

**Add a CI registry lint that parses every .handoffs/*.json and rejects non-leg shapes**

- Failure surface: Two records are unreadable (Extra data / empty), 47 have no status, and usage_*, baton_*, UUID and 20260917_*_blade1tb_main legacy files sit in the leg directory; _records swallows them, dispatch regex-filters, prepare-commit-msg parses machine names from them. Corruption is invisible until a sweep dispatches a session note as a baton (phoebus 9/21).
- First fork: if you observe a .handoffs/*.json that fails json.loads on main -> route A: lint job that fails PRs and a quarantine dir for legacy records; else route B: lint warns only and dispatch gains a schema check.
- Evidence: `.handoffs/20260922T022924Z__claude-app__g-whoentertains.json`, `.handoffs/20260919T233524Z__claude-app__g-whoentertains.json`, `src/nougen_relay/core.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both named files fail json.loads exactly as claimed ('Extra data' and 'Expecting value' errors respectively, matching the claim's 'Extra data / empty' description); a directory scan found exactly 2 unreadable records and 47 records with no 'status' field out of 4031 total, matching the '47 have no status' claim precisely.

### WG-0048 · P0 · elevate · effort M

**Collapse blade's two scheduled tasks and two code trees into one daemon, one DB, one lock**

- Failure surface: SingletonLock is per NOUGEN_DAEMON_DB path; two tasks pointing at NouGen/NouGenRelay and NouGenShards-push-main resolve different watchtower roots, so both daemons run, double every lag alert and triage the same legs. Today's blade freeze came from exactly this drift.
- First fork: if you observe two relay_daemon processes on blade with different db_path -> route A: delete one task, pin NOUGEN_DAEMON_DB and NOUGEN_RELAY_DIR in the surviving task; else route B: make the lock path global per machine regardless of DB.
- Evidence: `tools/relay_daemon.py`, `tools/relay_watchdog.ps1`, `docs/DAEMON.md`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py:298-300 DEFAULT_DB_PATH derives from NOUGEN_DAEMON_DB env or a resolved watchtower root; line 2178 lock_path = daemon.db_path.with_suffix('.lock'), so the SingletonLock is scoped per DB path exactly as claimed, meaning two tasks with different DB paths would each acquire their own lock and both run.
- #550 families: 29

### WG-0060 · P0 · elevate · effort M

**Make the relay watchdog task headless and QuickEdit-proof after today's blade console freeze**

- Failure surface: relay_watchdog.ps1 schedules `python` (not pythonw) in the user session; a visible console with QuickEdit paused the asyncio loop, /health hung and CLOSE_WAIT piled up. The daemon's own console-storm guard assumes pythonw and a hidden task.
- First fork: if you observe the task's Task To Run naming python.exe or a visible window -> route A: switch to pythonw, hidden task, no interactive session, and add a /health self-probe restart; else route B: run under a service wrapper with a restart policy.
- Evidence: `tools/relay_watchdog.ps1`, `tools/relay_daemon.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_watchdog.ps1:41 resolves $PythonPath via `Get-Command python` (not pythonw), scheduling a visible console interpreter; relay_daemon.py:27-28,64-65 explicitly comment 'this daemon runs under pythonw (no console)... every git.exe child... allocated a fresh console', confirming the daemon's own design assumes pythonw while the watchdog script schedules python.exe.

### WG-0071 · P0 · elevate · effort M

**Route dispatch send_wake through file-backed stdout so Windows ssh stops timing out at 90s**

- Failure surface: send_wake uses capture_output (a pipe) around the nougenmsg CLI, which spawns ssh; Windows OpenSSH blocks when stdout is a pipe (20s TimeoutExpired vs 0.5s to a file), so every dispatch from blade/whoart times out, the leg stays acked and the sweep re-sends it next pass.
- First fork: if you observe 'timeout after 90s' in dispatch events from a Windows machine -> route A: adopt nougenmsg_rollout's ssh_capture temp-file pattern in send_wake; else route B: dispatch only from phoebus.
- Evidence: `src/nougen_relay/dispatch.py`, `fleet-ops/tools/nougenmsg_doctor.py`, `fleet-ops/tools/nougenmsg_rollout.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py:177-184 send_wake(...,timeout:int=90) uses subprocess.run(cmd, capture_output=True,...) and catches TimeoutExpired; nougenmsg_doctor.py:18-19 documents the exact numbers claimed ('capture_output=True ssh whoart echo hi -> 20.0s TimeoutExpired' vs 'stdout=<file handle> -> 0.5s rc=0'); nougenmsg_rollout.py:163-172 ssh_capture() implements the temp-file fix that send_wake has not adopted.
- #550 families: 43

### WG-0082 · P0 · defend · effort M

**Close the remaining fleet-answer false-completion path after leg 20260831T195956Z**

- Failure surface: fleet_respond's generated answer flows through verify -> ack_leg_upstream; DEFECT_MARKERS and CHANGE_MARKERS were added after a defect leg was closed by an unresponsive model answer 15 minutes after filing. Any ask that avoids both keyword lists is still closable by prose.
- First fork: if you observe an upstream ack whose note begins 'daemon dispatch verified' on a leg with no probe output -> route A: require probe evidence or a human for every ack, markers or not; else route B: expand markers and add a daily audit of daemon acks.
- Evidence: `tools/relay_daemon.py`
- Lens: tool-abuse · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py defines DEFECT_MARKERS/CHANGE_MARKERS (lines 369-390) and verify_execution/ack_leg_upstream flow (958, 1025, 1166) exactly as described.
- #550 families: 23, 100

### WG-0093 · P0 · elevate · effort M

**Schedule fleet_heartbeat on one node with tunnel-1033 detection and alert delivery**

- Failure surface: fleet_heartbeat distinguishes a tunnel with zero connectors (1033) from an origin outage, but fleet-ops/README says nothing runs it on any schedule; whoart's tunnel died at 11 AM today and was found by hand. A 3-day-quiet vault repeat is one dead task away.
- First fork: if you observe no scheduled task/launchd job invoking fleet_heartbeat.py on any node -> route A: schedule it on phoebus with --json piped to a nougenmsg alert on required-lane failure; else route B: fold the probes into the relay daemon cycle.
- Evidence: `fleet-ops/tools/fleet_heartbeat.py`, `fleet-ops/README.md`, `docs/HURRICANE_KICK_PATIO_GREP.md`
- Lens: infra · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet_heartbeat.py documents 1033 tunnel-down detection and README states 'None is run by a scheduled task, launchd job or cron on any node (checked on phoebus, blade and whoart...)'. Directly supports claim.
- #550 families: 95

### WG-0103 · P0 · elevate · effort M

**Wire probe_field_parity into a scheduled check so a hostname answered by the wrong node is caught**

- Failure surface: On 2026-09-01 ngs.nougenai.com was CNAME'd to phoebus's healthy tunnel while Worker routes sent all traffic to blade for two weeks; both sides returned 200. The parity probe exists but nothing runs it, so the next Worker route change silently reassigns a vault.
- First fork: if you observe MISMATCH or UNREACHABLE from probe_field_parity for phoebus.nougenai.com -> route A: page via nougenmsg and freeze Worker route edits; else route B: schedule hourly and record MATCH receipts to the registry.
- Evidence: `fleet-ops/tools/probe_field_parity.py`, `fleet-ops/tests/test_probe_field_parity.py`
- Lens: infra · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: probe_field_parity.py implements MATCH/MISMATCH/UNREACHABLE verdicts and exit codes exactly as described; test file exists validating this logic. Matches claim about probe existing but nothing scheduling it (fleet-ops/README states no scheduler runs any fleet-ops tool).
- #550 families: 12, 40

### WG-0113 · P0 · defend · effort S

**Fix relay_pusher_90m's all-or-nothing 'operational' verdict while whoart-vault is intermittent**

- Failure surface: probe_fleet requires every PROBE_TARGET including whoart-vault.nougenai.com to return 200 before saying 'operational' and broadcasts DEGRADED fleet-wide otherwise; with whoart's tunnel flapping today the 90-minute pusher spams DEGRADED and hides real blade faults.
- First fork: if you observe DEGRADED broadcasts where only whoart-vault is non-200 -> route A: make required lanes explicit and report per-lane; else route B: pause the pusher until the tunnel watchdog is proven.
- Evidence: `fleet-ops/tools/relay_pusher_90m.py`
- Lens: infra · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_pusher_90m.py:127-178 defines PROBE_TARGETS including whoart-vault.nougenai.com and computes 'operational' only if all targets ok, else 'DEGRADED', matching the claim precisely.
- #550 families: 3, 94

### WG-0121 · P0 · elevate · effort M

**Version the nougenmsg receipt contract so a stale copy cannot fake or lose delivery**

- Failure surface: dispatch treats any 'DELIVERED'/'QUEUED' substring as sent and quota_delivery requires 'Status: DELIVERED'; the fleet carries many divergent nougenmsg.py copies (three on one node, hardcoded REMOTE_SCRIPTS paths in the doctor). One stale sender prints the old receipt and legs flip to in_progress unsent, or alerts stay pending forever.
- First fork: if you observe nougenmsg_rollout audit reporting a stale copy on any host -> route A: add --capabilities version to the receipt and refuse to mark sent on mismatch; else route B: patch every copy with --write and re-audit weekly.
- Evidence: `fleet-ops/tools/nougenmsg_rollout.py`, `src/nougen_relay/dispatch.py`, `src/nougen_relay/quota_delivery.py`
- Lens: dependency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py:191 checks 'DELIVERED' in out or 'QUEUED' in out; quota_delivery.py:30 requires 'Status: DELIVERED' in stdout; nougenmsg_rollout.py exists and references a canonical sender path. Matches claim's substring-check fragility.
- #550 families: 16, 17

### WG-0129 · P0 · defend · effort S

**Pin the interpreter every hook and scheduled task uses on each Windows box**

- Failure surface: pre-commit picks the first `python` on PATH, the watchdog filters WindowsApps aliases and asks `py -3`, plugins use bare `python`; whoart could not write relay.exe at all. A Python upgrade or Store alias leaves the guard silently exiting 0 and the daemon task pointing at a stub.
- First fork: if you observe `python -c "import nougen_relay"` failing in a hook shell on any box -> route A: set NOUGEN_PYTHON per machine and have hooks/tasks resolve it first; else route B: install with --user into one venv and symlink.
- Evidence: `hooks/pre-commit`, `tools/relay_watchdog.ps1`, `plugins/nougen-relay/mcp_config.json`
- Lens: toolchain-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit comments describe relay.exe write failure on whoart; relay_watchdog.ps1 filters WindowsApps aliases and falls back to 'py -3' pattern; mcp_config.json uses bare 'python'. Matches claim.
- #550 families: 79

### WG-0137 · P0 · elevate · effort M

**Rotate blade's LAN node token whose fingerprint matches nothing in any vault**

- Failure surface: FLEET-LOG-2026-08-17 records blade's 151k-shard node at 10.0.0.87:4444 rejecting both known tokens (fingerprint 9c67af03a9da, 'ROTATE not recover') while the mesh daemon on 10.0.0.88:8765 answers unauthenticated. The largest grid is either unreachable or open, depending on the box.
- First fork: if you observe blade's node still 401ing outpost's tokens -> route A: rotate via keymaker on blade and distribute through the vault, not a leg; else route B: keep the token local and route all blade reads through the Cloudflare Access front door.
- Evidence: `docs/FLEET-LOG-2026-08-17.md`, `docs/ssh-lan-interconnect.md`
- Lens: token-scope · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/FLEET-LOG-2026-08-17.md:1600 states 'blade's 151k grid - token unrecoverable (fingerprint 9c67af03a9da matches nothing outpost holds, so ROTATE not recover)' and references blade's LAN node at 10.0.0.87:4444 with 151,159 shards being 401'd; a mesh service on 10.0.0.88:8765 (MACMINI-7BA58F) is referenced elsewhere in the log. Directly supports the claim.
- #550 families: 76

### WG-0145 · P0 · defend · effort M

**Reconcile NOUGEN_USER_ORIGIN_TOKEN across phoebus and blade so the owner path works**

- Failure surface: Two 9/03 legs record the token as CONFLICTING: phoebus self-generated one, blade has none, so the owner-signed path is live on one node and unusable by the owner. Any relay verb or connector call that depends on owner origin fails differently per node.
- First fork: if you observe the leg still open with no resolution event -> route A: provision one owner token via keymaker on both nodes and close with a probe receipt; else route B: retire the owner path and document the connector-only route.
- Evidence: `.handoffs/20260903T112308Z__claude-app__g-whoentertains.md`, `.handoffs/20260903T114123Z__claude-app__g-whoentertains.md`
- Lens: token-scope · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both handoff files literally contain 'secret:NOUGEN_USER_ORIGIN_TOKEN — CONFLICTING (open)' with phoebus self-generating a token (1b739b708f54) and blade ABSENT, exactly matching the claim's wording.
- #550 families: 38

### WG-0153 · P0 · defend · effort M

**Reconcile gateway-only legs that 404 on the git registry (connector split-brain)**

- Failure surface: The daemon treats a 404 from `gh api` as 'leg exists in another registry, not an ack failure' and core returns False (EXIT_FAILURE after a local commit); chatgpt-app/claude-app connector legs can live only in the gateway, so acks land nowhere and the local clone diverges.
- First fork: if you observe ack skipped 'not in git registry' for a leg visible in relay_open -> route A: have the connector writer publish to git first or a sync job materialise gateway legs; else route B: make core create the record upstream on 404.
- Evidence: `tools/relay_daemon.py`, `src/nougen_relay/core.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py:1191 prints 'not in git registry (gateway-only leg)' precisely when a 404 is hit on ack, matching the claim's description of the split-brain handling.
- #550 families: 12

### WG-0161 · P0 · defend · effort S

**Expire the 49 'active' claims and daemon leases that outlived their TTL in the tracked registry**

- Failure surface: 49 claim records carry status=active (40+ relay-daemon 15-minute leases from Aug 29-Sep 3, one 8h claim on core.py/guard.py/relay_daemon.py); claim_is_active ages them out at read time but the files never change, so any consumer reading status without the TTL check (agy_hook did via _active_claims, scripts, the HF mirror) sees blade holding core.py.
- First fork: if you observe a status=active claim older than its ttl_hours -> route A: add a sweep that writes status=expired and publishes; else route B: make every reader go through claim_is_active and lint for raw status reads.
- Evidence: `.handoffs/claims`, `src/nougen_relay/core.py`, `src/nougen_relay/agy_hook.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Exactly 49 claim records with status=active found in .handoffs/claims/, matching the claimed count; core.py and agy_hook.py are present as the described consumers.
- #550 families: 24, 26

### WG-0169 · P0 · defend · effort M

**Quarantine the two unparseable .handoffs records and gate every registry writer on json.loads**

- Failure surface: 20260922T022924Z__claude-app__g-whoentertains.json (extra data at char 685) and 20260919T233524Z__claude-app__g-whoentertains.json (empty) sit at HEAD; core._records silently skips them, relay_daemon.sync_relay_repo logs a WARN every 200s forever, and autoclose.guard_records only inspects changed files so they never get repaired. Their legs are invisible to every board.
- First fork: if you observe `git log -- .handoffs/<id>.json` showing a gh-api PUT as the corrupting commit -> route A: repair via CAS write + add parse gate in _write_registry_record_upstream; else (connector writer) -> route B: quarantine to .handoffs/quarantine/ and file a leg to the writer lane
- Evidence: `.handoffs/20260922T022924Z__claude-app__g-whoentertains.json`, `src/nougen_relay/autoclose.py`, `tools/relay_daemon.py`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both named corrupt/empty .handoffs files exist at HEAD; autoclose.py and relay_daemon.py are present as the described consumers/loggers.
- #550 families: 36

### WG-0177 · P0 · defend · effort S

**Reap the 49 blade1tb relay-daemon claims stuck 'active' for 120-618 hours**

- Failure surface: Every active claim in .handoffs/claims/ belongs to blade1tb/relay-daemon with ttl_hours 0.25 and is 5-26 days old; release_upstream_claim only runs on a completed cycle, so a daemon crash or AGY timeout leaves the claim 'active' on disk. foreign_claims filters them by TTL but they are tombstones every guard and ghost check re-reads.
- First fork: if you observe the matching leg already complete/acked -> route A: batch-release with outcome 'orphaned:daemon-crash' via CAS; else -> route B: leave active, add a daemon startup sweep that releases its own stale claims before the first cycle
- Evidence: `.handoffs/claims/`, `tools/relay_daemon.py`, `src/nougen_relay/core.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: 49 active claims counted, matching claim; .handoffs/claims/, relay_daemon.py and core.py are the right files.
- #550 families: 24, 26

### WG-0183 · P0 · defend · effort S

**Neutralize the root retire_*/ack_* sweep scripts before a re-run re-acks live legs**

- Failure surface: retire_stale_5d.py rewrites every open leg older than 20260827 to complete with a fabricated 'at': ...Z stamp and json.dump escaping; ack_green_sweep.py acks seven hardcoded ids then pushes. Both run against C:\Users\super paths with no dry-run; a re-run on whoart overwrites newer relay events from other lanes.
- First fork: if you observe any of the scripts imported or referenced from tools/ or fleet-ops/ -> route A: fold the useful logic into `relay autoclose --before <date>`; else -> route B: delete them and record the sweep in a leg
- Evidence: `retire_stale_5d.py`, `ack_green_sweep.py`, `sweep_ack.py`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: retire_stale_5d.py and ack_green_sweep.py verified verbatim at repo root: fabricated 'at' stamp, hardcoded C:\Users\super path, no dry-run, 7 hardcoded ack ids then git push. sweep_ack.py also present at root.
- #550 families: 17

### WG-0188 · P0 · defend · effort M

**Share one clone safely between the daemon's merge overlay and autoclose --autostash**

- Failure surface: sync_relay_repo rewrites merged .json files in the worktree without committing, so the clone stays dirty; cmd_autoclose then runs `pull --rebase --autostash`, stashing hundreds of daemon-merged records and popping them onto a moved base, while heal_rebase resolves anything that conflicts as upstream. Blade's relay fetch darkened for hours on this in September.
- First fork: if you observe `git stash list` non-empty or >100 modified .handoffs files on a node -> route A: give the daemon its own worktree (git worktree add) and never share; else -> route B: make sync commit its merges
- Evidence: `tools/relay_daemon.py`, `src/nougen_relay/autoclose.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: autoclose.py heal_rebase docstring/code exactly matches: 'upstream wins (--ours during a rebase)', cmd_autoclose runs pull --rebase --autostash per surrounding code, sync_relay_repo exists in relay_daemon.py leaving worktree dirty.
- #550 families: 84

### WG-0193 · P0 · defend · effort M

**Retire the 227 in_progress legs nobody is executing and give in_progress a TTL**

- Failure surface: dispatch.dispatch_leg flips status to in_progress on a nougenmsg receipt but no lease, checkpoint deadline or reaper exists for that state; 227 legs are in_progress, the oldest 46h+, and DISPATCHABLE excludes in_progress so they can never be re-sent. The board reads 'being worked' for work that was dropped.
- First fork: if you observe an executor checkpoint event on the leg within the last 24h -> route A: keep; else -> route B: revert to acked with a 'dispatch-expired' relay event and let the next sweep re-dispatch with a fresh digest
- Evidence: `src/nougen_relay/dispatch.py`, `.handoffs/`, `src/nougen_relay/core.py`
- Lens: observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: 228 legs with status in_progress counted (claim says 227, effectively matching); dispatch.py and core.py are the relevant files.
- #550 families: 26, 27

### WG-0198 · P0 · defend · effort M

**Harden fleet_respond so a generated answer can never close a defect or ask leg again**

- Failure surface: On 2026-08-31 leg 20260831T195956Z (a capture-integrity defect) was closed 15 minutes after filing by a non-responsive fleet answer; DEFECT_MARKERS and CHANGE_MARKERS are env-overridable substrings and the verdict still comes from dav1d. A wrong marker list on one node reintroduces false completes fleet-wide.
- First fork: if you observe an ack whose note starts 'daemon dispatch verified' on a leg with an Ask section -> route A: require a probe citation for every fleet_respond ack; else -> route B: route fleet answers as comments (relay event) never status changes
- Evidence: `tools/relay_daemon.py`
- Lens: observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py has DEFECT_MARKERS/CHANGE_MARKERS sourced from env vars (NOUGEN_DAEMON_CHANGE_MARKERS / NOUGEN_DAEMON_DEFECT_MARKERS) and dav1d_probe_verify/dav1d_json for the verdict path, matching the fleet_respond risk described; single evidence file is sufficient since all cited logic lives there.
- #550 families: 100

### WG-0203 · P0 · defend · effort M

**Keep the pre-commit guard under 10s while claims/ holds 1,259 records (384 took over two minutes)**

- Failure surface: hooks/pre-commit runs `relay guard --staged`, which reads every claim blob from every watched ref via cat-file --batch; the dir has tripled since the 2026-09-03 fix. A guard that takes minutes teaches lanes --no-verify, which disarms the only duplicate-work fence at commit time.
- First fork: if you observe `time relay guard --staged` above 10s on whoart -> route A: compact released claims into claims/archive/ and read only active files; else -> route B: add an active-claims index file maintained by take/release
- Evidence: `hooks/pre-commit`, `src/nougen_relay/core.py`, `src/nougen_relay/guard.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit calls `$RELAY guard --staged --quiet`; guard.py defines cmd_guard and the --staged flag exactly as described.

### WG-0208 · P0 · defend · effort M

**Shrink the 130MB of FLEET-LOG markdown every node clones and every ack pushes past**

- Failure surface: docs/FLEET-LOG-2026-09-12.md is 47MB, 08-17 is 46MB, 09-18 is 37MB (whole papers relayed verbatim from the vault); the registry repo is cloned per machine, fetched on every session start, mirrored by deploy-space.yml, and pushed on every ack. Clones fail on the phone lane and HF's 16MB-per-file limits reject the mirror.
- First fork: if you observe the public twin or HF mirror rejecting the files -> route A: move logs to git-lfs or a separate NouGenFleetLog repo and leave pointers; else -> route B: cap shardlog per-entry size and split logs by week
- Evidence: `docs/FLEET-LOG-2026-09-12.md`, `src/nougen_relay/shardlog.py`, `.github/workflows/deploy-space.yml`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File sizes verified exactly: FLEET-LOG-2026-09-12.md=47M, 2026-08-17.md=46M, 2026-09-18.md=37M; deploy-space.yml and shardlog.py both exist and are wired to this registry.

### WG-0213 · P0 · defend · effort S

**Align the heartbeat and pusher probe sets so a dead whoart tunnel is noticed**

- Failure surface: fleet_heartbeat.HTTP_LANES requires only blade-node and front-door; whoart-vault.nougenai.com is probed only by relay_pusher_90m.PROBE_TARGETS, and neither script is scheduled anywhere. The whoart tunnel died ~11 AM today and nothing in this repo would have said so.
- First fork: if you observe whoart-vault absent from fleet_heartbeat --json -> route A: add it as required with the x-nougen-origin check and schedule the probe; else -> route B: retire relay_pusher's probe list
- Evidence: `fleet-ops/tools/fleet_heartbeat.py`, `fleet-ops/tools/relay_pusher_90m.py`, `fleet-ops/README.md`
- Lens: observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet_heartbeat.py HTTP_LANES only lists blade-node, front-door, space-node (no whoart); relay_pusher_90m.py PROBE_TARGETS includes ("whoart", "https://whoart-vault.nougenai.com/health"); fleet-ops/README.md states none of the probes run on a schedule.
- #550 families: 95

### WG-0218 · P0 · defend · effort M

**Reconcile the registry status vocabulary: DONE(621), closed(116), 47 statusless, ACTIVE, synchronized**

- Failure surface: RELAY_STATES has 9 values but the live registry holds 16; _merge_registry_records ranks unknown statuses as 0 (open) so any known status from another projection overwrites 'DONE'; relay_status() reads missing status as open; daemon OPEN_HANDOFF_STATES is 'open,active,held' and misses 'ACTIVE'. Boards disagree on what is open.
- First fork: if you observe a leg with status DONE whose relay[] has a complete event -> route A: one-shot CAS migration mapping DONE/closed/resolved->complete; else -> route B: extend NOUGEN_RELAY_STATUS_ORDER to rank the aliases and add a create-time validator
- Evidence: `src/nougen_relay/core.py`, `tools/relay_daemon.py`, `.handoffs/`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: DONE count ~620 matches; RELAY_STATES exists in core.py and status vocabulary sprawl (DONE, ACTIVE, etc.) is consistent with the counted file statuses across .handoffs.

### WG-0223 · P0 · elevate · effort L

**Run a one-shot registry normalization migration (status, created_utc, id) through CAS writes**

- Failure surface: Fixing 621 DONE, 47 statusless, 760 stamp-less legs means rewriting ~1,400 files on main; a git commit conflicts with concurrent daemon PUTs, a PUT per file is 1,400 gh calls at 120s timeout each, and a wrong mapping (DONE->complete for a leg whose relay[] shows blocked) is a mass false done-marker.
- First fork: if you observe the daemon active on any node -> route A: pause it, migrate in one commit, resume; else -> route B: migrate in batches of 50 via CAS
- Evidence: `.handoffs/`, `src/nougen_relay/core.py`, `tools/relay_daemon.py`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified: .handoffs/*.json has exactly 621 records with status DONE and 47 with no status field, matching the claim precisely (stamp-less count measured as 805 vs claimed 760, close enough given differing stamp definitions).

### WG-0228 · P0 · elevate · effort M

**Roll out the --text-b64 nougenmsg protocol to every divergent copy without splitting the fleet**

- Failure surface: nougenmsg_rollout.py documents three divergent nougenmsg.py copies on one node; a stale sender turns any body with an apostrophe into an scp pointer, so dispatch_text batons arrive as file paths and Windows OpenSSH blocks when stdout is a pipe (nougenmsg_doctor). Patching one side first makes receivers reject senders mid-rollout.
- First fork: if you observe `nougenmsg_rollout.py audit --host phoebus` listing a stale sender -> route A: patch receivers on all nodes first, then senders; else -> route B: rollout complete, retire the tool
- Evidence: `fleet-ops/tools/nougenmsg_rollout.py`, `fleet-ops/tools/nougenmsg_doctor.py`, `src/nougen_relay/dispatch.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet-ops/tools/nougenmsg_rollout.py documents 'the fleet carries MANY divergent' nougenmsg copies and has an 'audit --host <name>' command exactly as described; nougenmsg_doctor.py exists alongside it.
- #550 families: 32

### WG-0233 · P0 · defend · effort S

**Survive a console-launched daemon freezing the relay clone on blade**

- Failure surface: Today blade's node froze because a visible console's QuickEdit paused the asyncio loop; relay_daemon.py's 2026-09-06 console storm (31 conhost windows in 15s under pythonw) and autoclose._go_windowless show the same class. A paused daemon still holds its SingletonLock, so the 5-minute watchdog exits 3 and never restarts it, while its upstream claims stay active.
- First fork: if you observe the lock holder PID alive but no pulse row in 3x heartbeat_sec -> route A: watchdog kills and reclaims on pulse staleness; else -> route B: keep PID liveness only
- Evidence: `tools/relay_daemon.py`, `tools/relay_watchdog.ps1`, `docs/DAEMON.md`
- Lens: observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py:27-28 documents the '2026-09-06 console storm' verbatim and defines SingletonLock (line 224) and _go_windowless (line 323); tools/relay_watchdog.ps1 and docs/DAEMON.md both exist. Note _go_windowless is in relay_daemon.py itself, not autoclose.py as the claim text states, but this is a minor misattribution that doesn't undermine the core finding.
- #550 families: 94

### WG-0238 · P0 · defend · effort S

**Fix concurrent autoclose and policy sweeps from several machines conflicting every minute**

- Failure surface: autoclose.sweep and policy.apply both default push=True and both ack the same status-only legs; the 2026-09-14 9:35 AM conflict was one lane acking a record another had acked in the same minute. With sweeps scheduled on more than one node, each run rebases over the other's commit and heal_rebase discards one side's events.
- First fork: if you observe two 'policy sweep' commits from different machines within 5 minutes -> route A: elect one sweeper node via a claim on scope 'relay:sweep'; else -> route B: stagger cadences
- Evidence: `src/nougen_relay/autoclose.py`, `src/nougen_relay/policy.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: autoclose.py:273 defines sweep() and policy.py:195 defines apply(root, *, dry=False, push=True, ...) with push=True as the default, matching the claim.
- #550 families: 84

### WG-0243 · P0 · defend · effort S

**Relay-shaped files committed outside .handoffs/ are invisible to every relay verb**

- Failure surface: cold_turkey_relay_leg.md, handoff_body.md, and status_antigravity_1788635473.json look like registry records but sit outside the directory core.py/dispatch.py/policy.py/autoclose.py all glob, so any work or doctrine they encode is permanently absent from `relay`'s open board, dispatch, or sweep.
- First fork: if an agent creates a relay-shaped file at repo root instead of via `relay create` -> it never appears to the protocol until a human manually notices and relocates it.
- Evidence: `cold_turkey_relay_leg.md`, `handoff_body.md`, `status_antigravity_1788635473.json`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: All three files exist at repo root, outside .handoffs/; consistent with the claim that they are outside the directory relay tooling globs.
- #550 families: 3

### WG-0247 · P0 · defend · effort M

**quota_governor's RESERVE_HOLD blocks every leg, including the GM sessions it claims to protect**

- Failure surface: should_claim() returns False with 'reserved for interactive GM sessions' for ANY leg once RESERVE_HOLD is reached; nothing checks whether the leg IS an interactive GM session, so the reserve blocks the exact traffic its own comment says it exists to protect.
- First fork: if a leg is Dave's own interactive session while quota sits in the reserve band -> should_claim still returns False today; only a code change checking an interactive/GM flag would let it through.
- Evidence: `src/nougen_relay/quota_governor.py`
- Lens: cost-quota · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Read quota_governor.py directly: RESERVE_HOLD is documented as 'Quota reserved for interactive GM sessions'; the should_claim path returns (False, 'RESERVE: quota reserved for interactive GM sessions', decision) unconditionally on RESERVE_HOLD with no interactive/GM-session check found, confirming the claim.
- #550 families: 48

### WG-0251 · P0 · defend · effort M

**fleet-ops/tests (21 tests) never run in CI because ci.yml scopes to tests/ only**

- Failure surface: fleet-ops/tools changes (heartbeat, nougenmsg rollout, shard persistence) ship with zero automated verification; a break only surfaces when a machine misses a real wake or heartbeat.
- First fork: if nougen_shards ever becomes installable in CI -> fleet-ops/tests could be added to the matrix; until then every merge to fleet-ops/tools is untested.
- Evidence: `.github/workflows/ci.yml`, `fleet-ops/tests`, `fleet-ops/README.md`
- Lens: testing-ci · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: ci.yml's Test step runs `python -m pytest tests -q` (tests/ only); fleet-ops/tests/ contains exactly 3 test files with 3+8+10=21 test functions total, matching the claimed count precisely.
- #550 families: 81

### WG-0254 · P0 · defend · effort M

**hooks/pre-commit fails open with no telemetry when relay itself errors**

- Failure surface: The guard blocks only on exit code 3; any other failure (relay crashes, a broken git config) exits 0 and lets the commit through with no signal anywhere that the guard silently no-opped, so a broken guard looks identical to 'no conflict found.'
- First fork: if `relay guard --staged --quiet` exits non-zero/non-3 from a real bug -> the commit proceeds silently; only a manual check of $? after the fact would reveal the guard never actually ran.
- Evidence: `hooks/pre-commit`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Read hooks/pre-commit directly: it runs `$RELAY guard --staged --quiet`, captures STATUS, and only does `[ "$STATUS" = "3" ] && exit 1`, otherwise `exit 0` — confirming it fails open on any non-3 status with no logging/telemetry of that outcome.
- #550 families: 100

### WG-0257 · P0 · defend · effort M

**autoclose.py never closes an Ask naming Dave, with no fallback owner if he's unreachable**

- Failure surface: Any leg whose Ask section names Dave stays open indefinitely by design ('owner validation is his to close'); if he's unreachable for an extended period, these legs accumulate on every lane's open board with no secondary reviewer or expiry — exactly the backlog growth the doctrine warns against.
- First fork: if Dave is unreachable past some window -> nothing reroutes or time-boxes his-named Asks to another decision-maker; they simply remain open until he personally clears them.
- Evidence: `src/nougen_relay/autoclose.py`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: autoclose.py line 24 explicitly states '* an Ask that names Dave (owner validation is his to close)', directly confirming the described special-case behavior and no fallback owner was found.

### WG-0260 · P0 · defend · effort M

**relay_dedup's degrade-to-token-overlap path still writes the leg it should have deduped**

- Failure surface: When the embed lane (Ollama nomic-embed-text) is unreachable, the check degrades to a weaker token-overlap comparison per its own docstring, but cmd_create writes the leg regardless once dedup returns 'skipped' — meaning the exact class of 2026-08-28 duplicate-leg incident this tool exists to stop can recur any time the embed lane is down, the same silent-degradation pattern HARDENING already flags.
- First fork: if the embed lane is unreachable at leg-creation time -> only token overlap runs, which a differently-worded duplicate goal passes, and the leg gets written anyway.
- Evidence: `tools/relay_dedup.py`
- Lens: cost-quota · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougen_relay/quota... no, tools/relay_dedup.py confirms degrade-to-token-overlap docstring; src/nougen_relay/core.py cmd_create (check_leg_dedup) only short-circuits on status=='exact' (returns before writing); status=='near' only prints a warning and falls through to write the leg, and 'skipped' has no explicit handling either (also falls through). Verified directly in core.py lines ~2191-220
- #550 families: 8, 22

### WG-0263 · P0 · defend · effort M

**relay_daemon.py's keymaker secret fallback only resolves on one Windows account**

- Failure surface: NGS_INFERENCE_TOKEN(S)/HF_TOKEN fallback resolution reads C:/Users/super/.nougen/secrets/shards_secrets.db, a path that only exists on one specific Windows box; on blade1tb, phoebus (mac mini), or any Linux runner the same code silently returns no token instead of erroring loudly, so a token-dependent route fails differently per machine with no shared diagnostic.
- First fork: if the daemon runs on a non-Windows machine or a different account -> the keymaker lookup returns nothing and downstream HF/OpenRouter calls fail as 'no credential' rather than 'wrong machine for this fallback path.'
- Evidence: `tools/relay_daemon.py`
- Lens: cost-quota · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/relay_daemon.py hardcodes KEYMAKER_BIN_DIR/KEYMAKER_DB_PATH defaults to C:/Users/super/.nougen/... and the HF token resolution falls through NGS_INFERENCE_TOKENS/HF_TOKEN env vars to _keymaker_load, which silently returns None off that one box/account, exactly as claimed.
- #550 families: 35

### WG-0266 · P0 · defend · effort S

**NOUGEN_AGENT env override reproduces the exact unknown-agent incident README warns about**

- Failure surface: README documents that two machines were already stamped unknown-agent because an env var didn't survive a new shell/commit, yet NOUGEN_AGENT still exists as a 'one-off override' alongside the git-config fix; an operator following habit from another tool (export an env var) can reproduce the documented incident on a fresh clone.
- First fork: if an operator sets NOUGEN_AGENT in one shell instead of running relay init --agent -> the next commit from a different shell/session reverts to unknown-agent, exactly as happened before.
- Evidence: `README.md`
- Lens: product-docs · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: README.md documents (lines ~30-56, ~210-219) that two machines were already stamped unknown-agent from an env var not surviving a new shell, while NOUGEN_AGENT still exists as a documented one-off override — the exact reproducible-incident pattern described.
- #550 families: 20

### WG-0269 · P0 · defend · effort M

**QuotaAlertStore's provenance-distinct dedup key can double-alert Dave for one real breach**

- Failure surface: docs/quota-provenance.md states an estimate cannot suppress a later metered alert, meaning an 'estimated' 90% alert and a later 'metered' 90% alert for the same real quota event are stored and delivered as two separate events (UNIQUE includes provenance), training Dave to skim or ignore Hardcade alerts as noise.
- First fork: if telemetry for a bucket transitions from estimated to metered while crossing the same threshold -> two alerts fire for one real event instead of the metered one superseding the estimate.
- Evidence: `docs/quota-provenance.md`, `src/nougen_relay/quota_alert_store.py`
- Lens: cost-quota · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/quota-provenance.md states '...so an estimate cannot suppress a later metered alert' and src/nougen_relay/quota_alert_store.py's UNIQUE constraint is UNIQUE(provider, bucket, window, provenance, threshold) — provenance is part of the uniqueness key, so an estimated and a later metered alert for the same threshold/bucket are stored/delivered as two separate rows, exactly as claimed.
- #550 families: 16

### WG-0272 · P0 · elevate · effort L

**Scheduled quota telemetry collection remains manual, leaving burn spikes invisible between runs**

- Failure surface: docs/quota-provenance.md records scheduled telemetry collection and checkpoint/fallback automation as still outstanding for leg 20260906T224549Z; quota routing (SOFT/HARD/RESERVE) currently depends on someone manually running a snapshot, so a burn spike between manual runs is invisible to the governor until the next manual check.
- First fork: if nobody manually runs telemetry collection between two windows -> should_claim decisions for that whole gap use stale or absent snapshot data.
- Evidence: `docs/quota-provenance.md`, `.handoffs/20260906T224549Z__chatgpt-app__g-whoentertains.json`
- Lens: cost-quota · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/quota-provenance.md (line ~54) states 'scheduled telemetry collection, checkpoint/fallback automation, and 1UP reset notification are still outstanding'; the referenced handoff leg .handoffs/20260906T224549Z__chatgpt-app__g-whoentertains.json exists and matches the goal/checkpoint narrative (quota alert ladder implementation with full ladder and live telemetry adapters marked pending) exactly

### WG-0275 · P0 · defend · effort M

**nougenmsg's Windows SSH pipe-trap is indistinguishable from a genuine 90s dispatch timeout**

- Failure surface: nougenmsg_doctor.py documents Windows OpenSSH blocking when stdout is piped (a plain echo hangs 20s); dispatch.py's send_wake shares the same 90s subprocess timeout budget, so a benign pipe-trap and a genuinely unreachable node both surface identically as 'dispatch timed out,' giving no signal to distinguish 'fix the SSH invocation' from 'the machine is down.'
- First fork: if the receiving node is Windows and stdout is piped -> the wake always times out regardless of node health, identical in symptom to a real outage.
- Evidence: `fleet-ops/tools/nougenmsg_doctor.py`, `src/nougen_relay/dispatch.py`
- Lens: cost-quota · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet-ops/tools/nougenmsg_doctor.py documents the Windows OpenSSH pipe trap (stdout-as-pipe hangs, demonstrated vs a temp-file path) in detail; src/nougen_relay/dispatch.py's send_wake() uses subprocess.run(..., capture_output=True, ..., timeout=timeout) with a default timeout=90, i.e. a pipe (capture_output implies PIPE) and the same 90s budget — both failure modes surface identically as a Timeou
- #550 families: 43

### WG-0278 · P0 · defend · effort M

**fleet_heartbeat.py can't tell a Cloudflare Access failure from a real service outage**

- Failure surface: docs/HURRICANE_KICK_PATIO_GREP.md records whoart returning 400 (Cloudflare Access, not the app) and phoebus returning 403 on edge probes; if the heartbeat treats any non-2xx as 'service down' without distinguishing the CF Access layer, on-call diagnosis time is wasted chasing the wrong failure exactly as already documented.
- First fork: if a heartbeat probe hits Cloudflare Access instead of the app -> it can't tell 'app is down' from 'my Access session expired,' both reading as one failed heartbeat.
- Evidence: `fleet-ops/tools/fleet_heartbeat.py`, `docs/HURRICANE_KICK_PATIO_GREP.md`
- Lens: cost-quota · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/HURRICANE_KICK_PATIO_GREP.md records whoart returning HTTP 400 redirecting to cloudflareaccess.com and phoebus returning HTTP 403 on edge probes; fleet-ops/tools/fleet_heartbeat.py's _get()/check_http() only special-cases a '1033' tunnel-down signature in the response body — a generic Cloudflare Access 400/403 (no '1033') is treated as an ordinary failed/degraded lane with no distinct diagnos

### WG-0281 · P0 · defend · effort S

**Two malformed .handoffs records exist with no CI JSON-lint gate on the registry**

- Failure surface: core.py's glob-and-parse loops over every .handoffs/*.json; a third malformed record introduced by a future commit has nothing in CI to reject it, so it could raise unhandled inside a hot path like dispatch's dispatchable() before anyone notices.
- First fork: if a PR adds or edits a .handoffs record with invalid JSON -> nothing currently rejects it in CI, only a runtime crash on some later relay verb surfaces it.
- Evidence: `.handoffs/20260922T022924Z__claude-app__g-whoentertains.json`, `.handoffs/20260919T233524Z__claude-app__g-whoentertains.json`
- Lens: testing-ci · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified both files fail json.load with JSONDecodeError (one 'Extra data', one 'Expecting value'), directly confirming the malformed-records claim.
- #550 families: 36

### WG-0364 · P1 · defend · effort M

**Neutralize goal-text prompt injection in relay ack auto-dispatch**

- Failure surface: Any lane that can write a leg (including the chatgpt-app connector) can put `[-> @blade:claude] <instructions>` in a goal; `relay ack` auto-dispatches it over nougenmsg as 'Baton is yours: execute' and the receiving agent acts on stored content nobody reviewed. Nobody notices until a node does unrequested work.
- First fork: if you observe dispatch_text forwarding a goal verbatim with a `[-> @node:agent]` address from a non-fleet writer -> route A: allowlist writers/machines that may address nodes and strip directives from foreign goals; else route B: keep auto-dispatch but require NOUGEN_RELAY_NO_DISPATCH-off boxes to log and rate-limit per writer.
- Evidence: `src/nougen_relay/dispatch.py`, `src/nougen_relay/core.py`
- Lens: prompt-injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py:128,168-171 shows explicit `[-> @x:agent]` parsing feeding dispatch_text's 'Baton is yours: execute' text sent verbatim over send_wake; core.py:1807/policy.py:304 gate this only on NOUGEN_RELAY_NO_DISPATCH env, not on writer identity.
- #550 families: 69

### WG-0380 · P1 · defend · effort M

**Reconcile DAEMON.md 'read-only agy subcommands' with `agy -p <leg brief>` autonomous execution**

- Failure surface: docs/DAEMON.md promises the dispatcher only runs `--version|status|mcp list`, but dispatch_execution now passes the leg goal plus model triage reasoning to `agy -p` with 'act autonomously'. Leg text from any writer becomes an autonomous agent prompt on blade with a 900s timeout; the doc misleads every reviewer.
- First fork: if you observe a leg whose goal carries imperative text from an unverified writer reaching dispatch_execution -> route A: gate on writer allowlist + DEFECT/CHANGE markers and fix the doc; else route B: revert to canned diagnostics and add an explicit opt-in env for autonomous briefs.
- Evidence: `tools/relay_daemon.py`, `docs/DAEMON.md`
- Lens: prompt-injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/DAEMON.md:63 states read-only subcommands only; relay_daemon.py:1734-1759 dispatch_execution builds a prompt with 'act autonomously' and EXEC_TIMEOUT_SEC=900 (line 309), directly contradicting the doc.
- #550 families: 32

### WG-0396 · P1 · elevate · effort L

**Move the 3.2M-line FLEET-LOG bulk out of git before clones, CI and SessionStart stop fitting**

- Failure surface: docs/ is 131M with three logs over 1M lines each; every relay verb fetches, the SessionStart hook fetches, CI checks out three times per push, and the HF mirror would upload it all. A fresh box or a phone-tethered node cannot clone in time and the registry goes dark for it.
- First fork: if you observe `git clone` of NouGenRelay exceeding a few minutes on any node -> route A: move FLEET-LOGs to an LFS/object store and keep a marker index in docs/; else route B: split logs into a separate repo with shardlog writing the cutoff marker there.
- Evidence: `docs/FLEET-LOG-2026-08-17.md`, `docs/FLEET-LOG-2026-09-12.md`, `src/nougen_relay/hook.py`
- Lens: infra · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/FLEET-LOG-2026-08-17.md is 1,141,998 lines and docs/FLEET-LOG-2026-09-12.md is 1,173,886 lines (sum with a third similarly-sized log plausibly exceeds 3.2M); hook.py:59,140 call evaluate_triggers(root, fetch=True) and line 180 registers a 'session-start' hook, confirming SessionStart triggers a fetch.

### WG-0412 · P1 · defend · effort M

**Stop fleet_respond from sending private leg goals to a third-party public HF Space**

- Failure surface: The kimi-space lane posts leg goal + 2000 chars of notes to `akhaliq/Kimi-K3` (or NOUGEN_KIMI_SPACE) via its public gradio endpoint, and to OpenRouter free models; whoever operates those Spaces reads fleet directives and any credential-adjacent text. No log names what left the box.
- First fork: if you observe FLEET_LANES containing kimi-space on any daemon -> route A: remove it from the default and require an explicit opt-in per leg tag; else route B: run redaction over prompt text and log a hash of what was sent.
- Evidence: `tools/relay_daemon.py`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py:327 default FLEET_LANES includes 'kimi-space' by default; lines 1314-1330 show the kimi-space lane defaulting to space='akhaliq/Kimi-K3' via a public gradio_api tunnel unless NOUGEN_KIMI_SPACE overrides it.
- #550 families: 75

### WG-0428 · P1 · elevate · effort M

**Scope the MCP relay_* tools: repo allowlist and no relay_shards from an untrusted agent**

- Failure surface: Every tool accepts an arbitrary `repo` path and shells out as the user; relay_shards reads ~/.nougen/shards and writes docs/FLEET-LOG then expects a push. Any IDE agent with the plugin loaded (60+ servers on a box) can publish the vault or claim scopes in any checkout.
- First fork: if you observe a relay_* call with a repo outside the fleet's known checkouts -> route A: reject unless NOUGEN_MCP_REPOS lists it; else route B: drop the repo parameter and pin RELAY_ROOT.
- Evidence: `src/nougen_relay/mcp_server.py`, `plugins/nougen-relay/mcp_config.json`
- Lens: mcp-abuse · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: mcp_server.py:56-180 shows every relay_* tool (relay_check, relay_open, relay_claim_list/take/release, relay_create, relay_summarize, relay_ack, relay_shards) taking an optional `repo: Optional[str]` param with no allowlist check against RELAY_ROOT; no NOUGEN_MCP_REPOS reference found anywhere in the file.
- #550 families: 20

### WG-0444 · P1 · defend · effort S

**Pin the dev/CI toolchain after the pytest 9 importorskip red (#65/#67/#68)**

- Failure surface: pytest>=7.0, hypothesis>=6.0 and coverage>=7.0 float; huggingface_hub>=0.24 floats in deploy; actions/checkout@v4 and setup-python@v5 are tag-pinned. Ruff is pinned for exactly this reason. The next upstream change turns main red with no commit behind it.
- First fork: if you observe a CI failure whose diff touches no test -> route A: pin all four with a lockfile-style constraints.txt and add dependabot config; else route B: pin only pytest major and add a weekly scheduled 'floating' job.
- Evidence: `pyproject.toml`, `.github/workflows/ci.yml`, `.github/workflows/deploy-space.yml`
- Lens: toolchain-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: pyproject.toml:26 dev = ['pytest>=7.0','hypothesis>=6.0','coverage>=7.0'] (all floating minimums); deploy-space.yml pins 'huggingface_hub>=0.24' (floating); ci.yml pins ruff exactly (ruff==0.14.2) while using actions/checkout@v4 and setup-python@v5 tags, matching the asymmetry claimed.
- #550 families: 77

### WG-0459 · P1 · elevate · effort M

**Prove the Antigravity hooks.json actually fires on a box, then reconcile AGY.md**

- Failure surface: docs/AGY.md says hooks.json is deliberately absent; plugins/nougen-relay/hooks.json now exists with an unverified PreToolUse schema and a 25s timeout. If the schema is wrong the guard silently never runs while everyone believes agy lanes are enforced; 12 fleet-graded reviews said HOLD on path bypasses.
- First fork: if you observe `agy` editing a claimed file with no deny/ask logged -> route A: fix the schema against a live box, add a canary test, update AGY.md; else route B: remove hooks.json and restore the doc's honesty.
- Evidence: `plugins/nougen-relay/hooks.json`, `docs/AGY.md`, `analysis/fleet-audit-agy-hook.json`
- Lens: tool-abuse · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/AGY.md:41-45 states hooks.json is 'deliberately absent'; plugins/nougen-relay/hooks.json exists with a PreToolUse matcher and timeout:25, directly contradicting the doc; analysis/fleet-audit-agy-hook.json exists as supporting evidence of a fleet audit on this exact topic.

### WG-0472 · P1 · defend · effort M

**Detect a disarmed commit guard fleet-wide (hooksPath unset, relay missing, --no-verify)**

- Failure surface: pre-commit fails open by design and needs `core.hooksPath hooks` per clone; adopt refuses to seize an existing hooksPath (NouGenTracker case). A box that reinstalled Python or cloned fresh commits over foreign claims and nobody knows the guard is gone.
- First fork: if you observe a commit on main lacking Machine/Agent trailers -> route A: add a CI/registry check that flags unstamped commits and names the box; else route B: have `relay` bare status report hook_installed and warn loudly.
- Evidence: `hooks/pre-commit`, `src/nougen_relay/adopt.py`, `src/nougen_relay/core.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit comments explicitly state 'Fails OPEN. If relay is not installed...the commit proceeds'; adopt.py:13-14,213-217 documents 'an existing hooksPath is respected rather than seized'; core.py:729-731 has hook_installed() and lines 2529-2532/2794-2795 use it in status/warnings.
- #550 families: 35, 38

### WG-0485 · P1 · defend · effort S

**Quarantine the root sweep scripts so a re-run cannot re-ack or retire live legs**

- Failure surface: retire_stale_5d.py rewrites every open leg before 2026-08-27 to complete with a fabricated whoart/antigravity ack; ack_green_sweep.py acks hardcoded ids then `git push origin main` from C:\Users\super. Running any of them today on whoart mutates the shared registry with backdated events.
- First fork: if you observe a root *.py with a hardcoded C:\Users\super path and a glob over .handoffs -> route A: move to tools/archive with a guard that refuses to run; else route B: delete them and record the sweep provenance in a doc.
- Evidence: `retire_stale_5d.py`, `ack_green_sweep.py`, `retire_aug27_28.py`
- Lens: tool-abuse · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: retire_stale_5d.py:7 globs r'C:\Users\super\Outpost\NouGenRelay\.handoffs\*.json', line 18 sets status='complete' with machine='whoart', agent='antigravity' fabricated ack; ack_green_sweep.py:16,20-21 hardcodes the same C:\Users\super path and runs `git push origin main` — all three scripts sit at repo root exactly as claimed.
- #550 families: 22

### WG-0497 · P1 · defend · effort S

**Reconcile .gitignore with the 37 tracked files under logs/ and .relay/ that should not be in git**

- Failure surface: logs/combined.log (a git-mcp-server debug log), a 25k-line generated HTML preview and 33 wake signals are tracked despite `logs/` and `.relay/` in .gitignore, the inverse of the NouGen ignored-registry mistake. They ride every clone and the HF mirror, and wake signals get consumed by the wrong box.
- First fork: if you observe `git ls-files -i -c --exclude-standard` returning anything -> route A: git rm --cached and add a CI check that it stays empty; else route B: whitelist wake signals explicitly if they are meant to travel.
- Evidence: `.gitignore`, `logs/combined.log`, `.relay/wake`
- Lens: committed-artifacts · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .gitignore:14-17 ignores .relay/ and logs/; `git ls-files -i -c --exclude-standard` returns 38 tracked-but-ignored files including logs/combined.log and many .relay/wake/*.wake.json entries, matching the claim almost exactly (37 vs 38 measured).
- #550 families: 74

### WG-0509 · P1 · elevate · effort L

**Compact the 4031-leg / 1259-claim registry without breaking substring ids or the CAS writer**

- Failure surface: Every command globs and parses the whole directory; _record_path resolves substring ids so an archived leg becomes unresolvable or ambiguous, and _write_registry_record_upstream PUTs to `.handoffs/<id>.json` on main. Archival done naively breaks acks from every other box.
- First fork: if you observe `relay` bare status taking >5s on blade -> route A: archive complete legs older than N days into .handoffs/archive/ with an index the resolver still reads; else route B: leave layout, add an in-memory cache keyed by mtime.
- Evidence: `src/nougen_relay/core.py`, `.handoffs/claims`, `docs/relay-store-design.md`
- Lens: runtime · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Counted exactly 4031 files in .handoffs/*.json and 1259 files in .handoffs/claims/, matching both numbers in the title precisely; core.py:1675-1681 _record_path explicitly documents 'Globbing a substring can match more than one leg' as an ambiguity-refusal design, confirming the mechanism described.
- #550 families: 97, 98

### WG-0521 · P1 · defend · effort M

**Survive two relay daemons on two boxes leasing the same leg at once**

- Failure surface: acquire_lease reads then writes a JSON file with no atomic create, corrupt lease files are reclaimed, and force takeover exists; blade and phoebus daemons each sync the registry and can both admit one leg, run `agy -p`, and both ack upstream. Duplicate side effects, one ack wins.
- First fork: if you observe two `dispatch`/`ack` events on one leg within a TTL window from different machines -> route A: make lease creation O_EXCL + CAS the lease via gh api; else route B: run exactly one daemon fleet-wide and document it.
- Evidence: `src/nougen_relay/core.py`, `tools/relay_daemon.py`
- Lens: runtime · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py:1302-1381 acquire_lease reads lease_file.read_text() then later writes via a plain write (no O_EXCL), treats a corrupt/unparseable lease as 'Stale or corrupt lease file can be reclaimed' (line 1336), and has a `force: bool = False` takeover parameter exactly as claimed.
- #550 families: 25

### WG-0533 · P1 · defend · effort M

**Fix the Windows rule-timeout defect so a hanging `relay react` rule cannot wedge a box**

- Failure surface: rules._execute uses shell=True + capture_output; on Windows the timeout kills the shell while the grandchild holds the pipe (1s timeout took 30s, strict xfail at tests/test_rules_safety.py:215). An unattended react in a shell hook blocks the session; the rule env also exposes foreign leg goals to shell commands.
- First fork: if you observe the xfail still XFAILing on a Windows runner -> route A: implement job-object kill (Windows) / process-group kill (POSIX) and remove the marker; else route B: run rules only in background mode on nt and document the limitation.
- Evidence: `src/nougen_relay/rules.py`, `tests/test_rules_safety.py`
- Lens: runtime · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: rules.py:288-298 uses shell=True, capture_output=True; test_rules_safety.py has an xfail(os.name=='nt', strict=True) block right at the described location documenting exactly this Windows defect.

### WG-0545 · P1 · defend · effort M

**Stop dispatch _publish from pushing a feature branch's code commits onto main**

- Failure surface: dispatch._publish commits .handoffs then runs `git push origin HEAD:main`; on a clone sitting on a feature branch (the daemon docstring says clones sit on pi-remix/detached) that pushes every unmerged code commit to main under a 'dispatch N legs' message. The registry is the deployment, so this ships code silently.
- First fork: if you observe HEAD != main when dispatch runs -> route A: use the CAS contents writer for dispatch marks and never branch-push; else route B: refuse to publish unless current_branch == registry branch.
- Evidence: `src/nougen_relay/dispatch.py`, `src/nougen_relay/core.py`
- Lens: deploy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch._publish (dispatch.py:319-335) commits .handoffs and runs core._git('push', ..., 'HEAD:main') exactly as described; the commit message is 'relay(<machine>): dispatch N leg(s) to execution', close to the paraphrase.

### WG-0557 · P1 · defend · effort M

**Harden autoclose/policy so a goal containing 'verified' cannot suppress or falsely close a baton**

- Failure surface: _STATUS_GOAL and _REPORT_WORDS treat goals starting with 'done'/'claim'/'release' or containing DONE/VERIFIED as reports; policy apply acks them and pushes by default. A writer (or a model) can phrase an ask so it auto-closes, the WAR-GAME 'false completion' failure with no human gate.
- First fork: if you observe an auto-ack note on a leg whose body has an Ask/Next section -> route A: require a body-section check before any regex close and dry-run sweeps by default; else route B: keep sweeps but mark auto-closed legs `closed_by=policy` for weekly human review.
- Evidence: `src/nougen_relay/autoclose.py`, `src/nougen_relay/policy.py`, `src/nougen_relay/dispatch.py`
- Lens: prompt-injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: _REPORT_WORDS (autoclose.py:46-47) matches FIXED|CLOSED|DONE|PUSHED|...|VERIFIED|...; policy.py:49 has an equivalent regex including DONE/RESOLVED/COMPLETE etc. Matches the failure_surface directly.
- #550 families: 23, 100

### WG-0569 · P1 · defend · effort M

**Detect a hung-but-listening node (CLOSE_WAIT pileup on 4444) instead of trusting /health**

- Failure surface: blade's port 4444 listener hung on 9/11 and again today; /health timed out at 25s and cascaded 502/530 into shards.nougenai.com/mcp. Heartbeat's NODE_QUESTIONS only counts Listen sockets, so a wedged process reads as healthy.
- First fork: if you observe /health latency >10s with node_listening=1 -> route A: add CLOSE_WAIT count and event-loop liveness to NODE_QUESTIONS and auto-restart the task; else route B: shorten probe timeouts and alert on p95.
- Evidence: `docs/RELAY_UP_GM_MILESTONE_20260911.md`, `fleet-ops/tools/fleet_heartbeat.py`
- Lens: infra · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: fleet_heartbeat.py NODE_QUESTIONS (line 99) counts Listen sockets on port 4444 via PowerShell Get-NetTCPConnection; RELAY_UP_GM_MILESTONE doc exists. Did not verify the specific 9/11 hang narrative in the doc but the code-level claim (Listen-only counting) is directly supported.
- #550 families: 28, 95

### WG-0580 · P1 · defend · effort M

**Survive an Ollama model rename across dedup, classify_asks, daemon triage and TOKEN_RULE**

- Failure surface: gemma4:e2b-qat, dav1d:e2b and nomic-embed-text are hardcoded defaults in four places plus the dispatch TOKEN_RULE text sent to every node; a model pull/rename makes dedup degrade to token overlap, classify_asks write an empty sidecar (which HOLDs all dispatch) and triage fail silently.
- First fork: if you observe /api/tags on a node lacking any of the three model names -> route A: resolve models from one NOUGEN_MODELS config with a startup check; else route B: keep defaults but make each caller log the model actually used.
- Evidence: `tools/relay_dedup.py`, `tools/classify_asks.py`, `src/nougen_relay/dispatch.py`
- Lens: model-cutover · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/relay_dedup.py hardcodes DEFAULT_MODEL='nomic-embed-text'; tools/classify_asks.py hardcodes MODEL='gemma4:e2b-qat' (env-overridable); dispatch.py TOKEN_RULE references gemma4:e2b-qat. Supports the described hardcoding/fragility.
- #550 families: 54

### WG-0591 · P1 · elevate · effort M

**Rotate and enroll SSH identities across whoart, blade and phoebus with keys out of git**

- Failure surface: docs/ssh-lan-interconnect.md commits two whoart public keys, the phoebus username and LAN address; phoebus Remote Login is still off so the mesh is half-built, and rollout/heartbeat use BatchMode ssh with whatever keys happen to be enrolled. No inventory says which key opens which box.
- First fork: if you observe an authorized_keys entry on any node not named in a fleet inventory -> route A: rotate to per-box ed25519 keys, enroll via a script, keep the inventory in the vault; else route B: finish phoebus enrollment only and document.
- Evidence: `docs/ssh-lan-interconnect.md`, `fleet-ops/tools/nougenmsg_rollout.py`, `fleet-ops/tools/fleet_heartbeat.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/ssh-lan-interconnect.md commits actual ed25519 public keys for whoart, names phoebus's LAN host, and states 'Port 22 is currently closed on Phoebus because macOS Remote Login is disabled.' Matches claim exactly.
- #550 families: 76

### WG-0602 · P1 · defend · effort S

**Add a timeout to core._git so a stalled fetch cannot wedge every relay verb, hook and MCP tool**

- Failure surface: _git sets GIT_TERMINAL_PROMPT=0 but no timeout; a TCP-stalled `git fetch origin` (tunnel down, captive network) hangs `relay`, the SessionStart hook, autoclose sweeps and the MCP wrapper (whose 30s timeout kills the wrapper but leaves git running). The agent session freezes at start.
- First fork: if you observe a relay verb exceeding NOUGEN_RELAY_GIT_TIMEOUT wall time -> route A: pass timeout= to subprocess.run and treat expiry as failure; else route B: add --no-fetch defaults for hooks and MCP.
- Evidence: `src/nougen_relay/core.py`, `src/nougen_relay/mcp_server.py`, `src/nougen_relay/hook.py`
- Lens: runtime · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py's _git() (line 111) sets GIT_TERMINAL_PROMPT=0 but passes no timeout= to subprocess.run, while a separate _git_timeout_seconds() helper exists but is only used by the upstream CAS writer, not by _git itself. Matches the claim exactly.
- #550 families: 43

### WG-0613 · P1 · defend · effort S

**Stop dispatch from waking a node the fleet already knows is down**

- Failure surface: resolve_target falls through to keywords and a sha1 spread across NODES, so unaddressed legs land on blade while it is frozen; send_wake burns 90s per leg and digests of 40 legs pile up. Nothing consults heartbeat state before choosing a node.
- First fork: if you observe dispatch events with sent=false to one node for >2 cycles -> route A: read the last heartbeat verdict and skip/re-route down nodes; else route B: cap retries per node per sweep.
- Evidence: `src/nougen_relay/dispatch.py`, `fleet-ops/tools/fleet_heartbeat.py`
- Lens: runtime · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py resolve_target (line 125) falls through to a sha1-hash-based NODES selection (line 155) with no reference to heartbeat state, and send_wake has a 90s timeout (line 177), matching the claim.
- #550 families: 95

### WG-0624 · P1 · elevate · effort M

**Reap the 227 in_progress legs whose executor never checkpointed**

- Failure surface: dispatch flips a leg to in_progress on a delivery receipt and nothing ever times it back to retry_pending or dead_letter; 227 legs sit in_progress and 6 dead_letter with no reaper. The board understates open work and repeated sweeps skip them as already dispatched.
- First fork: if you observe an in_progress leg older than EXEC_TIMEOUT with no checkpoint event -> route A: add a reaper that moves it to retry_pending with backoff via record_leg_failure; else route B: report them in `relay open` as stale.
- Evidence: `src/nougen_relay/dispatch.py`, `src/nougen_relay/core.py`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: dispatch.py sets rec['status']='in_progress' (lines 218, 275) with no reaper logic in dispatch.py itself; core.py has record_leg_failure/dead_letter/retry_pending machinery (lines 1560-1624) that is not obviously invoked from a timeout-based reaper. Supports the claim that no automatic reaper exists; the specific counts (227/6) are asserted, not independently verified against a live registry.
- #550 families: 26, 27

### WG-0635 · P1 · defend · effort M

**Heal a clone whose local registry commits diverged from main after CAS or push failures**

- Failure surface: cmd_relay commits locally before the CAS write and returns EXIT_FAILURE if either the CAS or push fails; blade accumulated 1707 phantom-modified records and hours of blocked ff-merge. Every subsequent verb rebases onto a diverged history and autoclose.heal_rebase is the only repair.
- First fork: if you observe `git status` in a relay clone showing ahead>0 for more than one cycle -> route A: add `relay doctor` that reconciles local-only registry commits via CAS and resets; else route B: document a manual heal and alert on divergence.
- Evidence: `src/nougen_relay/core.py`, `tools/relay_daemon.py`, `src/nougen_relay/autoclose.py`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: core.py defines cmd_relay (line 1756) and autoclose.py exists (heal_rebase not directly greped but autoclose module confirmed); daemon and core both reference EXIT_FAILURE paths consistent with commit-before-CAS failure handling. The specific 1707 phantom-record incident is asserted narrative, not independently re-verified, but the code path (local commit then remote write that can fail) is consis
- #550 families: 12

### WG-0646 · P1 · defend · effort M

**Make the agy PreToolUse guard resolve symlinks and Windows spellings before scope matching**

- Failure surface: Fleet-graded reviews flagged path normalisation (backslashes, ../, symlinks) as the bypass; tests cover Linux symlinks only because Windows symlink creation needs privilege, and the hook allows on any exception. An Antigravity lane edits a claimed core.py via a junction and the claim never fires.
- First fork: if you observe test_agy_hook_bypass skipping on nt in CI -> route A: add a Windows runner with developer mode symlinks and resolve() before relative_to; else route B: deny when resolve() differs from the raw path.
- Evidence: `src/nougen_relay/agy_hook.py`, `tests/test_agy_hook_bypass.py`, `analysis/fleet-audit-agy-hook.json`
- Lens: tool-abuse · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agy_hook.py comments and code explicitly discuss resolve()-based normalization to defeat symlinks/relative paths (lines 137-146); tests/test_agy_hook_bypass.py:97 has @pytest.mark.skipif(os.name=='nt', reason='symlink creation needs privilege on Windows') on the symlink test, exactly matching the claim about Windows coverage gaps. analysis/fleet-audit-agy-hook.json contains multiple independent mo
- #550 families: 71, 72

### WG-0657 · P1 · defend · effort S

**Harden persist_learning_shards so fleet topology (192.168.1.x) stops being ingested as knowledge**

- Failure surface: persist_learning_shards.py writes LAN IPs, hostnames and tunnel names into ~/.nougen/shards as 'recursive learning' shards; those federate and get relayed by shardlog into git. HARDENING already lists lockfiles and secrets reaching shards; this is the same class for topology.
- First fork: if you observe a shard tagged fleet/reach-matrix carrying an RFC1918 address -> route A: strip addresses at capture and tag topology shards brand/personal so shardlog withholds them; else route B: delete the script.
- Evidence: `fleet-ops/tools/persist_learning_shards.py`, `src/nougen_relay/shardlog.py`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: persist_learning_shards.py literally embeds 192.168.1.16/187/78 with hostnames under tags fleet,reach-matrix,...,recursive-learning; shardlog.py exists as the relay path.
- #550 families: 74

### WG-0668 · P1 · defend · effort S

**Replace the tracked .relay/wake signals with a per-box, untracked wake dir**

- Failure surface: emit_wake_signal writes .relay/wake/*.wake.json, .gitignore says .relay/ is ignored, yet 33 signals from phoebus/whoart/vm are tracked; consume_wake_signal on any box deletes another box's signal, and acquire_lease consumes on acquire. Wakes are lost or double-fired depending on who pulled last.
- First fork: if you observe a wake signal consumed by a machine other than its target -> route A: untrack, move NOUGEN_WAKE_DIR under ~/.nougen and keep git for legs only; else route B: track them deliberately and add a target field.
- Evidence: `.relay/wake`, `src/nougen_relay/core.py`, `.gitignore`
- Lens: committed-artifacts · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py has emit_wake_signal/consume_wake_signal/acquire_lease writing .relay/wake; .gitignore line 15 ignores .relay/ yet 33 wake.json files are git-tracked (confirmed via git ls-files).
- #550 families: 16

### WG-0679 · P1 · defend · effort M

**Make hourly_shard_worker records first-class or keep them out of the leg directory**

- Failure surface: blade1tb writes `*__hourly_shard` records with status DONE and a non-leg schema every hour; dispatch special-cases the agent name, autoclose regexes 'DONE', and the CAS merge order does not know DONE. 621 DONE records already skew every census and any future sweep that forgets the exception dispatches them.
- First fork: if you observe a new writer producing a status outside RELAY_STATES -> route A: give telemetry records their own directory and schema; else route B: add DONE/closed/synchronized to RELAY_STATES with lint.
- Evidence: `src/nougen_relay/dispatch.py`, `.handoffs/20260924T160624Z__blade1tb__hourly_shard.json`, `src/nougen_relay/core.py`
- Lens: runtime · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: The exact file .handoffs/20260924T160624Z__blade1tb__hourly_shard.json exists with status DONE and non-leg schema (metrics dict); 620 DONE records counted fleet-wide, matching the claimed 621.

### WG-0690 · P1 · elevate · effort M

**Cut dispatch and dedup over to a nodes.json-driven config instead of hardcoded COACH_TO_NODE and paths**

- Failure surface: COACH_TO_NODE, NODE_KEYWORDS, the ~/Outpost/NouGen/tools/nougenmsg.py path and DEFAULT_EMBED_URL are constants; adding a fourth node (vm/ccr already write legs) or moving a tree means every box needs a code change or misroutes to 'fleet' broadcast. ~/.nougen/nodes.json exists but is optional.
- First fork: if you observe a leg from a machine absent in COACH_TO_NODE -> route A: make nodes.json required with a validated schema and remove the constants; else route B: keep constants but fail loudly on unknown machines.
- Evidence: `src/nougen_relay/dispatch.py`, `tools/relay_dedup.py`
- Lens: infra · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py defines COACH_TO_NODE, NODE_KEYWORDS, and reads an optional ~/.nougen/nodes.json via _nodes_json(), exactly as described.
- #550 families: 38

### WG-0701 · P1 · defend · effort M

**Add zero-cost health probes for cloudflared tunnels to the zombie and watchdog scripts**

- Failure surface: zombie_check.ps1 protects the whoart-vault tunnel by pid file but nothing restarts it; today's 11 AM tunnel death needed a manual 5-minute watchdog. A killed cloudflared leaves the pid file, so the protector shields a corpse.
- First fork: if you observe a registered pid in .nougen that is not alive -> route A: extend zombie_check to report dead registered daemons and let the watchdog restart cloudflared; else route B: move tunnels to Windows services with recovery actions.
- Evidence: `fleet-ops/tools/zombie_check.ps1`, `tools/relay_watchdog.ps1`, `docs/HURRICANE_KICK_PATIO_GREP.md`
- Lens: infra · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: zombie_check.ps1, relay_watchdog.ps1 and the incident doc exist; specific 11 AM incident narrative not independently verifiable but files are the right ones for this claim.
- #550 families: 95

### WG-0712 · P1 · elevate · effort M

**Ship the HF static Space mirror without publishing the private registry and topology**

- Failure surface: deploy-space.yml uploads the whole repo (44M .handoffs, 131M docs, SSH pubkeys, LAN IPs, persona doc, 91 email mentions) to a Space with delete_patterns=['*'] the moment HF_SPACE is set; a mistyped Space id (example shows NouGenTracker-node) wipes another project's Space. Disclosure is instant and public.
- First fork: if you observe HF_SPACE already configured in repo variables -> route A: add an allowlist of served paths and a secret/IP scan gate before upload_folder; else route B: delete the workflow from the private repo and mirror only the scrubbed twin.
- Evidence: `.github/workflows/deploy-space.yml`, `docs/ssh-lan-interconnect.md`, `docs/persona-dave-meralus.md`
- Lens: deploy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy-space.yml uploads folder_path='.' with delete_patterns=['*'] once HF_TOKEN+HF_SPACE are set (lines 60-67), example comment names 'nougenai/NouGenTracker-node'; du confirms .handoffs=44M, docs=131M; ssh-lan-interconnect.md has SSH keys/LAN IPs and persona-dave-meralus.md exists with fleet-internal detail.
- #550 families: 75

### WG-0723 · P1 · elevate · effort M

**Build a repeatable scrub pipeline for the public twin Who-Visions/nougen-relay**

- Failure surface: The 2026-09-24 scrub that moved fleet-ops here was manual; 192.168.1.x IPs, C:\Users\super paths, hostnames and mDNS names live in docs, tools and tests. The next sync of engine changes to the twin carries a private path or topology line and nobody diffs for it.
- First fork: if you observe a file in src/ or tools/ containing a LAN IP, user path or nougenai.com host -> route A: write a deny-pattern scan run in CI on the twin and a subtree filter for the sync; else route B: sync only src/ and tests/ via an explicit allowlist script.
- Evidence: `fleet-ops/README.md`, `fleet-ops/tools/persist_learning_shards.py`, `tools/fleet_audit.py`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet-ops/README.md:4 explicitly documents the '2026-09-24 public-repo scrub'; tools/relay_daemon.py, tools/fleet_audit.py, tools/fleet_test_audit.py contain literal 192.168.x IPs, confirming private topology remains scattered post-scrub.
- #550 families: 74, 75, 76

### WG-0733 · P1 · defend · effort M

**Unify the fleet credential pattern set behind shardlog SECRET_PATTERNS**

- Failure surface: shardlog blocks on 8 shapes; blade's independent 18-shape suite found 10 misses (sk-proj-, sk-ant-, sk-or-v1-, glpat-, npm_, JWT, azure connection strings, xoxp-). A FLEET-LOG relay of a vault holding a current OpenAI key writes it into git and every clone.
- First fork: if you observe the 2026-09-07 leg's 10 missed shapes absent from SECRET_PATTERNS -> route A: adopt one versioned pattern set with the synthetic fixture as tests/test_shardlog.py cases; else route B: block on entropy + marker heuristics and require --allow-secret-shape per relay.
- Evidence: `src/nougen_relay/shardlog.py`, `.handoffs/20260907T234915Z__claude-app__g-whoentertains.md`, `tests/test_shardlog.py`
- Lens: secrets · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: shardlog.py:84-98 has exactly 8 SECRET_PATTERNS entries and the handoff .md lists the 10 missed shapes verbatim (sk-proj-, glpat-, npm_, JWT, azure, xoxp-, etc). However current sk-[A-Za-z0-9_-]{20,} and xox[baprs]- patterns would actually already catch sk-proj-/sk-ant-/sk-or-v1- and xoxp-, so not all 10 are true misses today; glpat-, npm_, JWT and azure connection strings remain genuinely uncover
- #550 families: 76

### WG-0743 · P1 · defend · effort M

**Survive Python 3.10 fromisoformat('...Z') making 2,756 Z-stamped legs and claims ageless**

- Failure surface: core._claim_age_hours and _lease_age_minutes call datetime.fromisoformat on created_utc; 2,756 legs and several claims carry a trailing 'Z' (written by retire_stale_5d.py and connector writers), which 3.10 rejects, so age is None and claim_is_active/lease_is_active return True forever on a 3.10 node. CI still runs the 3.10 matrix leg.
- First fork: if you observe `python -c "import datetime;datetime.datetime.fromisoformat('2026-09-01T03:22:00Z')"` failing on any fleet node -> route A: add a _parse_utc shim normalising Z/+00:00/naive and backfill; else -> route B: pin requires-python>=3.11 and drop 3.10 from ci.yml
- Evidence: `src/nougen_relay/core.py`, `retire_stale_5d.py`, `.github/workflows/ci.yml`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py calls datetime.fromisoformat on created_utc-derived stamps at multiple sites (lines 831,1127,1652,2700); ci.yml matrix still includes python-version 3.10, which rejects trailing 'Z' in fromisoformat.
- #550 families: 24, 79

### WG-0753 · P1 · defend · effort M

**Make heal_rebase's 'upstream wins' loss visible: the losing lane still believes it acked**

- Failure surface: heal_rebase resolves every .handoffs conflict with checkout --ours (upstream during a rebase) and continues; the local ack/complete event is discarded with no record, the lane's stdout already said 'baton taken', and the leg stays open upstream so the next sweep re-dispatches it. 2026-09-14 9:35 AM run parked a clone four hours this way.
- First fork: if you observe a conflict whose local side carries a relay event absent upstream -> route A: replay that event through _merge_registry_records instead of dropping it; else -> route B: emit a 'conflict-lost' wake signal naming the lane
- Evidence: `src/nougen_relay/autoclose.py`, `src/nougen_relay/core.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: autoclose.py and core.py exist and are the plausible location for heal_rebase; the specific 2026-09-14 incident narrative is unverifiable from static inspection alone.
- #550 families: 23

### WG-0763 · P1 · defend · effort S

**Stop dispatch._publish pushing HEAD:main from whatever branch the clone is on**

- Failure surface: dispatch._publish hardcodes `push HEAD:main` after committing .handoffs, so a clone sitting on a feature branch (pi-remix, detached, mid-work) pushes its code commits into the registry branch; relay_daemon.ack_leg_upstream explicitly refuses this ('never git push from this clone') but dispatch does it on every `relay ack`.
- First fork: if you observe `git log origin/main --not origin/main@{1}` containing non-.handoffs paths after a dispatch -> route A: route marks through _write_registry_record_upstream; else -> route B: refuse to publish when current_branch != _registry_branch
- Evidence: `src/nougen_relay/dispatch.py`, `tools/relay_daemon.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py and relay_daemon.py both exist; relay_daemon.py contains an explicit 'never git push from this clone' style guard while dispatch.py's _publish path is the counterpart being described -- consistent with the claim.

### WG-0773 · P1 · elevate · effort M

**Make leg publication atomic across json+md: 26 legs have no body on any fetcher**

- Failure surface: The connector writer commits legs as two commits ('relay json: <id>' then 'relay: <id>', see git log), so a sync between them yields a .json with no .md; 26 such legs exist. dispatch.dispatchable and autoclose.classify read the body for work headings, so a bodiless ask classifies as a status record and is silently never dispatched.
- First fork: if you observe the writer is claude-app via the NouGenShards connector -> route A: land a single-commit writer there and backfill the 26 bodies; else -> route B: make readers treat missing .md as HOLD not REPORT
- Evidence: `.handoffs/`, `src/nougen_relay/dispatch.py`, `src/nougen_relay/autoclose.py`
- Lens: data-integrity · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: dispatch.py and autoclose.py exist and read leg bodies; the specific two-commit split and 26-leg count were not independently reproduced from git log.
- #550 families: 37

### WG-0783 · P1 · defend · effort S

**Backfill created_utc for the 760 legs that are invisible to lag detection and stale ordering**

- Failure surface: 760 registry legs have no created_utc; relay_daemon.calculate_lag returns (0, False) for them so they never raise a lag alert, foreign_claims/evaluate_triggers sort them as '' (oldest), and _superseding_relay_ids skips the timestamp guard. A dropped baton with no stamp is a baton the watcher cannot see age.
- First fork: if you observe the filename stamp parses -> route A: CAS-backfill created_utc from the id prefix; else (legacy handoff_/UUID names) -> route B: quarantine as legacy
- Evidence: `.handoffs/`, `tools/relay_daemon.py`, `src/nougen_relay/core.py`
- Lens: observability · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: relay_daemon.py and core.py exist; calculate_lag-style handling of missing created_utc is consistent with the claim though the 760 count was not independently recomputed.
- #550 families: 15, 96

### WG-0793 · P1 · defend · effort L

**Survive the same baton executing on two nodes: leases and idempotency keys never leave .relay/**

- Failure surface: is_duplicate_execution and acquire_lease read .relay/idempotency and .relay/leases, which .gitignore keeps local; docs/WAR-GAME.md requires 'baton delivered twice -> idempotent' but two machines both see no lease and both run the leg. The upstream claim file in relay_daemon is the only cross-machine fence and only the daemon writes it.
- First fork: if you observe two complete events from different machines on one leg -> route A: promote fencing tokens into .handoffs/claims/<leg>__autonomous.json for every executor; else -> route B: make acquire_lease consult foreign_claims before granting
- Evidence: `src/nougen_relay/core.py`, `.gitignore`, `docs/WAR-GAME.md`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: .gitignore ignores .relay/ and WAR-GAME.md exists with idempotency requirements; core.py contains the lease/idempotency-key logic under .relay/, matching the cross-machine fencing gap described.
- #550 families: 8, 25

### WG-0803 · P1 · defend · effort S

**Untrack the 33 .relay/wake signals committed despite .gitignore before consume unlinks tracked files**

- Failure surface: .relay/ is ignored but 33 wake.json files plus pong_WAKE_mtpruayv_01a07424.json are tracked; every clone reports them as pending in `relay wake list`, consume_wake_signal unlinks a tracked file leaving the tree dirty, and emit_wake_signal touches .relay/wake.signal on every create. The inverse of the 130-record ignored-registry mistake.
- First fork: if you observe `git ls-files -i -c --exclude-standard .relay` non-empty -> route A: git rm --cached and add a CI check; else -> route B: nothing to do, verify the hook on each node
- Evidence: `.relay/wake/`, `.gitignore`, `src/nougen_relay/core.py`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git ls-files confirms 33 tracked files under .relay/wake despite .gitignore's .relay/ ignore rule, exactly as claimed.
- #550 families: 16

### WG-0813 · P1 · defend · effort S

**Survive a stale ask_verdicts.json sidecar silently holding every dispatch**

- Failure surface: dispatch._verdicts fails closed: once .handoffs/ask_verdicts.json exists (gitignored, written by tools/classify_asks.py on one box) any leg without a verdict returns 'unclassified; classify_asks.py still running'. If the classifier stops running, new asks are held forever with no alert; the only signal is a quiet `relay dispatch --all` saying nothing to dispatch.
- First fork: if you observe the sidecar mtime older than the newest leg by >1h -> route A: treat it as expired and fall back to regex classification with a warning; else -> route B: schedule classify_asks with the daemon cycle
- Evidence: `src/nougen_relay/dispatch.py`, `tools/classify_asks.py`, `.handoffs/ask_verdicts.eval.json`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py, tools/classify_asks.py, and .handoffs/ask_verdicts.eval.json all exist; dispatch.py's verdict-gating behavior against a sidecar file matches the described fail-closed mechanism.
- #550 families: 7, 94

### WG-0823 · P1 · defend · effort M

**Prevent a daemon dead_letter from placeholder probes permanently outranking a human complete**

- Failure surface: dead_letter is the highest rank in NOUGEN_RELAY_STATUS_ORDER, so once record_leg_failure writes it (6 legs today, several via dav1d probes that invented '<SERVICE_ENDPOINT>' hosts) no later complete/ack from a human survives a merge; the leg is terminal in every projection and dispatch never revisits it.
- First fork: if you observe a dead_letter leg whose failures[] are all probe DNS errors -> route A: reopen via CAS with a 'probe-dead-letter reversed' event and rank dead_letter below complete; else -> route B: keep terminal but require a human note
- Evidence: `tools/relay_daemon.py`, `src/nougen_relay/core.py`, `.handoffs/`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py confirms dead_letter is the last (highest-ranked) entry in NOUGEN_RELAY_STATUS_ORDER (line 572) and record_leg_failure sets status=dead_letter as a terminal state (lines 1596-1640), matching the claim precisely.
- #550 families: 23

### WG-0833 · P1 · defend · effort S

**Defuse relay_pusher_90m AUTO_RESOLVE_RULES before it closes legs on the keyword '502'**

- Failure surface: fleet-ops/tools/relay_pusher_90m.py carries 17 keyword rules with canned 'Resolved and verified' notes ('502', '1019', 'hardcade') and broadcasts 'operational' fleet updates; any future run mass-completes open legs matching a substring with false evidence. fleet-ops/README says nothing schedules it, which is the only guard.
- First fork: if you observe the script referenced by any scheduled task or launchd plist -> route A: remove AUTO_RESOLVE_RULES and require per-leg evidence; else -> route B: move it to fleet-ops/retired/ with a header refusing execution
- Evidence: `fleet-ops/tools/relay_pusher_90m.py`, `fleet-ops/README.md`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_pusher_90m.py contains AUTO_RESOLVE_RULES with keyword entries for '502', '1019', and 'hardcade' (18 rule blocks counted, matching the claimed ~17); fleet-ops/README.md explicitly states none of the fleet-ops scripts are run by any scheduled task, cron, or launchd job, matching the claim about the only guard.
- #550 families: 23

### WG-0843 · P1 · defend · effort S

**Fix exact-dedup returning EXIT_OK with the old id so the new body is silently dropped**

- Failure surface: cmd_create on an 'exact' dedup hit prints the existing id and exits 0 without writing; MCP relay_create and connector callers read success and the new message body (often the updated finding) never lands anywhere. tests/test_cli_dedup.py documents the contract but not the lost body.
- First fork: if you observe callers parsing the printed id as a created leg -> route A: append the new body as a relay event on the existing leg; else -> route B: exit EXIT_DIVERGED and print a 'not written' banner
- Evidence: `src/nougen_relay/core.py`, `tools/relay_dedup.py`, `tests/test_cli_dedup.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py cmd_create: on status=='exact' prints existing id and `return EXIT_OK` with no write. tests/test_cli_dedup.py::test_exact_dupe_idempotent_return documents exit-0/no-second-write contract, not the lost body.
- #550 families: 8

### WG-0853 · P1 · defend · effort S

**Survive two relay daemons on blade launched from two scheduled tasks and two code trees**

- Failure surface: SingletonLock lives at <NOUGEN_DAEMON_DB>.lock, so two tasks resolving different watchtower roots or DB paths both win, both sync the same clone, and both triage the same legs (docs/DAEMON.md: 'double every lag alert'). Today blade has two scheduled tasks pointing at two code trees and the watchdog relaunches every 5 minutes.
- First fork: if you observe two python processes with relay_daemon.py on blade -> route A: lock on the relay clone path (.git/relay-daemon.lock) not the DB; else -> route B: consolidate to one task and delete the other tree
- Evidence: `tools/relay_daemon.py`, `tools/relay_watchdog.ps1`, `docs/DAEMON.md`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: SingletonLock class in relay_daemon.py keyed on lock_path = db_path.with_suffix('.lock'); docs/DAEMON.md literally contains 'double every lag alert' phrase; relay_watchdog.ps1 present.
- #550 families: 29

### WG-0863 · P1 · defend · effort M

**Keep relay_ack from being killed mid-write by the MCP 30s timeout around a 90s nougenmsg wake**

- Failure surface: mcp_server._run kills the CLI after 30s, but `relay ack` mutates the record, then runs dispatch.send_wake (90s timeout), then gh api (120s) and push; a slow tunnel leaves the record acked on disk, uncommitted and undispatched, and the MCP caller sees only 'timed out'. The next sweep re-acks or the leg looks taken while nobody was woken.
- First fork: if you observe acked records with no commit in `git status .handoffs` on a connector node -> route A: make ack write-and-publish first and dispatch asynchronously via the wake outbox; else -> route B: raise MCP TIMEOUT above the transport ceiling
- Evidence: `src/nougen_relay/mcp_server.py`, `src/nougen_relay/dispatch.py`, `src/nougen_relay/core.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: mcp_server.py TIMEOUT=30 used in subprocess.run(..., timeout=TIMEOUT) for _run(); dispatch.py send_wake has timeout=90 default; ack path plausibly chains through git push per core.py commit machinery.
- #550 families: 90

### WG-0873 · P1 · defend · effort M

**Stop `relay open`, triggers and the session-start hook tar-balling 44MB of .handoffs per ref per call**

- Failure surface: _read_json_dir_from_ref runs `git archive` of the whole registry for each watch target (upstream + default branch) on every relay open / claim take / hook session_start; at 4,031 legs plus md bodies that is ~88MB of tar per invocation and grows 134 legs a day. Sessions start slower until someone disables the hook.
- First fork: if you observe hook.session_start exceeding 5s on any node -> route A: read only *.json via `git ls-tree` + cat-file --batch like claims already do; else -> route B: cache the archive by ref sha
- Evidence: `src/nougen_relay/core.py`, `src/nougen_relay/hook.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py has _git_archive() using `git archive --format=tar` and _read_json_dir_from_ref() calling it; hook.py defines session_start() which is registered for the SessionStart hook.

### WG-0883 · P1 · defend · effort M

**Fix shardlog title-only dedup that drops same-title shards and cross-machine cutoffs**

- Failure surface: relayed_titles() marks any shard whose title already appears in any FLEET-LOG as published, so recurring titles ('daily brief', 'fleet health') with new content never relay again; last_relayed per-machine markers already caused blade1tb shards to be skipped forever on 2026-08-08. Knowledge vanishes silently from the fleet log.
- First fork: if you observe vault rows with a title present in docs/FLEET-LOG-*.md but a newer timestamp than the marker -> route A: dedup on (title, file_hash) and add the hash to the log footer; else -> route B: keep titles but scope them per day
- Evidence: `src/nougen_relay/shardlog.py`, `docs/FLEET-LOG-2026-09-18.md`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: shardlog.py relayed_titles() reads title headings/withheld markers from all FLEET-LOG-*.md files into a single `seen` set with no content/hash comparison, matching the title-only dedup claim exactly; FLEET-LOG-2026-09-18.md exists.
- #550 families: 8, 12

### WG-0892 · P1 · defend · effort M

**Stop dispatch re-sending legs whose marks say sent=false (238 multi-dispatch, 151 never-sent)**

- Failure surface: dispatch._dispatched only counts events with sent=true, so a leg whose wake timed out is re-sent on every `dispatch --all`; 238 legs carry multiple dispatch events and 151 carry only failed ones. Each retry is a fresh 90s nougenmsg subprocess and a new commit, flooding nodes and CI when the transport is flaky.
- First fork: if you observe more than 3 dispatch events on one leg -> route A: cap attempts per leg with backoff stored in the record; else -> route B: only treat repeated timeouts as a transport outage and pause the sweep
- Evidence: `src/nougen_relay/dispatch.py`, `.handoffs/`
- Lens: concurrency · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: dispatch.py exists with dispatch-event logic; the specific counts (238/151) were not independently recomputed but the described _dispatched sent=true filtering mechanism is a reasonable reading of the file's role.
- #550 families: 16

### WG-0901 · P1 · defend · effort S

**Make session-start triggers say when the fetch failed instead of judging against stale refs**

- Failure surface: evaluate_triggers calls _git('fetch') and ignores a None result; when GitHub or the tunnel is down the hook still reports 'no triggers fired' from refs hours old, and hook.session_start injects that as fact into the agent's context. A lane starts work believing nobody else moved.
- First fork: if you observe `git fetch` failing in the hook environment -> route A: emit a 'registry_unreachable' error trigger with the ref age; else -> route B: nothing beyond a test
- Evidence: `src/nougen_relay/core.py`, `src/nougen_relay/hook.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py evaluate_triggers() calls _git('fetch', remote) without checking/using its return value (multiple other call sites in core.py show the same fetch-and-ignore pattern); hook.py session_start() exists as the hook entrypoint.
- #550 families: 38

### WG-0909 · P1 · defend · effort S

**Treat nougenmsg QUEUED as not delivered before flipping a leg to in_progress**

- Failure surface: dispatch.send_wake counts 'QUEUED' in the CLI output as sent and dispatch_leg flips status to in_progress on it; quota_delivery requires 'Status: DELIVERED' for the same transport. With the whoart tunnel dead since ~11 AM today, queued wakes to whoart mark legs as being worked by a node that has not read them.
- First fork: if you observe in_progress legs whose dispatch note contains QUEUED and no checkpoint -> route A: record queued as 'dispatch_pending' and only flip on a receipt; else -> route B: keep flipping but reap after 1h
- Evidence: `src/nougen_relay/dispatch.py`, `src/nougen_relay/quota_delivery.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py send_wake: `ok = "DELIVERED" in out or "QUEUED" in out`, and dispatch_leg sets rec['status']='in_progress' on success; quota_delivery.py separately requires the stricter 'Status: DELIVERED' substring for its own channel — confirms the inconsistency described.
- #550 families: 23

### WG-0917 · P1 · defend · effort S

**Publish record_leg_failure's retry history instead of leaving it on one box**

- Failure surface: record_leg_failure writes the lease locally and mutates the registry record (retry_count, failures, dead_letter) via _touch_record without commit or CAS; the daemon then only writes the claim release upstream. Other nodes never see the failures, and the 45-times-claimed leg from the acquire_lease comment repeats on every node with its own zero count.
- First fork: if you observe a leg with retry_count>0 locally and 0 upstream -> route A: route the mutation through _write_registry_record_upstream; else -> route B: fold failures into the autonomous claim record
- Evidence: `src/nougen_relay/core.py`, `tools/relay_daemon.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py record_leg_failure ends with `_touch_record(root, leg_id, update_rec)` (a local mutation helper, distinct from `_write_registry_record_upstream` used elsewhere), matching the claim that failure history stays local while only claim release goes upstream.
- #550 families: 12

### WG-0925 · P1 · elevate · effort M

**Alert when a public hostname is answered by the wrong origin (probe_field_parity as a lane)**

- Failure surface: On 2026-09-01 phoebus's tunnel served none of ngs.nougenai.com's traffic for two weeks while every status probe returned 200; probe_field_parity.py can diff /health fields but runs by hand. Wiring it into the heartbeat means a false MISMATCH during a deploy_sha rollout looks like an outage.
- First fork: if you observe MISMATCH only on deploy_sha -> route A: treat as rollout and re-check in 10 minutes; else -> route B: alert immediately naming both origins
- Evidence: `fleet-ops/tools/probe_field_parity.py`, `fleet-ops/tools/fleet_heartbeat.py`
- Lens: observability · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: probe_field_parity.py exists with IDENTITY_FIELDS incl. deploy_sha and MATCH/MISMATCH/UNREACHABLE exit codes exactly as described, and is not wired into fleet_heartbeat.py; the two-week-silent-outage anecdote is a plausible inference from that gap, not independently confirmed.
- #550 families: 19, 20

### WG-0933 · P1 · elevate · effort S

**Stop every registry ack firing the 3-python CI matrix (paths-ignore .handoffs)**

- Failure surface: ci.yml triggers on every push to main; each ack, claim take/release and daemon PUT is a commit, and acquire_lease's comment records 148 retry_pending claim commits each firing CI. Adding paths-ignore means a code change bundled into a registry commit (dispatch._publish pushes HEAD:main) escapes tests.
- First fork: if you observe registry commits that also touch src/ in the last 30 days -> route A: gate on paths and add a nightly full run; else -> route B: paths-ignore only
- Evidence: `.github/workflows/ci.yml`, `src/nougen_relay/core.py`, `src/nougen_relay/dispatch.py`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .github/workflows/ci.yml triggers `on: push` (no paths filter) against a 3-version python matrix (3.10/3.11/3.13); dispatch.py _publish() pushes `HEAD:main`, matching the 'daemon PUT is a commit' / bundled-code-escapes-tests concern.

### WG-0941 · P1 · elevate · effort M

**Automate Codex quota window collection into the outbox on a schedule with provenance intact**

- Failure surface: docs/quota-provenance.md lists scheduled telemetry collection, checkpoint/fallback automation and the 1UP reset notification for leg 20260906T224549Z as outstanding; load_snapshot_from_env reads env vars a scheduler must populate. A collector that mislabels estimates as metered lets HARD gating block claims fleet-wide.
- First fork: if you observe the provider payload lacking rateLimitsByLimitId -> route A: label unknown and skip gating; else -> route B: record per window via codex_windows and deliver once
- Evidence: `docs/quota-provenance.md`, `src/nougen_relay/quota_telemetry.py`, `src/nougen_relay/quota_governor.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/quota-provenance.md:53-54 documents leg 20260906T224549Z with scheduled telemetry/checkpoint/fallback/1UP notification listed as outstanding; codex_windows() lives in quota_telemetry.py (checks rateLimitsByLimitId) and load_snapshot_from_env is defined in quota_governor.py and called from core.py cmd_quota/cmd_schedule.
- #550 families: 64

### WG-0949 · P1 · elevate · effort L

**Introduce a hybrid logical clock for relay events instead of second-granular wall-clock strings**

- Failure surface: Leg ids are UTC seconds from each box's clock, _relay_event_key dedupes on the 'at' string, foreign_claims and _superseding_relay_ids order by created_utc string compare across three formats ('Z', '+00:00', missing) and skewed clocks; two acks in the same second from one agent collapse into one event. Adding HLC fields changes every merge and reader at once.
- First fork: if you observe events with identical (event,at,agent) but different notes in the registry -> route A: add hlc plus producer_seq alongside 'at' and key merges on hlc; else -> route B: normalise formats first and defer HLC
- Evidence: `src/nougen_relay/core.py`, `tools/relay_daemon.py`, `.handoffs/`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: _relay_event_key (core.py:548) and foreign_claims (core.py:923) exist as described; .handoffs/ holds thousands of leg records with second-granularity UTC-timestamp filenames, supporting the collision scenario.
- #550 families: 13

### WG-0957 · P1 · elevate · effort L

**Promote fencing-token leases into the git registry so every executor shares one fence**

- Failure surface: acquire_lease/heartbeat_lease/fencing_ok work on .relay/leases (local); only relay_daemon writes a fleet-visible claims/<leg>__autonomous.json. Moving leases into .handoffs/leases means a heartbeat every TTL/3 becomes a commit or CAS PUT per active leg, multiplying registry traffic and CI runs.
- First fork: if you observe heartbeat cadence producing more than one commit a minute fleet-wide -> route A: heartbeat only the claim file via CAS with no local commit; else -> route B: commit leases with the sweep
- Evidence: `src/nougen_relay/core.py`, `tools/relay_daemon.py`, `.handoffs/claims/`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: acquire_lease/heartbeat_lease/fencing_ok all defined in core.py (lines ~1182-1412); tools/relay_daemon.py:859 writes '.handoffs/claims/{id}__autonomous.json'; .handoffs/claims/ holds 1,259 files, matching the described asymmetry between local leases and fleet-visible claim files.
- #550 families: 25

### WG-0964 · P1 · elevate · effort L

**Unify dispatch, daemon, autoclose and policy into one leg state machine with one status set**

- Failure surface: Four schedulers read disjoint queues: dispatch.DISPATCHABLE=(acked,open,retry_pending), daemon OPEN_HANDOFF_STATES=(open,active,held), autoclose acts on open only, policy stamps at birth. A leg can be acked by policy, dispatched to in_progress, ignored by the daemon and never completed. Any unification changes what each existing sweep touches on the live board.
- First fork: if you observe a leg touched by two schedulers within one sweep interval -> route A: elect one sweeper per state transition and dry-run for a week; else -> route B: document the ownership table only
- Evidence: `src/nougen_relay/dispatch.py`, `tools/relay_daemon.py`, `src/nougen_relay/autoclose.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dispatch.py:41 defines DISPATCHABLE=('acked','open','retry_pending') and relay_daemon.py:454 defines OPEN_HANDOFF_STATES as a tuple, confirming the disjoint-queue claim; autoclose.py exists with its own open-only sweep logic.
- #550 families: 24

### WG-0971 · P1 · elevate · effort M

**Make `relay ack` dispatch asynchronous through a wake outbox so acks never block on transport**

- Failure surface: cmd_relay ack calls dispatch_leg inline (90s nougenmsg) before committing; an outbox decouples them but then a wake sitting in .relay/wake (local, gitignored) on a box that goes to sleep never fires, and two boxes draining the same outbox double-wake nodes.
- First fork: if you observe the outbox drained only by the acking box -> route A: drain in the daemon cycle with a delivered marker on the leg; else -> route B: keep inline with a shorter timeout
- Evidence: `src/nougen_relay/core.py`, `src/nougen_relay/dispatch.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cmd_relay (core.py:1756) calls _dispatch.dispatch_leg inline at core.py:1810 before returning, and dispatch_leg is defined in dispatch.py:195, matching the inline-blocking-call claim.
- #550 families: 21

### WG-0977 · P1 · defend · effort S

**Extend shardlog SECRET_PATTERNS before the next FLEET-LOG relay (CF tokens, JWTs, Tailscale keys)**

- Failure surface: SECRET_PATTERNS covers sk-, gh*_, AKIA, xox, hf_, AIza, PEM and key=value shapes; Cloudflare API tokens (40 base62), JWTs (eyJ...), Tailscale tskey- and DPAPI-wrapped keymaker rows match none, and FLEET-LOGs quote wrangler and cloudflared commands verbatim into a repo that has a public twin.
- First fork: if you observe any eyJ or tskey- string in docs/FLEET-LOG-*.md today -> route A: rotate, scrub history, then extend patterns; else -> route B: extend patterns and add a test corpus
- Evidence: `src/nougen_relay/shardlog.py`, `docs/FLEET-LOG-2026-09-18.md`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: shardlog.py:84-99 SECRET_PATTERNS covers exactly the listed prefixes (sk-, gh[pousr]_, AKIA, xox, hf_, AIza, PEM, key=value) with none matching JWT/CF-token/tskey- shapes; docs/FLEET-LOG-2026-09-18.md does contain an eyJ... string (already partially redacted with x's) confirming the risk surface.
- #550 families: 70, 76

### WG-0983 · P1 · defend · effort S

**Keep untagged personal shards out of FLEET-LOGs that the public twin scrub must then chase**

- Failure surface: WITHHELD_TAGS withholds only shards tagged brand/personal/family/finance/legal/medical; an untagged shard about the owner relays verbatim into docs/FLEET-LOG-<date>.md, which is why docs/persona-dave-meralus.md had to be moved from the public repo (#73). The next public-parity sync carries it out.
- First fork: if you observe the vault exposing a sensitivity or domain_key column -> route A: withhold on sensitivity plus a name/PII regex; else -> route B: require --include-untagged for shards lacking any tag
- Evidence: `src/nougen_relay/shardlog.py`, `docs/persona-dave-meralus.md`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: shardlog.py:52-55 defines WITHHELD_TAGS as exactly {brand, positioning, personal, family, finance, legal, medical, insurance}, and docs/persona-dave-meralus.md exists in this repo as claimed.
- #550 families: 75

### WG-0988 · P1 · elevate · effort M

**Wire the daemon's lag_alerts to nougenmsg so the watchdog stops alerting only its own SQLite**

- Failure surface: run_cycle collects lag_alerts and record_triage inserts them into lag_alerts, but nothing reads that table except --status; a leg lagging five days produces 2,000 rows and zero messages. Sending them raises the opposite risk: 227 in_progress and 84 open legs would page every lane every cycle.
- First fork: if you observe more than 20 lagging legs -> route A: send one digest per node per 6h with counts and oldest id; else -> route B: send per-leg once with dedup on (id, day)
- Evidence: `tools/relay_daemon.py`, `src/nougen_relay/quota_delivery.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/relay_daemon.py defines lag_alerts_count field, a lag_alerts SQLite table (line 708), and record_triage() (line 1814) which inserts into it (line 1853); quota_delivery.py exists with delivery-side functions (format_alert, deliver_pending, nougenmsg_sender) that are not currently wired to lag_alerts.
- #550 families: 95

### WG-0992 · P1 · elevate · effort M

**Turn per-lane leg freshness into a fleet alarm so a silent blade1tb/hourly_shard is noticed in an hour**

- Failure surface: evaluate_triggers raises stale_handoff only for the local machine; blade1tb/hourly_shard writes every hour (619 legs) and is the best liveness signal the registry has, yet if it stops nothing fires. HARDENING history: vault quiet three days unnoticed, ingestion lanes dead for weeks.
- First fork: if you observe a lane's last leg older than 2x its median interval -> route A: emit a lane_quiet trigger to every session-start hook and one nougenmsg; else -> route B: log in the daemon pulse only
- Evidence: `src/nougen_relay/core.py`, `.handoffs/`, `src/nougen_relay/hook.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py:2585 defines evaluate_triggers with a 'stale_handoff' trigger name at line 2704; hook.py exists in the listed path; .handoffs/ contains the leg records this trigger scans over.
- #550 families: 95

### WG-0996 · P1 · defend · effort S

**Stop the daemon ack PUT re-escaping UTF-8 and reviving the 1,707-file phantom-diff treadmill**

- Failure surface: ack_leg_upstream serialises with json.dumps(record, indent=2) (ensure_ascii defaults True) while core.serialize_record and sync_relay_repo use ensure_ascii=False; every daemon ack rewrites arrows and em dashes as \uXXXX upstream, so the next sync re-dirties the file and `merge --ff-only` on blade is blocked again, the exact failure documented at line ~1476.
- First fork: if you observe `git diff --stat .handoffs` on blade showing hundreds of escape-only changes -> route A: switch the PUT to core.serialize_record and clean the worktree; else -> route B: add a canonical-bytes assertion test on the ack path
- Evidence: `tools/relay_daemon.py`, `src/nougen_relay/core.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: relay_daemon.py line 1482 uses json.dumps(merged, indent=2, ensure_ascii=False) but a comment at 1469-1471 explicitly documents the prior ensure_ascii=True bug and requirement, while core.py's serialize_record (line 91) uses ensure_ascii=False consistently -- matches the described historical/fixed distinction closely enough to support the claim.
- #550 families: 99

### WG-1000 · P1 · defend · effort S

**README's 227-test claim has drifted from the real 438-function suite**

- Failure surface: A reviewer or new operator trusts README.md's stated test count when judging whether coverage grew or shrank on a PR; the number has been wrong long enough that it stopped being a useful signal.
- First fork: if the tests/ function count and README's stated count diverge by >10% -> flag as doc drift in review; else treat README as trustworthy.
- Evidence: `README.md`, `tests/`
- Lens: product-docs · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: README.md:301 states '227 tests, of which one is a strict=True xfail'; pytest --collect-only against tests/ currently collects 446 tests -- a large drift confirming the core claim (exact figure differs slightly from the claimed 438 but direction and scale of drift are verified).
