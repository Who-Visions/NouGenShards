# NouGen war-game catalog

Generated index. Source of truth is `catalog.ndjson`; regenerate with
`python tools/wargame_catalog.py render` and gate with `render --check`.
See `README.md` in this directory for doctrine, method and how to claim an entry.

**1000 candidates** · P0 361 · P1 639 · P2 0 · P3 0

kind: defend 687 · elevate 313  
likelihood: observed 690 · likely 310 · speculative 0  
verdict: CONFIRMED 894 · PLAUSIBLE 106  
status: open 1000  
reserve (verified but outside the 1000): 1642

## By repo

| repo | total | P0 | P1 | P2 | P3 | defend | elevate | file |
|---|---|---|---|---|---|---|---|---|
| nougen-handoffs | 169 | 107 | 62 | 0 | 0 | 124 | 45 | [nougen-handoffs.md](nougen-handoffs.md) |
| fleet | 122 | 59 | 63 | 0 | 0 | 82 | 40 | [fleet.md](fleet.md) |
| NouGenRelay | 106 | 43 | 63 | 0 | 0 | 76 | 30 | [nougenrelay.md](nougenrelay.md) |
| NouGenMsg | 95 | 32 | 63 | 0 | 0 | 59 | 36 | [nougenmsg.md](nougenmsg.md) |
| NouGenShards | 86 | 30 | 56 | 0 | 0 | 55 | 31 | [nougenshards.md](nougenshards.md) |
| Visions-ai | 76 | 18 | 58 | 0 | 0 | 54 | 22 | [visions-ai.md](visions-ai.md) |
| Kaedra | 71 | 17 | 54 | 0 | 0 | 52 | 19 | [kaedra.md](kaedra.md) |
| Rhea-Noir | 64 | 17 | 47 | 0 | 0 | 49 | 15 | [rhea-noir.md](rhea-noir.md) |
| Dav1d | 68 | 9 | 59 | 0 | 0 | 43 | 25 | [dav1d.md](dav1d.md) |
| Yuki-Ai | 38 | 9 | 29 | 0 | 0 | 27 | 11 | [yuki-ai.md](yuki-ai.md) |
| Ai-with-Dav3--Alpha- | 12 | 7 | 5 | 0 | 0 | 8 | 4 | [ai-with-dav3-alpha.md](ai-with-dav3-alpha.md) |
| Iris-Ai | 12 | 4 | 8 | 0 | 0 | 7 | 5 | [iris-ai.md](iris-ai.md) |
| nougenai-mcp-gateway | 9 | 3 | 6 | 0 | 0 | 3 | 6 | [nougenai-mcp-gateway.md](nougenai-mcp-gateway.md) |
| unk-app-ai | 48 | 3 | 45 | 0 | 0 | 34 | 14 | [unk-app-ai.md](unk-app-ai.md) |
| Kam-ai | 17 | 2 | 15 | 0 | 0 | 9 | 8 | [kam-ai.md](kam-ai.md) |
| who-visions-tester | 7 | 1 | 6 | 0 | 0 | 5 | 2 | [who-visions-tester.md](who-visions-tester.md) |

## P0 — game these first

| id | repo | kind | title |
|---|---|---|---|
| WG-0001 | nougen-handoffs | defend | Rotate the NGS_TOKEN/NGS_NODE_TOKEN pair leaked via NouGenShards PR #397 and prove it |
| WG-0002 | fleet | elevate | Restore the /sync/hashes -> /sync/pull loop across blade, phoebus and whoart |
| WG-0003 | NouGenRelay | defend | Prove FLEET-LOG relays cannot carry the 21 known AIzaSy fingerprints out of the vault |
| WG-0004 | NouGenMsg | defend | Close the live emit_node shell injection on whoart and blade by hand-copy of untracked files |
| WG-0005 | NouGenShards | defend | Re-verify every HARDENING.md ✅ whose mechanism vanished in the 2026-09-05 history rewrite |
| WG-0006 | Visions-ai | defend | Rotate and purge the committed AI Studio key without breaking the three files that use it |
| WG-0007 | Kaedra | defend | Rotate and history-purge the two committed Notion integration tokens |
| WG-0008 | Rhea-Noir | defend | Rotate and purge the live Notion tokens hardcoded in Scripts/corrected_migration.py |
| WG-0009 | Dav1d | defend | Align local Python 3.11 launchers with the 3.12 container that multi-line f-strings require |
| WG-0010 | Yuki-Ai | elevate | Cut the 'Unk' pricing dependency: make core/yuki_models_spec.py the fleet source of truth for Gemini SKUs |
| WG-0011 | Ai-with-Dav3--Alpha- | elevate | Ship app/api/agent/route.ts persona proxy to replace the hard-coded localhost:8000 chat backend |
| WG-0012 | Iris-Ai | defend | Reconcile the three GCP identities and repoint every fleet caller at the live Iris URL |
| WG-0013 | nougenai-mcp-gateway | defend | Resolve the mcp.nougenai.com hostname claim between this repo and nougen-shard-gateway |
| WG-0014 | unk-app-ai | defend | Stop deploying Cloud Run with --allow-unauthenticated while every router uses get_optional_user |
| WG-0015 | Kam-ai | defend | Prove rule 1 holds when phoebus rebases a whoart-stamped Kam-ai commit |
| WG-0016 | who-visions-tester | defend | Resolve the DAV1D project migration in dav1d_brain or retire the BigQuery path |
| WG-0017 | nougen-handoffs | defend | Teach the sweep to cite leaked secrets by fingerprint, never by value |
| WG-0018 | fleet | defend | Keep the whoart-vault named tunnel alive under an admin task, not only the 5-minute user watchdog |
| WG-0019 | NouGenRelay | defend | Survive nougen_shards API drift in auto_capture_shard and every fleet-ops tool |
| WG-0020 | NouGenMsg | defend | Harden the verdict parser: a last line of 'NO' approves elevated delivery |
| WG-0021 | NouGenShards | defend | Survive descriptor exhaustion on phoebus without /health lying about auth |
| WG-0022 | Visions-ai | elevate | Resolve the split-brain GCP project (endless-duality vs mineral-subject vs who-visions-dav1d) end to end |
| WG-0023 | Kaedra | defend | Recover the Cloud Run agent from six never-committed modules that abort background_init |
| WG-0024 | Rhea-Noir | defend | Rotate the live Google API key in test_extract.py and purge it from the 2 GB git history |
| WG-0025 | Dav1d | defend | Defuse the [EXEC:] protocol: model text parsed for [EXEC: cmd] runs shell=True with a 'Do not refuse' override |
| WG-0026 | Yuki-Ai | defend | Purge committed biometric profiles (dave_facial_ip.json, cloud_vision landmarks) and rewrite history |
| WG-0027 | Ai-with-Dav3--Alpha- | defend | Degrade the Dav1d/Kaedra chat gracefully when Cloud Run returns 400/500/503 |
| WG-0028 | Iris-Ai | defend | Re-apply generation rate limiting lost in df074bc before the next quota incident |
| WG-0029 | nougenai-mcp-gateway | elevate | Land PR #3 switchboard tools without importing CC BY-NC-SA terms or provider secrets |
| WG-0030 | unk-app-ai | defend | Stop trading bot dev/test runs from writing to the live Firestore/BigQuery/Notion production targets |
| WG-0031 | Kam-ai | elevate | Arm the claim registry in every Kam-ai clone (core.hooksPath, nougen.machine, first record) |
| WG-0032 | nougen-handoffs | defend | Close Issue #342: masked decrypted-vault-secret print in tools/check_kg_keys.py shipped to main |
| WG-0033 | fleet | defend | Find the phoebus node slow-leak that ngs-node-refresh.sh papers over |
| WG-0034 | NouGenRelay | elevate | Add a CI registry lint that parses every .handoffs/*.json and rejects non-leg shapes |
| WG-0035 | NouGenMsg | defend | Latch phoebus's receiver: launchd wrapper never sets NOUGEN_AGY_MSG_AUTH and SKILL.md's 'open' value latches |
| WG-0036 | NouGenShards | elevate | Rotate NGS_NODE_TOKEN across blade/phoebus/whoart/Space/Worker without a 401 outage |
| WG-0037 | Visions-ai | elevate | Cut the Dockerfile CMD over to visions/api/app.py without breaking /query callers |
| WG-0038 | Kaedra | defend | Survive a lane committing to Kaedra with hooks uninstalled or the relay import broken |
| WG-0039 | Rhea-Noir | elevate | Shrink the 2 GB repo: 118 committed omniverse PNGs, Scripts/*.exe, json3 captions, zip and wav |
| WG-0040 | Dav1d | elevate | Move the 640MB of PDFs, Veo videos and cookbook out of git and the Cloud Build context |
| WG-0041 | Yuki-Ai | defend | Scan history for the API keys V11_CHANGELOG says were scrubbed from v10 files |
| WG-0042 | Ai-with-Dav3--Alpha- | defend | Replace the faked kaedra_verification_console.py with a real probe and relocate the Kaedra artifacts |
| WG-0043 | Iris-Ai | elevate | Decide Iris-Ai revival or retirement and fix the Iris-Vortex identity in README |
| WG-0044 | nougenai-mcp-gateway | elevate | Decide revive-or-retire for nougenai-mcp-gateway now that Watchtower owns the public gateway |
| WG-0045 | unk-app-ai | defend | Reconcile gemini_agent/models_spec.py's pricing table against actual GCP billing |
| WG-0046 | nougen-handoffs | defend | Fix the relay_claim_leg/relay_ack_leg leg_id path traversal (Issue #350) that shipped via PR #346 |
| WG-0047 | fleet | defend | Stop fleet-ssh-keepalive from orphaning ControlMaster processes and exhausting sshd on blade |
| WG-0048 | NouGenRelay | elevate | Collapse blade's two scheduled tasks and two code trees into one daemon, one DB, one lock |
| WG-0049 | NouGenMsg | defend | Retire the ten stale lane branches that each delete infra/ and the injection tests |
| WG-0050 | NouGenShards | defend | Run the claim-guard bypass drill: pre-commit fails open and hooksPath is opt-in |
| WG-0051 | Visions-ai | defend | Survive the next fleet-wide model-id sweep without rewriting router.py's RETIRED entries again |
| WG-0052 | Kaedra | elevate | Re-home the Kaedra deploy pipeline onto the Whovisions Fleet project (kaedra-agent-api) |
| WG-0053 | Rhea-Noir | defend | Stop veil_utils.ensure_schema and _create_property from auto-growing Notion schema (333 vs 399 props) |
| WG-0054 | Dav1d | defend | Stop advertising A2A skills that the JSON-RPC server only acknowledges |
| WG-0055 | Yuki-Ai | defend | Rotate the AniDB password committed in anidb_http_client.py and purge it from history |
| WG-0056 | Ai-with-Dav3--Alpha- | elevate | Land PR #1 (NouGenShards spotlight on Home.tsx) under an explicit merge-authority rule |
| WG-0057 | Iris-Ai | defend | Bring iris-agent-service /health back from 500/503 so the fleet roster reads ONLINE |
| WG-0058 | nougen-handoffs | elevate | Make CodeQL and GitGuardian findings gate NouGenShards merges instead of PR-comment-only flags |
| WG-0059 | fleet | defend | Consolidate the four diverged keymaker stores into one NOUGEN_SECRETS_VAULT_DIR per node |
| WG-0060 | NouGenRelay | elevate | Make the relay watchdog task headless and QuickEdit-proof after today's blade console freeze |
| WG-0061 | NouGenMsg | elevate | Build `nougenmsg doctor` that compares each node's executing build id to the repo (SOURCE.md is already wrong) |
| WG-0062 | NouGenShards | defend | Restore the relay ASK/REPORT classifier after the fleet-ops script split moved it out of tree |
| WG-0063 | Visions-ai | defend | Pin one Python across blade, phoebus, whoart and the container: 3.14 bytecode is already committed |
| WG-0064 | Kaedra | defend | Turn kaedra_hi_probe's hardcoded roster and LAN IPs into a fleet-owned config |
| WG-0065 | Rhea-Noir | defend | Deployed server silently runs in limited mode: sync_engine imports a missing env_loader module |
| WG-0066 | Dav1d | defend | Populate .handoffs so the fleet hooks stop failing open on this repo |
| WG-0067 | Yuki-Ai | defend | Pick one Gemini price table across cost tracker, models spec, PRICING alert and changelog |
| WG-0068 | Ai-with-Dav3--Alpha- | defend | Rotate the Cloudinary API secret committed in CLOUDINARY_SETUP.md and NETLIFY_DEPLOY.md |
| WG-0069 | nougen-handoffs | defend | Verify _harden_path ACL hardening now actually applies to vault keys on Windows nodes |
| WG-0070 | fleet | defend | Share the private-vault data key across replicas so /sync/push can unwrap ngenc1 bodies |
| WG-0071 | NouGenRelay | elevate | Route dispatch send_wake through file-backed stdout so Windows ssh stops timing out at 90s |
| WG-0072 | NouGenMsg | defend | Add request timeouts and connection limits to the ThreadingHTTPServer receiver |
| WG-0073 | NouGenShards | defend | Survive an Ollama outage on the embed lane without silently regrowing NULL embeddings |
| WG-0074 | Visions-ai | defend | Rotate the committed AI Studio key and purge it from code, tests and docs/logs history |
| WG-0075 | Kaedra | defend | Prove the fail-open relay claim hooks actually run on each fleet clone |
| WG-0076 | Rhea-Noir | defend | Snapshot before the seven archive scripts set archived:true on live canon pages |
| WG-0077 | Dav1d | defend | Audit every 'COMPLETE' doc against the code it claims to describe |
| WG-0078 | Yuki-Ai | defend | Scrub committed facial biometrics of a real person and set a retention policy |
| WG-0079 | Ai-with-Dav3--Alpha- | defend | Add .env.example and a secret-scanning pre-commit so the next agent lane cannot re-commit credentials |
| WG-0080 | nougen-handoffs | elevate | Write the sweep's authority scope: what an unattended session may merge, close, release or file |
| WG-0081 | fleet | defend | Stop blade from missing the 20s recall deadline on gateway fanout |
| WG-0082 | NouGenRelay | defend | Close the remaining fleet-answer false-completion path after leg 20260831T195956Z |
| WG-0083 | NouGenMsg | defend | Fence the Windows pipe timeout so a mid-turn session is retried, never pruned, on every lane |
| WG-0084 | NouGenShards | defend | Stop the fleet Worker's SHARD_GATEWAY_TOKEN drift from reading green for hours |
| WG-0085 | Visions-ai | defend | Refresh docs/CREDITS_AND_COSTS.md before it drives a real spend decision |
| WG-0086 | Kaedra | defend | Fix /health so it stops saying ok while background_init has failed since January |
| WG-0087 | Rhea-Noir | defend | Rotate and purge the live Notion tokens in Scripts/corrected_migration.py and the key in test_extract.py |
| WG-0088 | Dav1d | elevate | Back the advertised fleet contract: rag-retrieval and agent-orchestration are stubs behind the agent card |
| WG-0089 | Yuki-Ai | defend | Retire the crossplay safety-bypass experiment and product-decide same-gender only |
| WG-0090 | Ai-with-Dav3--Alpha- | defend | Purge the Google AI Studio key, Who Visions legal-entity file and 196 MiB venv from git history |
| WG-0091 | nougen-handoffs | defend | Land NouGenRelay#65 so Dav1d-planned probes with <PLACEHOLDER> argv never reach subprocess.run |
| WG-0092 | fleet | elevate | Wire reach_matrix and 3-layer telemetry into NouGen Live so gateway green stops masking federation red |
| WG-0093 | NouGenRelay | elevate | Schedule fleet_heartbeat on one node with tunnel-1033 detection and alert delivery |
| WG-0094 | NouGenMsg | defend | Stop --peers flashing consoles and stalling on AAAA: keep #5 and #6 from being undone by lane merges |
| WG-0095 | NouGenShards | defend | Publish relay handoff records without a `git add -A` leaking spend figures |
| WG-0096 | Visions-ai | elevate | Wire usage_tracker.py's cost accounting into the production API path, not just the CLIs |
| WG-0097 | Kaedra | elevate | Add a deploy-freshness watchdog for the public kaedra Cloud Run service |
| WG-0098 | Rhea-Noir | defend | Survive the death of the one Windows box rhea_bridge_server.py depends on |
| WG-0099 | Dav1d | elevate | Arm the relay hooks in Dav1d: populate .handoffs, set core.hooksPath on every lane, prove a refused commit |
| WG-0100 | Yuki-Ai | defend | Make the A2A card discoverable at one canonical path with a truthful service URL |
| WG-0101 | nougen-handoffs | defend | Audit .mcp.json fleet-wide for dead remote servers and empty env-substituted keys |
| WG-0102 | fleet | defend | Reconcile 49 on-disk 'active' claim JSONs against a connector that reports zero |
| WG-0103 | NouGenRelay | elevate | Wire probe_field_parity into a scheduled check so a hostname answered by the wrong node is caught |
| WG-0104 | NouGenMsg | defend | Survive concurrent cc_sessions.json rewrites without pruning a live Claude session |
| WG-0105 | NouGenShards | defend | Survive Kaedra cold-load timeouts without pinning VRAM forever |
| WG-0106 | Visions-ai | defend | Stop AGENTS.md from sending every agent lane to run live-billing tests |
| WG-0107 | Kaedra | defend | Public A2A card advertises real code-execution while the endpoint only simulates output |
| WG-0108 | Rhea-Noir | defend | Retire or restore the Moltbook public agent lane that half-exists in code and doctrine |
| WG-0109 | Dav1d | defend | Answer self-merge authority for Dav1d: master vs main, single WhoVisions author, claude/* branches |
| WG-0110 | Yuki-Ai | defend | Decide license and repo visibility before the A2A card keeps advertising github.com/Who-Visions/Yuki-Ai |
| WG-0111 | nougen-handoffs | defend | Verify self-reported test claims from substrate before the registry records them as truth |
| WG-0112 | fleet | elevate | Consolidate blade :4444 to one code tree and retire the Watchtower 'NouGen NGS Node' task |
| WG-0113 | NouGenRelay | defend | Fix relay_pusher_90m's all-or-nothing 'operational' verdict while whoart-vault is intermittent |
| WG-0114 | NouGenMsg | defend | Reconcile the nested and flat cc_sessions.json shapes before main's ping_claude reaches phoebus |
| WG-0115 | NouGenShards | defend | Keep the nougenmsg receiver auth-latched through a Keymaker miss |
| WG-0116 | Visions-ai | defend | Rotate the committed AI Studio key and stop Config.validate() from re-requiring one |
| WG-0117 | Kaedra | defend | Unauthenticated agent card leaks internal brand voice 'AAVE, tactical, uncensored' to the public |
| WG-0118 | Rhea-Noir | defend | Resolve the licensing exposure of proxy-rotated YouTube transcript ingestion and committed captions |
| WG-0119 | nougen-handoffs | defend | Rotate the 8 live Google API keys in vault\nougen_memories.db one lane at a time |
| WG-0120 | fleet | elevate | Answer self-merge authority and drain the 35-deep nougen-handoffs sweep backlog with an automated gate |
| WG-0121 | NouGenRelay | elevate | Version the nougenmsg receipt contract so a stale copy cannot fake or lose delivery |
| WG-0122 | NouGenMsg | defend | Stop the 20s ssh timeout from killing delivered fan-outs and prompting duplicate resends |
| WG-0123 | NouGenShards | elevate | Consolidate the Keymaker to one canonical store and retire Watchtower/agent_secrets.db strays |
| WG-0124 | Visions-ai | defend | Move sentinel_loop.py's heartbeat writes off the production interaction_logs table |
| WG-0125 | Kaedra | defend | Two live-looking Notion integration tokens remain committed despite a changelog entry claiming removal |
| WG-0126 | Rhea-Noir | defend | Set policy for the 29 offensive-security skill packs living in a creative-lore repo |
| WG-0127 | nougen-handoffs | elevate | Decide the registry write path and clear the 35-deep draft backlog in one pass |
| WG-0128 | fleet | elevate | Restore NouGenRelay Actions runner allocation and pin actions by SHA before merging #65/#67/#68 |
| WG-0129 | NouGenRelay | defend | Pin the interpreter every hook and scheduled task uses on each Windows box |
| WG-0130 | NouGenMsg | defend | Make background fleet fan-out failures visible after the 76s double-delivery |
| WG-0131 | NouGenShards | elevate | Grow past the 9 x 2GB grid ceiling for the million-shard destiny without re-routing dedup |
| WG-0132 | Visions-ai | elevate | Add a test step to cloudbuild.yaml before it deploys straight to public Cloud Run |
| WG-0133 | Kaedra | defend | Six submodule gitlinks have no .gitmodules, so a fresh clone gets empty directories |
| WG-0134 | Rhea-Noir | defend | Recover the Cosplay Remix Engine and Lightroom work that exists only on a machine, not in git |
| WG-0135 | nougen-handoffs | elevate | Add an open-PR and claims preflight to the sweep so parallel runs consolidate instead of piling up |
| WG-0136 | fleet | defend | Gate deploys on drift_check and which_tree so no node runs code from no git ref |
| WG-0137 | NouGenRelay | elevate | Rotate blade's LAN node token whose fingerprint matches nothing in any vault |
| WG-0138 | NouGenMsg | defend | Collapse the four-copies-per-Antigravity-ping fan-out with one message_id at the emitter |
| WG-0139 | NouGenShards | elevate | Add admission control to the node so fan-out bursts degrade gracefully instead of parking 327 threads |
| WG-0140 | Visions-ai | elevate | Enable .githooks/prepare-commit-msg by default so fresh clones don't commit unstamped |
| WG-0141 | Kaedra | defend | PolicyEngine's cost/risk scoring is never called from any FastAPI route |
| WG-0142 | Rhea-Noir | defend | Reconcile the 2158-vs-2174 blade acquisition contradiction between two LOCKED canon docs |
| WG-0143 | nougen-handoffs | defend | Survive a dependabot burst that opens six PRs and six sweep sessions in the same minute |
| WG-0144 | fleet | elevate | Converge the three nougenmsg variants (195/311/496 lines) into one shipped bus module |
| WG-0145 | NouGenRelay | defend | Reconcile NOUGEN_USER_ORIGIN_TOKEN across phoebus and blade so the owner path works |
| WG-0146 | NouGenMsg | defend | Bring whoart's untracked Outpost\NouGen bus copy under version control before the next hand-copy diverges |
| WG-0147 | NouGenShards | defend | Make /health stop lying: degraded DBs, persistent_storage false and slow recall must change the answer |
| WG-0148 | Visions-ai | defend | Fix the dormant "unrecognized machine" guard that only activates after the first handoff leg |
| WG-0149 | Kaedra | defend | No CI test/lint gate exists anywhere despite CHANGELOG claiming Cloud Build replaced GitHub Actions 'for CI/CD' |
| WG-0150 | Rhea-Noir | elevate | Designate the canon system of record among Notion, veillore.db, 686 md files and NouGenShards |
| WG-0151 | nougen-handoffs | elevate | Close the webhook coverage gap: PRs opened while a sweep is mid-run are never swept |
| WG-0152 | fleet | defend | Remove PT72H ExecutionTimeLimit and 0-restart settings from admin-owned node and tunnel tasks |
| WG-0153 | NouGenRelay | defend | Reconcile gateway-only legs that 404 on the git registry (connector split-brain) |
| WG-0154 | NouGenMsg | elevate | B7-observability: Ship `nougenmsg doctor` comparing each node's running build_id to the repo |
| WG-0155 | NouGenShards | elevate | Publish the wargames/ corpus that HARDENING, CI and coach_governor cite but the tree lacks |
| WG-0156 | Visions-ai | defend | Stop pooling anonymous callers into the shared "user"/"default_user" memory bucket |
| WG-0157 | Kaedra | defend | prepare-commit-msg's own header documents that rebases reattribute commits to the wrong machine/lane |
| WG-0158 | Rhea-Noir | elevate | Decide archive-vs-revive and merge authority for a repo idle since 2026-04-30 |
| WG-0159 | nougen-handoffs | defend | Fix NouGenRelay's Actions runner allocation (runner_id: 0) so #65/#67/#68 can be validated at all |
| WG-0160 | fleet | defend | Survive the local Ollama lane going dark while the tray process still runs |
| WG-0161 | NouGenRelay | defend | Expire the 49 'active' claims and daemon leases that outlived their TTL in the tracked registry |
| WG-0162 | NouGenMsg | defend | Alert when a :8766 receiver's auth mode drifts from required to open |
| WG-0163 | NouGenShards | defend | Protect main against another disjoint-history force-push |
| WG-0164 | Visions-ai | elevate | Confirm visions/core/router.py's audit() actually runs somewhere before the next model-id sweep |
| WG-0165 | Kaedra | defend | 720 Atomic Buster's mandatory relay leg authenticates with a hardcoded placeholder token by default |
| WG-0166 | Rhea-Noir | defend | Retire the local planning-with-files ledger that diverges from relay handoffs |
| WG-0167 | nougen-handoffs | elevate | Roll out the /health write-path probe (NGS_HEALTH_WRITE_PROBE_S) so a wedged vault no longer hangs health |
| WG-0168 | fleet | elevate | Roll task_truth.ps1 to blade and phoebus and alarm on tasks with no NextRunTime |
| WG-0169 | NouGenRelay | defend | Quarantine the two unparseable .handoffs records and gate every registry writer on json.loads |
| WG-0170 | NouGenMsg | elevate | B9-devex: Converge the three phoebus install paths and the whoart 72h task limit into one supervised service per node |
| WG-0171 | NouGenShards | defend | Converge relay_triage rules with NouGenRelay's e2b ASK/REPORT verdicts into one recorded decision |
| WG-0172 | Visions-ai | defend | Correct A2A_IMPLEMENTATION.md's "Optional" bearer auth to "none, ever" |
| WG-0173 | Kaedra | elevate | Broad Google Workspace OAuth scopes are requested but never wired into any API route or tool registry |
| WG-0174 | Rhea-Noir | defend | Converge or kill the second production Rhea deployed to Agent Engine by deploy_cloudshell.sh |
| WG-0175 | nougen-handoffs | elevate | Move vault\RECOVERY_KEY.txt offline and confirm private_vault status still resolves |
| WG-0176 | fleet | elevate | Schedule the weekly embedding backfill sweep on every node under the VRAM gate |
| WG-0177 | NouGenRelay | defend | Reap the 49 blade1tb relay-daemon claims stuck 'active' for 120-618 hours |
| WG-0178 | NouGenMsg | defend | Capture what phoebus actually executes: infra/phoebus holds federation.py, not the bus |
| WG-0179 | NouGenShards | defend | Wire relay_triage into relay_watch announce() without silencing NEEDS_OWNER legs |
| WG-0180 | Visions-ai | defend | Reconcile root app.py's real surface with the A2A/Bandit docs that describe visions/api/app.py |
| WG-0181 | nougen-handoffs | defend | Track and stop the recurring db1 quarantine (4 hits in two days) instead of 'tracked separately' |
| WG-0182 | fleet | defend | Make a console-launched node impossible: enforce hidden launch and NO_COLOR for ngs_node_serve |
| WG-0183 | NouGenRelay | defend | Neutralize the root retire_*/ack_* sweep scripts before a re-run re-acks live legs |
| WG-0184 | NouGenMsg | elevate | B3-routing: Upgrade _probe_nodes from TCP-connect to an authenticated /health round-trip so a hung node reads unreachab… |
| WG-0185 | NouGenShards | defend | Make the claim guard's fail-open observable so duplicated work stops being a surprise |
| WG-0186 | nougen-handoffs | defend | Keep relay_live.py from stalling forever on SSH (NOUGEN_RELAY_LIVE_SSH_CONNECT_S) when a node's tunnel dies |
| WG-0187 | fleet | defend | Survive the next runaway fan-out: one ledger and one kill switch across four spend trackers |
| WG-0188 | NouGenRelay | defend | Share one clone safely between the daemon's merge overlay and autoclose --autostash |
| WG-0189 | NouGenMsg | defend | Detect from the sender when a receiver silently drops from auth=required to auth=open |
| WG-0190 | NouGenShards | elevate | Wire the metered lanes into billing.log_usage before selling a Pro tier |
| WG-0191 | nougen-handoffs | defend | Merge the relay_watch_node.py rewrites without regressing the 9h36m relay-blindness fix |
| WG-0192 | fleet | defend | Keep recall complete:true when the cold path exceeds NOUGEN_RECALL_DEADLINE_S |
| WG-0193 | NouGenRelay | defend | Retire the 227 in_progress legs nobody is executing and give in_progress a TTL |
| WG-0194 | NouGenMsg | defend | Pin which of blade's two code trees the remote CLI and scheduled task actually run |
| WG-0195 | NouGenShards | defend | Stop the Space cold boot from blocking 95-250s on api.gradio.app analytics |
| WG-0196 | nougen-handoffs | defend | Bring nougenai.com back from 502 without touching the shards.nougenai.com gateway route |
| WG-0197 | fleet | defend | Decouple the write signature from the read cache before continuous capture at scale |
| WG-0198 | NouGenRelay | defend | Harden fleet_respond so a generated answer can never close a defect or ask leg again |
| WG-0199 | NouGenMsg | defend | Bring whoart's untracked live bus files under git without stopping the running node |
| WG-0200 | NouGenShards | elevate | Wire lane_freshness --json into `nougen hi` so stale ingestion lanes are seen at session start |
| WG-0201 | nougen-handoffs | defend | Keep the 07:00 NouGenTube drip inside YouTube rate limits after the 7/24 IP block and the GM ban warning |
| WG-0202 | fleet | defend | Resurrect the fleet usage ledger writer so free-lane volume is measurable again |
| WG-0203 | NouGenRelay | defend | Keep the pre-commit guard under 10s while claims/ holds 1,259 records (384 took over two minutes) |
| WG-0204 | NouGenMsg | defend | Collapse phoebus's three documented install paths into one interpreter-safe receiver |
| WG-0205 | NouGenShards | elevate | Schedule the weekly embedding backfill on all three nodes with its own freshness sensor |
| WG-0206 | nougen-handoffs | defend | Stop unrelated PRs from rewriting tools/zombie_killer.py into a SIGKILL-by-default supervisor |
| WG-0207 | fleet | defend | Retire the relay-embedded usage dailies without losing June-July history |
| WG-0208 | NouGenRelay | defend | Shrink the 130MB of FLEET-LOG markdown every node clones and every ack pushes past |
| WG-0209 | NouGenMsg | defend | Add a sender/receiver contract test before trusting the green injection suite |
| WG-0210 | NouGenShards | defend | Mark or remove the unapproved continuous-sync draft so no lane implements against the Dave lock |
| WG-0211 | nougen-handoffs | defend | Survive a free-lane auth outage (Codex 402 / Gemini API_KEY_INVALID) without a lane dying silently |
| WG-0212 | fleet | defend | Introduce a new box (cloud CCR, rebuilt phoebus) to the registry without unknown-agent stamps or replay re-attribution |
| WG-0213 | NouGenRelay | defend | Align the heartbeat and pusher probe sets so a dead whoart tunnel is noticed |
| WG-0214 | NouGenMsg | defend | Lock the cc_sessions.json rewrite so concurrent fan-outs cannot drop a live Claude session |
| WG-0215 | NouGenShards | defend | Enforce the coach fan-out cap in code for Claude-side workflows, not only fleet lanes |
| WG-0216 | nougen-handoffs | defend | Restore or retire the chatgpt-codex-connector review lane that posts 'usage limits reached' on every PR |
| WG-0217 | fleet | defend | Turn on nougen.requireClaim fleet-wide without teaching lanes to reach for --no-verify |
| WG-0218 | NouGenRelay | defend | Reconcile the registry status vocabulary: DONE(621), closed(116), 47 statusless, ACTIVE, synchronized |
| WG-0219 | NouGenMsg | defend | Emit the DELIVERED/QUEUED receipt line relay dispatch keys on from main's CLI |
| WG-0220 | NouGenShards | defend | Gate tracker-dailies publication on a mechanical privacy check, not inspection |
| WG-0221 | nougen-handoffs | defend | Verify cross-repo merge-order preconditions (ShadowDweller#4 before NouGenShards #491) from a scoped session |
| WG-0222 | fleet | elevate | Adopt the relay registry and claim-guard hooks in the 9 repos that lack them, with a CI drift check |
| WG-0223 | NouGenRelay | elevate | Run a one-shot registry normalization migration (status, created_utc, id) through CAS writes |
| WG-0224 | NouGenMsg | elevate | Make ping_antigravity able to say delivered: fix the relative import and land the tri-state |
| WG-0225 | NouGenShards | defend | Collapse the two handoff namespaces before one `git add -A` publishes spend and incident notes |
| WG-0226 | nougen-handoffs | defend | Split or reject 156-file mega PRs that bundle unrelated projects (MRSB, affect/persona) into NouGenShards |
| WG-0227 | fleet | defend | Recover from a wedged registry checkout (pull --rebase left .git/rebase-merge for four hours) |
| WG-0228 | NouGenRelay | elevate | Roll out the --text-b64 nougenmsg protocol to every divergent copy without splitting the fleet |
| WG-0229 | NouGenMsg | elevate | Reconcile PR #2's cc_msg.py against main instead of the 1331234 baseline |
| WG-0230 | NouGenShards | defend | Stop the sync/push cascade regression from shipping a third time |
| WG-0231 | nougen-handoffs | defend | Block stale-base PRs that silently revert merged production fixes (#434, #397 at 35 commits behind) |
| WG-0232 | fleet | defend | Contain a hanging or hostile rule/trigger on Windows where NOUGEN_RULES_TIMEOUT cannot kill the grandchild |
| WG-0233 | NouGenRelay | defend | Survive a console-launched daemon freezing the relay clone on blade |
| WG-0234 | NouGenMsg | elevate | Publish one env-var reference and a config doctor for the five competing namespaces |
| WG-0235 | NouGenShards | elevate | Retire the Space latency band-aid by finding the 3-day recall degradation |
| WG-0236 | nougen-handoffs | elevate | Sweep expired claims (ttl_hours) across nougen-handoffs, NouGenQ and NouGenRelay automatically |
| WG-0237 | fleet | defend | Detect a dead relay watch on any node the day it dies, not nine days later |
| WG-0238 | NouGenRelay | defend | Fix concurrent autoclose and policy sweeps from several machines conflicting every minute |
| WG-0239 | NouGenMsg | elevate | Add a scheduled cross-node synthetic ping that alerts when /health hangs rather than refuses |
| WG-0240 | NouGenShards | elevate | Publish the phoebus GATEWAY role: own tokens, tracker dailies, and a failover decision |
| WG-0241 | nougen-handoffs | defend | Win the live claim race: three lanes claimed the same Xoah slice within 44s and ignored the stand-down |
| WG-0242 | fleet | elevate | Roll task_truth.ps1 to blade and phoebus and clear PT72H/0-restart admin tasks in one Dave-supervised window |
| WG-0243 | NouGenRelay | defend | Relay-shaped files committed outside .handoffs/ are invisible to every relay verb |
| WG-0244 | NouGenMsg | elevate | Detect a quiet bus lane the way the vault-quiet incident demanded |
| WG-0245 | nougen-handoffs | elevate | Ship a schema and validator for queue/task_*.md and handoff_*.json across three naming eras |
| WG-0246 | fleet | defend | Consolidate blade :4444 to one code tree and retire the competing Watchtower scheduled task |
| WG-0247 | NouGenRelay | defend | quota_governor's RESERVE_HOLD blocks every leg, including the GM sessions it claims to protect |
| WG-0248 | NouGenMsg | defend | Stop timeout-after-delivery retries from double-sending fleet broadcasts |
| WG-0249 | nougen-handoffs | defend | Finish or kill the Open Engine task queue: gemini/codex tasks unclaimed since 2026-07-06 |
| WG-0250 | fleet | defend | Resolve an autonomous canon leg that contradicts a GM lock (Artemis Patera vs lock 30385@db2) without waiting on Dave |
| WG-0251 | NouGenRelay | defend | fleet-ops/tests (21 tests) never run in CI because ci.yml scopes to tests/ only |
| WG-0252 | nougen-handoffs | elevate | Run the held 47.8%-drift vault reindex (148k files, write mode) before brain-scan Move 4 |
| WG-0253 | fleet | defend | Supersede withdrawn rulings that older shards still state as binding (purge rule withdrawn 9/7) |
| WG-0254 | NouGenRelay | defend | hooks/pre-commit fails open with no telemetry when relay itself errors |
| WG-0255 | nougen-handoffs | defend | Land the pull-clone working tree (GM WIP + 5 audit fixes + steal list) that is 37 commits behind origin/main |
| WG-0256 | fleet | elevate | Build a decision-aging escalation ladder for items unmoved for weeks (#455 28 sweeps, NouGenQ #1 56 days) |
| WG-0257 | NouGenRelay | defend | autoclose.py never closes an Ask naming Dave, with no fallback owner if he's unreachable |
| WG-0258 | nougen-handoffs | defend | Detect a lane that stops writing handoffs (codex silent since 2026-07-18) within a day, not two months |
| WG-0259 | fleet | elevate | Consolidate Dave asks into one daily EOD decision packet without dropping any lock-bound item |
| WG-0260 | NouGenRelay | defend | relay_dedup's degrade-to-token-overlap path still writes the leg it should have deduped |
| WG-0261 | nougen-handoffs | elevate | Run stored-key liveness probes fleet-wide without tripping secret scanners or spending credits |
| WG-0262 | fleet | defend | Survive and pre-empt a history-rewriting force-push on shared main (2026-09-05 closed ~20 PRs) |
| WG-0263 | NouGenRelay | defend | relay_daemon.py's keymaker secret fallback only resolves on one Windows account |
| WG-0264 | nougen-handoffs | defend | Restore a quarantined db1 on the HF Space /data bucket mount after a WAL-on-network failure |
| WG-0265 | fleet | defend | Rotate NGS_TOKEN and NGS_NODE_TOKEN leaked via PR #397 across three nodes and the worker in one window |
| WG-0266 | NouGenRelay | defend | NOUGEN_AGENT env override reproduces the exact unknown-agent incident README warns about |
| WG-0267 | nougen-handoffs | defend | Make every read-only tool open the live vault read-only (relay_push malformed-image crashes) |
| WG-0268 | fleet | defend | Gate public canon/wiki publication on an owner-handle privacy scrub before the Redline sync lands |
| WG-0269 | NouGenRelay | defend | QuotaAlertStore's provenance-distinct dedup key can double-alert Dave for one real breach |
| WG-0270 | nougen-handoffs | defend | Prove capture truth from substrate after the write-path fix was dropped by a squash merge |
| WG-0271 | fleet | defend | Verify and revoke an agent capability grant that lives only in a relay leg (Kaedra 'ALL tools' authorization) |
| WG-0272 | NouGenRelay | elevate | Scheduled quota telemetry collection remains manual, leaving burn spikes invisible between runs |
| WG-0273 | nougen-handoffs | defend | Merge relay_watch_node singleton lock and blind-alert without reinstating either incident |
| WG-0274 | fleet | defend | Refuse 'ultracode is on' style reminders that are not Dave's instruction before another 2.1M-token workflow |
| WG-0275 | NouGenRelay | defend | nougenmsg's Windows SSH pipe-trap is indistinguishable from a genuine 90s dispatch timeout |
| WG-0276 | nougen-handoffs | defend | Prove HLC merge survives real clock skew between blade, phoebus and whoart |
| WG-0277 | fleet | defend | Stop estimated quota from enforcing stops and unknown quota from reporting green across Codex/Fable lanes |
| WG-0278 | NouGenRelay | defend | fleet_heartbeat.py can't tell a Cloudflare Access failure from a real service outage |
| WG-0279 | nougen-handoffs | defend | Recover 196 stranded quota-wake tickets and pin writer/reader path resolution per node |
| WG-0280 | fleet | defend | Merge NouGenRelay #65/#67/#68 while CI cannot allocate a runner (runner_id:0 billing) without lowering the bar |
| WG-0281 | NouGenRelay | defend | Two malformed .handoffs records exist with no CI JSON-lint gate on the registry |
| WG-0282 | nougen-handoffs | defend | Alert when a node writes handoffs locally but never pushes (93 files behind, remote casing) |
| WG-0283 | fleet | elevate | Route sweep review findings (e.g. #507 duplicate GET /shards/{id}) to the author lane via dispatch instead of a queue f… |
| WG-0284 | nougen-handoffs | defend | Detect deployed-code vs main divergence after a squash merge drops a fix |
| WG-0285 | fleet | elevate | Wire pr_lease 'one objective, one PR' into the nougen-loop pr stage to stop duplicate PRs (#476/#477, #503/#455) |
| WG-0286 | nougen-handoffs | defend | Force MCP server reload when vault path or module code changes under a long-lived process |
| WG-0287 | fleet | elevate | Separate NouGenMsg chat traffic ([NouGenMsg -> @phoebus]) from relay batons so the open board holds only work |
| WG-0288 | nougen-handoffs | defend | Guard issue bookkeeping against GitHub's negation-blind closing-keyword parser |
| WG-0289 | fleet | elevate | Recover the wargames/ directory 40+ docs cite and add a CI check that every referenced war game exists |
| WG-0290 | nougen-handoffs | defend | Keep whoart pinned to gemma4:e2b-qat when a fleet-wide default-model swap lands first |
| WG-0291 | fleet | defend | Require independent-method verification before any escalation packet reaches Dave |
| WG-0292 | nougen-handoffs | defend | Sanitize leg_id before relay_claim_leg/relay_ack_leg write into the claims directory |
| WG-0293 | fleet | defend | Move ASK/REPORT classification to 3-vendor consensus without freezing the board on a HOLD sidecar |
| WG-0294 | nougen-handoffs | defend | Make lane_freshness watch DB imports, not just files (arxiv DB lane silent 17 days) |
| WG-0295 | fleet | defend | Retire transport-by-file fleet logs and purge the 46MB verbatim vault dump from NouGenRelay |
| WG-0296 | nougen-handoffs | defend | Make a lane outage distinguishable from a quiet weekend (feed error exit 0 killed arxiv twice) |
| WG-0297 | fleet | defend | Enforce the lore-isolation invariant against fleet logs carrying Shadow Dweller manuscript prose |
| WG-0298 | nougen-handoffs | defend | Set per-lane freshness thresholds so frozen codex/gemini dirs and a 93h handoff gap alarm |
| WG-0299 | fleet | elevate | Unify Watchtower/Outpost tree naming behind NOUGEN_WORKSPACE_ROOT across skills, tools and RELAYS.md |
| WG-0300 | nougen-handoffs | defend | Build an escalation channel that actually reaches a lane (three Open Engine tasks idle 80 days) |
| WG-0301 | fleet | elevate | Normalize licensing across the fleet (source-available vs MIT vs ISC vs none) |
| WG-0302 | nougen-handoffs | defend | Detect CI that lies (lint red since ruff 0.16 made pytest report skipped for weeks) |
| WG-0303 | fleet | elevate | Replace hardcoded fleet tables in fleet_ping.py and fleet_dashboard.py with discovery |
| WG-0304 | nougen-handoffs | defend | Distinguish runner-never-allocated CI red from code red when job logs return 404 |
| WG-0305 | fleet | defend | Propagate the claim-guard hooks to the nine repos without them and add a drift check |
| WG-0306 | nougen-handoffs | elevate | Instrument the Gemini/Antigravity lane before reporting delegation share again |
| WG-0307 | fleet | elevate | Reconcile Xoah canon locks (March 15, 2162) against 37 October-13 and age 20-27 variants |
| WG-0308 | nougen-handoffs | defend | Probe Ollama by port not process so a dark 11434 is never read as 'local models unavailable' |
| WG-0309 | fleet | defend | Purge committed SQLite state from persona repos (Dav1d sessions, Yuki knowledge, unk lore) |
| WG-0310 | nougen-handoffs | defend | Survive a blade power loss mid-write across the vault and the registry |
| WG-0311 | fleet | elevate | Integrate the nougenmsg branch clone: three divergent copies of nougenmsg.py |
| WG-0312 | nougen-handoffs | elevate | Purge quoted NGS tokens from `handoffs` history while three machines hold clones |
| WG-0313 | fleet | defend | Scrub the public Kaedra repo of GCP inventory, LAN IPs, Notion topology and transcript dumps |
| WG-0314 | nougen-handoffs | defend | Make /api/health the single source of truth for NouGenQ key presence (cached page lied) |
| WG-0315 | nougen-handoffs | defend | Coalesce webhook bursts so six PRs in 65 minutes do not spawn six sweep sessions |
| WG-0316 | nougen-handoffs | elevate | Unify the four repos' .handoffs registries so a sweep can see claims in every leg |
| WG-0317 | nougen-handoffs | elevate | Add a sensitivity field to handoffs so insurance claims and personal photos stop hitting a public branch |
| WG-0318 | nougen-handoffs | defend | Fuzz the Windows shell layer of handoff writes (cmd.exe newline cut, $3 expansion) |
| WG-0319 | nougen-handoffs | defend | Separate the keymaker credential vault path from NOUGEN_VAULT_DIR so secrets never land in the shard dir |
| WG-0320 | nougen-handoffs | defend | Verify vault key ACL hardening actually applied (icacls explicit ACEs, swallowed _harden_path ImportError) |
| WG-0321 | nougen-handoffs | elevate | Make node launchers path-agnostic across blade, phoebus and whoart (two tasks, two code trees) |
| WG-0322 | nougen-handoffs | defend | Restore the mesh write lane across reboots without leaving SOL_MESH_TOKEN unset (503 fail-closed) |
| WG-0323 | nougen-handoffs | elevate | Answer the self-merge question and drain the 35-PR sweep-record backlog in one pass |
| WG-0324 | nougen-handoffs | elevate | Add claim TTL expiry across nougen-handoffs, NouGenQ and NouGenRelay after a 65h-overdue claim was found by hand |
| WG-0325 | nougen-handoffs | defend | Enforce claim stand-down: #476/#477 shipped API-incompatible duplicates after a live claim race told one lane to stop |
| WG-0326 | nougen-handoffs | defend | Verify every 'tracked separately' cross-reference resolves to a real issue or claim |
| WG-0327 | nougen-handoffs | defend | Prove fixes from substrate, not narrative: relay chain cited commit f05b550 that exists in no repo |
| WG-0328 | nougen-handoffs | elevate | Turn sweep findings into a merge gate after CodeQL secret logging (#342) and path traversal (#350) shipped |
| WG-0329 | nougen-handoffs | defend | Verify the ShadowDweller#4 precondition before #491 deletes the combat engine from NouGenShards |
| WG-0330 | nougen-handoffs | defend | Detect stale-base PRs that silently revert fixed bugs (#434 reverted the WhoArt quarantine fix) |
| WG-0331 | nougen-handoffs | defend | Block mega-PRs that bundle third-party EPUBs and unrelated projects (#435, 156 files, learn-with-mrs-b) |
| WG-0332 | nougen-handoffs | defend | Stop scope-creep bundles like #423's SIGKILL-by-default OS-wide zombie nuke riding a CLI subcommand PR |
| WG-0333 | nougen-handoffs | defend | Rotate and redact the two NGS bearer tokens quoted verbatim in queue records, then rewrite shared history |
| WG-0334 | nougen-handoffs | elevate | Close the 8-live-Google-key rotation and RECOVERY_KEY.txt moves the 08-07 handoff left awaiting GM |
| WG-0335 | nougen-handoffs | elevate | Port NouGenShards' published-surface guard to the registry: 28 C:\Users\super paths and 9 LAN IPs live here |
| WG-0336 | nougen-handoffs | defend | Remove off-domain personal data from fleet memory: house renovation ledger, insurance claims, selfie descriptions |
| WG-0337 | nougen-handoffs | elevate | Publish a JSON schema for handoff records: machine is a string in 48 files and an object in 18 |
| WG-0338 | nougen-handoffs | defend | Fix the queue filename split: three task_YYYYMMDDTHHMMSSZ_ files sort out of order against task_YYYYMMDD_HHMMSS_ |
| WG-0339 | nougen-handoffs | defend | Treat the Codex connector's 'usage limits reached' on every PR as a dead reviewer lane, not noise |
| WG-0340 | nougen-handoffs | defend | Fix the usage watchdog before it reports delegation share again: ccusage is blind to Gemini and misreads Codex |
| WG-0341 | nougen-handoffs | defend | Detect PRs that never triggered a sweep (#400/#401, #409, #468-#482 gap) before they merge unreviewed |
| WG-0342 | nougen-handoffs | defend | Break the single-box secret dependency: NouGenQ's OPENROUTER_API_KEY can only be set from blade1tb |
| WG-0343 | nougen-handoffs | defend | Build a flake registry so sweeps stop mis-classifying test_boot_quarantine_nonblocking and HLC drift as defects |
| WG-0344 | nougen-handoffs | defend | Stop carrying NouGenRelay CI red for 6+ sweeps: job logs 404 for the integration and #65 stayed undrawn |
| WG-0345 | nougen-handoffs | defend | Set a dependabot policy after zod v4, pydantic-core and tomlkit bumps each broke a build |
| WG-0346 | nougen-handoffs | defend | Require a test artifact behind every '290 passed' and '201/201 green' claim in a handoff |
| WG-0347 | nougen-handoffs | elevate | Roll the hardcoded-account-path guard out as a fleet pre-commit after four PRs tripped it in a week |
| WG-0348 | nougen-handoffs | defend | Write the sweep's authority envelope: it marks PRs ready, merges siblings, opens issues, releases NouGenQ claims |
| WG-0349 | nougen-handoffs | defend | Forbid sweeps from pushing to other lanes' PR branches after #514's lint fix landed mid-sweep |
| WG-0350 | nougen-handoffs | defend | Bring nougenai.com back from 502 before any public product surface points at it |
| WG-0351 | nougen-handoffs | defend | Keep canon names consistent across 600 records after EchoVault->Toujou and metameric->Valerion renames |
| WG-0352 | nougen-handoffs | elevate | Land NouGenQ #1 deploy preflight (54 days open) before the merged Q Live Prompt Loop reaches the public lane |
| WG-0353 | nougen-handoffs | elevate | Flip the Evolution Wing distill lane default only after restarting the stale nougen-shards MCP server |
| WG-0354 | nougen-handoffs | elevate | Run the HELD vault reindex (47.8% drift) before brain-scan Move 4 corrupts benchmark baselines |
| WG-0355 | nougen-handoffs | elevate | Pin the fleet .mcp.json: ollama-mcp's Node 25 patch lives in the npx cache and reverts on clear |
| WG-0356 | nougen-handoffs | defend | Close relay legs when their PR merges: leg 20260913T174622Z stayed in_progress after #341 landed |
| WG-0357 | nougen-handoffs | defend | Prevent writer/reader path splits like the 196 stranded quota-wake tickets from recurring in the registry |
| WG-0358 | nougen-handoffs | defend | Check claims against the live branch, not the checkout: sweeps reported 'no claims' while NouGenQ held a stale one |
| WG-0359 | nougen-handoffs | defend | Handle sweeps that exceed their trigger scope (#485 fixed NouGenRelay CI, #467 root-caused the daemon) |
| WG-0360 | nougen-handoffs | defend | Finish or kill the Open Engine task queue: three 2026-07-06 lane tasks unclaimed after three escalations |
| WG-0361 | nougen-handoffs | defend | Make the acknowledged_by field real or drop it: 415 of 449 handoff JSONs are still status open |

## Coverage of the #550 scenario families

663 of 1000 entries map to at least one of the 100 families in `families.json` (NouGenShards#550). 11 families have no catalog entry yet: 4, 5, 10, 14, 45, 47, 51, 55, 61, 80, 89.

| # | family | entries |
|---|---|---|
| 1 | Empty recall on healthy lane | 1 |
| 2 | Empty recall on degraded lane | 4 |
| 3 | Partial coverage mistaken for absence | 15 |
| 4 | FTS implicit AND starvation | 0 |
| 5 | Domain mask hides near exact match | 0 |
| 6 | Corrupt DB reports false empty | 8 |
| 7 | Vector cache stale signature | 5 |
| 8 | Duplicate capture idempotency | 13 |
| 9 | Shard amend after capture | 3 |
| 10 | Retract semantics | 0 |
| 11 | Forget semantics | 2 |
| 12 | Cross-node recall divergence | 24 |
| 13 | Clock skew across nodes | 6 |
| 14 | Future-dated shard | 0 |
| 15 | Out-of-order shard replay | 7 |
| 16 | Duplicate message delivery | 20 |
| 17 | Message replay after ack | 5 |
| 18 | Missing sender metadata | 5 |
| 19 | Forged sender text in message body | 5 |
| 20 | Unknown origin handling | 16 |
| 21 | Relay leg never acked | 17 |
| 22 | Relay leg acked twice | 6 |
| 23 | Relay completion without evidence | 24 |
| 24 | Relay stale claim | 5 |
| 25 | Two agents claim same task | 18 |
| 26 | Claim expires mid-task | 8 |
| 27 | Node disappears after claim | 4 |
| 28 | Node returns with stale state | 10 |
| 29 | Plugin registers twice | 14 |
| 30 | Plugin throws during startup | 4 |
| 31 | Plugin imports private code from public package | 1 |
| 32 | Plugin API contract drift | 17 |
| 33 | Plugin tool name collision | 1 |
| 34 | Plugin route collision | 9 |
| 35 | Local config missing | 14 |
| 36 | Local config malformed | 15 |
| 37 | Local config partially written | 5 |
| 38 | Local config stale | 31 |
| 39 | LAN IP changes | 6 |
| 40 | Hostname changes | 5 |
| 41 | DNS failure | 2 |
| 42 | Gateway returns 500 | 6 |
| 43 | Gateway times out | 10 |
| 44 | Gateway succeeds slowly | 1 |
| 45 | Gateway returns malformed JSON | 0 |
| 46 | Gateway returns valid empty payload | 2 |
| 47 | Circuit breaker opens | 0 |
| 48 | Circuit breaker never closes | 1 |
| 49 | Retry storm | 11 |
| 50 | Retry backoff jitter | 1 |
| 51 | Shared Ollama already running | 0 |
| 52 | Ollama cold start timeout | 4 |
| 53 | Ollama model missing | 4 |
| 54 | Ollama wrong model selected | 4 |
| 55 | Ollama partial response | 0 |
| 56 | Model unload during request | 2 |
| 57 | Cloud lane quota exhausted | 14 |
| 58 | Cloud lane rate limited | 3 |
| 59 | Free lane returns degraded output | 3 |
| 60 | Model router chooses expensive lane unnecessarily | 2 |
| 61 | Token lease denied | 0 |
| 62 | Token lease leaked | 7 |
| 63 | Token lease double-spend | 2 |
| 64 | Quota reset boundary | 2 |
| 65 | Cost accounting drift | 24 |
| 66 | Cache hit misreported | 1 |
| 67 | Cache miss misreported | 1 |
| 68 | Cache poisoning | 1 |
| 69 | Prompt injection in shard content | 11 |
| 70 | Secret-shaped literal in generated artifact | 15 |
| 71 | Path traversal in tool input | 7 |
| 72 | Symlink escape | 1 |
| 73 | Unsafe temp file reuse | 1 |
| 74 | Public repo leaks owner machine metadata | 13 |
| 75 | Public repo leaks canon/private lore | 23 |
| 76 | Public repo leaks credentials | 42 |
| 77 | Dependency update breaks API | 16 |
| 78 | Dependency update breaks tests only on one OS | 2 |
| 79 | Python minor version regression | 6 |
| 80 | Node version regression | 0 |
| 81 | CI skipped required test | 14 |
| 82 | CI green with test discovery failure | 11 |
| 83 | Flaky test masked by retry | 2 |
| 84 | Race in concurrent capture | 11 |
| 85 | Race in concurrent amend | 6 |
| 86 | SQLite locked | 3 |
| 87 | Disk full | 1 |
| 88 | DB file truncated | 3 |
| 89 | Read-only filesystem | 0 |
| 90 | Power loss during write | 3 |
| 91 | Restart during sync | 7 |
| 92 | Partial federation response | 1 |
| 93 | Slowest store dominates wall clock | 6 |
| 94 | One dead store blocks global answer | 8 |
| 95 | Health cache stale | 37 |
| 96 | Coverage metric stale | 4 |
| 97 | Index backfill interrupted | 9 |
| 98 | Rebuild produces non-deterministic output | 2 |
| 99 | Re-run changes answer without data change | 1 |
| 100 | War-game claims success without a receipt | 33 |
