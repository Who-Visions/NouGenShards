# War-game candidates — nougen-handoffs

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

169 candidates · P0 107 · P1 62 · P2 0 · P3 0 · defend 124 · elevate 45

| id | P | kind | title |
|---|---|---|---|
| WG-0001 | P0 | defend | Rotate the NGS_TOKEN/NGS_NODE_TOKEN pair leaked via NouGenShards PR #397 and prove it |
| WG-0017 | P0 | defend | Teach the sweep to cite leaked secrets by fingerprint, never by value |
| WG-0032 | P0 | defend | Close Issue #342: masked decrypted-vault-secret print in tools/check_kg_keys.py shipped to main |
| WG-0046 | P0 | defend | Fix the relay_claim_leg/relay_ack_leg leg_id path traversal (Issue #350) that shipped via PR #346 |
| WG-0058 | P0 | elevate | Make CodeQL and GitGuardian findings gate NouGenShards merges instead of PR-comment-only flags |
| WG-0069 | P0 | defend | Verify _harden_path ACL hardening now actually applies to vault keys on Windows nodes |
| WG-0080 | P0 | elevate | Write the sweep's authority scope: what an unattended session may merge, close, release or file |
| WG-0091 | P0 | defend | Land NouGenRelay#65 so Dav1d-planned probes with <PLACEHOLDER> argv never reach subprocess.run |
| WG-0101 | P0 | defend | Audit .mcp.json fleet-wide for dead remote servers and empty env-substituted keys |
| WG-0111 | P0 | defend | Verify self-reported test claims from substrate before the registry records them as truth |
| WG-0119 | P0 | defend | Rotate the 8 live Google API keys in vault\nougen_memories.db one lane at a time |
| WG-0127 | P0 | elevate | Decide the registry write path and clear the 35-deep draft backlog in one pass |
| WG-0135 | P0 | elevate | Add an open-PR and claims preflight to the sweep so parallel runs consolidate instead of piling up |
| WG-0143 | P0 | defend | Survive a dependabot burst that opens six PRs and six sweep sessions in the same minute |
| WG-0151 | P0 | elevate | Close the webhook coverage gap: PRs opened while a sweep is mid-run are never swept |
| WG-0159 | P0 | defend | Fix NouGenRelay's Actions runner allocation (runner_id: 0) so #65/#67/#68 can be validated at all |
| WG-0167 | P0 | elevate | Roll out the /health write-path probe (NGS_HEALTH_WRITE_PROBE_S) so a wedged vault no longer hangs health |
| WG-0175 | P0 | elevate | Move vault\RECOVERY_KEY.txt offline and confirm private_vault status still resolves |
| WG-0181 | P0 | defend | Track and stop the recurring db1 quarantine (4 hits in two days) instead of 'tracked separately' |
| WG-0186 | P0 | defend | Keep relay_live.py from stalling forever on SSH (NOUGEN_RELAY_LIVE_SSH_CONNECT_S) when a node's tunnel dies |
| WG-0191 | P0 | defend | Merge the relay_watch_node.py rewrites without regressing the 9h36m relay-blindness fix |
| WG-0196 | P0 | defend | Bring nougenai.com back from 502 without touching the shards.nougenai.com gateway route |
| WG-0201 | P0 | defend | Keep the 07:00 NouGenTube drip inside YouTube rate limits after the 7/24 IP block and the GM ban warning |
| WG-0206 | P0 | defend | Stop unrelated PRs from rewriting tools/zombie_killer.py into a SIGKILL-by-default supervisor |
| WG-0211 | P0 | defend | Survive a free-lane auth outage (Codex 402 / Gemini API_KEY_INVALID) without a lane dying silently |
| WG-0216 | P0 | defend | Restore or retire the chatgpt-codex-connector review lane that posts 'usage limits reached' on every PR |
| WG-0221 | P0 | defend | Verify cross-repo merge-order preconditions (ShadowDweller#4 before NouGenShards #491) from a scoped session |
| WG-0226 | P0 | defend | Split or reject 156-file mega PRs that bundle unrelated projects (MRSB, affect/persona) into NouGenShards |
| WG-0231 | P0 | defend | Block stale-base PRs that silently revert merged production fixes (#434, #397 at 35 commits behind) |
| WG-0236 | P0 | elevate | Sweep expired claims (ttl_hours) across nougen-handoffs, NouGenQ and NouGenRelay automatically |
| WG-0241 | P0 | defend | Win the live claim race: three lanes claimed the same Xoah slice within 44s and ignored the stand-down |
| WG-0245 | P0 | elevate | Ship a schema and validator for queue/task_*.md and handoff_*.json across three naming eras |
| WG-0249 | P0 | defend | Finish or kill the Open Engine task queue: gemini/codex tasks unclaimed since 2026-07-06 |
| WG-0252 | P0 | elevate | Run the held 47.8%-drift vault reindex (148k files, write mode) before brain-scan Move 4 |
| WG-0255 | P0 | defend | Land the pull-clone working tree (GM WIP + 5 audit fixes + steal list) that is 37 commits behind origin/main |
| WG-0258 | P0 | defend | Detect a lane that stops writing handoffs (codex silent since 2026-07-18) within a day, not two months |
| WG-0261 | P0 | elevate | Run stored-key liveness probes fleet-wide without tripping secret scanners or spending credits |
| WG-0264 | P0 | defend | Restore a quarantined db1 on the HF Space /data bucket mount after a WAL-on-network failure |
| WG-0267 | P0 | defend | Make every read-only tool open the live vault read-only (relay_push malformed-image crashes) |
| WG-0270 | P0 | defend | Prove capture truth from substrate after the write-path fix was dropped by a squash merge |
| WG-0273 | P0 | defend | Merge relay_watch_node singleton lock and blind-alert without reinstating either incident |
| WG-0276 | P0 | defend | Prove HLC merge survives real clock skew between blade, phoebus and whoart |
| WG-0279 | P0 | defend | Recover 196 stranded quota-wake tickets and pin writer/reader path resolution per node |
| WG-0282 | P0 | defend | Alert when a node writes handoffs locally but never pushes (93 files behind, remote casing) |
| WG-0284 | P0 | defend | Detect deployed-code vs main divergence after a squash merge drops a fix |
| WG-0286 | P0 | defend | Force MCP server reload when vault path or module code changes under a long-lived process |
| WG-0288 | P0 | defend | Guard issue bookkeeping against GitHub's negation-blind closing-keyword parser |
| WG-0290 | P0 | defend | Keep whoart pinned to gemma4:e2b-qat when a fleet-wide default-model swap lands first |
| WG-0292 | P0 | defend | Sanitize leg_id before relay_claim_leg/relay_ack_leg write into the claims directory |
| WG-0294 | P0 | defend | Make lane_freshness watch DB imports, not just files (arxiv DB lane silent 17 days) |
| WG-0296 | P0 | defend | Make a lane outage distinguishable from a quiet weekend (feed error exit 0 killed arxiv twice) |
| WG-0298 | P0 | defend | Set per-lane freshness thresholds so frozen codex/gemini dirs and a 93h handoff gap alarm |
| WG-0300 | P0 | defend | Build an escalation channel that actually reaches a lane (three Open Engine tasks idle 80 days) |
| WG-0302 | P0 | defend | Detect CI that lies (lint red since ruff 0.16 made pytest report skipped for weeks) |
| WG-0304 | P0 | defend | Distinguish runner-never-allocated CI red from code red when job logs return 404 |
| WG-0306 | P0 | elevate | Instrument the Gemini/Antigravity lane before reporting delegation share again |
| WG-0308 | P0 | defend | Probe Ollama by port not process so a dark 11434 is never read as 'local models unavailable' |
| WG-0310 | P0 | defend | Survive a blade power loss mid-write across the vault and the registry |
| WG-0312 | P0 | elevate | Purge quoted NGS tokens from `handoffs` history while three machines hold clones |
| WG-0314 | P0 | defend | Make /api/health the single source of truth for NouGenQ key presence (cached page lied) |
| WG-0315 | P0 | defend | Coalesce webhook bursts so six PRs in 65 minutes do not spawn six sweep sessions |
| WG-0316 | P0 | elevate | Unify the four repos' .handoffs registries so a sweep can see claims in every leg |
| WG-0317 | P0 | elevate | Add a sensitivity field to handoffs so insurance claims and personal photos stop hitting a public branch |
| WG-0318 | P0 | defend | Fuzz the Windows shell layer of handoff writes (cmd.exe newline cut, $3 expansion) |
| WG-0319 | P0 | defend | Separate the keymaker credential vault path from NOUGEN_VAULT_DIR so secrets never land in the shard dir |
| WG-0320 | P0 | defend | Verify vault key ACL hardening actually applied (icacls explicit ACEs, swallowed _harden_path ImportError) |
| WG-0321 | P0 | elevate | Make node launchers path-agnostic across blade, phoebus and whoart (two tasks, two code trees) |
| WG-0322 | P0 | defend | Restore the mesh write lane across reboots without leaving SOL_MESH_TOKEN unset (503 fail-closed) |
| WG-0323 | P0 | elevate | Answer the self-merge question and drain the 35-PR sweep-record backlog in one pass |
| WG-0324 | P0 | elevate | Add claim TTL expiry across nougen-handoffs, NouGenQ and NouGenRelay after a 65h-overdue claim was found by hand |
| WG-0325 | P0 | defend | Enforce claim stand-down: #476/#477 shipped API-incompatible duplicates after a live claim race told one lane to stop |
| WG-0326 | P0 | defend | Verify every 'tracked separately' cross-reference resolves to a real issue or claim |
| WG-0327 | P0 | defend | Prove fixes from substrate, not narrative: relay chain cited commit f05b550 that exists in no repo |
| WG-0328 | P0 | elevate | Turn sweep findings into a merge gate after CodeQL secret logging (#342) and path traversal (#350) shipped |
| WG-0329 | P0 | defend | Verify the ShadowDweller#4 precondition before #491 deletes the combat engine from NouGenShards |
| WG-0330 | P0 | defend | Detect stale-base PRs that silently revert fixed bugs (#434 reverted the WhoArt quarantine fix) |
| WG-0331 | P0 | defend | Block mega-PRs that bundle third-party EPUBs and unrelated projects (#435, 156 files, learn-with-mrs-b) |
| WG-0332 | P0 | defend | Stop scope-creep bundles like #423's SIGKILL-by-default OS-wide zombie nuke riding a CLI subcommand PR |
| WG-0333 | P0 | defend | Rotate and redact the two NGS bearer tokens quoted verbatim in queue records, then rewrite shared history |
| WG-0334 | P0 | elevate | Close the 8-live-Google-key rotation and RECOVERY_KEY.txt moves the 08-07 handoff left awaiting GM |
| WG-0335 | P0 | elevate | Port NouGenShards' published-surface guard to the registry: 28 C:\Users\super paths and 9 LAN IPs live here |
| WG-0336 | P0 | defend | Remove off-domain personal data from fleet memory: house renovation ledger, insurance claims, selfie descriptions |
| WG-0337 | P0 | elevate | Publish a JSON schema for handoff records: machine is a string in 48 files and an object in 18 |
| WG-0338 | P0 | defend | Fix the queue filename split: three task_YYYYMMDDTHHMMSSZ_ files sort out of order against task_YYYYMMDD_HHMMSS_ |
| WG-0339 | P0 | defend | Treat the Codex connector's 'usage limits reached' on every PR as a dead reviewer lane, not noise |
| WG-0340 | P0 | defend | Fix the usage watchdog before it reports delegation share again: ccusage is blind to Gemini and misreads Codex |
| WG-0341 | P0 | defend | Detect PRs that never triggered a sweep (#400/#401, #409, #468-#482 gap) before they merge unreviewed |
| WG-0342 | P0 | defend | Break the single-box secret dependency: NouGenQ's OPENROUTER_API_KEY can only be set from blade1tb |
| WG-0343 | P0 | defend | Build a flake registry so sweeps stop mis-classifying test_boot_quarantine_nonblocking and HLC drift as defects |
| WG-0344 | P0 | defend | Stop carrying NouGenRelay CI red for 6+ sweeps: job logs 404 for the integration and #65 stayed undrawn |
| WG-0345 | P0 | defend | Set a dependabot policy after zod v4, pydantic-core and tomlkit bumps each broke a build |
| WG-0346 | P0 | defend | Require a test artifact behind every '290 passed' and '201/201 green' claim in a handoff |
| WG-0347 | P0 | elevate | Roll the hardcoded-account-path guard out as a fleet pre-commit after four PRs tripped it in a week |
| WG-0348 | P0 | defend | Write the sweep's authority envelope: it marks PRs ready, merges siblings, opens issues, releases NouGenQ claims |
| WG-0349 | P0 | defend | Forbid sweeps from pushing to other lanes' PR branches after #514's lint fix landed mid-sweep |
| WG-0350 | P0 | defend | Bring nougenai.com back from 502 before any public product surface points at it |
| WG-0351 | P0 | defend | Keep canon names consistent across 600 records after EchoVault->Toujou and metameric->Valerion renames |
| WG-0352 | P0 | elevate | Land NouGenQ #1 deploy preflight (54 days open) before the merged Q Live Prompt Loop reaches the public lane |
| WG-0353 | P0 | elevate | Flip the Evolution Wing distill lane default only after restarting the stale nougen-shards MCP server |
| WG-0354 | P0 | elevate | Run the HELD vault reindex (47.8% drift) before brain-scan Move 4 corrupts benchmark baselines |
| WG-0355 | P0 | elevate | Pin the fleet .mcp.json: ollama-mcp's Node 25 patch lives in the npx cache and reverts on clear |
| WG-0356 | P0 | defend | Close relay legs when their PR merges: leg 20260913T174622Z stayed in_progress after #341 landed |
| WG-0357 | P0 | defend | Prevent writer/reader path splits like the 196 stranded quota-wake tickets from recurring in the registry |
| WG-0358 | P0 | defend | Check claims against the live branch, not the checkout: sweeps reported 'no claims' while NouGenQ held a stale one |
| WG-0359 | P0 | defend | Handle sweeps that exceed their trigger scope (#485 fixed NouGenRelay CI, #467 root-caused the daemon) |
| WG-0360 | P0 | defend | Finish or kill the Open Engine task queue: three 2026-07-06 lane tasks unclaimed after three escalations |
| WG-0361 | P0 | defend | Make the acknowledged_by field real or drop it: 415 of 449 handoff JSONs are still status open |
| WG-0365 | P1 | defend | Close CodeQL #112/#113: dav1d_exec uncontrolled command line and exception text returned by /dav1d/ask |
| WG-0381 | P1 | defend | Harden GET /shards/{id} db_index selection and dedupe the two competing route handlers in app.py |
| WG-0397 | P1 | elevate | Roll NGS_FLEET_PEER_TOKEN out to blade/phoebus/whoart and rotate it without dropping federation |
| WG-0413 | P1 | elevate | Unblock NouGenQ #1 deploy-preflight after 56 days and hand off the auth/secrets/deploy steps it defers |
| WG-0429 | P1 | defend | Never bake a trycloudflare quick-tunnel URL into the fleet worker's SHARD_GATEWAY_URL |
| WG-0445 | P1 | elevate | Assign per-node ports (NOUGEN_NODE_<NODE>_PORT) and IPv4-first peers across whoart/phoebus/blade |
| WG-0460 | P1 | defend | Prove quota-wake tickets reach the daemon on all three nodes after the ~/Outpost vs ~/.nougen/relay split |
| WG-0473 | P1 | defend | Keep the Hugging Face Space snapshot deploy green when requirements.txt or oversized PDFs change |
| WG-0486 | P1 | defend | Prune closed Cloud Run services (DAV1D, RHEA, BANDIT, old KAEDRA) from every fleet roster that still calls them |
| WG-0498 | P1 | defend | Probe and rotate the still-unprobed secret classes in the archive (PEM, OpenAI, GCP SA, Slack, HF, OpenRouter) |
| WG-0510 | P1 | defend | Land the pytest 9 importorskip fix (NouGenRelay#68) so test_mcp_server skips cleanly when the MCP SDK is absent |
| WG-0522 | P1 | elevate | Cut the frontier lane from Fable 5 subscription to API without breaking the usage watchdog rate card |
| WG-0534 | P1 | defend | Purge rotated-key residue from Txt Saves\, antigravity logs, .dart_tool and sol_tools.py |
| WG-0546 | P1 | defend | Reconcile Python 3.13 on phoebus, 3.11 on blade1tb and the 3.10-3.12 CI matrix before a version-only bug ships |
| WG-0558 | P1 | elevate | Install lane_guard_precommit.py on every machine so hardcoded account paths die before CI (4th instance) |
| WG-0570 | P1 | elevate | Encrypt the 2.5 GB 'Just Dave' archive with private_vault encrypt-file, abort on row count != 379,163 |
| WG-0581 | P1 | elevate | Replace per-sweep re-flag sections with a carried-items index (first_flagged/last_checked per item) |
| WG-0592 | P1 | defend | Give automated sweeps their own git identity instead of committing as the GM's account |
| WG-0603 | P1 | elevate | Resume the paused 26k AI-tool-history brain import behind the capture secret guard |
| WG-0614 | P1 | defend | Fix the coach-governor lint failure and close the /live control-plane gap on main |
| WG-0625 | P1 | elevate | Add a schema+validator for handoff_*.json without breaking NouGenShards handoff_feed discovery |
| WG-0636 | P1 | defend | Fix naive-vs-UTC timestamp mix that misorders handoff_feed across blade and whoart |
| WG-0647 | P1 | defend | Reconcile the two queue filename clocks (task_YYYYMMDD_HHMMSS vs task_YYYYMMDDTHHMMSSZ) |
| WG-0658 | P1 | defend | Run a backup/restore drill for handoffs.db while rebuild-db rewrites it under a live writer |
| WG-0669 | P1 | defend | Survive a disk-full WAL checkpoint on blade's C: drive without a malformed vault |
| WG-0680 | P1 | defend | Reconcile the three divergent shard stores (11,800 / 50,926 / 17,771) without doubling or dropping |
| WG-0691 | P1 | defend | Run the HELD full reindex over 148k vault files without corrupting benchmark baselines |
| WG-0702 | P1 | defend | Rotate the ~55 plaintext credentials in nougen_memories.db in blast-radius order |
| WG-0713 | P1 | elevate | Roll out /health BEGIN IMMEDIATE write-probe across every mounted DB without wedging health |
| WG-0724 | P1 | elevate | Build the fleet NLI pass over conflict_candidates so supersession is more than a pending table |
| WG-0734 | P1 | elevate | Turn the one-shot audit_daemon.sh into a triaged pipeline or delete its committed outputs |
| WG-0744 | P1 | defend | Write a scope limit for sweeps that release claims, open issues and ready PRs in other repos |
| WG-0754 | P1 | defend | Add an open-PR preflight so parallel sweeps stop being blind to each other's drafts |
| WG-0764 | P1 | defend | Tombstone known-corrupt records (19-char truncation, $3,922 mangled) without rewriting history |
| WG-0774 | P1 | defend | Detect permission-policy drift that silently disabled the sweep's self-merge step |
| WG-0784 | P1 | defend | Expire stale claims automatically (NouGenQ claim sat 65h past a 6h TTL) |
| WG-0794 | P1 | defend | Make claims/ the enforced claim-before-work registry (#238/#239, #289/#291, #295/#296 collisions) |
| WG-0804 | P1 | defend | Coordinate quality_daemon and host_power autonomous writers on the same working tree |
| WG-0814 | P1 | defend | Define append-only merge rules for queue files two sweeps race to update |
| WG-0824 | P1 | elevate | Rotate NGS_NODE_TOKEN and NGS_FLEET_PEER_TOKEN across the 3-node fanout with no auth gap |
| WG-0834 | P1 | elevate | Enable secondary-vault federation reads without curated shards sinking under transcript noise |
| WG-0844 | P1 | defend | Kill or bind the 193 orphan .sessions/*.start markers that join to no session_id |
| WG-0854 | P1 | defend | Make acknowledged_by real or drop it (415 of 454 handoffs still open) |
| WG-0864 | P1 | defend | Stop sweeps declaring 'clean' while the Python matrix is still in_progress |
| WG-0874 | P1 | defend | Judge daemon liveness by heartbeat mtime, never by the content it last wrote |
| WG-0884 | P1 | defend | Detect the MCP capture lane dropping mid-session and diverting writes to the Python API |
| WG-0893 | P1 | elevate | Migrate root handoff_*.json to YYYYMMDDTHHMMSSZ__machine__agent naming without reordering the feed |
| WG-0902 | P1 | defend | Make the NouGenTube harvest resumable after a session crash leaves a 0-byte batch |
| WG-0910 | P1 | defend | Stop each re-flag sweep from re-copying the leaked secret into a new registry file |
| WG-0918 | P1 | defend | Put Sol-Ai frozen-baseline files under version control before an agent edit has no rollback |
| WG-0926 | P1 | defend | Stop session_id sharing across lanes (claude-cli and gemini records carry the same uuid) |
| WG-0934 | P1 | defend | Guard registry readers against Git-LFS pointer stubs parsed as corrupt PDFs and images |
| WG-0942 | P1 | defend | Sweep the dependabot batch once and pin lockfiles before pydantic-core drift breaks pip again |
| WG-0950 | P1 | elevate | Roll handoff_push.py redact-verify-refuse gate onto every registry writer fleet-wide |
| WG-0958 | P1 | defend | Cap queue/ filename length before a 142-char verdict-name breaks a Windows clone |
| WG-0965 | P1 | defend | Guard against GitHub closing-keyword negation: 'does not close #255' will auto-close #255 |
| WG-0972 | P1 | defend | Define the sweep's post-merge role when owners merge within 3 minutes of opening (#341, #467, #445) |
| WG-0978 | P1 | elevate | Extend sweep scope from 4 repos to the 7 NouGen repos gemini found without multiplying the trigger storm |
| WG-0984 | P1 | defend | Catch stacked PRs targeting a feature branch (#436 on #435's branch) before they inherit its findings |
| WG-0989 | P1 | defend | Scrub personal Gmail addresses and OpenRouter key-id fragments from the vault-encryption handoffs |
| WG-0993 | P1 | defend | Decide whether machine_id, hostnames and session UUIDs belong in a published handoff record |
| WG-0997 | P1 | elevate | Decide the registry's visibility and add secret scanning before the next sweep quotes a token |

---

### WG-0001 · P0 · defend · effort M

**Rotate the NGS_TOKEN/NGS_NODE_TOKEN pair leaked via NouGenShards PR #397 and prove it**

- Failure surface: Two live bearer tokens (node auth for shards.nougenai.com fanout) sit in a public PR diff and are re-quoted verbatim in two registry records; 11+ sweeps flagged with zero rotation confirmation anywhere. Anyone reading the PR can authenticate to a node as the owner vault.
- First fork: if you observe the two tokens still accepted by any node /health auth -> rotate on all three nodes first, then verify each node's scheduled task picks up the new env; else -> record rotation evidence in the registry and move to history scrub
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260916_231500_pr433-conflicts-with-merged-421-supersedes-431-432-428-duplicates-426-397-11th-flag.md`, `queue/task_20260916_062900_pr412-clean-pending-checks-issue342-350-still-open.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260915_115500_pr397... quotes both live tokens verbatim (NGS_TOKEN in tools/fleet_detail.py, NGS_NODE_TOKEN in tools/run_node_blade.bat) and queue/task_20260916_231500_pr433... re-verifies both still live in the diff, 11+ consecutive sweeps, zero rotation. Evidence directly supports claim; third path (pr412) not read but first two suffice.
- #550 families: 76, 100

### WG-0017 · P0 · defend · effort S

**Teach the sweep to cite leaked secrets by fingerprint, never by value**

- Failure surface: The automated relay-check routine copied both bearer tokens verbatim into queue/ records and a public PR comment, turning one leak into three. Every future GitGuardian hit will be re-broadcast the same way unless the sweep redacts.
- First fork: if you observe a sweep record containing a string that matches a secret-scanner pattern -> block the record write and rewrite with sha256[:8] fingerprint; else -> add the redaction step to the sweep's flag template and back-test on the #397 record
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260916_231500_pr433-conflicts-with-merged-421-supersedes-431-432-428-duplicates-426-397-11th-flag.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Same two files confirm the sweep itself copied both bearer tokens verbatim into the queue/ record and referenced a PR comment restating them -- exactly the re-broadcast the item describes.
- #550 families: 70

### WG-0032 · P0 · defend · effort S

**Close Issue #342: masked decrypted-vault-secret print in tools/check_kg_keys.py shipped to main**

- Failure surface: CodeQL py/clear-text-logging-sensitive-data flagged on PR #340, PR self-merged in 3 minutes unfixed; carried 15+ sweeps with duplicate fixes #373/#375 colliding. Vault key material reaches logs on every debug run.
- First fork: if you observe #373 already merged (sweep pr451 says it did) -> verify check_kg_keys.py on main no longer calls _unprotect for output and close #342; else -> pick #373 over #375, merge, then re-scan
- Evidence: `queue/task_20260913_205200_pr340-codeql-clear-text-secret-log.md`, `queue/task_20260913_210800_pr341-secret-log-shipped-unfixed-issue342.md`, `queue/task_20260920_174749_pr451-deps-consolidate-breaks-pip-tomlkit-gradio-conflict-373-merged.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260913_205200_pr340...md and task_20260913_210800_pr341...md document the exact code (`masked = val[:8] + '...' + val[-4:]`, print of decrypted secret) and Issue #342 opened after PR #340 self-merged in 3 minutes unfixed; task_20260920_174749_pr451...md confirms PR #373 (the fix, closing #342/#350) merged 2026-09-20 -- fully matches the claim including the pr451 pointer.
- #550 families: 70, 76

### WG-0046 · P0 · defend · effort M

**Fix the relay_claim_leg/relay_ack_leg leg_id path traversal (Issue #350) that shipped via PR #346**

- Failure surface: Two MCP tools write `claims_dir / f"{leg_id}__autonomous.json"` with unsanitized leg_id; any relay leg or MCP caller can write arbitrary files on the node host. Flagged as a PR comment, merged unfixed, escalated to an issue nobody owns.
- First fork: if you observe #373 merged with the sanitize pattern from evolution.py -> write a regression test with `../` leg_ids and close #350; else -> land the sanitizer and audit the other 50 tools in the 52-tool MCP surface for the same pattern
- Evidence: `queue/task_20260914_044500_pr346-relay-claim-leg-path-traversal.md`, `queue/task_20260914_080330_pr349-clean-flagged-346-path-traversal-shipped.md`
- Lens: injection · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260914_044500_pr346...md documents the exact vulnerable code (`claims_dir / f"{leg_id}__autonomous.json"`, unsanitized) and task_20260914_080330_pr349...md confirms PR #346 merged unfixed and the finding was escalated to Issue #350 -- matches claim exactly including the evolution.py sanitize-pattern reference.
- #550 families: 71

### WG-0058 · P0 · elevate · effort M

**Make CodeQL and GitGuardian findings gate NouGenShards merges instead of PR-comment-only flags**

- Failure surface: Both #340 (secret logging) and #346 (path traversal) merged with open high-severity alerts because the sweep only comments; the CodeQL rollup is failing but not a required check. The registry becomes the only tracker of shipped vulns.
- First fork: if you observe branch protection on main with required checks -> add the CodeQL rollup and secret scan to the required set and watch the next dependabot burst for false blocks; else -> enable protection first, then required checks, and grant the sweep a documented bypass path for pure-doc PRs
- Evidence: `queue/task_20260913_210800_pr341-secret-log-shipped-unfixed-issue342.md`, `queue/task_20260914_080330_pr349-clean-flagged-346-path-traversal-shipped.md`
- Lens: security-gate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260913_210800_pr341 and task_20260914_080330_pr349 together document both #340 (secret logging) and #346 (path traversal) merging with open high-severity alerts because the sweep is comment-only, exactly supporting the claim that CodeQL/GitGuardian findings are not gating merges.

### WG-0069 · P0 · defend · effort M

**Verify _harden_path ACL hardening now actually applies to vault keys on Windows nodes**

- Failure surface: private_vault.py imported a keymaker._harden_path that never existed; the ImportError was swallowed so every key written since was never icacls-locked. Existing key files on blade1tb/whoart remain world-readable until re-hardened.
- First fork: if you observe icacls on the keymaker vault dir showing inherited Users read -> run a one-time re-harden over existing keys and log warnings; else -> add a startup check that fails closed when _harden_path is unavailable
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260915_123500_pr398-supersedes-397-new-codeql-cleartext-log-issue342-recurrence.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260915_115500_pr397...md documents verbatim that private_vault.py imported a keymaker._harden_path that never existed, causing every _write_recovery_key/_generate_key call to raise ImportError silently swallowed, so vault keys were never ACL-hardened; task_20260915_123500_pr398...md documents the fix PR and its own new CodeQL findings -- matches claim exactly.

### WG-0080 · P0 · elevate · effort M

**Write the sweep's authority scope: what an unattended session may merge, close, release or file**

- Failure surface: Sweeps have merged sibling drafts, filed issues, posted PR comments and considered releasing stale NouGenQ claims with no recorded scope; 35 sessions each re-derived the self-merge question. Either they over-act or they freeze, and both have happened.
- First fork: if you observe Dave answering the nougen-handoffs#135 comment -> encode that answer as a scope doc the sweep reads at start; else -> ship the narrowest safe default (single-new-file zero-overlap doc PRs self-merge; everything else flag-only) as CANDIDATE
- Evidence: `queue/task_20260908_180700_meta-six-unmerged-handoff-drafts.md`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: tool-abuse · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260908_180700_meta-six-unmerged-handoff-drafts.md documents the exact process gap (six parallel sweep sessions each opening unmerged draft PRs, no scope for self-merge, GM decision never recorded) and task_20260923_194500_pr513...md confirms the self-merge question is still open ~2h20m at a 35-deep backlog, first raised on nougen-handoffs#135 -- matches the claim's narrative and figures exa

### WG-0091 · P0 · defend · effort M

**Land NouGenRelay#65 so Dav1d-planned probes with <PLACEHOLDER> argv never reach subprocess.run**

- Failure surface: relay_daemon.dav1d_probe_verify lets an Ollama planner invent probe commands; 441 of 1184 claims dead-lettered, several because `curl http://<PHOEBUS_NODE_ENDPOINT>/status/sync` ran literally. A model-authored argv reaching a shell is also an injection seam.
- First fork: if you observe the NouGenRelay runner still allocating no runner (runner_id 0) -> validate #65 locally and merge on local evidence, labeled CANDIDATE; else -> let CI prove it, then re-triage the 441 dead_letter claims
- Evidence: `queue/task_20260921_161500_pr467-dead-letter-fix-merged-root-caused-daemon-placeholder-probes-relay65.md`, `queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: tool-abuse · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260921_161500_pr467...md documents exactly: 441 of 1184 recorded claims (37%) ended dead_letter, and a grep for literal <[A-Z_]*> template tokens found claim files with unresolved placeholders as literal probe arguments (e.g. `curl http://<PHOEBUS_NODE_ENDPOINT>/status/sync`); NouGenRelay#65 is documented as the fix -- exact match including the 441/1184 figure.
- #550 families: 71

### WG-0101 · P0 · defend · effort S

**Audit .mcp.json fleet-wide for dead remote servers and empty env-substituted keys**

- Failure surface: remote.mcpservers.org sequentialthinking went NXDOMAIN and e2b hung on an unset ${E2B_API_KEY}; /doctor showed 4 failures on one machine only because someone ran it. Other nodes' .mcp.json copies likely still carry both.
- First fork: if you observe another node's .mcp.json referencing remote.mcpservers.org or ${E2B_API_KEY} -> apply the same swap/removal and re-run doctor; else -> add a scheduled doctor run whose failures post to nougenmsg
- Evidence: `_claude_handoff_msg.md`, `claims/20260817T045532Z__whoart__fable.json`
- Lens: mcp · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: _claude_handoff_msg.md documents both findings verbatim: e2b removed because E2B_API_KEY was empty/unset causing a hang, and sequentialthinking swapped because remote.mcpservers.org went NXDOMAIN -- exact match to the claim's two named issues.
- #550 families: 36, 38

### WG-0111 · P0 · defend · effort M

**Verify self-reported test claims from substrate before the registry records them as truth**

- Failure surface: A 20-record chatgpt-app/claude-app chain asserted a fix in commit f05b550 with 176 tests passing; the commit exists in no repo. PR #447 claimed 15/15 passing while CI was red. The registry became a ledger of fiction.
- First fork: if you observe a handoff citing a sha -> resolve it in all four repos before recording; else -> mark the claim UNVERIFIED in the record and route to the owner lane
- Evidence: `queue/task_20260907_161100_f05b550-commit-not-found.md`, `queue/task_20260919_230500_pr448-clean-boot-port-fix-447-ci-red-373-sole-carryover.md`
- Lens: provenance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260907_161100_f05b550-commit-not-found.md documents in detail the chain of handoffs claiming a fix landed in commit f05b550 with 176 tests passing, confirms via get_commit/git log that no such commit existed in any of the four in-scope repos at the time, and task_20260919_230500_pr448...md documents PR #447's self-reported '15/15 tests passing' claim contradicted by CI showing CodeQL 
- #550 families: 100

### WG-0119 · P0 · defend · effort L

**Rotate the 8 live Google API keys in vault\nougen_memories.db one lane at a time**

- Failure surface: Eight fully-live AIza keys (313 plaintext rows, davemeralus account carries spendable credits) were probed live and left unrotated awaiting GM go-ahead. A batch rotation breaks Gemini lanes, sol_tools.py and blerdcon tooling simultaneously.
- First fork: if you observe a key returning 200 on generativelanguage /v1beta/models -> rotate that one, probe its dependent lane, then next; else (403/SERVICE_DISABLED) -> still rotate, it is a valid key, do not treat as dead
- Evidence: `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`, `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.json`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: claude cli handoffs/handoff_20260807_221134...md states verbatim: 8 fully-live Google API keys, 313 rows, davemeralus@gmail.com carries credits, rotation set is 8 not 44, Move 1 says rotate one at a time probing Gemini lanes/sol_tools.py/blerdcon tooling -- matches the claim's specifics exactly.
- #550 families: 62

### WG-0127 · P0 · elevate · effort M

**Decide the registry write path and clear the 35-deep draft backlog in one pass**

- Failure surface: Every sweep since #135 declines to merge its predecessor; findings for NouGenShards #470-#514 exist only in unmerged branches, so the next sweep, handoff_feed and any human reading `handoffs` are blind to two days of fleet state.
- First fork: if you observe Dave's answer on nougen-handoffs#135 -> apply it (direct fast-forward push, or self-merge for single-file zero-overlap records) and squash-merge #135-#170 oldest-first; else -> pick option (b) as CANDIDATE, merge the backlog, and record the decision in the registry
- Evidence: `queue/task_20260908_180700_meta-six-unmerged-handoff-drafts.md`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both evidence files exist and directly document the unmerged-backlog problem and the #513 registry backlog at 35 deep.

### WG-0135 · P0 · elevate · effort M

**Add an open-PR and claims preflight to the sweep so parallel runs consolidate instead of piling up**

- Failure surface: Six sweeps in 13 hours each opened a draft blind to the others; two records stuck at a stale state until a human diffed six branches. The preflight exists manually (pr346/pr348 sweeps did it) but not in the routine.
- First fork: if you observe an open sweep draft with mergeable_state clean at trigger time -> merge it (or rebase onto it) before cutting a branch; else -> cut from tip and record the tip sha in the new file
- Evidence: `queue/task_20260908_180700_meta-six-unmerged-handoff-drafts.md`, `queue/task_20260914_063200_pr348-relay-ssh-stall-clean-drafts-piled-up.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Meta task file documents six blind parallel drafts; pr348 record documents the manual preflight pattern the item wants automated.
- #550 families: 25

### WG-0143 · P0 · defend · effort M

**Survive a dependabot burst that opens six PRs and six sweep sessions in the same minute**

- Failure surface: #458-#463 opened within 24 seconds; each pull_request.opened webhook spawns its own sweep, each racing to merge the previous record and write its own. Some records were written by a concurrent sweep (pr461 notes '#457's registry PR already merged by a concurrent sweep').
- First fork: if you observe more than one PR opened by dependabot[bot] within 60s -> the first sweep claims the batch and the rest exit after writing a one-line pointer; else -> normal single-PR sweep
- Evidence: `queue/task_20260921_153900_pr463-pydantic-core-lockfile-conflict-root-caused-fixed.md`, `queue/task_20260921_153200_pr461-clean-annotated-doc-bump-ci-in-progress-419-closed.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr463 and pr461 records both document the six-PR dependabot burst within seconds and a concurrent sweep overwriting/merging another's record.
- #550 families: 25, 84

### WG-0151 · P0 · elevate · effort M

**Close the webhook coverage gap: PRs opened while a sweep is mid-run are never swept**

- Failure surface: #400/#401, #403 and #427-#429 were only caught by ad-hoc catch-up sections in later records; a pull_request.opened-only trigger with no reconciliation means merged-unswept PRs (secrets, path leaks) go unrecorded in the fleet's memory.
- First fork: if you observe a PR number gap between consecutive sweep records -> run a reconciliation pass over list_pull_requests since last tip; else -> add synchronize/ready_for_review triggers and an hourly reconcile
- Evidence: `queue/task_20260915_204434_pr402-clean-catchup-400-401-coverage-gap.md`, `queue/task_20260916_204500_pr430-clean-fleet-agents-target-fix-backlog-427-429-not-yet-swept.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr402 and pr430 records document PR-number gaps (400/401, 427-429) only caught by ad-hoc catch-up sections.
- #550 families: 3

### WG-0159 · P0 · defend · effort M

**Fix NouGenRelay's Actions runner allocation (runner_id: 0) so #65/#67/#68 can be validated at all**

- Failure surface: Every lint/test job on NouGenRelay fails in ~2s with no runner ever assigned; 15+ sweeps carried 'CI red' as if it were code, and the placeholder-probe fix (#65) has never had a real run. A repo-level runner/label or billing setting is the cause.
- First fork: if you observe a workflow `runs-on` label with no matching runner or an Actions spending cap hit -> fix the setting and re-run #68; else -> switch the workflow to ubuntu-latest hosted runners as CANDIDATE
- Evidence: `queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`, `queue/task_20260923_143344_pr498-clean-wake-daemon-watchdirs-mirror-fix-registry-backlog-22deep-relay-ci-infra-confirmed.md`
- Lens: ci-infra · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr486 and pr498 records both state CI red on NouGenRelay is runner-allocation infra, not code, matching the claim directly.

### WG-0167 · P0 · elevate · effort M

**Roll out the /health write-path probe (NGS_HEALTH_WRITE_PROBE_S) so a wedged vault no longer hangs health**

- Failure surface: Today blade's /health hung and CLOSE_WAIT piled up; PR #507 adds BEGIN IMMEDIATE/ROLLBACK probes per mounted DB with a 2s cap. A watchdog that treats the new `write_path.blocked` warning as healthy, or a probe that itself blocks, recreates the freeze.
- First fork: if you observe the 5-min watchdog reading only HTTP 200 -> teach it to parse write_path.ok; else -> deploy #507 to one node, wedge a DB deliberately, confirm health returns within timeout_s
- Evidence: `queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr507 record exists and matches the health write-path probe / CLOSE_WAIT description directly.
- #550 families: 94

### WG-0175 · P0 · elevate · effort M

**Move vault\RECOVERY_KEY.txt offline and confirm private_vault status still resolves**

- Failure surface: The master key for all 224 encrypted 'Just Dave' files sits in plaintext beside the archive it protects; moving it is GM-only and blocks Move 3. Wrong sequencing leaves the vault undecryptable or the key still on disk.
- First fork: if you observe `private_vault status` resolving via the DPAPI keymaker after the file is removed -> proceed to encrypt-file on the archive; else -> restore the key from the offline copy and stop, no archive encryption
- Evidence: `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`, `gemini handoffs/handoff_20260807_175232_feat_private-vault-encryption.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Same handoff .md states RECOVERY_KEY.txt still plaintext beside archive, master key for 224 encrypted 'Just Dave' files, blocks Move 3, GM action only, and Move 0 explicitly says verify private_vault status still resolves after moving it -- matches claim precisely.

### WG-0181 · P0 · defend · effort M

**Track and stop the recurring db1 quarantine (4 hits in two days) instead of 'tracked separately'**

- Failure surface: core.quarantine_malformed_dbs kept quarantining db1 on boot; PR #250 said it was tracked but nothing exists; #382 moved the heal off the startup path so the node now boots fast while db1 is silently missing from federation answers.
- First fork: if you observe db1 quarantined on any node right now -> pull the file, run integrity_check, and file the issue with logs; else -> add a quarantine counter to /health and alert on the second occurrence
- Evidence: `queue/task_20260906_153000_db1-quarantine-untracked.md`, `queue/task_20260915_033748_pr382-boot-quarantine-nonblocking-merged-clean-issue342-350-still-open.md`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: db1-quarantine-untracked and pr382 records both exist and directly document the untracked recurring quarantine and the boot-time change moving it off the startup path.
- #550 families: 6

### WG-0186 · P0 · defend · effort S

**Keep relay_live.py from stalling forever on SSH (NOUGEN_RELAY_LIVE_SSH_CONNECT_S) when a node's tunnel dies**

- Failure surface: Before #348 a hung SSH fetch blocked the relay loop indefinitely; whoart's tunnel died today for hours. Without ConnectTimeout/ServerAlive the relay watch on other nodes freezes and the fleet loses the baton.
- First fork: if you observe GIT_SSH_COMMAND set on a node -> the env override bypasses the fix, set the timeouts there too; else -> confirm core.sshCommand carries the three options on each repo clone
- Evidence: `queue/task_20260914_063200_pr348-relay-ssh-stall-clean-drafts-piled-up.md`, `queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr348 record exists and documents exactly this SSH-stall problem prompting timeout options; pr486 provides fleet corroboration.
- #550 families: 43

### WG-0191 · P0 · defend · effort M

**Merge the relay_watch_node.py rewrites without regressing the 9h36m relay-blindness fix**

- Failure surface: #270 fixed phoebus sitting unaware of 62 remote legs because alerts were gated on 'no fresh legs'; #289/#291 rewrote the same loop from a stale base. A naive conflict resolution restores the wrong gate and blinds the watcher again.
- First fork: if you observe the merged pull() missing divergence()/missing_legs() -> reject the merge; else -> replay the 62-leg scenario against the merged watcher before landing
- Evidence: `queue/task_20260908_033800_pr289-291-relay-watch-conflict.md`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260908_033800 record exists and directly documents the #289/#291 conflict risk against the #270 relay-blindness fix, matching the claim closely.

### WG-0196 · P0 · defend · effort M

**Bring nougenai.com back from 502 without touching the shards.nougenai.com gateway route**

- Failure surface: The brand domain has returned 502 since at least 2026-06-13 while the shards subdomain is the live 3-node gateway; a DNS or Cloudflare fix on the apex that touches the shared zone can take the gateway down with it.
- First fork: if you observe the 502 originating from a Cloudflare worker route on the apex -> fix the worker binding only; else -> check origin/tunnel for the apex and leave the shards.* tunnel config untouched, verify /health after
- Evidence: `claude handoffs/PLAYBOOK_2026-06-13.md`, `queue/task_20260914_042500_pr345-clean-issue342-nouq-prs-stale.md`
- Lens: deploy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: PLAYBOOK_2026-06-13.md explicitly states 'nougenai.com returns 502 (deploy/routing)' while shards.nougenai.com is described as the live gateway elsewhere in the fleet docs.
- #550 families: 42

### WG-0201 · P0 · defend · effort M

**Keep the 07:00 NouGenTube drip inside YouTube rate limits after the 7/24 IP block and the GM ban warning**

- Failure surface: ~20 rapid caption fetches tripped a multi-hour IP block on egress 174.176.143.129; GM ordered all burst harvesting stopped. The daily task now drips with NOUGEN_YT_DRIP_CAP=5, but cookies.txt is still pending and any parallel run re-triggers the flag.
- First fork: if you observe harvest_daily.log with a circuit OPEN line -> skip drip that day and alert, never retry; else -> confirm NEW_FETCHES <= cap and 8s pacing, and never run from a signed-in session
- Evidence: `_msg_nougentube_harvest.md`, `_msg_evolve_wing.md`
- Lens: scheduled-task · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: _msg_nougentube_harvest.md documents the IP block on egress 174.176.143.129 and the harvest circuit-breaker behavior; _msg_evolve_wing.md corroborates ongoing harvest activity.
- #550 families: 58

### WG-0206 · P0 · defend · effort M

**Stop unrelated PRs from rewriting tools/zombie_killer.py into a SIGKILL-by-default supervisor**

- Failure surface: #423 bundled a full rewrite of the process reaper merged five minutes earlier (#420), adding SIGKILL defaults and game-themed subcommands; a supervisor that kills the wrong node process on blade takes the gateway down.
- First fork: if you observe zombie_killer.py on main with insta_kill/nuke subcommands -> revert to #420's reaper and require a claim for supervisor changes; else -> add a test that the default action is SIGTERM with a grace period
- Evidence: `queue/task_20260916_155200_pr423-native-open-subcommand-bundles-reverted-zombie-killer-rewrite.md`, `queue/task_20260916_062900_pr412-clean-pending-checks-issue342-350-still-open.md`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr423 record directly documents the zombie_killer.py rewrite bundled into an unrelated PR five minutes after #420 merged, matching the claim closely.

### WG-0211 · P0 · defend · effort M

**Survive a free-lane auth outage (Codex 402 / Gemini API_KEY_INVALID) without a lane dying silently**

- Failure surface: On 2026-07-25 Codex went 402 and Gemini 400 API_KEY_INVALID; Codex billing stopped after Jun 29 and nobody noticed for a month because ccusage has zero Gemini instrumentation and misreads Codex.
- First fork: if you observe a lane's last handoff older than 7 days (codex: 2026-07-18) -> probe its key with a read-only call and alert; else -> add per-lane key liveness to the daily watchdog
- Evidence: `claude handoffs/handoff_20260729_084228_chore_public-surface-untrack-internal.md`, `codex handoffs/`
- Lens: auth · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: claude handoffs/handoff_20260729_084228_chore_public-surface-untrack-internal.md explicitly states the Codex 402/Gemini 400 API_KEY_INVALID outage and 'Codex billing stopped after Jun 29'; codex handoffs/ latest file is handoff_20260718_235619, matching the cited 2026-07-18 staleness date.
- #550 families: 57, 59

### WG-0216 · P0 · defend · effort S

**Restore or retire the chatgpt-codex-connector review lane that posts 'usage limits reached' on every PR**

- Failure surface: Every recent NouGenShards PR carries the same bot notice; the Codex review lane is dead but still installed, adding noise the sweep must filter and giving a false sense of a second reviewer.
- First fork: if you observe the Codex subscription renewed -> confirm one real review lands; else -> uninstall the connector and record the lane as retired in the registry
- Evidence: `queue/task_20260920_163119_pr450-codeql-blocked-uncontrolled-cmdline-exception-exposure-373-sole-carryover.md`, `queue/task_20260914_234124_pr363-keymaker-test-fixture-clean-issue342-350-still-unowned.md`
- Lens: supply-chain · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both cited queue files quote the exact recurring PR comment: 'chatgpt-codex-connector[bot] ... Codex usage limits reached/review-credit exhaustion ... not actionable', confirming a dead-but-installed review lane on every recent PR.
- #550 families: 57

### WG-0221 · P0 · defend · effort S

**Verify cross-repo merge-order preconditions (ShadowDweller#4 before NouGenShards #491) from a scoped session**

- Failure surface: #491 deletes the combat engine from NouGenShards on the promise it landed in WhoVisions/ShadowDweller#4, which the sweep's GitHub scope cannot see; merging on trust can delete the only copy of 786 lines and 33 tests.
- First fork: if you observe the sweep token unable to read ShadowDweller -> hold #491 and ask a lane with scope to attach the merge sha; else -> verify #4 merged, then merge #491
- Evidence: `queue/task_20260923_031550_pr491-nougenfight-moved-out-shadowdweller-dep-unverifiable-backlog-17deep.md`
- Lens: supply-chain · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260923_031550...pr491 documents exactly this: PR #491 deletes 786 lines/tests from NouGenShards citing WhoVisions/ShadowDweller#4 (33 tests passing) as the landing spot, explicitly states 'This session's GitHub access is scoped to NouGenShards/NouGenRelay/nougen-handoffs/NouGenQ only — WhoVisions/ShadowDweller is out of scope', and recommends holding the merge until verified — matches
- #550 families: 15

### WG-0226 · P0 · defend · effort M

**Split or reject 156-file mega PRs that bundle unrelated projects (MRSB, affect/persona) into NouGenShards**

- Failure surface: #435 (+19,286 lines) bundled an entire unrelated project and an undescribed persona subsystem; nobody can review it, CI fails on hardcoded paths, and #436 stacked on its branch. If merged wholesale, unreviewed code ships to the gateway.
- First fork: if you observe a PR over N files touching more than one top-level package -> the sweep labels it unreviewable and asks for a split; else -> normal review
- Evidence: `queue/task_20260917_003600_pr435-mega-pr-bundles-unrelated-mrsb-project-and-affect-persona-subsystem-hardcoded-paths-fail-ci-duplicates-433.md`, `queue/task_20260917_065500_pr436-duplicate-gauntlet-q4-q7-fix-already-on-base-branch-inherits-435-mess.md`
- Lens: supply-chain · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260917_003600...pr435 confirms +19286/-9 across 156 files, an unrelated learn-with-mrs-b project, and an undescribed affect/behavior/persona/emoji subsystem; pr436's file confirms it targeted PR #435's own branch and 'inherits every open #435 finding until #435 lands' -- matches the stacking claim.

### WG-0231 · P0 · defend · effort M

**Block stale-base PRs that silently revert merged production fixes (#434, #397 at 35 commits behind)**

- Failure surface: #434 reverted two previously fixed production bugs and #397 carried a federation refactor that never landed; a squash-merge of either overwrote main's fixes with no diff line saying 'revert'.
- First fork: if you observe a PR whose merge-base is >N commits behind main -> require a rebase before review; else -> diff the merge result against main for deleted fix hunks
- Evidence: `queue/task_20260916_231430_pr434-ngs-canonical-fact-snapshots-stale-branch-reverts-fixed-bugs.md`, `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`
- Lens: supply-chain · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260916_231430...pr434 documents the branch reverting the WhoArt-boot-quarantine fix and the write-fault-vs-malformed-row fix; queue/task_20260915_115500...pr397 documents 'branch is 35 commits stale' (tip cf3e249 vs fork 4792954) plus two leaked bearer tokens -- matches both halves of the claim exactly.
- #550 families: 28

### WG-0236 · P0 · elevate · effort M

**Sweep expired claims (ttl_hours) across nougen-handoffs, NouGenQ and NouGenRelay automatically**

- Failure surface: A NouGenQ claim sat active 65h past its 6h TTL with the lane commit never pushed and was found only by hand; claims/ here holds four released records and nothing has claimed since August, so TTL is unenforced everywhere.
- First fork: if you observe a claim with created_utc + ttl_hours < now and no released_utc -> mark expired, notify the lane via nougenmsg, and free the scope; else -> no-op and log the check
- Evidence: `claims/`, `claims/20260817T045532Z__whoart__fable.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260923_194500...pr513 explicitly documents a NouGenQ claim (20260921T025036Z__blade1tb__claude-cli.json) found 'status: active, ~65h past its 6h TTL, never released,' matching the claim verbatim; claims/ here holds exactly four released records, none since 2026-08-17.
- #550 families: 26

### WG-0241 · P0 · defend · effort M

**Win the live claim race: three lanes claimed the same Xoah slice within 44s and ignored the stand-down**

- Failure surface: phoebus/claude-cli claimed first, blade1tb/claude-cli 10s later, phoebus/claude-app 44s later; an explicit STOP via nougenmsg was ignored and two API-incompatible implementations (#476/#477) were built.
- First fork: if you observe a claim on a leg already claimed within the TTL -> refuse the second claim at write time; else -> proceed, and make stand-down messages block the losing lane's next push
- Evidence: `queue/task_20260921_190525_pr477-xoah-toolbelt-slice1-duplicates-476-live-claim-race-standdown-ignored.md`, `queue/task_20260921_190637_pr476-duplicates-pr477-xoah-toolbelt-slice1-flagged-relay65-relay67-ci-infra-carried.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260921_190525...pr477 gives exact timestamps: phoebus/claude-cli 18:56:02Z, blade1tb/claude-cli 18:56:12Z (+10s), phoebus/claude-app 18:56:46Z (+44s), an explicit stand-down at 19:00:51Z that blade1tb's push (19:00:56Z) beat by 5 seconds -- matches the claim's timing precisely, and confirms #476/#477 as the two incompatible implementations.
- #550 families: 25

### WG-0245 · P0 · elevate · effort M

**Ship a schema and validator for queue/task_*.md and handoff_*.json across three naming eras**

- Failure surface: Records exist as handoff_YYYYMMDD_HHMMSS_*, YYYYMMDDTHHMMSSZ__machine__agent and task_20260923T172312Z_ vs task_20260923_ in the same dir; NouGenShards #513 had to patch discovery/sort to cope. The next naming drift silently drops records from the feed.
- First fork: if you observe a file the validator cannot parse -> the sweep refuses to write a sibling until renamed; else -> validate on every PR and backfill an index.json
- Evidence: `queue/task_20260923T172312Z_pr501-nougenmsg-node-resolve-clean-registry-backlog-24deep.md`, `20260816T232004Z__whoart__codex.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: hygiene · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed three distinct naming conventions coexist: handoff_YYYYMMDD_HHMMSS_*.json (e.g. handoff_20260828_105352_blade1tb_main.json), YYYYMMDDTHHMMSSZ__machine__agent.json (20260816T232004Z__whoart__codex.json), and both task_20260923T172312Z_... and task_20260923_...  in queue/ simultaneously; queue/task_20260923_194500...pr513 documents handoff.py being patched specifically to recognize multipl
- #550 families: 36

### WG-0249 · P0 · defend · effort M

**Finish or kill the Open Engine task queue: gemini/codex tasks unclaimed since 2026-07-06**

- Failure surface: agent_tasks in handoffs.db and three queue/ ledgers were created for gemini and codex lanes; only the smoke test ever reached done, escalations went to unmerged drafts, and the retrieval junk-score bug the gemini task describes is still open.
- First fork: if you observe gemini/codex lanes still producing no handoffs -> reassign the three tasks to claude-cli or close won't-fix with a reason; else -> ping the lane via nougenmsg with the queue command
- Evidence: `queue/task_20260706_110919_b8c580c4.md`, `claude cli handoffs/handoff_20260705_031341_claude-cli_atom-audit-fixes.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: queue/task_20260706_110919_b8c580c4.md documents a gemini-lane task created 2026-07-06, 'still todo, unclaimed 60/69 days after creation', escalated three times with zero response; claude cli handoffs/handoff_20260705_031341...atom-audit-fixes.md references the Open Engine task queue protocol appended to CLAUDE.md/GEMINI.md/AGENTS.md -- matches the claim.

### WG-0252 · P0 · elevate · effort L

**Run the held 47.8%-drift vault reindex (148k files, write mode) before brain-scan Move 4**

- Failure surface: ~71k arxiv backfill files are unindexed; the repair is a write-mode pass over the live vault HELD for GM. Running it during a benchmark corrupts baselines; not running it means every recall answers from half the vault.
- First fork: if you observe an active benchmark or dream pass on the vault -> wait; else -> snapshot the vault DBs, run index_integrity.py reindex, verify drift < NOUGEN_INTEGRITY_DRIFT_PCT, then Move 4
- Evidence: `claude cli handoffs/handoff_20260730_011159_chore_valerion-naming-purge.md`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260730_011159...valerion-naming-purge.md states verbatim: '47.8% index drift quantified... ~71k of 148,368 files, all arxiv_* backfill family... Repair command ready but HELD for GM (vault write mode)' and explicitly recommends running the reindex before Move 4 -- matches the claim's numbers exactly.
- #550 families: 97

### WG-0255 · P0 · defend · effort M

**Land the pull-clone working tree (GM WIP + 5 audit fixes + steal list) that is 37 commits behind origin/main**

- Failure surface: Uncommitted supersession, conflict-candidate and index-integrity work sits in one working tree with GM WIP; a stray checkout or the blade1tb 08-28 handoff's own uncommitted core.py/keymaker.py edits can overwrite either set with no recovery.
- First fork: if you observe the tree still dirty against origin/main -> stash-branch it (feat/valerion-supersession), commit as-is, then rebase; else -> confirm which PR carried it and close the loop
- Evidence: `claude cli handoffs/handoff_20260730_011159_chore_valerion-naming-purge.md`, `handoff_20260828_105352_blade1tb_main.json`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260730_011159...valerion-naming-purge.md states verbatim: 'Pull-clone working tree now carries: GM WIP + 5 brain-scan audit fixes + steal-list implementation, all uncommitted, 37 behind origin/main'; handoff_20260828_105352_blade1tb_main.json's git diff lists uncommitted changes to src/nougen_shards/core.py and keymaker.py -- matches both halves of the claim.
- #550 families: 28

### WG-0258 · P0 · defend · effort M

**Detect a lane that stops writing handoffs (codex silent since 2026-07-18) within a day, not two months**

- Failure surface: codex handoffs/ ends 07-18 and gemini handoffs/ 08-07 with no alert; the HARDENING history already records ingestion lanes dying silently for weeks. The registry knows the last write time but nothing reads it.
- First fork: if you observe a lane's newest record older than 48h while its scheduled task ran -> alert via nougenmsg and mark the lane degraded; else -> record freshness per lane in the daily watchdog
- Evidence: `codex handoffs/`, `gemini handoffs/`, `claude handoffs/handoff_20260729_084228_chore_public-surface-untrack-internal.md`
- Lens: operate · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Directory listings confirm codex handoffs/ ends at handoff_20260718_235619 and gemini handoffs/ ends at handoff_20260807_231130 with no later entries, matching the claimed 07-18/08-07 staleness dates exactly.
- #550 families: 95

### WG-0261 · P0 · elevate · effort M

**Run stored-key liveness probes fleet-wide without tripping secret scanners or spending credits**

- Failure surface: Kaedra's auth-check asks each provider whether a stored key works; its realistic fixtures needed an allowlist because CI secret scanners flagged them, and probing paid endpoints can spend the davemeralus credits the incident is trying to protect.
- First fork: if you observe a probe target with no free read-only endpoint -> skip and mark unprobed; else -> probe, and keep fixtures in a scanner-allowlisted path with a comment saying why they look real
- Evidence: `claude cli handoffs/handoff_20260804_222419_KushBoyGroups-Mac-mini_feat_auth-check.md`, `queue/task_20260908_000500_pr278-fixture-secret-scan-collision.md`
- Lens: auth · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: claude cli handoffs/handoff_20260804_222419...feat-auth-check.md references the Kaedra auth-check work and a commit '3fd22ab test(surface): allowlist the auth-check fixtures, and say why they look real'; queue/task_20260908_000500...pr278 documents the exact fixture-vs-secret-scanner collision (gitleaks flagging realistic synthetic credential fixtures) -- matches the claim.

### WG-0264 · P0 · defend · effort M

**Restore a quarantined db1 on the HF Space /data bucket mount after a WAL-on-network failure**

- Failure surface: Four 'vtable constructor failed' quarantines in 13h were caused by WAL forced on a network-backed mount; #253 switched to DELETE journal mode but no drill proves a quarantined grid DB can be restored or its shards re-ingested.
- First fork: if you observe /health vault_journal_mode != DELETE on a bucket mount -> route A: stop writes and flip journal mode before restore; else -> route B: restore quarantined file into scratch, quick_check, re-capture surviving rows
- Evidence: `queue/task_20260906_153000_db1-quarantine-untracked.md`, `queue/task_20260908_020000_pr284-relay-push-readonly-and-255-status.md`
- Lens: data-integrity/corruption · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both files exist; the first is explicitly titled 'db1-quarantine-untracked' directly documenting the quarantine incident this item concerns.
- #550 families: 91

### WG-0267 · P0 · defend · effort S

**Make every read-only tool open the live vault read-only (relay_push malformed-image crashes)**

- Failure surface: relay_push.py opened the live vault read-write for pure SELECTs and hit 'database disk image is malformed' twice; any other tool doing the same on a busy node can wedge a checkpoint. #284 sat dirty and unmerged.
- First fork: if you observe any tool under tools/ opening nougen_shards_*.db without mode=ro -> route A: uri=True mode=ro sweep with a test that asserts CREATE TABLE fails; else -> route B: central get_connection(readonly=True) helper
- Evidence: `queue/task_20260908_020000_pr284-relay-push-readonly-and-255-status.md`
- Lens: data-integrity/corruption · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File exists and its title directly names 'relay-push-readonly' and 'pr284', matching the failure_surface claim about relay_push.py and PR #284.

### WG-0270 · P0 · defend · effort M

**Prove capture truth from substrate after the write-path fix was dropped by a squash merge**

- Failure surface: captured:false reason:duplicate returned for brand-new content; the fix (f05b550) was squash-dropped by #273 so production ran unmerged code with no commit to roll back to. A response is not evidence; the canary must read its row back.
- First fork: if you observe a capture response with no existing_shard_id/durable field -> route A: canary write + GET /shards/{id} byte-compare before trusting any lane; else -> route B: assert durable:true and shard_id resolvable per node
- Evidence: `queue/task_20260907_161100_f05b550-commit-not-found.md`
- Lens: data-integrity/durable-write · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File exists and is titled exactly 'f05b550-commit-not-found', directly matching the commit-sha-dropped-by-squash claim.
- #550 families: 100

### WG-0273 · P0 · defend · effort M

**Merge relay_watch_node singleton lock and blind-alert without reinstating either incident**

- Failure surface: Two lanes rewrote pull()/main() the same day: #270 fixed a 9h36m blindness (62 legs unseen), #289 fixed a FETCH_HEAD race and 8 immortal duplicate watchers on whoart. A pick-one-side resolution loses one fix and both PRs sat dirty 14.5h.
- First fork: if you observe more than one relay_watch_node process on whoart -> route A: land the singleton lock first, then re-apply blind-alert on top; else -> route B: land #270 diagnostics wrapped around #289's fetch-then-merge body
- Evidence: `queue/task_20260908_033800_pr289-291-relay-watch-conflict.md`
- Lens: distributed/races · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File exists and its title 'pr289-291-relay-watch-conflict' directly names the relay_watch_node conflict between the two PRs described.
- #550 families: 29

### WG-0276 · P0 · defend · effort M

**Prove HLC merge survives real clock skew between blade, phoebus and whoart**

- Failure surface: receive_hlc reads its own time.time(); a tick between now() and receive resets logical_counter to 0. The fix pinned the test clock only; production nodes with skewed wall clocks will still produce non-monotonic HLCs and misorder relay legs.
- First fork: if you observe local_curr_ms > remote_physical_ms by more than drift tolerance on any leg -> route A: clamp to max and bump counter, log drift; else -> route B: reject the leg and alert clock skew
- Evidence: `queue/task_20260923_143500_pr499-hlc-clock-race-test-fix-clean-registry-backlog-22deep.md`, `queue/task_20260921_063827_pr456-clean-diff-ci-red-unrelated-hlc-flake.md`
- Lens: distributed/clocks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both files exist, titled 'pr499-hlc-clock-race-test-fix' and 'pr456-...-hlc-flake', directly matching the HLC clock-race/receive_hlc claim.
- #550 families: 13

### WG-0279 · P0 · defend · effort M

**Recover 196 stranded quota-wake tickets and pin writer/reader path resolution per node**

- Failure surface: wake_daemon.WATCH_DIRS hardcoded the canonical path while the writer honored NOUGEN_RELAY_DIR; whoart dropped a month of wake tickets (oldest 2026-08-28). #495 flipped the split direction instead of closing it.
- First fork: if you observe tickets in Outpost\NouGenRelay\.relay\wake older than 1h -> route A: replay them through the daemon then dedupe; else -> route B: archive and assert writer and reader resolve the same dir on every node
- Evidence: `queue/task_20260923_143344_pr498-clean-wake-daemon-watchdirs-mirror-fix-registry-backlog-22deep-relay-ci-infra-confirmed.md`, `queue/task_20260923_143500_pr499-hlc-clock-race-test-fix-clean-registry-backlog-22deep.md`
- Lens: distributed/partial-failure · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr498 file content explicitly describes wake_daemon.WATCH_DIRS hardcoded, NOUGEN_RELAY_DIR/FLEET_RELAY_DIR, 196 real tickets, oldest from 2026-08-28 -- matches the failure_surface verbatim.
- #550 families: 62

### WG-0282 · P0 · defend · effort S

**Alert when a node writes handoffs locally but never pushes (93 files behind, remote casing)**

- Failure surface: handoff create + rebuild-db committed and pushed nothing; blade was 8 behind with 93 uncommitted records while reporting '388 records'; a remote URL casing redirect masked failed pushes. Phoebus could not see blade's handoffs for weeks.
- First fork: if you observe local record count > origin/handoffs record count by >5 -> route A: handoff_push.py run and freshness line in the next handoff; else -> route B: nightly check of `git status --porcelain | wc -l` per node with a push-notification
- Evidence: `claude cli handoffs/handoff_20260802_114315_claude-cli_cli-colour-theme.md`
- Lens: observability/silent-death · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff file explicitly describes create+rebuild-db pushing nothing, blade 8 behind with 93 uncommitted files, '388 records' being local-only, and the remote casing redirect masking pushes; matches claim closely.
- #550 families: 12

### WG-0284 · P0 · defend · effort M

**Detect deployed-code vs main divergence after a squash merge drops a fix**

- Failure surface: #273's squash silently dropped the durable-write fix so production ran code with no commit on main; which_tree.py exists to report what a running process imports but its own count() shadow bug broke every real --proc match.
- First fork: if you observe a running node whose imported file hash != main's blob -> route A: flag DEPLOY-DRIFT in /health and the sweep; else -> route B: nightly which_tree --proc on every node into the registry
- Evidence: `queue/task_20260907_161100_f05b550-commit-not-found.md`, `queue/task_20260908_050200_pr295-296-which-tree-shadow-fix-collision.md`
- Lens: observability/false-done · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Task file confirms PR #273 squash-merge silently dropped the durable-write fix (f05b550), leaving production code with no ancestor commit on main; second file confirms which_tree.py's count() shadow bug broke --proc matches.
- #550 families: 28

### WG-0286 · P0 · defend · effort S

**Force MCP server reload when vault path or module code changes under a long-lived process**

- Failure surface: core.GLOBAL_DIR resolved once at import so the MCP read a wrong-but-populated store for its lifetime and every miss looked like a healthy no-match; the evolution module also ran pre-patch until restart. No restart signal exists.
- First fork: if you observe recall footer vault dir != NOUGEN_VAULT_DIR -> route A: server self-restarts or refuses queries; else -> route B: supervisor restarts on .mcp.json or src mtime change
- Evidence: `claude cli handoffs/handoff_20260724_162810_chore_public-surface-untrack-internal.md`, `_msg_evolve_wing.md`
- Lens: observability/health-that-lies · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: First file directly describes core.GLOBAL_DIR resolving once at import causing a long-lived MCP to read the wrong-but-populated store; second file confirms the running MCP loads the pre-patch evolution module until restart.
- #550 families: 38

### WG-0288 · P0 · defend · effort S

**Guard issue bookkeeping against GitHub's negation-blind closing-keyword parser**

- Failure surface: 'does not close #255' in #284's body registered #284 as the closer; a merge would have credited the wrong fix and closed an unresolved defect. Sweeps rely on issue state as memory.
- First fork: if you observe closed_by_pull_requests listing a PR whose body negates closing -> route A: comment and reword before merge; else -> route B: sweep verifies closing credit matches the root-cause PR
- Evidence: `queue/task_20260908_020000_pr284-relay-push-readonly-and-255-status.md`
- Lens: data-integrity/tracker · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Task file directly documents PR #284's body saying 'does not close #255' yet GitHub's closed_by_pull_requests listing #284 as the closer, exactly matching the claim.

### WG-0290 · P0 · defend · effort S

**Keep whoart pinned to gemma4:e2b-qat when a fleet-wide default-model swap lands first**

- Failure surface: #239 hardcoded gemma4:e2b for every node and merged before the node-aware #238; whoart lost its Rule 0.5.1 pinned model and Rule 0.5.1 is no longer even a citable anchor. Per-node config lives in code.
- First fork: if you observe ping_ollama default != the node's /api/tags resident model -> route A: per-node override file wins over code default; else -> route B: revert to node-aware map and document the rule
- Evidence: `queue/task_20260905_132200_ollama-model-collision.md`
- Lens: distributed/config-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File documents PR #239 merging first with a hardcoded default overriding whoart's CLAUDE.md Rule 0.5.1 pin, and a later note that 'git grep 0.5.1' finds only an incidental mention, not a defined rule.
- #550 families: 54

### WG-0292 · P0 · defend · effort S

**Sanitize leg_id before relay_claim_leg/relay_ack_leg write into the claims directory**

- Failure surface: MCP-exposed relay_claim_leg builds `claims_dir / f"{leg_id}__autonomous.json"` from caller input; a `../` leg_id writes anywhere on the host, corrupting the claims store the fleet coordinates on.
- First fork: if you observe a leg_id not matching [A-Za-z0-9_-]+ -> route A: reject with error; else -> route B: slugify and record the original in the file body
- Evidence: `queue/task_20260914_044500_pr346-relay-claim-leg-path-traversal.md`
- Lens: data-integrity/store-escape · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File quotes the exact vulnerable code path (claims_dir / f"{leg_id}__autonomous.json") with unsanitized leg_id, matching the claim verbatim.
- #550 families: 71

### WG-0294 · P0 · defend · effort S

**Make lane_freshness watch DB imports, not just files (arxiv DB lane silent 17 days)**

- Failure surface: Per-paper .md files landed daily while the vault DB shard lane wrote zero on every day 07-06..07-23; lane_freshness.py measures files so the DB stall was invisible and reported OK.
- First fork: if you observe newest shard row date lagging newest .md by >48h -> route A: freshness reports the DB lane STALE and exits non-zero; else -> route B: add a shard-count delta line per lane
- Evidence: `handoff_20260725_082206_chore_public-surface-untrack-internal.md`
- Lens: observability/lane-freshness · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File explicitly states the DB shard lane wrote zero every day 07-06 to 07-23 while .md files landed daily, and that lane_freshness.py measures files so the stall would be invisible — matches claim exactly.
- #550 families: 96

### WG-0296 · P0 · defend · effort S

**Make a lane outage distinguishable from a quiet weekend (feed error exit 0 killed arxiv twice)**

- Failure surface: Feed fetch failures were recorded in feed_errors but exited 0, so the lane died 2026-06-18 and 2026-07-06 unnoticed; the rewrite adds a status enum but the Monday first-weekday run was the only proof and the 3-day rule is a human watch rule.
- First fork: if you observe status EMPTY_UNEXPECTED or FEED_ERRORS on a weekday -> route A: exit 2 and push-notify; else -> route B: EMPTY_EXPECTED_SKIPDAY only when the feed's own skipDays says so
- Evidence: `handoff_20260725_082206_chore_public-surface-untrack-internal.md`, `handoff_20260725_080721_chore_public-surface-untrack-internal.md`
- Lens: observability/silent-death · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: First file: 'Feed fetch failure recorded in feed_errors but still exited 0 ... exactly how the lane died 2026-06-18 and 2026-07-06.' Second file lays out the Monday-run watch rule as a manual human rule. Matches claim closely.
- #550 families: 2

### WG-0298 · P0 · defend · effort S

**Set per-lane freshness thresholds so frozen codex/gemini dirs and a 93h handoff gap alarm**

- Failure surface: handoffs lane went STALE at 93h against a 48h threshold once; codex handoffs stopped 2026-07-18 and gemini 2026-08-07 with no alarm because the lane dirs are not freshness lanes at all. A dead lane looks like an idle one.
- First fork: if you observe a lane dir with no write in 7 days -> route A: mark lane RETIRED in an index and stop counting it; else -> route B: per-lane threshold from its own write cadence and alert on 3x
- Evidence: `claude cli handoffs/handoff_20260707_080748_claude-cli_atom-audit-fixes.md`, `codex handoffs/`, `gemini handoffs/`
- Lens: observability/lane-freshness · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff file logs 'handoffs STALE (93h, threshold 48h)' matching the claim exactly; directory listings confirm codex handoffs' newest file is 2026-07-18 and gemini handoffs' newest is 2026-08-07, both with no freshness alarm mechanism evident.
- #550 families: 96

### WG-0300 · P0 · defend · effort S

**Build an escalation channel that actually reaches a lane (three Open Engine tasks idle 80 days)**

- Failure surface: Gemini/codex tasks from 2026-07-06 were escalated three times, but two escalations were draft PRs never merged so the flag never reached the lane; the drill blocker was cleared in an hour and nobody resumed. Re-flagging adds nothing.
- First fork: if you observe an escalation whose PR is unmerged after 24h -> route A: escalate via nougenmsg/push to the lane and GM; else -> route B: reassign or close won't-fix with a recorded decision
- Evidence: `queue/task_20260706_110919_b8c580c4.md`, `queue/task_20260706_114216_6472397a.md`, `queue/task_20260706_112027_afeb7ff0.md`
- Lens: observability/alerting-gap · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Files show three 2026-07-06 tasks (gemini/codex owner lanes) each with escalation entries describing 'Two prior automated escalations ... opened as drafts and never merged, so this flag never reached the lane'; the drill task shows the blocker (Ollama D: drive) resolved within hours as a false alarm. Matches claim closely.
- #550 families: 27

### WG-0302 · P0 · defend · effort S

**Detect CI that lies (lint red since ruff 0.16 made pytest report skipped for weeks)**

- Failure surface: NouGenShards CI showed Import-test and pytest 'skipped' because Lint failed first; twelve 'prints success while doing nothing' defects shipped behind it. Sweeps count 'success/skipped' as green.
- First fork: if you observe pytest job conclusion == skipped on main -> route A: sweep flags CI-LYING and treats the PR as unverified; else -> route B: require pytest to run independent of lint
- Evidence: `handoff_20260724_200141_chore_public-surface-untrack-internal.md`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: observability/false-done · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: First file: 'CI Lint had been failing since ruff 0.16.0, so Import-test and pytest reported skipped... suite had not actually run in CI since that release', plus the twelve silent-success defects list. Directly matches claim; second file is only weak supporting context (CI-green sweep pattern) but not contradicting.
- #550 families: 82

### WG-0304 · P0 · defend · effort S

**Distinguish runner-never-allocated CI red from code red when job logs return 404**

- Failure surface: NouGenRelay #65/#67/#68/#70 show every job failing in 2-3 seconds for 46h; the sweep token gets 403/404 on logs so it cannot tell infra from regression, and a real dead-letter fix sat undrawn 2+ days.
- First fork: if you observe all jobs completing < 5s after start -> route A: classify INFRA and page the repo owner, not the PR author; else -> route B: fetch logs with an owner token and triage as code
- Evidence: `queue/task_20260923_143344_pr498-clean-wake-daemon-watchdirs-mirror-fix-registry-backlog-22deep-relay-ci-infra-confirmed.md`
- Lens: observability/health-that-lies · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File documents #65 and #70 both showing lint/test jobs failing in 2-3 seconds, 46 hours apart, get_job_logs returning 404, and #65 (a real dead-letter fix) undrawn 2+ days — matches claim precisely.
- #550 families: 81

### WG-0306 · P0 · elevate · effort M

**Instrument the Gemini/Antigravity lane before reporting delegation share again**

- Failure surface: ccusage returns -0.0 for Gemini (no instrumentation) and under-reports Codex; a false 'doctrine drift, delegation 0%' alarm fired 07-24, and Haiku is priced 5x by rate-card gaps. Spend decisions ride on these numbers.
- First fork: if you observe agent=='all' rows or -0.0 in the watchdog input -> route A: split by modelBreakdowns and mark Gemini UNINSTRUMENTED; else -> route B: wire step-count proxy from the 37 conversation DBs
- Evidence: `claude handoffs/handoff_20260729_084228_chore_public-surface-untrack-internal.md`, `handoff_20260808_001044_feat_private-vault-encryption.md`
- Lens: observability/metrics-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: First file confirms -0.0 for Gemini meaning no instrumentation, Codex under-reporting, the false 07-24 doctrine-drift/0% delegation alarm, Haiku rate-card gap (5x overpricing), and 37 conversation DBs — matches claim in detail.

### WG-0308 · P0 · defend · effort S

**Probe Ollama by port not process so a dark 11434 is never read as 'local models unavailable'**

- Failure surface: whoart's ollama tray process was alive with nothing listening; two sessions concluded local models were gone and a stale OLLAMA_MODELS=D: env var once produced a false 'drive disconnected' diagnosis. Scheduled-task repetition attached to a logon trigger never fires.
- First fork: if you observe /api/tags not answering while the process exists -> route A: ollama_guard.ps1 restart and record the incident; else -> route B: treat as truly down and fall to OpenRouter/HF lanes
- Evidence: `queue/task_20260923_182727_pr510-clean-ollama-guard-ps1-ci-pending-backlog-31-deep-selfmerge-unanswered.md`, `queue/task_20260706_114216_6472397a.md`
- Lens: observability/health-that-lies · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: First file cites the concrete 2026-09-23 incident (tray process alive, nothing on 11434, two sessions wrongly concluded unavailable) and the logon-trigger-repetition issue; second file documents the earlier stale OLLAMA_MODELS=D: false 'drive disconnected' diagnosis. Matches claim closely.
- #550 families: 95

### WG-0310 · P0 · defend · effort M

**Survive a blade power loss mid-write across the vault and the registry**

- Failure surface: 16 host deaths in 30 days on an AC-only Razer with the battery removed; a death mid-capture or mid-handoff-create leaves a half-written .json twin or WAL frame, and the boot-death recorder only captures the current boot.
- First fork: if you observe a 41/6008 event since last boot -> route A: run quick_check on all DBs and validate the last handoff twin before any lane resumes; else -> route B: normal start with the death count in the handoff
- Evidence: `claude cli handoffs/handoff_20260724_184537_chore_public-surface-untrack-internal.md`, `handoff_20260724_200141_chore_public-surface-untrack-internal.md`
- Lens: data-integrity/partial-failure · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: First file states '16 host deaths in 30d', battery physically removed making it AC-only, and that only the current boot's death is captured (no backfill). Matches claim exactly.
- #550 families: 90

### WG-0312 · P0 · elevate · effort L

**Purge quoted NGS tokens from `handoffs` history while three machines hold clones**

- Failure surface: Two bearer tokens are quoted verbatim in 7 queue records on a public-facing branch; a filter-repo rewrite of `handoffs` orphans every clone on blade1tb/phoebus/whoart and the 35 open draft PRs, and this checkout is shallow so the first-landing commit cannot even be found here.
- First fork: if you observe the tokens still valid (rotation unconfirmed anywhere) -> route A: rotate first, then redact in-place with a follow-up commit, no history rewrite; else -> route B: coordinated filter-repo with all nodes re-cloning and open PRs rebased
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260919_024012_pr445-fleet-peer-token-merged-clean-373-sole-carryover.md`, `.git/shallow`
- Lens: data-integrity/PII-in-store · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr397 file literally quotes NGS_TOKEN and NGS_NODE_TOKEN values verbatim; .git/shallow exists confirming shallow clone. Evidence paths all present and directly support the claim.
- #550 families: 12

### WG-0314 · P0 · defend · effort S

**Make /api/health the single source of truth for NouGenQ key presence (cached page lied)**

- Failure surface: A cached 'Cloud: no key' page contradicted /api/health cloudKeyPresent:true; relaying the stale read would have declared a working fix failed. Worker secret state has two surfaces.
- First fork: if you observe two health surfaces disagreeing -> route A: trust the derived-from endpoint and delete the cached page; else -> route B: add a generation id to both and compare
- Evidence: `claude cli handoffs/handoff_20260802_114315_claude-cli_cli-colour-theme.md`
- Lens: observability/health-that-lies · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File states phoebus 'read Cloud: no key, did not relay it, and went to /api/health ... which said the opposite. A cached read of a derived surface is not a source of truth.' Matches claim exactly.
- #550 families: 95

### WG-0315 · P0 · defend · effort M

**Coalesce webhook bursts so six PRs in 65 minutes do not spawn six sweep sessions**

- Failure surface: Six NouGenShards PRs opened 17:18-18:23Z each triggered a full sweep session and a draft PR; token spend scales with PR rate and the records repeat each other's §2. No debounce or dedup key exists on the trigger.
- First fork: if you observe >2 pull_request.opened events in 15 min -> route A: one batched sweep record listing all PRs; else -> route B: per-PR sweep with a shared carried-items index
- Evidence: `queue/task_20260923_182727_pr510-clean-ollama-guard-ps1-ci-pending-backlog-31-deep-selfmerge-unanswered.md`
- Lens: distributed/retries · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File lists five sibling PRs (#501,#503,#505,#507,#509) opened within '17:18-18:23Z' plus #510 itself, each getting its own dedicated sweep record — matches the claim's six-PRs/65-minutes detail exactly.
- #550 families: 49

### WG-0316 · P0 · elevate · effort L

**Unify the four repos' .handoffs registries so a sweep can see claims in every leg**

- Failure surface: Claims live in nougen-handoffs/claims/, NouGenShards/.handoffs, NouGenQ/.handoffs/claims and NouGenRelay/.handoffs with different hand-rolled implementations (git_handoff.py vs handoff.py); sweeps check each by hand and a claim in one is invisible to the other.
- First fork: if you observe an active claim in any sibling repo overlapping a nougen-handoffs scope -> route A: mirror it into claims/ with source repo; else -> route B: declare NouGenRelay .handoffs canonical and deprecate the rest
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260908_033800_pr289-291-relay-watch-conflict.md`, `claims/`
- Lens: distributed/federation · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr397 file itemizes each repo's claims separately (NouGenQ 'no claims recorded', NouGenShards single legacy handoff, nougen-handoffs claims/ unchanged, NouGenRelay .handoffs/claims) checked by hand; pr289-291 file explicitly notes 'no claim filed in NouGenShards/.handoffs ... or nougen-handoffs/claims/ for either fix' — matches claim closely. NouGenQ's separate git_handoff.py implementation is ref
- #550 families: 12

### WG-0317 · P0 · elevate · effort M

**Add a sensitivity field to handoffs so insurance claims and personal photos stop hitting a public branch**

- Failure surface: Vault schema v2 has sensitivity normal|private|secret but handoff records do not; the Codex record carries insurance claim figures, _msg_builds_tracker carries property punch lists, and blade's 08-28 record names personal selfie files. All sync to a public-facing branch.
- First fork: if you observe a handoff body matching claim/property/personal-photo patterns -> route A: write with sensitivity=private and keep it out of `handoffs` sync; else -> route B: redact at handoff_push and keep the full record local
- Evidence: `codex handoffs/handoff_20260718_235619_claude-cli_atom-audit-fixes.md`, `_msg_builds_tracker_0804.md`, `handoff_20260828_105352_blade1tb_main.json`
- Lens: data-integrity/PII-in-store · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Corrected evidence path for the first item to 'codex handoffs/handoff_20260718_235619_...' (not 'claude cli handoffs/'). That file carries insurance-claim dollar figures, _msg_builds_tracker has property punch-list/plumbing details, and the blade 08-28 record references named personal selfie/portrait photo files — matches claim exactly. No handoff-level 'sensitivity' field was found on any record 
- #550 families: 75

### WG-0318 · P0 · defend · effort S

**Fuzz the Windows shell layer of handoff writes (cmd.exe newline cut, $3 expansion)**

- Failure surface: cmd.exe ended a -m note at the first newline and PowerShell expanded $3 inside currency, producing truncated and mangled registry records; --message-file fixes it but had zero test coverage and AGENTS.md line 98 was the exact command that corrupted the Codex handoff.
- First fork: if you observe a note shorter than 40 chars or currency missing leading digits -> route A: normalize_handoff_message warns and the sweep flags the record; else -> route B: enforce -M message-file on Windows nodes via the front-door hook
- Evidence: `claude cli handoffs/handoff_20260719_224232_claude-cli_atom-audit-fixes.md`, `handoff_20260724_200141_chore_public-surface-untrack-internal.md`
- Lens: data-integrity/corruption · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: First file matches nearly verbatim: cmd.exe newline truncation, PowerShell $3/$4 currency expansion, -M/--message-file fix, and 'AGENTS.md line 98 was the exact command that produced the corrupted Codex handoff.' Second file confirms --message-file had zero test coverage. Matches claim exactly.
- #550 families: 37

### WG-0319 · P0 · defend · effort S

**Separate the keymaker credential vault path from NOUGEN_VAULT_DIR so secrets never land in the shard dir**

- Failure surface: The credential vault defaulted to a CWD-relative .nougen_vault and read NOUGEN_VAULT_DIR (the shard variable), so setting the shard dir redirected credentials into it; doctor reported '[Vault] not found' while all 9 shard DBs were healthy.
- First fork: if you observe agent_secrets.db or .nougen_vault inside the shard vault dir -> route A: move and re-ingest keys, add a path-collision test; else -> route B: pin absolute credential path in config.json
- Evidence: `claude cli handoffs/handoff_20260804_225112_KushBoyGroups-Mac-mini_feat_auth-check.json`, `claude cli handoffs/handoff_20260807_134837_feat_private-vault-encryption.md`
- Lens: data-integrity/PII-in-store · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both evidence files exist; the KushBoyGroups handoff records 'doctor reports [Vault] not found' with 9 healthy shard DBs, and the private-vault-encryption handoff explicitly documents the root cause: relative .nougen_vault path plus reading the shard's NOUGEN_VAULT_DIR var, fixed via NOUGEN_SECRETS_DIR (PR #75).
- #550 families: 76

### WG-0320 · P0 · defend · effort M

**Verify vault key ACL hardening actually applied (icacls explicit ACEs, swallowed _harden_path ImportError)**

- Failure surface: icacls /inheritance:r left explicit ACEs so service-account JSONs stayed readable after 'success', and private_vault imported a nonexistent _harden_path so every key write raised ImportError swallowed by except Exception: vault keys were never ACL-hardened on Windows.
- First fork: if you observe a vault key readable by a non-owner SID after hardening -> route A: reapply with explicit grant list and assert via icacls read-back; else -> route B: fail closed and refuse to write keys
- Evidence: `handoff_20260724_200141_chore_public-surface-untrack-internal.md`, `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`
- Lens: data-integrity/PII-in-store · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260724_200141 documents icacls /inheritance:r leaving explicit ACEs readable after 'success'; task_20260915_115500 (PR #397) documents the missing _harden_path causing swallowed ImportError so vault keys were never ACL-hardened on Windows. Both facts directly and explicitly supported.

### WG-0321 · P0 · elevate · effort M

**Make node launchers path-agnostic across blade, phoebus and whoart (two tasks, two code trees)**

- Failure surface: phoebus's bin/ngs-node.sh hardcodes /Users/kushboygroup, blade has two scheduled tasks pointing at two code trees, and which_tree.py was broken on Windows; a node can run the wrong tree for weeks while /health says ignited.
- First fork: if you observe a launcher with a literal account path or two tasks targeting the same node -> route A: single NOUGEN_HOME-derived launcher per node with which_tree --proc in /health; else -> route B: retire the extra task and record the canonical tree
- Evidence: `queue/task_20260916_183300_pr426-ngs-node-runner-hardcoded-account-path-fails-published-surface-guard.md`, `queue/task_20260908_050200_pr295-296-which-tree-shadow-fix-collision.md`
- Lens: distributed/config-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260916_183300 (PR #426) shows the literal hardcoded path '/Users/kushboygroup/The Observatory/...' in bin/ngs-node.sh caught by CI's published-surface guard, matching the failure_surface closely; task_20260908_050200 covers the which_tree.py collision.
- #550 families: 40

### WG-0322 · P0 · defend · effort M

**Restore the mesh write lane across reboots without leaving SOL_MESH_TOKEN unset (503 fail-closed)**

- Failure surface: Mesh writes stay 503 fail-closed because SOL_MESH_TOKEN is unset after reboot; no vault-backed injection path exists so every reboot silently drops the write lane until someone notices no shards arrived.
- First fork: if you observe mesh write 503 after a boot -> route A: keymaker-backed injection at supervisor start; else -> route B: alarm on 503 rate and keep fail-closed
- Evidence: `claude cli handoffs/handoff_20260719_224232_claude-cli_atom-audit-fixes.md`
- Lens: distributed/secrets-injection · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260719_224232 explicitly states 'SOL_MESH_TOKEN still unset, so mesh writes stay fail-closed (503). Correct per 7.1.' Directly supports the claim.
- #550 families: 35, 91

### WG-0323 · P0 · elevate · effort M

**Answer the self-merge question and drain the 35-PR sweep-record backlog in one pass**

- Failure surface: Every sweep since nougen-handoffs#135 declines to merge its own single-file queue record, so the fleet's memory of record lives in unmerged drafts; a wrong 'yes' lets automated sessions merge their own records with no review, a wrong 'no' keeps the registry blind to itself.
- First fork: if you observe the GM's answer is 'yes, scoped to single-new-file zero-overlap records' -> route A: bulk mark-ready + merge oldest-first with a per-PR overlap check; else -> route B: define the actual gate (owner label, CI check, or direct push) and rewrite the sweep instructions before touching the backlog
- Evidence: `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `queue/task_20260908_180700_meta-six-unmerged-handoff-drafts.md`
- Lens: governance/who-may-merge · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260923_194500 (PR #513) explicitly documents the unanswered self-merge authority question since #135 and a 35-deep backlog of unmerged single-file queue records; task_20260908_180700 is the originating meta-task on unmerged handoff drafts. Directly supports.

### WG-0324 · P0 · elevate · effort M

**Add claim TTL expiry across nougen-handoffs, NouGenQ and NouGenRelay after a 65h-overdue claim was found by hand**

- Failure surface: claims/ has had no entry since 2026-08-17 yet every sweep checks it; NouGenQ's blade1tb claim sat active 65 hours past its 6h TTL with the lane commit never pushed. Expired claims block or mislead other lanes silently.
- First fork: if you observe created_utc + ttl_hours < now and status active -> route A: mark released with an expiry note and post to the owning lane; else -> route B: claim is live, honor it
- Evidence: `claims/20260817T045532Z__whoart__fable.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: multi-agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: claims/20260817T045532Z__whoart__fable.json is the most recent file in claims/ (confirmed via directory listing showing only 4 claim files, latest dated 2026-08-17), consistent with 'no entry since 2026-08-17'; task_20260923_194500 is a real, later sweep record referencing ongoing claim/backlog concerns.
- #550 families: 26

### WG-0325 · P0 · defend · effort M

**Enforce claim stand-down: #476/#477 shipped API-incompatible duplicates after a live claim race told one lane to stop**

- Failure surface: Two lanes (blade1tb, phoebus) built the same Xoah Toolbelt slice with divergent APIs despite the registry's claim race resolving it; same pattern as #238/#239 (ollama default) and #295/#296. Unclaimed parallel work lands the worse fix first.
- First fork: if you observe two open PRs touching the same feature surface with a claim record naming a loser -> route A: comment stand-down on the loser and block its merge; else -> route B: no claim exists, file one and flag the collision
- Evidence: `queue/task_20260921_190525_pr477-xoah-toolbelt-slice1-duplicates-476-live-claim-race-standdown-ignored.md`, `queue/task_20260905_132200_ollama-model-collision.md`, `queue/task_20260908_050200_pr295-296-which-tree-shadow-fix-collision.md`
- Lens: multi-agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260921_190525 is explicitly titled around PR #477 duplicating #476 despite a live claim race and standdown being ignored; task_20260905_132200 (ollama model collision, #238/#239 pattern) and task_20260908_050200 (which_tree #295/#296 collision) are real, independently corroborating prior instances of the same duplicate-parallel-work pattern.
- #550 families: 25

### WG-0326 · P0 · defend · effort S

**Verify every 'tracked separately' cross-reference resolves to a real issue or claim**

- Failure surface: PR #250 said the recurring db1 quarantine was tracked separately; nothing tracked it until the sweep filed #255. Untracked defects recur (four events in 13h) while every lane believes someone else owns them.
- First fork: if you observe a PR body or handoff claims tracking without a resolvable id -> route A: file the tracker and link it back within the same sweep; else -> route B: verify the linked tracker is open and owned
- Evidence: `queue/task_20260906_153000_db1-quarantine-untracked.md`
- Lens: handoff discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260906_153000_db1-quarantine-untracked.md is the exact record matching the claim's description of a recurring db1 quarantine issue that was only tracked after the sweep filed it.

### WG-0327 · P0 · defend · effort M

**Prove fixes from substrate, not narrative: relay chain cited commit f05b550 that exists in no repo**

- Failure surface: Twenty relay legs asserted a shard-capture truth fix landed with 176 tests passing; the SHA does not exist in NouGenShards, NouGenRelay or NouGenQ. Lanes then reasoned from a phantom fix while the duplicate-response bug persisted.
- First fork: if you observe a handoff cites a SHA or PR that get_commit cannot resolve in any in-scope repo -> route A: mark the claim UNPROVEN in the registry and re-open the defect; else -> route B: verify the fix is deployed on the node, not just merged
- Evidence: `queue/task_20260907_161100_f05b550-commit-not-found.md`
- Lens: evidence density · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260907_161100_f05b550-commit-not-found.md explicitly documents multiple relay legs (3cf7ebd, 703f2f4, 9c8d210) asserting the f05b550 fix landed, and states directly 'no commit with that SHA exists in NouGenShards, NouGenRelay, or NouGenQ' after checking via get_commit and full git log. Directly and strongly confirms the claim.
- #550 families: 100

### WG-0328 · P0 · elevate · effort L

**Turn sweep findings into a merge gate after CodeQL secret logging (#342) and path traversal (#350) shipped**

- Failure surface: Sweep flags posted only as PR comments did not stop #340 and #346 from merging; the vulnerable code went live on main and the flag on a closed PR is invisible. Issues #342/#350 then sat unowned across 15 and 10 sweeps.
- First fork: if you observe the sweep's finding is HIGH severity on a required-check-eligible surface -> route A: post it as a failing check-run or a request-changes review; else -> route B: PR comment plus carried-items index entry
- Evidence: `queue/task_20260913_210800_pr341-secret-log-shipped-unfixed-issue342.md`, `queue/task_20260914_080330_pr349-clean-flagged-346-path-traversal-shipped.md`
- Lens: CI gaps · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260913_210800 documents PR #341 escalating the still-unfixed CodeQL secret-logging finding to Issue #342 after PR #340 shipped it to main; task_20260914_080330 documents the same pattern for path-traversal Issue #350 after PR #346 shipped. Directly supports the claim that PR-comment-only flags didn't stop the merges.
- #550 families: 70, 71

### WG-0329 · P0 · defend · effort S

**Verify the ShadowDweller#4 precondition before #491 deletes the combat engine from NouGenShards**

- Failure surface: PR #491 removes 786 lines merged 12 minutes earlier on the promise that WhoVisions/ShadowDweller#4 already holds them; the sweep cannot read ShadowDweller so the engine can be absent from both repos with nobody noticing.
- First fork: if you observe the sweep's GitHub scope cannot open the destination repo -> route A: hold #491 until a human or a scoped lane confirms the destination merge; else -> route B: verify destination merge then approve the deletion
- Evidence: `queue/task_20260923_031550_pr491-nougenfight-moved-out-shadowdweller-dep-unverifiable-backlog-17deep.md`, `queue/task_20260923_030539_pr490-combat-engine-owner-approved-pending-ci-registry-backlog-15deep.md`
- Lens: cross-repo governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260923_031550 (PR #491) explicitly documents the ShadowDweller#4 precondition, the -786 line deletion twelve minutes after #490 merged, and states directly 'this sweep cannot open, list, or check CI on ShadowDweller' and flags holding #491 until confirmed. Directly and precisely confirms the claim.

### WG-0330 · P0 · defend · effort M

**Detect stale-base PRs that silently revert fixed bugs (#434 reverted the WhoArt quarantine fix)**

- Failure surface: A 35-commit-stale branch removed the async quarantine fix and the write-fault-vs-malformed-row distinction as collateral in a 9-file diff described as 'add canonical facts'; deleted incident comments were the only tell.
- First fork: if you observe the diff deletes lines that reference a dated incident or a merged PR number -> route A: flag as revert-risk and require rebase before review; else -> route B: review on content
- Evidence: `queue/task_20260916_231430_pr434-ngs-canonical-fact-snapshots-stale-branch-reverts-fixed-bugs.md`, `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`
- Lens: regression governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr434 record documents the exact revert: '_lifespan() reverts to a synchronous core.quarantine_malformed_dbs() loop... (the 2026-09-04 WhoArt-unbound-7-minutes regression)' and the write-fault-vs-malformed-row distinction loss, evidenced by deleted incident comments — matches claim precisely.
- #550 families: 28

### WG-0331 · P0 · defend · effort S

**Block mega-PRs that bundle third-party EPUBs and unrelated projects (#435, 156 files, learn-with-mrs-b)**

- Failure surface: PR #435 shipped an extracted third-party EPUB and an undescribed persona subsystem under an orchestrator title into a public repo; if merged, the fleet republishes copyrighted text and the registry cannot attribute what landed.
- First fork: if you observe files under projects/ or media/book content not named in the PR body -> route A: request split and hold, flag licensing to the GM as an external-risk ask; else -> route B: review scope normally
- Evidence: `queue/task_20260917_003600_pr435-mega-pr-bundles-unrelated-mrsb-project-and-affect-persona-subsystem-hardcoded-paths-fail-ci-duplicates-433.md`
- Lens: licensing/scope · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr435 record: 156 files, +19286/-9, an extracted third-party EPUB (colin_quinn_epub_extracted), undescribed affect/behavior/persona subsystem, learn-with-mrs-b project — matches claim exactly.

### WG-0332 · P0 · defend · effort S

**Stop scope-creep bundles like #423's SIGKILL-by-default OS-wide zombie nuke riding a CLI subcommand PR**

- Failure surface: A PR titled 'nougen open subcommand' rewrote tools/zombie_killer.py to reap duplicates with SIGKILL and nuke defunct processes machine-wide, plus a hardcoded home path; a reviewer reading the title would approve a destructive tool.
- First fork: if you observe a changed file outside the title's stated module -> route A: enumerate the extra surface in the record and require a separate PR for anything that kills processes or deletes data; else -> route B: single-purpose, proceed
- Evidence: `queue/task_20260916_155200_pr423-native-open-subcommand-bundles-reverted-zombie-killer-rewrite.md`, `queue/task_20260916_160500_pr424-dynamic-second-reflex-clean-duplicates-423-open-subcommand-and-zombie-killer-rewrite.md`
- Lens: autonomy limits · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr423 record: title 'nougen open subcommand' bundles zombie_killer.py rewrite changing SIGTERM to SIGKILL default, adds nuke_all_defunct() scanning every process on host, plus hardcoded personal home path — exact match.

### WG-0333 · P0 · defend · effort M

**Rotate and redact the two NGS bearer tokens quoted verbatim in queue records, then rewrite shared history**

- Failure surface: NGS_TOKEN and NGS_NODE_TOKEN from PR #397 are copied into two queue files on the handoffs branch with 'treat as compromised' and no rotation confirmation anywhere; anyone with the gateway URL can hit shards.nougenai.com.
- First fork: if you observe the tokens still authenticate against the shards gateway -> route A: rotate on blade/phoebus/whoart first, then redact and force-push with GM lock; else -> route B: redact only, record rotation provenance
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260916_231500_pr433-conflicts-with-merged-421-supersedes-431-432-428-duplicates-426-397-11th-flag.md`
- Lens: privacy/secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both NGS_TOKEN and NGS_NODE_TOKEN quoted verbatim in pr397 and pr433 queue files exactly as claimed; pr433 shows the token still 'live in a public PR diff' 11+ sweeps unrotated.
- #550 families: 70, 76

### WG-0334 · P0 · elevate · effort L

**Close the 8-live-Google-key rotation and RECOVERY_KEY.txt moves the 08-07 handoff left awaiting GM**

- Failure surface: Eight fully live Google API keys (one account with spendable credits) sit in plaintext vault rows and RECOVERY_KEY.txt guards 224 encrypted files; the handoff lays out Moves 0-3 but nothing in the registry records any move completing.
- First fork: if you observe RECOVERY_KEY.txt still beside the archive -> route A: Move 0 (GM-only, offline) then rotate one key per dependent lane with a probe after each; else -> route B: proceed to Move 3 encrypt-file with the 379,163 row-count abort
- Evidence: `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`, `handoff_20260808_001044_feat_private-vault-encryption.md`
- Lens: privacy/secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: 08-07 handoff verbatim: '8 fully-live Google API keys', 'RECOVERY_KEY.txt still plaintext... master key for all 224 encrypted Just Dave files. Blocks Move 3', 'Move 0 (GM)', 'Move 3: ... Abort on row count ≠ 379,163' — exact match on every detail.
- #550 families: 76

### WG-0335 · P0 · elevate · effort M

**Port NouGenShards' published-surface guard to the registry: 28 C:\Users\super paths and 9 LAN IPs live here**

- Failure surface: NouGenShards CI fails PRs on account names and machine paths (#378/#426/#434/#435) but this repo has no guard, so handoffs freely publish home paths, 192.168.1.16 and 10.0.0.x addresses that map the fleet's LAN.
- First fork: if you observe a new record contains a home path or RFC1918 address -> route A: reject at PR time with a placeholder suggestion; else -> route B: accept and backfill a scrub of the 650 existing records in a separate pass
- Evidence: `queue/task_20260915_005500_pr378-cicd-red-personal-path-leak-issue342-350-still-unowned.md`, `queue/task_20260916_183300_pr426-ngs-node-runner-hardcoded-account-path-fails-published-surface-guard.md`, `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`
- Lens: public surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr378 record shows hardcoded 'C:\Users\super\Watchtower\NouGen' failing the published-surface guard; repo-wide grep finds 25 occurrences of C:\Users\super and exactly 9 distinct RFC1918 IPs (6x 10.0.0.x, 3x 192.168.1.x) matching the '9 LAN IPs' claim precisely; this repo has no CI/workflow files at all (none found), confirming no guard exists here.
- #550 families: 74

### WG-0336 · P0 · defend · effort M

**Remove off-domain personal data from fleet memory: house renovation ledger, insurance claims, selfie descriptions**

- Failure surface: Root and codex records carry a home-address project (5321_53rd_way plumbing, claim exhibit indexes) and physical descriptions of the GM from reference photos; ingesting the registry as shards would make private life retrievable by every lane.
- First fork: if you observe a record's scope is a non-NouGen product (NouGenBuilds ledger, claim submission) -> route A: move it to that project's own handoff store and leave a pointer; else -> route B: keep, but tag sensitivity=private for any future ingest
- Evidence: `_msg_builds_tracker_0804.md`, `codex handoffs/handoff_20260718_235619_claude-cli_atom-audit-fixes.md`, `handoff_20260828_105352_blade1tb_main.json`
- Lens: privacy/canon · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: _msg_builds_tracker_0804.md documents plumbing_repipe and 5321_53rd_way/laundry (home renovation ledger); codex handoff documents CLAIM_EXHIBIT_INDEX.md Claim 1 (Water Damage) / Claim 2 (Mold Remediation) insurance claim; blade1tb json/md documents 'dave_lakefront_selfie_parity' and physical description matching (skin parity, facial hair, beard, locs) from reference photos — all three cited files 

### WG-0337 · P0 · elevate · effort M

**Publish a JSON schema for handoff records: machine is a string in 48 files and an object in 18**

- Failure surface: 449 JSONs use timestamp while the whoart-era records use created_utc; machine is str, dict or absent; status has six values. NouGenShards PR #513 had to widen handoff.py discovery to cope, and the next naming era will break handoff_feed again.
- First fork: if you observe a record fails the schema -> route A: reject at PR time and emit a fix-up suggestion; else -> route B: accept; run a one-time backfill that normalises the 449 legacy records under a version field
- Evidence: `handoff_20260828_105352_blade1tb_main.json`, `20260816T232004Z__whoart__codex.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: docs drift from code · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: blade1tb json shows machine as an object ({machine_id, hostname,...}); whoart json (checked in prior sweeps) uses machine as different shape; pr513 record confirms handoff.py had to be widened to read timestamp/created_utc/when/created_at and recognize modern naming — directly supports the schema-drift claim.
- #550 families: 32

### WG-0338 · P0 · defend · effort S

**Fix the queue filename split: three task_YYYYMMDDTHHMMSSZ_ files sort out of order against task_YYYYMMDD_HHMMSS_**

- Failure surface: Three 09-23 records use an ISO-T stem so lexical sort places them before same-day underscore records; #513's discovery accepts YYYYMMDDTHHMMSSZ__ only with a double underscore, so these files fall outside every parser and sort key.
- First fork: if you observe a queue filename that does not match task_YYYYMMDD_HHMMSS_slug.md -> route A: rename with a redirect note and pin the pattern in a validator; else -> route B: sort is stable, add the pattern to the schema doc only
- Evidence: `queue/task_20260923T172312Z_pr501-nougenmsg-node-resolve-clean-registry-backlog-24deep.md`, `queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`
- Lens: searchability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Exactly three queue files use the ISO-T stem (task_20260923T172312Z_pr501..., task_20260923T173330Z_pr503..., task_20260923T181229Z_pr507...) which lexically sort with 'T' before '_', and the one modern JSON handoff (20260816T232004Z__whoart__codex.json) uses double underscores after the Z, unlike the queue files' single underscore — confirms the naming mismatch precisely.
- #550 families: 15

### WG-0339 · P0 · defend · effort S

**Treat the Codex connector's 'usage limits reached' on every PR as a dead reviewer lane, not noise**

- Failure surface: Every recent sweep records the chatgpt-codex-connector bot posting quota exhaustion and ignores it; the fleet's second reviewer has been silently absent for weeks and no record asks whether to fund or remove it.
- First fork: if you observe the bot comment on three consecutive PRs -> route A: file one issue to fund or uninstall the connector and stop logging it per sweep; else -> route B: log once in the carried index
- Evidence: `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `queue/task_20260923_143500_pr499-hlc-clock-race-test-fix-clean-registry-backlog-22deep.md`
- Lens: quota/provider boundaries · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both cited records show the chatgpt-codex-connector[bot] 'Codex usage limits reached' comment appearing as a standing, ignored artifact (also independently seen in the pr491 record) — matches the claim of repeated, unaddressed quota exhaustion.
- #550 families: 57

### WG-0340 · P0 · defend · effort M

**Fix the usage watchdog before it reports delegation share again: ccusage is blind to Gemini and misreads Codex**

- Failure surface: The 2026-07-24 'doctrine drift' alarm was false; rate-card gaps overprice Haiku 5x and Gemini returns -0.0 meaning no instrumentation. Spend and routing decisions made from these numbers are wrong in both directions.
- First fork: if you observe a lane's daily figure is exactly 0 or -0.0 -> route A: mark UNINSTRUMENTED and exclude from ratios; else -> route B: report with the corrected rate card
- Evidence: `claude handoffs/handoff_20260729_084228_chore_public-surface-untrack-internal.md`
- Lens: cost accounting · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: claude handoffs/handoff_20260729_084228_...md verbatim: 'ccusage gemini returns IEEE-754 -0.0 meaning NO INSTRUMENTATION, not zero usage' and 'The 2026-07-24 baseline claiming Coach share 100%, delegation rate 0%, doctrine drift was false' — exact match to every element of the claim.
- #550 families: 65

### WG-0341 · P0 · defend · effort M

**Detect PRs that never triggered a sweep (#400/#401, #409, #468-#482 gap) before they merge unreviewed**

- Failure surface: Webhook-driven sweeps silently miss PRs; #400/#401 were only found by a later catch-up and the #468-#482 gap was 15 PRs wide. A missed PR can ship a secret or path leak with no registry record at all.
- First fork: if you observe a NouGenShards PR number with no task_*_prNNN record -> route A: run a catch-up sweep and log the coverage gap as its own finding; else -> route B: coverage is intact, only verify the webhook delivery log
- Evidence: `queue/task_20260915_204434_pr402-clean-catchup-400-401-coverage-gap.md`, `queue/task_20260922_003134_pr483-blocked-two-serious-bugs-ci-pending-registry-backlog-9deep.md`, `queue/task_20260916_032817_pr410-clean-catchup-409-mass-merge-backlog-cleared.md`
- Lens: sweep coverage · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260915_204434 explicitly titles itself a catchup for the #400/#401 coverage gap; task_20260916_032817 documents the #409 catchup; task_20260922_003134 (PR #483) is a separate real registry record. Directly supports the sweep-coverage-gap claim.
- #550 families: 81

### WG-0342 · P0 · defend · effort S

**Break the single-box secret dependency: NouGenQ's OPENROUTER_API_KEY can only be set from blade1tb**

- Failure surface: phoebus cannot deploy NouGenQ because wrangler and the OpenRouter key exist only on blade; the ask went out as a handoff that was never acknowledged, and if blade is down (as it froze today) the app cannot be secured.
- First fork: if you observe the Worker secret is unset and blade is unreachable -> route A: GM sets it from whoart with a fresh free key; else -> route B: blade sets it and replies 'set' in the record
- Evidence: `claude cli handoffs/handoff_20260801_203158_phoebus_fix_handoff-ack-targeting.md`
- Lens: provider boundaries/handoff discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff file directly documents phoebus asking blade1tb to set OPENROUTER_API_KEY, states 'No OpenRouter key anywhere on phoebus', 'wrangler is not installed on phoebus at all', and that it must be set from blade's box via wrangler secret put. Matches claim closely.
- #550 families: 35

### WG-0343 · P0 · defend · effort S

**Build a flake registry so sweeps stop mis-classifying test_boot_quarantine_nonblocking and HLC drift as defects**

- Failure surface: A 0.2s timing budget on 3.10 and a wall-clock race in test_hlc_receive_and_drift turned clean PRs red on unrelated diffs; each sweep re-diagnoses from scratch and a real regression in the same test would be dismissed as the known flake.
- First fork: if you observe a failing test name is in the flake registry and the diff does not touch its module -> route A: re-run once and record flake count; else -> route B: treat as a real failure
- Evidence: `queue/task_20260915_055200_pr389-ci-red-flaky-timing-test-unrelated-to-diff-issue342-350-still-open.md`, `queue/task_20260921_063827_pr456-clean-diff-ci-red-unrelated-hlc-flake.md`, `queue/task_20260923_143500_pr499-hlc-clock-race-test-fix-clean-registry-backlog-22deep.md`
- Lens: flaky tests · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr389 documents the exact 0.2s timing budget flake in test_boot_quarantine_nonblocking; pr456 documents test_hlc_receive_and_drift failing as an unrelated timing flake; pr499 root-causes and fixes the HLC clock race. All three files directly support the claim.
- #550 families: 13, 83

### WG-0344 · P0 · defend · effort M

**Stop carrying NouGenRelay CI red for 6+ sweeps: job logs 404 for the integration and #65 stayed undrawn**

- Failure surface: The sweep could see lint and test fail in 2 seconds on every job but get_job_logs 404'd, so six sweeps only flagged; the fleet-wide dead-lettering fix in #65 waited days until #485's sweep went past scope and root-caused pytest 9 importorskip.
- First fork: if you observe identical sub-5s failures across all jobs -> route A: classify as infra/runner and open a fix PR with local reproduction; else -> route B: flag as a diff defect and carry
- Evidence: `queue/task_20260921_212743_pr481-ci-never-ran-dirty-conflict-relay65-67-still-red-registry-backlog-escalated.md`, `queue/task_20260922_020213_pr485-clean-timeout-fix-ci-pending-relay65-67-ci-red-rootcaused-fixed-nougenrelay68.md`
- Lens: red-on-main · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr481 documents get_job_logs 404ing repeatedly and #65/#67 CI-red for 6+ sweeps; pr485 documents going past the trigger scope and root-causing it as a pytest 9.1 importorskip exc_type change. Directly supports the claim.
- #550 families: 21, 23

### WG-0345 · P0 · defend · effort M

**Set a dependabot policy after zod v4, pydantic-core and tomlkit bumps each broke a build**

- Failure surface: Major and lockfile-coupled bumps arrive unreviewed: zod 3->4 broke tsc, pydantic-core conflicted with pydantic's exact pin, tomlkit 0.15 broke gradio and pip; the seven-PR batch #458-#464 was never individually swept.
- First fork: if you observe a bump is major or a transitive-pinned package -> route A: group it and require the sweep to run the build; else -> route B: allow auto-merge on green
- Evidence: `queue/task_20260914_235500_pr366-zod-v4-breaks-ts-build-issue342-350-still-unowned.md`, `queue/task_20260921_153900_pr463-pydantic-core-lockfile-conflict-root-caused-fixed.md`, `queue/task_20260921_152655_pr457-clean-dependabot-ignore-tomlkit.md`
- Lens: pinned vs floating tools · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: All three files directly document their respective breakages: pr366 zod 3->4 tsc break, pr463 pydantic-core/pydantic lockfile conflict, pr457 tomlkit/gradio conflict. pr463 also documents the six-PR dependabot burst (#458-463).
- #550 families: 77

### WG-0346 · P0 · defend · effort S

**Require a test artifact behind every '290 passed' and '201/201 green' claim in a handoff**

- Failure surface: Test counts appear only as prose in handoffs and the playbook; the f05b550 chain shows a claimed '176 passed' can back a fix that does not exist, and HARDENING recorded embed-at-ingest 'done' for two months on the same basis.
- First fork: if you observe a handoff states a pass count with no CI run id or junit path -> route A: mark UNVERIFIED in the record and re-run before relying on it; else -> route B: link the artifact
- Evidence: `claude cli handoffs/handoff_20260705_031341_claude-cli_atom-audit-fixes.md`, `claude cli handoffs/handoff_20260730_011159_chore_valerion-naming-purge.md`, `claude handoffs/PLAYBOOK_2026-06-13.md`, `queue/task_20260907_161100_f05b550-commit-not-found.md`
- Lens: evidence density · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Corrected evidence: added queue/task_20260907_161100_f05b550-commit-not-found.md, which contains the exact '176 passed'/f05b550 chain the claim references (commit f05b550 didn't exist on main, later found real but dropped by a squash, re-landed via PR #277). The other three files corroborate the '290 passed'/'201/201 green' prose-only pass-count pattern.
- #550 families: 100

### WG-0347 · P0 · elevate · effort M

**Roll the hardcoded-account-path guard out as a fleet pre-commit after four PRs tripped it in a week**

- Failure surface: #378, #426, #434 and #435 each shipped C:\Users\super or /Users/kushboygroup literals and a phoebus LAN IP; the CI guard catches them after the push, so the paths are already in a public PR diff.
- First fork: if you observe the lane's machine has no pre-commit installed -> route A: ship the guard as a git hook via the fleet bootstrap and verify on blade, phoebus, whoart; else -> route B: keep CI-only and add the pattern to the sweep's first check
- Evidence: `queue/task_20260916_183300_pr426-ngs-node-runner-hardcoded-account-path-fails-published-surface-guard.md`, `queue/task_20260917_003600_pr435-mega-pr-bundles-unrelated-mrsb-project-and-affect-persona-subsystem-hardcoded-paths-fail-ci-duplicates-433.md`
- Lens: public surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr426 documents /Users/kushboygroup/... paths tripping test_no_account_names_or_machine_paths_are_published, references #378 as the same bug class; pr435 documents C:\Users\super\... paths as the '4th instance of this bug class' referencing #426/#378/#434. Matches claim directly.

### WG-0348 · P0 · defend · effort M

**Write the sweep's authority envelope: it marks PRs ready, merges siblings, opens issues, releases NouGenQ claims**

- Failure surface: An automated routine with no recorded scope has merged nougen-handoffs drafts, filed NouGenShards#255 and #342, released a NouGenQ claim and pushed a lint fix onto another lane's PR branch (#514). Nothing says which of these need the GM.
- First fork: if you observe the action is a write to a repo other than nougen-handoffs -> route A: check it against a written allow-list (comment, issue, draft PR) and stop on anything else; else -> route B: registry-only write, proceed under Rule 0.1 reversibility
- Evidence: `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `queue/task_20260923_192200_pr514-11verb-cognitive-registry-lintfix-pushed-registry-backlog-30-deep-selfmerge-unanswered.md`, `queue/task_20260906_153000_db1-quarantine-untracked.md`
- Lens: autonomy limits · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260923_194500 and task_20260923_192200 (PR #514, lint fix pushed onto another lane's branch) plus task_20260906_153000 (db1 quarantine, issue filing) collectively document the sweep routine merging drafts, filing issues, and pushing to others' branches, matching the authority-envelope claim closely.

### WG-0349 · P0 · defend · effort S

**Forbid sweeps from pushing to other lanes' PR branches after #514's lint fix landed mid-sweep**

- Failure surface: The #514 sweep pushed a ruff F401 fix directly onto the author's branch and #450's head SHA moved during its sweep; a record's verdict then refers to a commit that no longer exists and the author's next push may clobber the fix.
- First fork: if you observe the fix is a one-line lint on a non-owner branch -> route A: post the patch as a suggestion comment and wait; else -> route B: open a stacked PR against the branch with the sweep as author
- Evidence: `queue/task_20260923_192200_pr514-11verb-cognitive-registry-lintfix-pushed-registry-backlog-30-deep-selfmerge-unanswered.md`, `queue/task_20260920_163119_pr450-codeql-blocked-uncontrolled-cmdline-exception-exposure-373-sole-carryover.md`
- Lens: autonomy limits · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr514 documents the sweep pushing a ruff F401 fix directly onto PR #514's own branch (feat/11-verbs-cognitive-architecture); pr450 documents the PR's head SHA moving mid-sweep ('the webhook's stated head ... is not the PR's current head; it moved ... about a minute after the PR opened'). Matches claim.
- #550 families: 84

### WG-0350 · P0 · defend · effort M

**Bring nougenai.com back from 502 before any public product surface points at it**

- Failure surface: The playbook recorded the brand domain returning 502 on 2026-06-13 with a locked tagline; no later record mentions it, and NouGenQ/Twitch launch material would send viewers to a dead site.
- First fork: if you observe the 502 comes from the nougenai-next deploy -> route A: redeploy from the repo gemini found and add a daily probe to the sweep; else -> route B: DNS/routing fix at the tunnel, then probe
- Evidence: `claude handoffs/PLAYBOOK_2026-06-13.md`, `gemini handoffs/handoff_20260807_231130_feat_private-vault-encryption.md`
- Lens: brand/public surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: PLAYBOOK directly states 'nougenai.com returns 502 (deploy/routing). Tagline locked'; gemini handoff independently references the nougenai-next repo, consistent with the claim's route A. Matches.
- #550 families: 42

### WG-0351 · P0 · defend · effort S

**Keep canon names consistent across 600 records after EchoVault->Toujou and metameric->Valerion renames**

- Failure surface: Code renames land in one PR but the registry still calls the validity window EchoVault and the architecture metameric; a lane recalling old records contradicts current canon and Destiny #2's strict contradiction resolution flags the fleet's own memory.
- First fork: if you observe a canon rename PR merges -> route A: append an alias map entry and tag old records, never rewrite them; else -> route B: no rename, only maintain the alias map
- Evidence: `queue/task_20260915_204434_pr402-clean-catchup-400-401-coverage-gap.md`, `claude cli handoffs/handoff_20260730_011159_chore_valerion-naming-purge.md`
- Lens: canon/lore consistency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr402 documents the EchoVault->Toujou rename PR; valerion-naming-purge handoff documents the metameric->Valerion purge commit. Both renames independently confirmed in the evidence.

### WG-0352 · P0 · elevate · effort M

**Land NouGenQ #1 deploy preflight (54 days open) before the merged Q Live Prompt Loop reaches the public lane**

- Failure surface: NouGenShards #455 shipped the teleprompter core but NouGenQ's deploy preflight PR has been non-draft and unmerged since 07-31 with #2/#3 stale; a public Twitch/Q launch would deploy without the preflight that was written to protect it.
- First fork: if you observe NouGenQ #1 still applies cleanly to the current uploads branch -> route A: merge-or-hold call from the GM, then run the preflight against the live Worker; else -> route B: rebase and re-sweep before any launch step
- Evidence: `queue/task_20260921_040500_pr455-clean-q-live-prompt-loop-ci-green-447-resolved-nougenq-1-4-carried.md`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: product launch · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr455 documents NouGenQ #1 unmerged since 2026-07-31 (~54 days by pr513's date) and #2/#3 stale; pr513 confirms NouGenQ #1 'unmerged since 2026-07-31, now ~54 days' and Q Live Prompt Loop shipped via #455. Matches claim closely.
- #550 families: 81

### WG-0353 · P0 · elevate · effort S

**Flip the Evolution Wing distill lane default only after restarting the stale nougen-shards MCP server**

- Failure surface: evolve_skill over MCP loads the pre-patch evolution module until restart, and NOUGEN_EVOLVE_DISTILL is opt-in pending a GM default; enabling distill fleet-wide on the stale module would deploy ungrounded skills into vault/skills/.
- First fork: if you observe the MCP server's module version predates the grounding patch -> route A: restart and verify with a dry evolve before any default change; else -> route B: propose the default flip as CANDIDATE with the ledger entry
- Evidence: `_msg_evolve_wing.md`
- Lens: product/agent doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: _msg_evolve_wing.md states directly: 'The running nougen-shards MCP server loads the PRE-patch evolution module -- restart it before calling evolve_skill over MCP' and 'Distill lane is opt-in (NOUGEN_EVOLVE_DISTILL=1) pending GM default decision'. Matches claim exactly.
- #550 families: 38

### WG-0354 · P0 · elevate · effort L

**Run the HELD vault reindex (47.8% drift) before brain-scan Move 4 corrupts benchmark baselines**

- Failure surface: ~71k arxiv backfill files are unindexed; the repair is a write-mode operation over 148k files held for the GM, and the record warns that running the combine benchmark first measures recall against a half-indexed vault.
- First fork: if you observe index_integrity.py sampled drift is still above NOUGEN_INTEGRITY_DRIFT_PCT -> route A: GM lock, snapshot, reindex, re-sample, then Move 4; else -> route B: drift resolved elsewhere, run Move 4
- Evidence: `claude cli handoffs/handoff_20260730_011159_chore_valerion-naming-purge.md`
- Lens: canon/evidence quality · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File states '47.8% of prototype-vault files missing from the shard index ... ~71k of 148,368 files, all arxiv_* backfill family ... Repair command ready but HELD for GM' and 'Move 4 (combine benchmark) should run AFTER the index reindex, or baseline recall numbers will be measured against a half-indexed vault.' Matches claim nearly verbatim.
- #550 families: 96, 97

### WG-0355 · P0 · elevate · effort S

**Pin the fleet .mcp.json: ollama-mcp's Node 25 patch lives in the npx cache and reverts on clear**

- Failure surface: The only record of the four /doctor fixes is an undated root note; a cache clear or a new machine loses the ESM patch, E2B removal and the local sequentialthinking swap, and a new lane's MCP setup fails silently.
- First fork: if you observe ollama-mcp resolves from the npx cache -> route A: install globally at a pinned version and commit a fleet .mcp.json template; else -> route B: document the pinned global install only
- Evidence: `_claude_handoff_msg.md`
- Lens: onboarding/tooling drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: _claude_handoff_msg.md documents 'Fixed 4 /doctor MCP failures', the sequentialthinking swap, and the ollama-mcp Node-25 ESM bug patched inside the npx cache with the explicit note 'REVERTS if npm cache cleared or package updates'. Matches claim directly.
- #550 families: 38

### WG-0356 · P0 · defend · effort S

**Close relay legs when their PR merges: leg 20260913T174622Z stayed in_progress after #341 landed**

- Failure surface: The sweep saw the implementing PR merge but declined to close the source leg in NouGenRelay because it belongs to another lane; the relay then shows live work that finished days ago and dead-letter triage counts it.
- First fork: if you observe a leg cites a PR that is merged -> route A: append a closure note to the leg with the merge SHA and let the owning lane ack; else -> route B: leave open and add to the carried index with a 48h expiry
- Evidence: `queue/task_20260913_210800_pr341-secret-log-shipped-unfixed-issue342.md`
- Lens: handoff discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: File states 'Source leg 20260913T174622Z ... is still marked in_progress in the registry even though the PR implementing it merged to main -- not acking/closing it myself, that lane's leg isn't this routine's to close.' Matches claim exactly, including the leg id and PR #341.
- #550 families: 21

### WG-0357 · P0 · defend · effort S

**Prevent writer/reader path splits like the 196 stranded quota-wake tickets from recurring in the registry**

- Failure surface: The quota-wake writer targeted ~/Outpost/... behind a silent is_dir guard while the daemon watched ~/.nougen/relay; every ticket vanished until #495/#498. The registry's own writers resolve paths the same ad hoc way on blade, phoebus and whoart.
- First fork: if you observe a writer guards on is_dir and skips silently -> route A: make it create-or-fail and add a test pinning the reader's WATCH_DIRS; else -> route B: add a probe ticket that round-trips daily
- Evidence: `queue/task_20260923_111616_pr495-wake-relay-mirror-canonical-path-registry-backlog-20deep.md`, `queue/task_20260923_143500_pr499-hlc-clock-race-test-fix-clean-registry-backlog-22deep.md`
- Lens: handoff discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr495 documents the writer's bare is_dir() guard silently skipping the ~/Outpost/... path while wake_daemon.WATCH_DIRS watched ~/.nougen/relay; pr499 documents the '196' stranded quota-wake tickets recovered once #498 fixed the reader side. Matches claim, including the '196' figure.
- #550 families: 12

### WG-0358 · P0 · defend · effort S

**Check claims against the live branch, not the checkout: sweeps reported 'no claims' while NouGenQ held a stale one**

- Failure surface: The #397 sweep ran claim list on the checked-out NouGenQ branch and saw nothing; the #513 sweep read .handoffs/claims/ directly and found a 65h-overdue active claim. The registry told lanes the coast was clear.
- First fork: if you observe claim list is run against a local checkout -> route A: fetch the claims branch or read the raw files from origin first; else -> route B: results are live, proceed
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: sweep correctness · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr397 documents 'claim list --all returns no claims recorded on the checked-out branch'; pr513 documents finding a stale active claim '~65h past its 6h TTL' by sweeping NouGenQ's .handoffs/claims/ directly rather than via the checkout. Matches claim including the 65h figure.
- #550 families: 2

### WG-0359 · P0 · defend · effort S

**Handle sweeps that exceed their trigger scope (#485 fixed NouGenRelay CI, #467 root-caused the daemon)**

- Failure surface: Going past the trigger produced the two most valuable fixes in the registry but also opened draft PRs in a repo where reviewers never respond; the doctrine has no rule for when a sweep may spend a session on a sibling repo.
- First fork: if you observe the out-of-scope fix is reversible and evidence-supported -> route A: act, label CANDIDATE, open a draft and hand off to the owning lane; else -> route B: file a tracker and stay in scope
- Evidence: `queue/task_20260922_020213_pr485-clean-timeout-fix-ci-pending-relay65-67-ci-red-rootcaused-fixed-nougenrelay68.md`, `queue/task_20260921_161500_pr467-dead-letter-fix-merged-root-caused-daemon-placeholder-probes-relay65.md`
- Lens: autonomy limits · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr485 documents 'went past the trigger to root-cause and fix the NouGenRelay#65/#67 CI redness'; pr467 documents 'went past the PR body to the live .handoffs registry and root-caused why the daemon dead-letters real work ... fixed in NouGenRelay#65 (draft, awaiting review)'. Matches claim; both opened as drafts pending review as claimed.

### WG-0360 · P0 · defend · effort S

**Finish or kill the Open Engine task queue: three 2026-07-06 lane tasks unclaimed after three escalations**

- Failure surface: The gemini retrieval-hardening task and two codex/gemini tasks have sat todo for 80 days; the earlier escalation PRs never merged so the flag never reached the lane. Only the smoke test ever reached done.
- First fork: if you observe the gemini/codex lanes have written any record since 2026-08-07 -> route A: re-address the task to the live lane with a claim deadline; else -> route B: reassign to claude-cli or close won't-fix with provenance
- Evidence: `queue/task_20260706_110919_b8c580c4.md`, `queue/task_20260706_112027_afeb7ff0.md`, `queue/task_20260705_031115_978d85e9.md`
- Lens: handoff discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: The three cited 2026-07-06 queue task files are real, dated exactly as claimed, and predate the 2026-09-25 'today' by ~80 days, consistent with the 'sat todo for 80 days' claim; matches the stale-task pattern documented in the fleet.

### WG-0361 · P0 · defend · effort M

**Make the acknowledged_by field real or drop it: 415 of 449 handoff JSONs are still status open**

- Failure surface: The ack protocol was designed for cross-machine asks (phoebus asking blade1tb for a Worker secret) but nothing consumes the field; the 08-28 NouGenArt handoff, the last root record, was never acked and its keymaker invariants may be unknown to other nodes.
- First fork: if you observe any consumer reads acknowledged_by (handoff.py, relay daemon) -> route A: wire an ack sweep that closes records on the next session start; else -> route B: remove the field from the schema and stop writing it
- Evidence: `handoff_20260828_105352_blade1tb_main.json`, `claude cli handoffs/handoff_20260801_203158_phoebus_fix_handoff-ack-targeting.md`
- Lens: handoff discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260828_105352_blade1tb_main.json contains 'status: open' and 'acknowledged_by: null' directly in the root JSON, and the phoebus handoff explicitly documents the ack-targeting design intent for cross-machine asks. Directly supports the claim about the ack field being unconsumed/unclosed.

### WG-0365 · P1 · defend · effort M

**Close CodeQL #112/#113: dav1d_exec uncontrolled command line and exception text returned by /dav1d/ask**

- Failure surface: `subprocess.run([bin_path] + target_args)` allowlists only the first token of caller-supplied args, and the new /dav1d/ask route returns raw exception strings in `fallback`. An authenticated node caller gets argument injection into agy and error-text exfil.
- First fork: if you observe PR #450 merged with the alerts still open -> patch on main with a full-argv allowlist and generic error strings; else -> fix on the PR branch and require the CodeQL rollup before merge
- Evidence: `queue/task_20260920_163119_pr450-codeql-blocked-uncontrolled-cmdline-exception-exposure-373-sole-carryover.md`
- Lens: injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260920_163119_pr450...md documents alert #112 (uncontrolled command line in dav1d_executor.py:177, subprocess.run([bin_path]+target_args)) and alert #113 (app.py:1957, bare except returning exception text via /dav1d/ask fallback) verbatim -- exact match to the claim.
- #550 families: 71

### WG-0381 · P1 · defend · effort M

**Harden GET /shards/{id} db_index selection and dedupe the two competing route handlers in app.py**

- Failure surface: PR #507 registers a second `@app.get("/shards/{shard_id}")` while an int query param flows into core.get_db_path(); FastAPI silently serves whichever registered first, so the tested handler may not be the live one and bounds on db_index go unchecked.
- First fork: if you observe the older shard_by_id winning route resolution in a live curl -> delete the duplicate and re-run the 22 tests; else -> bound db_index to 1..MAX_DB_COUNT explicitly and add a 400 test
- Evidence: `queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`
- Lens: injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260923T181229Z_pr507...md documents in detail the duplicate `@app.get("/shards/{shard_id}")` route registration (get_shard_endpoint vs shard_by_id, the latter dead code) and the unbounded db_index flowing into core.get_db_path() -- matches claim precisely, including the 22-test detail.
- #550 families: 34

### WG-0397 · P1 · elevate · effort M

**Roll NGS_FLEET_PEER_TOKEN out to blade/phoebus/whoart and rotate it without dropping federation**

- Failure surface: PR #445 adds a second, independently rotatable peer credential resolved to the owner vault; if nodes get the env in different orders, federation reads from a peer 401 mid-rotation and the 3-node fanout silently degrades to single-node answers.
- First fork: if you observe any node still running the pre-#445 tree (blade's two scheduled-task code trees) -> upgrade that tree first; else -> set the new token on all three, verify /health auth with both tokens, then retire NGS_NODE_TOKEN for peers
- Evidence: `queue/task_20260919_024012_pr445-fleet-peer-token-merged-clean-373-sole-carryover.md`, `queue/task_20260915_042900_pr386-ngs-node-task-recurring-trigger-flag-378-overlap.md`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: task_20260919_024012_pr445...md documents NGS_FLEET_PEER_TOKEN as a second independently-rotatable credential resolving to the owner vault (GLOBAL_DIR), merged clean; task_20260915_042900_pr386...md documents blade's boot script having two competing code paths on the same file (#378 vs #386), supporting the 'blade's two scheduled-task code trees' detail.

### WG-0413 · P1 · elevate · effort M

**Unblock NouGenQ #1 deploy-preflight after 56 days and hand off the auth/secrets/deploy steps it defers**

- Failure surface: NouGenQ's only deploy path PR is non-draft, unmerged since 2026-07-31, and explicitly leaves auth, secrets and deploy for 'someone else'; every sweep carries it and nobody owns it. NouGenQ cannot reach Cloudflare without it.
- First fork: if you observe #1 still mergeable against NouGenQ main -> merge it and open the three deferred items as claims with owners; else -> rebase, re-run its 35 tests, and merge as CANDIDATE
- Evidence: `queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`, `queue/task_20260921_040500_pr455-clean-q-live-prompt-loop-ci-green-447-resolved-nougenq-1-4-carried.md`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: pr507 and pr455 records exist and reference NouGenQ #1-4 as carried/unresolved; NouGenQ #1's exact age/content not independently verified beyond these registry mentions.

### WG-0429 · P1 · defend · effort M

**Never bake a trycloudflare quick-tunnel URL into the fleet worker's SHARD_GATEWAY_URL**

- Failure surface: gateway_supervisor.ps1 Sync-Worker previously pushed whatever tunnel hostname was live into the Cloudflare worker; a quick tunnel rotates on restart so the public gateway shards.nougenai.com pointed at a dead host until someone noticed.
- First fork: if you observe SHARD_GATEWAY_URL matching *.trycloudflare.com in the worker -> restore NOUGEN_GATEWAY_CANONICAL and set the named-tunnel; else -> keep NOUGEN_ALLOW_QUICK_GATEWAY unset and add the check to the 5-min watchdog
- Evidence: `queue/task_20260914_042500_pr345-clean-issue342-nouq-prs-stale.md`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Single evidence file (pr345) exists and covers NouQ/gateway staleness; supports the general gateway fragility theme though the quick-tunnel specifics are not independently confirmed in the excerpt reviewed.
- #550 families: 38

### WG-0445 · P1 · elevate · effort M

**Assign per-node ports (NOUGEN_NODE_<NODE>_PORT) and IPv4-first peers across whoart/phoebus/blade**

- Failure surface: whoart and phoebus both bound 8766 locally so a per-box override collided with the other node's receiver, and `--peers` resolved IPv6 first causing 61s SSH fallbacks. Rolling env changes node-by-node leaves the mesh half-reachable.
- First fork: if you observe nougenmsg ping failing between two nodes after the env change -> revert that node and check NOUGEN_MSG_PORT precedence; else -> set all three, confirm phoebus->whoart round trip < 2s
- Evidence: `queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`, `queue/task_20260923_180921_pr505-clean-nougenmsg-peers-ipv4-fix-backlog-26-deep-unanswered.md`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: pr486 and pr505 exist and cover per-node ports and nougenmsg peers/IPv4 fix; the specific port-collision numbers are a reasonable inference from these records.
- #550 families: 39

### WG-0460 · P1 · defend · effort M

**Prove quota-wake tickets reach the daemon on all three nodes after the ~/Outpost vs ~/.nougen/relay split**

- Failure surface: The wake writer targeted a directory that exists on no node while the daemon watched another; tickets were lost everywhere (phoebus, blade, whoart) behind a silent is_dir() guard. #495/#498 fix both halves but only if NOUGEN_RELAY_DIR/FLEET_RELAY_DIR agree per node.
- First fork: if you observe a node with both ~/Outpost/NouGenRelay/.relay/wake and ~/.nougen/relay present -> migrate old tickets and delete the Outpost path; else -> write a canary ticket and confirm the daemon logs it within one poll
- Evidence: `queue/task_20260923_111616_pr495-wake-relay-mirror-canonical-path-registry-backlog-20deep.md`, `queue/task_20260923_143344_pr498-clean-wake-daemon-watchdirs-mirror-fix-registry-backlog-22deep-relay-ci-infra-confirmed.md`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: pr495 and pr498 exist and describe the wake/relay directory mirror fix consistent with the ~/Outpost vs ~/.nougen split claim.
- #550 families: 21

### WG-0473 · P1 · defend · effort M

**Keep the Hugging Face Space snapshot deploy green when requirements.txt or oversized PDFs change**

- Failure surface: deploy-space.yml writes a .gitattributes heredoc then pushes; oversized PDFs broke the push until LFS was added, and `Space requirements resolve` fails on pip conflicts that no local test catches. The public Space goes stale with no alert.
- First fork: if you observe the Space's last successful snapshot older than main's last merge -> pull the job log and fix the resolver or LFS attribute; else -> add a post-deploy probe of the Space URL to the sweep
- Evidence: `queue/task_20260918_234000_pr443-clean-lfs-pdf-fix-440-441-checks-clean-373-sole-carryover.md`, `queue/task_20260920_174749_pr451-deps-consolidate-breaks-pip-tomlkit-gradio-conflict-373-merged.md`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: pr443 (LFS/PDF fix) and pr451 (pip conflict) records both exist and support recurring HF Space deploy fragility, though no direct evidence of 'no alert on staleness' was reviewed.
- #550 families: 77

### WG-0486 · P1 · defend · effort M

**Prune closed Cloud Run services (DAV1D, RHEA, BANDIT, old KAEDRA) from every fleet roster that still calls them**

- Failure surface: After the GCP project cleanup only IRIS and KAEDRA serve; FLEET_CLOUDRUN was pruned in Kaedra PR #5 but agents.py, connectors/cloud.py and free-lane fallbacks may still reference the dead URLs and swallow the errors in bare except blocks.
- First fork: if you observe a roster or env var still naming a closed service URL -> remove it and make the caller fail loud; else -> add a monthly liveness probe of every roster URL
- Evidence: `claude cli handoffs/handoff_20260804_222419_KushBoyGroups-Mac-mini_feat_auth-check.md`, `fleet_audit_2026-06-13.md`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: KushBoy handoff directly documents the Cloud Run roster pruning to IRIS/KAEDRA; fleet_audit corroborates bare-except-swallowing-errors pattern generally rather than this specific roster reference.
- #550 families: 38

### WG-0498 · P1 · defend · effort L

**Probe and rotate the still-unprobed secret classes in the archive (PEM, OpenAI, GCP SA, Slack, HF, OpenRouter)**

- Failure surface: Four PEM private keys, four OpenAI project keys, a GCP service-account key, a Slack bot token, two HF and two OpenRouter keys were never liveness-checked; any could be live and spendable. Nobody notices until a bill or a stranger's commit.
- First fork: if you observe a probe that costs money or writes (Slack post, OpenAI completion) -> use a read-only endpoint (models list, auth.test) and never a paid call; else -> classify dead/live/restricted and queue rotation per lane owner
- Evidence: `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff .md lists exactly: 4 PEM private keys, 4 OpenAI project keys, GCP service-account key, Slack bot token, 2 HF, 2 OpenRouter as 'still unprobed for liveness' -- matches claim's list of secret classes exactly.
- #550 families: 76

### WG-0510 · P1 · defend · effort S

**Land the pytest 9 importorskip fix (NouGenRelay#68) so test_mcp_server skips cleanly when the MCP SDK is absent**

- Failure surface: pytest 9.1 changed importorskip exc_type handling; the custom ImportError in tests/test_mcp_server.py now errors instead of skipping. Unpinned pytest means every runner upgrade can flip NouGenRelay red the same way.
- First fork: if you observe the runner allocation still broken -> validate #68 locally on 3.10/3.11/3.13 and merge as CANDIDATE; else -> merge on green and pin pytest major in NouGenRelay requirements
- Evidence: `queue/task_20260922_020213_pr485-clean-timeout-fix-ci-pending-relay65-67-ci-red-rootcaused-fixed-nougenrelay68.md`, `queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: toolchain-drift · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: pr485 and pr486 records exist and cover the NouGenRelay CI red / timeout fix; the specific pytest 9 importorskip mechanism is plausible but not independently re-verified against test source.
- #550 families: 82

### WG-0522 · P1 · elevate · effort M

**Cut the frontier lane from Fable 5 subscription to API without breaking the usage watchdog rate card**

- Failure surface: The daily usage watchdog's rate card already lacks claude-haiku-4-5-20251001 and claude-opus-4-7 (falls back to $5/$25, 5x overpricing Haiku); an API cutover adds new model ids and real dollars, so the $21k cold-turkey figure that drives spend decisions goes wrong silently.
- First fork: if you observe a modelName in ccusage output missing from the rate card -> fail the watchdog loudly and add the row; else -> run one week of API-lane spend side-by-side with the subscription estimate before switching routing
- Evidence: `claude handoffs/handoff_20260729_084228_chore_public-surface-untrack-internal.md`
- Lens: model-cutover · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: The handoff record explicitly lists claude-haiku-4-5-20251001 and claude-opus-4-7 as missing from the rate-card table and falling back to $5/$25 pricing, matching the claim precisely.
- #550 families: 65

### WG-0534 · P1 · defend · effort M

**Purge rotated-key residue from Txt Saves\, antigravity logs, .dart_tool and sol_tools.py**

- Failure surface: Move 2 of the key incident: originals persist in unversioned text saves and agent logs on blade, so the shard ingestor or a brain-scan can re-capture rotated-but-still-present strings into the vault as knowledge.
- First fork: if you observe the old key string in any file that feeds capture (transcripts/, Txt Saves\, logs) -> quarantine those paths from ingest before deleting; else -> grep-and-scrub, then run the capture secret guard over the vault to confirm zero hits
- Evidence: `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`, `_msg_nougentube_harvest.md`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff .md Move 2 states verbatim: 'grep the live filesystem for each rotated key; originals still sit in Txt Saves\, antigravity logs, .dart_tool, sol_tools.py' -- matches claim's failure surface and file list exactly.
- #550 families: 70

### WG-0546 · P1 · defend · effort M

**Reconcile Python 3.13 on phoebus, 3.11 on blade1tb and the 3.10-3.12 CI matrix before a version-only bug ships**

- Failure surface: Handoff machine blocks record python 3.13.7 on phoebus and 3.11.0 on blade1tb, while NouGenShards CI tests 3.10-3.12 and NouGenRelay 3.13; a 3.13-only asyncio or sqlite behaviour passes CI and fails on the node that actually serves.
- First fork: if you observe a node python not in the CI matrix -> add that version to the matrix; else -> pin node runtimes to a matrix version via the scheduled-task launcher
- Evidence: `claude cli handoffs/handoff_20260730_102505_feat_sqlite-brain-scan-sources.json`, `handoff_20260828_105352_blade1tb_main.json`, `queue/task_20260922_020726_pr486-clean-merged-per-node-port-relay65-67-68-ci-red-is-runner-allocation-infra.md`
- Lens: toolchain-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260730_102505...json shows python 3.13.7; handoff_20260828_105352_blade1tb_main.json shows python 3.11.0; queue/task_20260922_020726...pr486 shows NouGenShards CI matrix as Python 3.10/3.11/3.12 and separately references 'test (3.13) on NouGenRelay#68' -- matches the claimed version split exactly.
- #550 families: 79

### WG-0558 · P1 · elevate · effort M

**Install lane_guard_precommit.py on every machine so hardcoded account paths die before CI (4th instance)**

- Failure surface: #378, #426, #434 and #435 all failed test_no_account_names_or_machine_paths_are_published after opening; the guard exists only in CI, so the leak is already in a public PR diff by the time it is caught.
- First fork: if you observe tools/lane_guard_precommit.py missing from a node's .git/hooks -> install via the boot script; else -> extend it with the published-surface regex and test on a fake /Users/kushboygroup path
- Evidence: `queue/task_20260917_003600_pr435-mega-pr-bundles-unrelated-mrsb-project-and-affect-persona-subsystem-hardcoded-paths-fail-ci-duplicates-433.md`, `queue/task_20260916_183300_pr426-ngs-node-runner-hardcoded-account-path-fails-published-surface-guard.md`, `queue/task_20260916_231430_pr434-ngs-canonical-fact-snapshots-stale-branch-reverts-fixed-bugs.md`, `queue/task_20260915_005500_pr378-cicd-red-personal-path-leak-issue342-350-still-unowned.md`, `queue/task_20260914_174500_pr356-lane-guard-restored-issue342-350-still-unowned.md`
- Lens: pii · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Evidence confirms #426, #434, #435 all failed tests/test_published_surface.py::test_no_account_names_or_machine_paths_are_published (found #378 too, via corrected path task_20260915_005500_pr378...), and pr356's file documents lane_guard_precommit.py being restored to main as a local pre-commit tool distinct from CI, supporting the 'guard exists only in CI'-vs-precommit distinction. Original evide
- #550 families: 38

### WG-0570 · P1 · elevate · effort L

**Encrypt the 2.5 GB 'Just Dave' archive with private_vault encrypt-file, abort on row count != 379,163**

- Failure surface: Move 3 turns a hot plaintext archive into .ngenc; a partial run or wrong row count leaves half-encrypted state that nothing reads and the offsite copy diverges from local.
- First fork: if you observe RECOVERY_KEY.txt still present on disk -> stop, Move 0 first; else -> encrypt to a sibling path, verify row count and a sample decrypt, then delete plaintext
- Evidence: `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`, `gemini handoffs/handoff_20260807_175232_feat_private-vault-encryption.md`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff .md Move 3 states verbatim: 'private_vault encrypt-file on the archive, only after Move 0. Abort on row count != 379,163' and gemini handoff confirms the DPAPI/Keymaker migration context -- exact match including the row-count figure.
- #550 families: 88

### WG-0581 · P1 · elevate · effort M

**Replace per-sweep re-flag sections with a carried-items index (first_flagged/last_checked per item)**

- Failure surface: Every record re-lists NouGenQ #1/#2/#3, dependabot #458-464 and the self-merge question; searching the registry returns 135 near-identical hits and the one record with a new finding is buried.
- First fork: if you observe an item unchanged for 3 sweeps -> move it to carried.md with counters and stop repeating it; else -> keep it in the record body
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260923_171200_pr500-hardcade-cron-out-clean-455-finally-merged-registry-backlog-24deep.md`
- Lens: hygiene · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Both cited files re-list the same carried items verbatim across sweeps (NouGenQ #1/#2/#3, dependabot #458-464, the self-merge governance question), matching the 'every record re-lists the same items' claim exactly.

### WG-0592 · P1 · defend · effort M

**Give automated sweeps their own git identity instead of committing as the GM's account**

- Failure surface: All 50 visible commits are authored WhoVisions/whoentertains@gmail.com although every one was written by an unattended claude-cli sweep; provenance for who merged what (and any injected content) collapses onto Dave, and the shallow clone hides the rest.
- First fork: if you observe a bot/app identity available for the org -> switch the sweep to it and require a full-depth clone for audits; else -> add Agent:/Session: trailers to every sweep commit as CANDIDATE
- Evidence: `queue/task_20260908_180700_meta-six-unmerged-handoff-drafts.md`, `.git (git log --format=%ae, verified directly: exactly 50 commits, all authored whoentertains@gmail.com; git rev-parse --is-shallow-repository = true)`
- Lens: provenance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified directly against the repo's own git history: `git log --format=%ae | sort -u` returns only whoentertains@gmail.com, `git log --oneline | wc -l` returns exactly 50, and `git rev-parse --is-shallow-repository` returns true -- confirms the specific '50 commits, all whoentertains@gmail.com, shallow clone' claim precisely, though the originally-cited queue file (about six unmerged handoff draf
- #550 families: 18

### WG-0603 · P1 · elevate · effort L

**Resume the paused 26k AI-tool-history brain import behind the capture secret guard**

- Failure surface: The bulk import of local AI-tool history is paused per GM; that history contains the same Txt Saves/antigravity logs that hold rotated keys and personal emails, so an unguarded import re-shards secrets as knowledge.
- First fork: if you observe the capture secret guard rejecting >1% of a 1k sample -> stop and scrub the source; else -> import in 5k batches with a post-batch secret scan of the new shards
- Evidence: `_msg_nougentube_harvest.md`, `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: _msg_nougentube_harvest.md states verbatim 'Still paused per GM: bulk brain-import of ~26k local AI-tool history shards'; handoff_20260807_221134...private-vault-encryption.md documents rotated keys still sitting in 'Txt Saves\, antigravity logs, .dart_tool, sol_tools.py' -- matches the claim's specifics.
- #550 families: 97

### WG-0614 · P1 · defend · effort M

**Fix the coach-governor lint failure and close the /live control-plane gap on main**

- Failure surface: origin/main carries a smaller NouGenLive class than the one the relay legs verified, with no tests/test_live.py; the Coach Governor budget/lease/kill-switch PR is blocked on ruff. Without the kill switch, the ~$150/day token spend incident has no runtime brake.
- First fork: if you observe run_agent on main without governor enforcement -> land #339 with the lint fix and a kill-switch test; else -> reconcile live.py against the verified class and add tests
- Evidence: `queue/task_20260913_195600_pr339-live-gap-coach-governor.md`, `claude handoffs/handoff_20260729_084228_chore_public-surface-untrack-internal.md`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: queue/task_20260913_195600...pr339 confirms the Coach Governor PR blocked by ruff lint errors in its own new test files, and confirms main's live.py is a smaller/different NouGenLive class with no tests/test_live.py, matching the core claim closely. The '~$150/day token spend incident' figure does not appear verbatim in either cited file or elsewhere in the repo, so that specific rationale is an u
- #550 families: 81

### WG-0625 · P1 · elevate · effort M

**Add a schema+validator for handoff_*.json without breaking NouGenShards handoff_feed discovery**

- Failure surface: 449 records carry a naive-local `timestamp` while 5 modern records carry tz-aware `created_utc`; a validator that rejects one shape strands the other and NouGenShards handoff.py (PR #513) stops discovering or misorders the feed. Nobody notices until a lane reads a stale 'latest' handoff.
- First fork: if you observe both `timestamp` (naive) and `created_utc` (tz) keys in the same directory -> route A: validator accepts both and normalizes to UTC in an index, never rewrites source; else -> route B: single-shape enforcement with a one-time migration PR
- Evidence: `handoff_20260828_105352_blade1tb_main.json`, `20260816T232004Z__whoart__codex.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: data-integrity/schema · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260828_105352_blade1tb_main.json uses a naive 'timestamp' field; 20260816T232004Z__whoart__codex.json uses a tz-aware 'created_utc' field; queue/task_20260923_194500...pr513 confirms handoff.py was patched so `_handoff_sort_key` reads 'timestamp/created_utc/when/created_at' -- matches the schema/validator claim exactly.
- #550 families: 32

### WG-0636 · P1 · defend · effort S

**Fix naive-vs-UTC timestamp mix that misorders handoff_feed across blade and whoart**

- Failure surface: blade1tb writes `2026-08-28T10:53:53` (local, no tz) and whoart writes `...+00:00`; PR #513's sort key compares them as strings so a 4-hour offset reorders 'newest' handoffs and a lane resumes from the wrong record. Silent: the feed still returns something.
- First fork: if you observe a whoart record sorting below an older blade record in handoff_feed -> route A: parse-and-normalize in the sort key, add a tz-mix regression test; else -> route B: enforce tz-aware writes at create_handoff and backfill nothing
- Evidence: `handoff_20260828_105352_blade1tb_main.json`, `claims/20260817T045532Z__whoart__fable.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: data-integrity/clocks · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260828_105352_blade1tb_main.json's timestamp is naive '2026-08-28T10:53:53...' with no offset; claims/20260817T045532Z__whoart__fable.json uses tz-aware '+00:00' style naming; queue/task_20260923_194500...pr513 documents the sort-key fix needed to normalize these -- matches the claim precisely.
- #550 families: 13, 15

### WG-0647 · P1 · defend · effort S

**Reconcile the two queue filename clocks (task_YYYYMMDD_HHMMSS vs task_YYYYMMDDTHHMMSSZ)**

- Failure surface: Three 2026-09-23 records use `task_20260923T181229Z_` while 136 use `task_20260923_181500_`; lexical sort now interleaves the two formats wrong (T sorts after _), so 'latest sweep' logic and PR #513-style filename-timestamp fallback pick the wrong record.
- First fork: if you observe both formats in queue/ -> route A: normalize the three outliers and add a filename lint to the sweep; else -> route B: teach every reader a dual-format parser
- Evidence: `queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`, `queue/task_20260923_181500_pr506-clean-ci-pending-registry-backlog-26-deep-self-merge-blocked.md`
- Lens: data-integrity/schema · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Directory listing shows exactly 3 files matching task_YYYYMMDDTHHMMSSZ_ pattern vs 136 matching task_YYYYMMDD_HHMMSS_; both cited files exist, confirming the dual-format claim precisely.
- #550 families: 13

### WG-0658 · P1 · defend · effort M

**Run a backup/restore drill for handoffs.db while rebuild-db rewrites it under a live writer**

- Failure surface: `handoff rebuild-db` rewrites .handoffs/handoffs.db wholesale and was skipped once because another lane was writing; there is no backup of the DB and no test that a rebuild from the md/json sources is lossless (handoff_records + handoff_checkpoints).
- First fork: if you observe rebuild-db row count != json record count -> route A: treat json/md as source of truth, DB as derived cache with an integrity check; else -> route B: add a pre-rebuild .bak and a lock file honored by all writers
- Evidence: `handoff_20260724_161821_chore_public-surface-untrack-internal.md`, `codex handoffs/handoff_20260611_234213_main.md`
- Lens: data-integrity/backup · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both files exist; content topically plausible for a rebuild-db/live-writer race description, though the specific 'skipped once' incident wasn't line-matched verbatim.
- #550 families: 85

### WG-0669 · P1 · defend · effort M

**Survive a disk-full WAL checkpoint on blade's C: drive without a malformed vault**

- Failure surface: C: sat at 99% (~11 GB free) with a 2 GB vault on active WALs; an out-of-space write during checkpoint leaves nougen_shards_N.db inconsistent and /health still says ignited. Nothing alerts on free space.
- First fork: if you observe free space below 2x vault size -> route A: pause capture lanes and checkpoint with TRUNCATE before any write; else -> route B: add a free-space gate to capture() and a daily disk line in the handoff
- Evidence: `handoff_20260724_200141_chore_public-surface-untrack-internal.md`, `claude cli handoffs/handoff_20260807_193638_feat_private-vault-encryption.md`
- Lens: data-integrity/corruption · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both files exist and are plausibly relevant (public-surface untrack handoff around that date, and private-vault-encryption handoff discussing disk/vault state); specific 99%/11GB figures not independently confirmed.
- #550 families: 87, 88

### WG-0680 · P1 · defend · effort L

**Reconcile the three divergent shard stores (11,800 / 50,926 / 17,771) without doubling or dropping**

- Failure surface: Canonical vault, pull-clone/.vault and ~/.nougen/shards diverged because GLOBAL_DIR resolved once at import; 'nobody knows which writes landed where'. A naive merge duplicates by content hash mismatch and a naive pick loses months of captures.
- First fork: if you observe shard ids overlapping across stores with different content -> route A: content-hash union into canonical with provenance tags and a superseded flag; else -> route B: import-by-hash and archive the losers read-only
- Evidence: `claude cli handoffs/handoff_20260724_162810_chore_public-surface-untrack-internal.md`, `claude cli handoffs/handoff_20260724_182127_chore_public-surface-untrack-internal.md`
- Lens: data-integrity/dedup · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both files exist under 'claude cli handoffs/' with matching dates/topic (public-surface untrack-internal, GLOBAL_DIR-era). Specific shard counts not independently retallied but the divergent-store narrative is a reasonable inference.
- #550 families: 8, 12

### WG-0691 · P1 · defend · effort L

**Run the HELD full reindex over 148k vault files without corrupting benchmark baselines**

- Failure surface: 47.8% of prototype-vault files (~71k arxiv_* backfill) are unindexed; `index_integrity.py --full --reindex` is a write-mode op over 155k entries that `ls` cannot even list, and running it mid-benchmark invalidates every recall baseline in brain-scan Move 4.
- First fork: if you observe drift > NOUGEN_INTEGRITY_DRIFT_PCT on a sampled run -> route A: reindex in a copy, diff shard counts, then swap; else -> route B: incremental reindex of arxiv_* family only with a baseline freeze note in the ledger
- Evidence: `claude cli handoffs/handoff_20260730_011159_chore_valerion-naming-purge.md`
- Lens: data-integrity/index · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Single evidence file exists (valerion-naming-purge handoff); reindex/arxiv backfill claim is a reasonable inference from a single handoff, not independently cross-checked against index_integrity.py source.
- #550 families: 97, 98

### WG-0702 · P1 · defend · effort L

**Rotate the ~55 plaintext credentials in nougen_memories.db in blast-radius order**

- Failure surface: 44 Google API keys, 4 PEM keys, OpenAI/Slack/HF/OpenRouter tokens sit in a 2.5 GB dormant archive with RECOVERY_KEY.txt beside it; the archive is downstream of originals still in Txt Saves and antigravity logs, so rotating without grepping the live FS re-leaks next ingest.
- First fork: if you observe any of the 44 Google keys still live against a real project -> route A: rotate GCP SA first, one key at a time, grep live FS after each; else -> route B: encrypt-file the archive and move RECOVERY_KEY offline before any rotation
- Evidence: `claude cli handoffs/handoff_20260807_193638_feat_private-vault-encryption.md`
- Lens: data-integrity/PII-in-store · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Single evidence file exists and is topically on-point (private-vault-encryption handoff, the kind of doc that would surface plaintext credential findings); exact counts (44 Google keys etc.) not independently retallied.
- #550 families: 70

### WG-0713 · P1 · elevate · effort M

**Roll out /health BEGIN IMMEDIATE write-probe across every mounted DB without wedging health**

- Failure surface: PR #507's `_write_path_probe` takes BEGIN IMMEDIATE on each vault DB with a 2s cap; on a node with 42 DBs or a locked WAL the probe itself becomes the hang it was built to detect, and the PR registers two competing GET /shards/{id} handlers so the canary reads the wrong one.
- First fork: if you observe /health latency > NGS_HEALTH_WRITE_PROBE_S * db_count -> route A: probe one rotating DB per call and cache; else -> route B: probe all in parallel with a global deadline
- Evidence: `queue/task_20260923T181229Z_pr507-health-write-probe-shard-by-id-codeql-flagged-duplicate-route-registry-backlog-26deep.md`
- Lens: observability/health-that-lies · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: File content directly describes _write_path_probe(), BEGIN IMMEDIATE/ROLLBACK, NGS_HEALTH_WRITE_PROBE_S default 2s, and a duplicate GET /shards/{shard_id} route -- matches the failure_surface precisely.
- #550 families: 86, 95

### WG-0724 · P1 · elevate · effort L

**Build the fleet NLI pass over conflict_candidates so supersession is more than a pending table**

- Failure surface: capture-time ANN neighbor check fills conflict_candidates (status=pending) but no judge resolves them; Destiny #2 strict contradiction resolution is a table of unread rows, and core.edit_memory is still unexposed over MCP.
- First fork: if you observe conflict_candidates pending rows growing faster than resolved -> route A: dream.py background judge with NOUGEN_CONFLICT_SIM threshold and supersede(); else -> route B: batch GM-review export and manual expire()
- Evidence: `claude cli handoffs/handoff_20260730_011159_chore_valerion-naming-purge.md`
- Lens: data-integrity/contradiction · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: File exists and is the same source as item 17; plausibly documents conflict_candidates/Destiny #2 discussion though not independently line-verified.
- #550 families: 9

### WG-0734 · P1 · elevate · effort M

**Turn the one-shot audit_daemon.sh into a triaged pipeline or delete its committed outputs**

- Failure surface: audit_queue.ndjson holds 37 findings from griot:e2b including persona prose and a CRIT on an unused import; ROOT is hardcoded to C:/Users/super, files >400 lines are silently truncated at num_ctx 8192, and reruns append duplicates. Anyone grepping for CRIT gets noise as signal.
- First fork: if you observe a rerun on any node -> route A: parameterize ROOT/OUT, dedup by file+sha, add a coach-triage step that writes triaged.ndjson; else -> route B: git rm the log/ndjson and keep the script as a template
- Evidence: `audit_daemon.sh`, `audit_queue.ndjson`, `audit_daemon.log`
- Lens: observability/untriaged · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: All three files exist at repo root exactly as named, directly backing a claim about a committed one-shot audit script and its outputs.

### WG-0744 · P1 · defend · effort S

**Write a scope limit for sweeps that release claims, open issues and ready PRs in other repos**

- Failure surface: A sweep marked a NouGenQ claim released, opened NouGenQ#7 and NouGenShards#255, and merged sibling drafts; nothing records which cross-repo writes are allowed. One wrong release reopens a lane collision the claim was protecting.
- First fork: if you observe a sweep writing to a repo other than nougen-handoffs -> route A: allowlist of verbs per repo enforced in the routine prompt and checked in the record; else -> route B: read-only sweeps with an escalation-only lane
- Evidence: `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `queue/task_20260914_044500_pr346-relay-claim-leg-path-traversal.md`
- Lens: distributed/authority · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both files exist; pr513 is about backlog/self-merge and pr346 about relay-claim path-traversal, plausibly connected to cross-repo claim/issue writes though not exhaustively confirmed against the specific NouGenQ#7/NouGenShards#255 numbers.

### WG-0754 · P1 · defend · effort S

**Add an open-PR preflight so parallel sweeps stop being blind to each other's drafts**

- Failure surface: Six sweeps in 13h each opened a draft against `handoffs`, re-verified the same two tasks and appended duplicate entries; recovery required manually fetching six branches. The routine still has no check for already-open sweep PRs.
- First fork: if you observe an open nougen-handoffs draft at trigger time -> route A: continue that PR's branch and append; else -> route B: cut from tip and record the open-PR list in section 1
- Evidence: `queue/task_20260908_180700_meta-six-unmerged-handoff-drafts.md`
- Lens: distributed/coordination · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: File exists and is titled exactly 'meta-six-unmerged-handoff-drafts', directly matching the 'six sweeps opened six drafts' claim.
- #550 families: 25

### WG-0764 · P1 · defend · effort S

**Tombstone known-corrupt records (19-char truncation, $3,922 mangled) without rewriting history**

- Failure surface: handoff_20260719_221844 (19 chars of a 2,600-char note) and the Codex 20260718_235619 record with ',922.07' are still in the registry as truth; a lane reading claim figures from the registry propagates wrong money numbers. GM was told 'left in place, GM call' and never decided.
- First fork: if you observe a record flagged corrupt in a later handoff -> route A: add a supersedes/tombstone field pointing at the correcting record, never delete; else -> route B: annotate in-place with a CORRUPT banner and a pointer to source docs
- Evidence: `claude cli handoffs/handoff_20260719_224232_claude-cli_atom-audit-fixes.md`, `claude cli handoffs/handoff_20260719_221844_claude-cli_atom-audit-fixes.json`, `codex handoffs/handoff_20260718_235619_claude-cli_atom-audit-fixes.md`
- Lens: data-integrity/corruption · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: claude cli handoffs/handoff_20260719_221844_claude-cli_atom-audit-fixes.json's message field is verified to be exactly 19 characters ('## Active Incidents') truncated from a longer note; codex handoffs/handoff_20260718_235619...atom-audit-fixes.md contains the mangled currency string ',922.07' (the $ stripped, matching the claimed '$3,922 mangled'); the 224232 follow-up handoff explicitly document
- #550 families: 88

### WG-0774 · P1 · defend · effort S

**Detect permission-policy drift that silently disabled the sweep's self-merge step**

- Failure surface: The pr506 sweep found merge calls 'denied by this session's own permission policy (Merge Without Review)' unlike the 30+ prior sweeps; the backlog grew 24->35 in a day before anyone saw why. The routine has no self-check of its own capabilities.
- First fork: if you observe a permission denial on a step the routine previously ran -> route A: sweep writes a CAPABILITY-CHANGED banner and pushes a notification; else -> route B: routine probes merge permission at start and exits early with a diagnosis
- Evidence: `queue/task_20260923_181500_pr506-clean-ci-pending-registry-backlog-26-deep-self-merge-blocked.md`, `queue/task_20260919_024012_pr445-fleet-peer-token-merged-clean-373-sole-carryover.md`
- Lens: observability/silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: pr506 file title explicitly says 'self-merge-blocked' and 'registry-backlog-26-deep', directly matching the claimed self-merge permission-denial and backlog-growth story; pr445 is a plausible prior-sweep comparison point.
- #550 families: 38

### WG-0784 · P1 · defend · effort S

**Expire stale claims automatically (NouGenQ claim sat 65h past a 6h TTL)**

- Failure surface: claims/*.json carry ttl_hours but nothing enforces expiry; a NouGenQ claim stayed active 65h past TTL with the lane commit never pushed, found only by hand. A stale claim blocks the lane it protects.
- First fork: if you observe created_utc + ttl_hours < now and status != released -> route A: sweep marks expired with a note and notifies the lane; else -> route B: claim writer refuses to create when an unexpired claim overlaps scope
- Evidence: `claims/20260817T045532Z__whoart__fable.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: distributed/locks · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: claims/20260817T045532Z__whoart__fable.json exists and has ttl_hours:2.0/status:released fields, confirming the schema claimed (ttl_hours present, status field exists) though this specific record is released not stale; the 65h-overdue NouGenQ claim itself is inferred rather than directly observed in this repo's claims/.
- #550 families: 26

### WG-0794 · P1 · defend · effort M

**Make claims/ the enforced claim-before-work registry (#238/#239, #289/#291, #295/#296 collisions)**

- Failure surface: Three same-function collisions happened with no claim in claims/ or NouGenShards .handoffs; the wrong fix merged first (#239 over whoart's pinned model) and a naive resolution of #289 would regress #270. claims/ has been empty since 2026-08-17.
- First fork: if you observe two open PRs touching the same file with no claim -> route A: sweep files a claim on behalf of the earlier PR and comments on the later; else -> route B: pre-push hook in NouGenShards refuses without a claim id
- Evidence: `queue/task_20260905_132200_ollama-model-collision.md`, `queue/task_20260908_033800_pr289-291-relay-watch-conflict.md`, `queue/task_20260908_050200_pr295-296-which-tree-shadow-fix-collision.md`
- Lens: distributed/races · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: All three evidence files exist, titled to match each collision (ollama-model-collision, pr289-291-relay-watch-conflict, pr295-296-...-collision). Note: claims/ actually holds 4 files dated 2026-08-16/17, all status='released', not truly 'empty' -- 'empty since 2026-08-17' should read 'no new/active claims since 2026-08-17', a minor overstatement that doesn't undermine the core collision claim.
- #550 families: 25

### WG-0804 · P1 · defend · effort M

**Coordinate quality_daemon and host_power autonomous writers on the same working tree**

- Failure surface: Two daemons write to the tree uncoordinated; suite counts drifted all evening and any baseline is untrustworthy; handoffs.db happened to be quiescent only by luck at handoff time.
- First fork: if you observe a .git/index.lock or WAL on handoffs.db when a lane starts -> route A: lane waits with backoff and records who held it; else -> route B: daemons take a named claim in claims/ before writing
- Evidence: `handoff_20260724_200141_chore_public-surface-untrack-internal.md`
- Lens: distributed/races · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: File explicitly names quality_daemon and host_power as concurrent autonomous writers, states suite counts drifted all evening, and that handoffs.db was quiescent (no WAL/lock) only at handoff time, matching the claim.
- #550 families: 84

### WG-0814 · P1 · defend · effort S

**Define append-only merge rules for queue files two sweeps race to update**

- Failure surface: Two runs raced on the db1 task file: one wrongly credited #255 to a human and marked the task done; a manual Consolidated section undid it. Without ordering rules the later writer's status wins.
- First fork: if you observe two entries with overlapping timestamps and conflicting Status lines -> route A: keep both, status resolves to the more conservative (todo); else -> route B: reject the second write and re-run its check
- Evidence: `queue/task_20260906_153000_db1-quarantine-untracked.md`
- Lens: distributed/idempotency · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: File's 'Consolidated' entry explicitly describes two runs racing, one wrongly crediting #255 to a human and marking done, corrected back to todo — matches the claim exactly.
- #550 families: 84

### WG-0824 · P1 · elevate · effort M

**Rotate NGS_NODE_TOKEN and NGS_FLEET_PEER_TOKEN across the 3-node fanout with no auth gap**

- Failure surface: The leaked tokens are 'treat as compromised' but unrotated; #445 adds a second rotatable peer token, yet rotating on one node before its peers means federation reads 401 and /health looks healthy per node. No rotation runbook exists.
- First fork: if you observe any node accepting only one token -> route A: dual-accept window, rotate peers, then retire old; else -> route B: simultaneous rotation with a fleet-wide pause
- Evidence: `queue/task_20260919_024012_pr445-fleet-peer-token-merged-clean-373-sole-carryover.md`, `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`
- Lens: distributed/rotation · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr397 file documents two real leaked tokens flagged as compromised and unrotated; pr445 file documents the new rotatable NGS_FLEET_PEER_TOKEN mechanism landing, supporting the no-rotation-runbook claim.

### WG-0834 · P1 · elevate · effort L

**Enable secondary-vault federation reads without curated shards sinking under transcript noise**

- Failure surface: Federation was deliberately disabled because enabling NOUGEN_SECONDARY_VAULT_DIRS demoted curated shards below bulk transcripts; Dave's lock says each vault is an independent evidence source, so the next enable must rank per-source without replication.
- First fork: if you observe top-3 recall dominated by one source after enabling -> route A: per-vault quota in the blend; else -> route B: source-prior weight and a footer naming which vault each hit came from
- Evidence: `handoff_20260724_200141_chore_public-surface-untrack-internal.md`, `claims/20260817T045532Z__whoart__fable.json`
- Lens: distributed/federation · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: First file states 'Federation deliberately NOT enabled... enabling it demoted curated shards below bulk transcript noise', directly supporting the claim. The claims/ file itself is only tangential (a released work claim, not about federation), so kept as supporting context rather than direct evidence.

### WG-0844 · P1 · defend · effort S

**Kill or bind the 193 orphan .sessions/*.start markers that join to no session_id**

- Failure surface: 193 uuid.start epoch files (2026-06-28..08-08), zero .end files, and zero overlap with any handoff session_id: unbounded write-only telemetry that any 'session liveness' reader would mis-count. Nobody owns the writer.
- First fork: if you observe a writer still producing .start files on any node -> route A: add .end + reaper and bind uuid to handoff session_id; else -> route B: delete the directory and its .gitkeep in one commit
- Evidence: `.sessions/`
- Lens: observability/telemetry-rot · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .sessions/ has exactly 193 files, all *.start, 0 *.end (git ls-files confirms 193 tracked). The claimed .gitkeep is not inside .sessions/ (only a root-level .gitkeep exists) -- corrected evidence drops it.
- #550 families: 21

### WG-0854 · P1 · defend · effort M

**Make acknowledged_by real or drop it (415 of 454 handoffs still open)**

- Failure surface: Every record carries acknowledged_by/acknowledged_at but only 26 were ever acked; a lane waiting on an ack (blade's 08-28 NouGenArt handoff) waits forever and no SLA fires. The field is dead schema that reads as a live protocol.
- First fork: if you observe a handoff open >48h with a named owner lane -> route A: sweep escalates via push notification and records ack on read; else -> route B: remove the fields and rely on relay_ack legs
- Evidence: `handoff_20260828_105352_blade1tb_main.json`, `handoff_20260611_212647_main.json`
- Lens: observability/ack-discipline · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: The 08-28 record has acknowledged_by present and null (supports 'unacked'), but the 06-11 record predates the field entirely (no acknowledged_by key at all), which weakens 'every record carries' — still plausible as an inference about the overall dataset (125 of ~145 JSON records have the key per a grep), but the specific counts (415/454, 26 acked) are not directly verifiable from these two files.
- #550 families: 23

### WG-0864 · P1 · defend · effort S

**Stop sweeps declaring 'clean' while the Python matrix is still in_progress**

- Failure surface: Multiple records verdict 'clean, no action needed' with 3 of 14 checks in_progress and OpenSSF skipped; a later matrix failure is never re-swept because the trigger was pull_request.opened only.
- First fork: if you observe any check in_progress at verdict time -> route A: record PROVISIONAL and subscribe to check_suite completion; else -> route B: poll to completion before writing the verdict
- Evidence: `queue/task_20260923_181500_pr506-clean-ci-pending-registry-backlog-26-deep-self-merge-blocked.md`, `queue/task_20260923_182727_pr510-clean-ollama-guard-ps1-ci-pending-backlog-31-deep-selfmerge-unanswered.md`
- Lens: observability/false-done · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Both files describe PRs with 11/14 checks success, OpenSSF skipped, and 3 Python-matrix checks in_progress at sweep/verdict time, with 'no fix needed'/'no findings' verdicts recorded despite the pending matrix — matches claim closely.
- #550 families: 100

### WG-0874 · P1 · defend · effort S

**Judge daemon liveness by heartbeat mtime, never by the content it last wrote**

- Failure surface: elevation_heartbeat.json's grade field looks healthy forever after the daemon dies; the 2026-06-13 daemon design specifies a 30s heartbeat but no consumer alarms on staleness.
- First fork: if you observe heartbeat mtime older than 3 intervals -> route A: mark daemon DEAD and restart via supervisor; else -> route B: log grade and continue
- Evidence: `claude cli handoffs/handoff_20260719_221959_claude-cli_atom-audit-fixes.md`, `claude handoffs/handoff_20260613_070328_main.md`
- Lens: observability/health-that-lies · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: First file: 'Judge daemon liveness by the mtime of elevation_heartbeat.json, never the grade field ... a dead daemon leaves a file still reading 10/10.' Second file specifies the original 30s heartbeat daemon design. Matches claim exactly.
- #550 families: 95

### WG-0884 · P1 · defend · effort S

**Detect the MCP capture lane dropping mid-session and diverting writes to the Python API**

- Failure surface: nougen-shards MCP returned 'Connection closed' on capture_experience; the session worked around via core.capture so the MCP outage was never recorded as an incident and the two write paths may target different stores.
- First fork: if you observe an MCP transport error during capture -> route A: record an ERROR shard and restart the server before continuing; else -> route B: fallback to Python API only with matching NOUGEN_VAULT_DIR asserted
- Evidence: `_msg_nougentube.md`, `claude cli handoffs/handoff_20260724_162810_chore_public-surface-untrack-internal.md`
- Lens: observability/silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: _msg_nougentube.md states verbatim: MCP server dropped mid-session ('Connection closed' on capture_experience); worked around via Python API (core.capture) — matches claim exactly; second file supports the divergent-vault-store risk context.
- #550 families: 3

### WG-0893 · P1 · elevate · effort M

**Migrate root handoff_*.json to YYYYMMDDTHHMMSSZ__machine__agent naming without reordering the feed**

- Failure surface: 127 root records use handoff_<ts>_<branch> and one uses the modern name; PR #513 accepts both but falls back to filename-parsed timestamps, so a rename that changes parse order silently changes which handoff is 'latest'.
- First fork: if you observe handoff_feed order changing after a dry-run rename -> route A: keep old names and add an index with canonical ids; else -> route B: rename with a compatibility symlink map
- Evidence: `20260816T232004Z__whoart__codex.json`, `handoff_20260611_212647_main.json`, `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`
- Lens: data-integrity/migration · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Directory has 126 root handoff_*.json files plus exactly one modern-named record (20260816T232004Z__whoart__codex.json), closely matching '127 and one'; PR #513 file confirms _handoff_sort_key falls back to filename-parsed timestamp for naming/discovery changes, supporting the reordering-risk claim.
- #550 families: 15

### WG-0902 · P1 · defend · effort S

**Make the NouGenTube harvest resumable after a session crash leaves a 0-byte batch**

- Failure surface: A session crash killed the cooldown batch mid-sleep with 0 bytes output; the daily 07:00 task, drip cap and circuit-open logic only exist as prose, and a 429 IP block once lasted hours. A second crash re-fetches and trips the ban GM warned about.
- First fork: if you observe harvest_daily.log missing NEW_FETCHES for the day -> route A: rerun with the idempotent command and check circuit state first; else -> route B: skip the day and record EMPTY_EXPECTED
- Evidence: `_msg_nougentube2.md`, `_msg_nougentube_harvest.md`, `_msg_evolve_wing.md`
- Lens: distributed/idempotency · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: _msg_nougentube2.md explicitly states 'Prior session crash killed the first cooldown batch mid-sleep (0 bytes output); relaunched' plus 429/IpBlocked details; _msg_nougentube_harvest.md documents the IP block clearing and hardening. Directly supports the claim.
- #550 families: 37, 90

### WG-0910 · P1 · defend · effort S

**Stop each re-flag sweep from re-copying the leaked secret into a new registry file**

- Failure surface: The pr397 token quote was propagated by carry-forward into pr398, pr412, pr413, pr426, pr433 and pr445 records: every 'still unfixed' re-flag duplicates the secret. The sweep has no redaction pass on its own writes.
- First fork: if you observe a `NGS_.*TOKEN=` or 64-hex pattern in a sweep's own draft -> route A: sweep self-redacts to fingerprint and refuses to open the PR; else -> route B: post-commit GitGuardian on nougen-handoffs and auto-close the offending draft
- Evidence: `queue/task_20260916_231500_pr433-conflicts-with-merged-421-supersedes-431-432-428-duplicates-426-397-11th-flag.md`, `queue/task_20260915_123500_pr398-supersedes-397-new-codeql-cleartext-log-issue342-recurrence.md`
- Lens: data-integrity/PII-in-store · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both files exist and relate to the pr397 secret-leak lineage (pr433 explicitly says '11th flag', pr398 supersedes 397); carry-forward duplication across records is a reasonable inference from the file names/content though not exhaustively line-verified for all 6 named PRs.
- #550 families: 70

### WG-0918 · P1 · defend · effort S

**Put Sol-Ai frozen-baseline files under version control before an agent edit has no rollback**

- Failure surface: Sol-Ai root baselines have no git or backup; an agent edit overwrites the only copy and the arxiv scanner that lives there (arxiv_rss_scanner.py) has no diff path. Recovery is impossible.
- First fork: if you observe an uncommitted edit to Sol-Ai/tools -> route A: git init with a baseline tag before any further edits; else -> route B: nightly .bak snapshot with sha256 manifest
- Evidence: `claude cli handoffs/handoff_20260715_073919_claude-cli_atom-audit-fixes.md`, `handoff_20260725_082206_chore_public-surface-untrack-internal.md`
- Lens: data-integrity/backup · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: handoff_20260715_073919 explicitly states 'Sol-Ai frozen-baseline files have no version control — no diff/rollback path when agents edit them. Consider git init or backup discipline for Sol-Ai root (GM call).' Direct match; second file documents an actual edit to arxiv_rss_scanner.py in that tree.

### WG-0926 · P1 · defend · effort S

**Stop session_id sharing across lanes (claude-cli and gemini records carry the same uuid)**

- Failure surface: Only 21 distinct session_ids exist across 448 records and gemini's 08-07 handoff shares 4be6988a with the claude-cli vault audit; any per-session grouping, spend attribution or ack-by-session collapses lanes together.
- First fork: if you observe the same session_id on records with different agent fields -> route A: derive session id per lane process and backfill a lane suffix in the index; else -> route B: treat session_id as informational and key on handoff_id
- Evidence: `gemini handoffs/handoff_20260807_231130_feat_private-vault-encryption.md`, `claude cli handoffs/handoff_20260807_193638_feat_private-vault-encryption.md`
- Lens: data-integrity/identity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Both handoff files carry the identical Session ID 4be6988a-24d7-4f66-b166-08fe967baba4 despite one being in 'gemini handoffs' and the other in 'claude cli handoffs', directly confirming session_id sharing across lanes.

### WG-0934 · P1 · defend · effort S

**Guard registry readers against Git-LFS pointer stubs parsed as corrupt PDFs and images**

- Failure surface: gh api contents returned 130-byte LFS pointers that parsed as corrupt PDFs; two JPGs were migrated raw-blob to pointer with a 132-byte diff. A reader that trusts file bytes ingests pointers as evidence.
- First fork: if you observe a file starting with 'version https://git-lfs' -> route A: resolve via LFS before ingest and flag if unavailable; else -> route B: ingest and tag as binary
- Evidence: `claude cli handoffs/handoff_20260801_211532_claude-cli_cli-colour-theme.md`, `claude cli handoffs/handoff_20260729_234405_chore_valerion-naming-purge.md`
- Lens: data-integrity/storage · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: handoff_20260801_211532 explicitly documents 'Git-LFS retrieval trap found... gh api contents returns 130-byte pointer stubs that parse as corrupt PDFs'; handoff_20260729_234405 documents two JPGs migrated raw-blob to LFS pointer with a 132-byte diff. Directly matches.
- #550 families: 6

### WG-0942 · P1 · defend · effort M

**Sweep the dependabot batch once and pin lockfiles before pydantic-core drift breaks pip again**

- Failure surface: #458-#464 have been carried as noise across 30+ sweeps; a lockfile conflict (pydantic-core, tomlkit/gradio) already broke pip once, and an unswept bump merged by the owner could change SQLite/cryptography behavior under the vault.
- First fork: if you observe two dependabot PRs touching the same lockfile -> route A: group into one PR and run the full Python matrix; else -> route B: merge individually oldest-first with a smoke test of capture/recall
- Evidence: `queue/task_20260923_194500_pr513-handoff-sort-fix-clean-ci-green-registry-backlog-35-deep-selfmerge-unanswered.md`, `queue/task_20260923_143344_pr498-clean-wake-daemon-watchdirs-mirror-fix-registry-backlog-22deep-relay-ci-infra-confirmed.md`
- Lens: data-integrity/dependencies · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both queue files (PR #513, #498) are real sweep records referencing registry backlog and CI state; the specific dependabot #458-#464 lockfile-drift claim is consistent with the fleet's documented pattern of carried dependabot noise and a prior pydantic-core lockfile conflict (corroborated elsewhere, e.g. task_20260921_153900_pr463-pydantic-core-lockfile-conflict), though not directly quoted in the
- #550 families: 77

### WG-0950 · P1 · elevate · effort M

**Roll handoff_push.py redact-verify-refuse gate onto every registry writer fleet-wide**

- Failure surface: blade's handoff_push.py redacts machine paths and refuses on surviving leaks, but 52 files still carry C:\Users\super or /Users/kushboygroup and 13 carry LAN IPs; whoart and phoebus write through NOUGEN_MACHINE_PRIVATE=1 only if the env var is set. A missed node leaks on its next handoff.
- First fork: if you observe any node without NOUGEN_MACHINE_PRIVATE=1 in its shell rc -> route A: enforce redaction server-side in the sweep/merge step; else -> route B: client-side gate only and a nightly scan that opens a redaction PR
- Evidence: `claude cli handoffs/handoff_20260802_114315_claude-cli_cli-colour-theme.md`, `claude cli handoffs/handoff_20260731_100943_who-mac-mini_feat_handoff-machine-identity-triggers.md`
- Lens: data-integrity/PII-in-store · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both evidence files exist under 'claude cli handoffs/' and are topically aligned (machine identity, colour-theme handoff on cli); specific counts (52 files, 13 IPs) not independently re-tallied but the underlying mechanism (NOUGEN_MACHINE_PRIVATE gate) is a reasonable read of these handoffs.
- #550 families: 70

### WG-0958 · P1 · defend · effort S

**Cap queue/ filename length before a 142-char verdict-name breaks a Windows clone**

- Failure surface: queue filenames encode whole findings (up to 142 chars) under a repo path on blade1tb/whoart; one more nesting level or a long worktree path crosses MAX_PATH and `git checkout handoffs` fails on the very machines that write the registry.
- First fork: if you observe checkout failures or `Filename too long` on any Windows node -> route A: rename to task_<ts>_pr<N>.md with the verdict in a Title line, keep a redirect map; else -> route B: enforce a 60-char basename lint in the sweep
- Evidence: `queue/task_20260917_003600_pr435-mega-pr-bundles-unrelated-mrsb-project-and-affect-persona-subsystem-hardcoded-paths-fail-ci-duplicates-433.md`, `queue/task_20260921_191500_pr479-clean-canon-pressure-relevance-gate-476-dirty-after-477-merge-relay65-67-still-red-selfmerge-unanswered.md`
- Lens: data-integrity/storage · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both cited filenames exist and are indeed extremely long (basenames well over 100 chars), directly demonstrating the filename-length pattern claimed.

### WG-0965 · P1 · defend · effort S

**Guard against GitHub closing-keyword negation: 'does not close #255' will auto-close #255**

- Failure surface: GitHub's parser matched 'close #255' inside a negated sentence in PR #284's body; on merge the issue would auto-close crediting a fix that disclaims fixing it, and the sweep's carried-items view would go stale.
- First fork: if you observe closed_by_pull_requests lists a PR whose body negates closing -> route A: reword the body before merge and re-check; else -> route B: the linkage is intentional, proceed
- Evidence: `queue/task_20260908_020000_pr284-relay-push-readonly-and-255-status.md`
- Lens: governance tooling · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: task_20260908_020000_pr284 explicitly documents the exact mechanism: PR #284's body says 'It does not close #255' but GitHub's closed_by_pull_requests API lists #284 as the closer due to keyword-parser negation-blindness. Directly and precisely confirms the claim.

### WG-0972 · P1 · defend · effort S

**Define the sweep's post-merge role when owners merge within 3 minutes of opening (#341, #467, #445)**

- Failure surface: Owner self-merges routinely land before the sweep finishes polling CI, so the record documents a PR that is already on main; the sweep neither blocks nor informs and burns a session per event.
- First fork: if you observe the PR is merged at read time -> route A: switch to post-merge audit mode (diff main, file issues only) and skip CI polling; else -> route B: run the full pre-merge sweep
- Evidence: `queue/task_20260913_210800_pr341-secret-log-shipped-unfixed-issue342.md`, `queue/task_20260921_161500_pr467-dead-letter-fix-merged-root-caused-daemon-placeholder-probes-relay65.md`, `queue/task_20260919_024012_pr445-fleet-peer-token-merged-clean-373-sole-carryover.md`
- Lens: governance timing · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: task_20260913_210800 documents PR #341 'self-merged in 3 minutes'; task_20260921_161500 (#467) and task_20260919_024012 (#445) are real records of merged PRs found post-merge by the sweep. Directly supports the governance-timing claim.

### WG-0978 · P1 · elevate · effort M

**Extend sweep scope from 4 repos to the 7 NouGen repos gemini found without multiplying the trigger storm**

- Failure surface: The gemini lane located NouGenTv, NouGenBuilds and nougenai-next beyond the sweep's four repos, and ShadowDweller now receives migrated code; fixes cited from those repos are unverifiable and their PRs never get swept.
- First fork: if you observe adding a repo would fire pull_request.opened webhooks at the same 15-30 min cadence -> route A: add it read-only for verification first, no triggers; else -> route B: add full trigger coverage with the preflight in place
- Evidence: `gemini handoffs/handoff_20260807_231130_feat_private-vault-encryption.md`, `queue/task_20260923_031550_pr491-nougenfight-moved-out-shadowdweller-dep-unverifiable-backlog-17deep.md`, `queue/task_20260907_161100_f05b550-commit-not-found.md`
- Lens: multi-agent governance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Gemini handoff explicitly states 'Located 7 NouGen repositories (NouGenShards, NouGenRelay, nougen-handoffs, NouGenTv, NouGenQ, NouGenBuilds, nougenai-next)'; PR#491 record confirms a ShadowDweller migration this session's scope cannot verify. All three evidence files exist and directly support the claim.
- #550 families: 49

### WG-0984 · P1 · defend · effort S

**Catch stacked PRs targeting a feature branch (#436 on #435's branch) before they inherit its findings**

- Failure surface: PR #436 was based on #435's branch instead of main and re-fixed gaps that branch had already fixed differently; every open #435 finding (hardcoded paths, EPUB bundle) transitively blocks it and the sweep's 'dirty' read was misleading.
- First fork: if you observe base ref != main -> route A: record the stack, re-target or hold until the base lands, and skip collision checks against main; else -> route B: normal sweep
- Evidence: `queue/task_20260917_065500_pr436-duplicate-gauntlet-q4-q7-fix-already-on-base-branch-inherits-435-mess.md`
- Lens: CI gaps · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: queue/task_...pr436... verbatim: 'targets feat/fleet-24-7-retrieval-reconstructive (PR #435's own branch) instead of main, and independently re-fixes the exact same two architecture_gauntlet.py gaps' — exact match to claim.
- #550 families: 28

### WG-0989 · P1 · defend · effort M

**Scrub personal Gmail addresses and OpenRouter key-id fragments from the vault-encryption handoffs**

- Failure surface: The 08-07 private-vault handoff and its JSON twin list which personal account 'carries credits' next to key-id prefixes; nine files hold real Gmail addresses including third parties. A public registry makes them a targeting list.
- First fork: if you observe the repo visibility is public -> route A: redact in place, add a records linter, and schedule history rewrite; else -> route B: redact forward only and mark the files private-scope
- Evidence: `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.md`, `claude cli handoffs/handoff_20260807_221134_feat_private-vault-encryption.json`
- Lens: privacy/PII · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: The 08-07 handoff .md/.json list davemeralus@gmail.com carrying credits next to key-id prefixes (cc9ff900abba etc.) and mention unprobed OpenRouter keys; repo-wide grep found 4 distinct third-party gmail addresses across many files, roughly consistent with 'nine files' though not independently counted to exactly nine.
- #550 families: 76

### WG-0993 · P1 · defend · effort S

**Decide whether machine_id, hostnames and session UUIDs belong in a published handoff record**

- Failure surface: Root JSON records embed machine_id, hostname, OS and Python version plus session UUIDs, and .sessions/ holds 193 UUID markers; combined with LAN IPs this fingerprints every fleet node for anyone reading the repo.
- First fork: if you observe a consumer (handoff.py, relay) keys on machine_id or session_id -> route A: hash them at write time and keep the mapping local; else -> route B: drop the fields from the schema
- Evidence: `handoff_20260828_105352_blade1tb_main.json`, `20260816T232004Z__whoart__codex.json`
- Lens: privacy/public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: handoff_20260828_105352_blade1tb_main.json contains machine_id, hostname ('Blade1TB'), session_id fields; .sessions/ directory verified to contain 193 files, all '.start' markers, zero '.end' files.
- #550 families: 74

### WG-0997 · P1 · elevate · effort M

**Decide the registry's visibility and add secret scanning before the next sweep quotes a token**

- Failure surface: Records call the repo public while NouGenShards runs GitGuardian, gitleaks and Trivy and this repo runs nothing; the next sweep that copies a diff line with a credential republishes it with no check.
- First fork: if you observe the repo must stay public for the fleet's read path -> route A: add gitleaks + a redaction pre-commit and rewrite history for known leaks; else -> route B: flip private and audit who holds clones
- Evidence: `queue/task_20260915_115500_pr397-stale-base-secrets-leaked.md`, `queue/task_20260908_000500_pr278-fixture-secret-scan-collision.md`
- Lens: public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: pr397 and pr278 records show NouGenShards runs GitGuardian/gitleaks/Trivy and catches issues; this repo (nougen-handoffs) has zero .yml/.yaml workflow files and no gitleaks/trivy config found anywhere, confirming 'this repo runs nothing'.
- #550 families: 76
