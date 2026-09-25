# War-game candidates — Kaedra

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

71 candidates · P0 17 · P1 54 · P2 0 · P3 0 · defend 52 · elevate 19

| id | P | kind | title |
|---|---|---|---|
| WG-0007 | P0 | defend | Rotate and history-purge the two committed Notion integration tokens |
| WG-0023 | P0 | defend | Recover the Cloud Run agent from six never-committed modules that abort background_init |
| WG-0038 | P0 | defend | Survive a lane committing to Kaedra with hooks uninstalled or the relay import broken |
| WG-0052 | P0 | elevate | Re-home the Kaedra deploy pipeline onto the Whovisions Fleet project (kaedra-agent-api) |
| WG-0064 | P0 | defend | Turn kaedra_hi_probe's hardcoded roster and LAN IPs into a fleet-owned config |
| WG-0075 | P0 | defend | Prove the fail-open relay claim hooks actually run on each fleet clone |
| WG-0086 | P0 | defend | Fix /health so it stops saying ok while background_init has failed since January |
| WG-0097 | P0 | elevate | Add a deploy-freshness watchdog for the public kaedra Cloud Run service |
| WG-0107 | P0 | defend | Public A2A card advertises real code-execution while the endpoint only simulates output |
| WG-0117 | P0 | defend | Unauthenticated agent card leaks internal brand voice 'AAVE, tactical, uncensored' to the public |
| WG-0125 | P0 | defend | Two live-looking Notion integration tokens remain committed despite a changelog entry claiming removal |
| WG-0133 | P0 | defend | Six submodule gitlinks have no .gitmodules, so a fresh clone gets empty directories |
| WG-0141 | P0 | defend | PolicyEngine's cost/risk scoring is never called from any FastAPI route |
| WG-0149 | P0 | defend | No CI test/lint gate exists anywhere despite CHANGELOG claiming Cloud Build replaced GitHub Actions 'for CI/CD' |
| WG-0157 | P0 | defend | prepare-commit-msg's own header documents that rebases reattribute commits to the wrong machine/lane |
| WG-0165 | P0 | defend | 720 Atomic Buster's mandatory relay leg authenticates with a hardcoded placeholder token by default |
| WG-0173 | P0 | elevate | Broad Google Workspace OAuth scopes are requested but never wired into any API route or tool registry |
| WG-0369 | P1 | defend | Fix PolicyEngine prod detection so Universe DB writes stop scoring as internal |
| WG-0385 | P1 | defend | Reconcile the hi_probe fleet roster after the 09-11 rewrite silently reverted the 08-04 prune |
| WG-0401 | P1 | defend | Give kaedra a real readiness signal so /health stops lying to hi_probe and A2A peers |
| WG-0417 | P1 | defend | Replace the placeholder keymaker token and 0o777 socket in the nougenmsg client and daemon |
| WG-0433 | P1 | defend | Survive the wake daemon's 600s/1800s lifetime expiring mid-mission on a hidden scheduled task |
| WG-0449 | P1 | defend | Decide whether the committed .claude/settings.local.json is fleet policy or a permission leak |
| WG-0464 | P1 | defend | Restore or vendor the six orphan gitlinks so voice builds from a fresh clone |
| WG-0477 | P1 | defend | Survive the retirement of preview model IDs hardcoded in kaedra/core/config.py MODELS |
| WG-0490 | P1 | defend | Survive a hostile POST to /webhook/notion or /sync mutating the VeilVerse ingestion queue |
| WG-0502 | P1 | defend | Scope down the Google OAuth token and gate gmail_to_notion before inbox mail lands in Notion |
| WG-0514 | P1 | defend | Stop autosync_handoffs from mirroring GCP inventory and LAN topology into Notion |
| WG-0526 | P1 | defend | Survive the 4455 kaedra_gateway token leaking or its tunnel exposing Ollama unauthenticated |
| WG-0538 | P1 | defend | Survive the A2A card advertising write endpoints to peers and crawlers |
| WG-0550 | P1 | elevate | Move Kaedra secrets to Secret Manager/keymaker with a revocation drill |
| WG-0562 | P1 | elevate | Finish or delete the BigQuery memory tiers that were never created |
| WG-0574 | P1 | elevate | Cut every Notion client over to the 2025-09-03 data_source API before 2022-06-28 queries stop resolving |
| WG-0585 | P1 | elevate | Un-ignore kaedra_mobile/lib and ship the Flutter app pointed at the live gateway |
| WG-0596 | P1 | elevate | Stand up a pytest lane for Kaedra that survives pytest 9 and mocks live services |
| WG-0607 | P1 | elevate | Onboard Kaedra's lore ingestion into NouGenShards behind the capture-secret guard |
| WG-0618 | P1 | elevate | Move hi_probe off the hardcoded Mac path into a hidden scheduled job with a heartbeat shard |
| WG-0629 | P1 | elevate | Consolidate /webhook/notion and /hooks/notion into one signed handler that actually syncs |
| WG-0640 | P1 | defend | Purge committed session transcripts and call recordings and set a retention rule |
| WG-0651 | P1 | defend | Stop all public /v1/chat callers sharing one Vertex Memory Bank user 'kaedra-user-main' |
| WG-0662 | P1 | elevate | Build a clean Cloud Run image without losing runtime-read markdown and db files |
| WG-0673 | P1 | elevate | Wire KaedraOrchestrator into app state (state.orchestrator is never assigned) |
| WG-0684 | P1 | defend | Use stable idempotency keys for Square invoice create/send (uuid4 per call) |
| WG-0695 | P1 | defend | Give kaedra_wake_daemon seen-state, a single-instance lock and no 600s blind spot |
| WG-0706 | P1 | defend | Stop nougenmsg_enhanced_client dual-delivering via HTTP, socket and inbox fallbacks |
| WG-0717 | P1 | defend | Stop the socket pipe daemon from acking every payload as 'ok' without auth or framing |
| WG-0728 | P1 | defend | Re-fence the NouGenShards Kaedra tool loop, which is no longer read-only |
| WG-0738 | P1 | defend | Add a lock to kaedra_hi_probe's failsafe before it killall's Ollama mid-inference |
| WG-0748 | P1 | elevate | Restore or remove the phantom memory stack imports in background_init |
| WG-0758 | P1 | defend | Turn the committed failing smoke/validation logs into an enforced pre-deploy gate |
| WG-0768 | P1 | elevate | Retire the dead Vertex Reasoning Engine path with its two conflicting resource IDs |
| WG-0778 | P1 | elevate | Finish or retire the BigQuery memory tier whose tables were never created |
| WG-0788 | P1 | elevate | Track kaedra_mobile/lib and define offline-cache conflict rules against ephemeral sessions |
| WG-0798 | P1 | elevate | Run a fresh-clone restore drill: six gitlinks with no .gitmodules block voice and resources |
| WG-0808 | P1 | defend | kaedra_mobile/lib is swallowed by the root .gitignore, so the Flutter app source was never committed |
| WG-0818 | P1 | defend | Deploy target name drifts between cloudbuild.yaml's `kaedra` and the shell scripts' `kaedra-shadow-tactician` |
| WG-0828 | P1 | defend | AGENT_UPGRADE_NOTICE.md still cites a retired Reasoning Engine resource as current guidance |
| WG-0838 | P1 | defend | License metadata says MIT while README says Proprietary for the same repo |
| WG-0848 | P1 | defend | Personal call transcripts and session logs are committed inside a repo backing a public-facing product |
| WG-0858 | P1 | defend | /execute-code lets any unauthenticated caller spend Vertex tokens simulating arbitrary code |
| WG-0868 | P1 | defend | Keyword-only 'needs_deep_thinking' heuristic lets any public caller force expensive Pro+high-thinking routing |
| WG-0878 | P1 | defend | PolicyEngine's hardcoded example prod-DB id doesn't match real Notion workspace ids, so the write-risk gate can never f… |
| WG-0888 | P1 | defend | No rate-limiting middleware exists across ~62 public routes on a single gunicorn worker |
| WG-0897 | P1 | defend | Five test scripts import modules relocated to legacy/ and will ImportError on any run attempt |
| WG-0906 | P1 | defend | pre-commit relay claim-guard fails open and its opt-in flag is unset in this clone |
| WG-0914 | P1 | defend | kaedra_wake_daemon.py only print()s inbound fleet directives with no ack, wake action, or shard capture |
| WG-0922 | P1 | defend | /upload accepts any file with no size/type checks and serves it publicly under the kaedra domain |
| WG-0930 | P1 | defend | Product version drifts across four sources with no single source of truth |
| WG-0938 | P1 | elevate | Fix mprocs.yaml's pylint watcher to run on the actual deploy platform instead of Windows-only `py -3.12` |
| WG-0946 | P1 | defend | SyncManager.upsync() blind-pushes local dirty entities to Notion on process exit with no conflict check |
| WG-0954 | P1 | defend | 55 VeilVerse Notion pages sit 'Untitled' with missing Name property, never remediated |

---

### WG-0007 · P0 · defend · effort M

**Rotate and history-purge the two committed Notion integration tokens**

- Failure surface: Two live-format ntn_ tokens sit in tracked files despite CHANGELOG 2026-01-07 claiming the hardcoded token was removed; anyone with repo read (or a shard harvest of the tree) gets write access to the VeilVerse workspace and nobody notices until pages change.
- First fork: if you observe either token still authenticates against api.notion.com/v1/users/me -> revoke in Notion, rotate NOTION_TOKEN on Cloud Run and every machine, then rewrite history; else -> treat as dead and only purge from history
- Evidence: `tools/backup_veilverse.py`, `debug_notion_raw.py`, `CHANGELOG.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both ntn_ tokens present verbatim in tools/backup_veilverse.py and debug_notion_raw.py; CHANGELOG.md 2026-01-07 entry explicitly claims the hardcoded token was removed, contradicting the live tokens still in tree.
- #550 families: 76

### WG-0023 · P0 · defend · effort L

**Recover the Cloud Run agent from six never-committed modules that abort background_init**

- Failure surface: kaedra/api/main.py background_init and kaedra/agents/base.py import bigquery_memory, stores, engram_service, mcp_client, context and agent_types, none of which have ever been committed; ImportError fires before state.agent is set so /v1/chat, /v1/chat/completions, /execute-code and /story/generate return 503 forever on any fresh build, and commit c9f3ae8 already records all fleet /health checks failing 500/503.
- First fork: if you observe the modules exist on a Windows working tree (untracked) -> commit them behind a smoke import test; else -> stub or delete the imports and re-plan hierarchical memory
- Evidence: `kaedra/api/main.py`, `kaedra/agents/base.py`, `tools/kaedra_hi_probe.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra/agents/base.py imports ..core.agent_types (AgentThread) which does not exist as a tracked or untracked file in kaedra/core/; git ls-files shows no agent_types.py/context.py/mcp_client.py/engram_service.py/stores.py/bigquery_memory.py matching these module names, confirming ImportError would fire.
- #550 families: 30

### WG-0038 · P0 · defend · effort M

**Survive a lane committing to Kaedra with hooks uninstalled or the relay import broken**

- Failure surface: hooks/ only work after git config core.hooksPath hooks; pre-commit exits 0 when nougen_relay is missing or errors, and prepare-commit-msg already misattributed a rebase on 2026-07-31. With NouGenRelay CI red (pytest 9 importorskip, NouGenRelay#68) a broken install disarms the claim guard on every machine while everyone believes it runs.
- First fork: if you observe recent commits without Machine/Agent trailers -> hooks are not installed on that lane, add a bootstrap check; else -> make the guard log loudly when it falls back to exit 0
- Evidence: `hooks/pre-commit`, `hooks/prepare-commit-msg`
- Lens: toolchain-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit shows exit 0 at line 31 when nougen_relay is not importable via any of python/python3, and a final exit 0 at line 40, confirming the guard fails open silently.
- #550 families: 23

### WG-0052 · P0 · elevate · effort L

**Re-home the Kaedra deploy pipeline onto the Whovisions Fleet project (kaedra-agent-api)**

- Failure surface: Commit c9f3ae8 says GCP cleanup closed gen-lang-client-0939852539's neighbours and Kaedra now lives at kaedra-agent-api in a different project, but cloudbuild.yaml, config.py PROJECT_ID, CLOUD_RUN_URL, deploy scripts and GCP_INVENTORY all still name the old project; a deploy from this repo either fails or resurrects a service in the wrong project with Firestore kaedra-chat left behind.
- First fork: if you observe gcloud projects describe on the old project returns ACTIVE -> plan a data move for Firestore and buckets first; else -> rewrite every project reference and deploy to the fleet project with a rollback tag
- Evidence: `cloudbuild.yaml`, `kaedra/core/config.py`, `.agent/handoff/GCP_INVENTORY.md`
- Lens: deploy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Commit c9f3ae8 exists verbatim with message confirming GCP cleanup, project migration to Whovisions Fleet (kaedra-agent-api) and that surviving services still report OFFLINE on health; cloudbuild.yaml and config.py (PROJECT_ID=gen-lang-client-0939852539) and GCP_INVENTORY.md (same project id) still reference the old project, exactly as claimed.

### WG-0064 · P0 · defend · effort M

**Turn kaedra_hi_probe's hardcoded roster and LAN IPs into a fleet-owned config**

- Failure surface: FLEET_CLOUDRUN, LAN IPs 192.0.2.87/178, SSH keys and Mac paths are literals; after 'prune closed Cloud Run projects' a retired service reads as offline forever and a renumbered host reads as ghost, and PR #5 shows a wrong-attribute bug went unnoticed six weeks.
- First fork: if you observe FLEET_CLOUDRUN entries returning 404/NXDOMAIN -> route A: source the roster from NouGenRelay .handoffs or fleet_whoami; else route B: mark stale entries and alert on roster drift.
- Evidence: `tools/kaedra_hi_probe.py`
- Lens: observability/metrics-drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/kaedra_hi_probe.py:79 FLEET_CLOUDRUN={...} literal dict, lines 621/712/714/619 hardcode IPs 192.0.2.87, 198.51.100.78, 192.0.2.178; git log shows 'Merge PR #5: fix(tools) use response.status in cloud fleet health check' (commit 501e415) confirming a real attribute-usage bugfix landed on this file.
- #550 families: 39

### WG-0075 · P0 · defend · effort S

**Prove the fail-open relay claim hooks actually run on each fleet clone**

- Failure surface: hooks/pre-commit exits 0 when relay is missing and needs core.hooksPath per clone; prepare-commit-msg documents a 2026-07-31 rebase that reattributed a phoebus commit to blade1tb; nobody can tell which machines have the guard armed.
- First fork: if you observe a commit without Nougen-Machine trailer after 2026-08-02 -> route A: add a hook-armed heartbeat to the probe payload; else route B: audit git config core.hooksPath on blade/phoebus/whoart.
- Evidence: `hooks/pre-commit`, `hooks/prepare-commit-msg`
- Lens: observability/health-lies · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit line 31 and 40 'exit 0' when relay tooling is unavailable ('Fails OPEN', documented at line 14); hooks/prepare-commit-msg lines 23-25 document the measured 2026-07-31 rebase on blade that rewrote a commit stamped phoebus/claude-cli into blade1tb -- matches claim verbatim.
- #550 families: 23, 100

### WG-0086 · P0 · defend · effort S

**Fix /health so it stops saying ok while background_init has failed since January**

- Failure surface: background_init imports kaedra.services.stores, bigquery_memory, context, engram_service and mcp_client, none of which exist, so the task dies at import; /health still returns status ok and version 0.0.9, the probe's cloud check passes, and /generate answers 'Agent still warming up' forever.
- First fork: if you observe /generate on the live URL returning 503 warming up -> route A: make /health report init state and fail readiness; else route B: keep /health liveness-only and add /health/ready wired to state.agent.
- Evidence: `kaedra/api/main.py`, `tools/kaedra_hi_probe.py`
- Lens: observability/health-lies · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra/api/main.py background_init() imports kaedra.services.stores, bigquery_memory, context (via engram/context provider), engram_service, mcp_client - all five confirmed missing from kaedra/services/. /health (line 535) unconditionally returns status ok, version 0.0.9, independent of background_init state.
- #550 families: 95

### WG-0097 · P0 · elevate · effort M

**Add a deploy-freshness watchdog for the public kaedra Cloud Run service**

- Failure surface: The core package has not changed since 2026-01-31 and GCP_INVENTORY records the last deploy on 2026-01-12, yet the service is public and on the fleet roster; nothing alerts when the deployed revision drifts from main or when the service stops being deployed at all.
- First fork: if you observe gcloud run revisions list showing a revision older than the last main commit touching kaedra/ -> route A: add revision SHA to /health and let the probe compare; else route B: add a weekly Cloud Build trigger.
- Evidence: `.agent/handoff/GCP_INVENTORY.md`, `cloudbuild.yaml`, `kaedra/api/main.py`
- Lens: observability/lane-freshness · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .agent/handoff/GCP_INVENTORY.md:16 records 'Last Deployed: 2026-01-12T21:17:36Z' (scan date 2026-01-13); cloudbuild.yaml and kaedra/api/main.py confirmed to exist and define the deploy path with no revision-drift check.
- #550 families: 95

### WG-0107 · P0 · defend · effort S

**Public A2A card advertises real code-execution while the endpoint only simulates output**

- Failure surface: Any fleet peer or external agent reading /.well-known/agent.json sees 'code-execution' listed as a capability and routes real tasks to it, but /execute-code just asks Gemini to narrate what the code would print (main.py:994 TODO), so results are fabricated and silently wrong.
- First fork: if a caller trusts the advertised capability list -> it dispatches real execution tasks to Kaedra, else -> it probes /execute-code first and discovers the simulation
- Evidence: `kaedra/api/main.py:1130-1160`, `kaedra/api/main.py:980-997`
- Lens: product-public-surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.json (main.py ~1130-1160) lists 'code-execution' capability; /execute-code (main.py ~980-997) has a TODO 'Connect to Vertex AI Code Execution Tool if available' and just prompts Gemini to 'Simulate the output', returning status:'simulated'.
- #550 families: 100

### WG-0117 · P0 · defend · effort S

**Unauthenticated agent card leaks internal brand voice 'AAVE, tactical, uncensored' to the public**

- Failure surface: Anyone hitting the public, no-auth /.well-known/agent.json sees Kaedra's internal persona description verbatim; screenshotted or quoted externally it reads as an offensive/uncensored brand claim with no context.
- First fork: if a journalist/user/competitor fetches the public card -> the raw persona string is exposed, else -> it stays an internal-only detail
- Evidence: `kaedra/api/main.py:1130-1160`
- Lens: brand · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: /.well-known/agent.json route has no auth dependency and its extensions block literally contains "personality": "AAVE, tactical, uncensored".
- #550 families: 75

### WG-0125 · P0 · defend · effort S

**Two live-looking Notion integration tokens remain committed despite a changelog entry claiming removal**

- Failure surface: tools/backup_veilverse.py and debug_notion_raw.py hardcode what look like real ntn_ Notion tokens; anyone with repo read access (or a public fork/clone) gets write access to the VeilVerse workspace, contradicting CHANGELOG's 2026-01-07 'remove hardcoded Notion token' entry.
- First fork: if the tokens are still live -> anyone reading the repo gets workspace write access, else if already revoked -> it's just a lingering false sense of the problem being fixed
- Evidence: `tools/backup_veilverse.py:12`, `debug_notion_raw.py:4`, `CHANGELOG.md:23`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: backup_veilverse.py:12 has OLD_TOKEN = "ntn_Q303..."; debug_notion_raw.py:4 has token = "ntn_u303..."; CHANGELOG.md:23 claims '2026-01-07: fix: remove hardcoded Notion token, use env var instead' -- contradicted by these still-present hardcoded tokens.
- #550 families: 76

### WG-0133 · P0 · defend · effort M

**Six submodule gitlinks have no .gitmodules, so a fresh clone gets empty directories**

- Failure surface: git ls-files -s shows 160000 gitlink entries for chatterbox, legacy/chatterbox_legacy, resources/screenwriting_prompts, resources/writingway, .agent/whisper-flow, and temp_hacker_movies, but no .gitmodules file exists to tell git where to fetch them from; a new machine's clone silently gets empty folders where voice (tts_chatterbox.py) and other resources are expected.
- First fork: if a fresh clone runs `git submodule update` -> it errors with no .gitmodules registered, else if nobody notices -> tts_chatterbox.py fails later looking for missing chatterbox code
- Evidence: `git ls-files -s | grep ^160000 (chatterbox, legacy/chatterbox_legacy, resources/screenwriting_prompts, resources/writingway, .agent/whisper-flow, temp_hacker_movies)`, `(no .gitmodules file present)`
- Lens: onboarding · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified via `git ls-files -s | grep ^160000`: exactly these 6 paths (.agent/whisper-flow, chatterbox, legacy/chatterbox_legacy, resources/screenwriting_prompts, resources/writingway, temp_hacker_movies) are gitlinks (mode 160000). No .gitmodules file exists at repo root. Directories on disk are empty.

### WG-0141 · P0 · defend · effort L

**PolicyEngine's cost/risk scoring is never called from any FastAPI route**

- Failure surface: kaedra/control/policy.py implements WEIGHT_HIGH_COST and an APPROVAL_THRESHOLD meant to gate risky/expensive actions under L1 autonomy, but grepping the whole api/ package shows zero references to PolicyEngine — the governance layer exists in code yet gates nothing on the actual public surface that spends money and writes to Notion.
- First fork: if a request goes through kaedra/control/orchestrator_runtime.py (autonomous path) -> PolicyEngine scores it, else if it hits any of the ~62 kaedra/api routes directly -> no risk scoring happens at all
- Evidence: `kaedra/control/policy.py:1-60`, `grep -rn PolicyEngine kaedra/api/ (no matches)`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: policy.py:1-60 defines PolicyEngine with WEIGHT_HIGH_COST and APPROVAL_THRESHOLD=60. `grep -rn PolicyEngine kaedra/api/` returns zero matches, confirming it's never referenced from the api package.

### WG-0149 · P0 · defend · effort L

**No CI test/lint gate exists anywhere despite CHANGELOG claiming Cloud Build replaced GitHub Actions 'for CI/CD'**

- Failure surface: CHANGELOG.md records 'Remove GitHub Actions - using Cloud Build for CI/CD' (2025-12-03) and 'remove GitHub Actions workflow (using Cloud Build trigger instead)' (2025-12-14), but cloudbuild.yaml's actual steps are only docker build, push, and deploy — no pytest/pylint/lint step exists anywhere, so every merge to main ships straight to the public Cloud Run service with zero automated checks.
- First fork: if a commit lands on main and the Cloud Build trigger fires -> it builds and deploys with no test gate, else if someone manually runs tests locally first -> that's the only check that ever happens
- Evidence: `CHANGELOG.md:62`, `CHANGELOG.md:161`, `cloudbuild.yaml:1-42`
- Lens: testing-ci · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: CHANGELOG.md:62 and :161 confirmed with the quoted text; cloudbuild.yaml steps are only docker build/push and gcloud run deploy (lines 1-42), no test/lint step anywhere in the file.
- #550 families: 81

### WG-0157 · P0 · defend · effort M

**prepare-commit-msg's own header documents that rebases reattribute commits to the wrong machine/lane**

- Failure surface: The hook's header comment records a measured 2026-07-31 failure where rebasing rewrote commit attribution trailers to the wrong machine/agent lane; since this is a known, documented, unfixed defect in the attribution mechanism the fleet relies on for provenance, any future rebase across lanes can silently misattribute work again.
- First fork: if a commit is made without rebase -> attribution trailer stays correct, else if the branch is later rebased across machine/lane boundaries -> the header's own comment says attribution silently corrupts
- Evidence: `hooks/prepare-commit-msg:1-30 (header comment documenting the 2026-07-31 rebase misattribution)`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Read hooks/prepare-commit-msg header directly: it explicitly documents 'Measured 2026-07-31: `git rebase origin/main` on blade rewrote a commit stamped `phoebus` / `claude-cli` into `blade1tb` / `unknown-agent`' and states the fix rule is 'AN EXISTING TRAILER IS NEVER OVERWRITTEN' specifically because of this observed failure. Matches the claim closely and verbatim.
- #550 families: 18

### WG-0165 · P0 · defend · effort S

**720 Atomic Buster's mandatory relay leg authenticates with a hardcoded placeholder token by default**

- Failure surface: rules/720-atomic-buster.md names the MsgNode:8766 broadcast as the mandatory LOOP1 RELAY step, but nougenmsg_enhanced_client.py's AUTH_TOKEN falls back to the literal string 'keymaker_authenticated_token' whenever NOUGEN_AGY_MSG_TOKEN/AGY_MSG_TOKEN are unset — any lane missing the real env var authenticates fleet-critical relay messages with a well-known default instead of a real credential.
- First fork: if NOUGEN_AGY_MSG_TOKEN is set in the environment -> real auth is used, else (unset, e.g. a fresh machine or misconfigured lane) -> the client silently sends the hardcoded placeholder token as if it were valid auth
- Evidence: `rules/720-atomic-buster.md:17-20 (LOOP1 RELAY step, MsgNode:8766)`, `tools/nougenmsg_enhanced_client.py:14 (hardcoded fallback token)`, `tools/nougenmsg_enhanced_client.py:53-54 (token used in auth headers)`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg_enhanced_client.py:14 reads exactly: AUTH_TOKEN = os.environ.get("NOUGEN_AGY_MSG_TOKEN") or os.environ.get("AGY_MSG_TOKEN") or "keymaker_authenticated_token" — confirmed hardcoded fallback, used at lines 53-54 as both X-NouGen-Key and Bearer auth headers. rules/720-atomic-buster.md does document the MsgNode:8766 broadcast as the mandatory LOOP1 RELAY step (step 3, 'Broadcast live s
- #550 families: 23

### WG-0173 · P0 · elevate · effort S

**Broad Google Workspace OAuth scopes are requested but never wired into any API route or tool registry**

- Failure surface: tools/google_auth.py requests gmail.modify, full calendar, full drive, documents, spreadsheets, tasks, and contacts.readonly scopes, but grepping kaedra/api/main.py and kaedra/core/tools.py shows google_workspace is never referenced from either — an overbroad, unused OAuth grant sits live with no code path exercising or auditing it, a governance liability if the token is ever compromised for no product benefit.
- First fork: if the OAuth token is scoped down or revoked -> no functionality is lost since nothing uses it, else if it's left as-is and later wired into an unauthenticated route -> the full breadth of gmail.modify/drive access becomes reachable from the public surface
- Evidence: `tools/google_auth.py:19-27 (SCOPES list)`, `kaedra/core/tools.py (grep google_workspace: no matches)`, `kaedra/api/main.py (grep google_workspace: no matches)`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/google_auth.py:19-27 SCOPES list confirmed exactly: gmail.modify, calendar, drive, documents, spreadsheets, tasks, contacts.readonly. grep for 'google_workspace' in kaedra/core/tools.py and kaedra/api/main.py returns zero matches, confirming it's unreferenced.

### WG-0369 · P1 · defend · effort M

**Fix PolicyEngine prod detection so Universe DB writes stop scoring as internal**

- Failure surface: policy.py flags 'prod' only when the database_id contains '2e7ca671' (the Handoff DB) or a 'C_PUBLIC' channel prefix; writes to UNIVERSE_DB_ID 2e5ca671 score 10 and auto-execute under threshold 60, so the L1 approval gate never fires for the lore bible.
- First fork: if you observe orchestrator_runtime executing notion.write events with score < 60 against 2e5ca671 -> hard-block writes until the ID table is real; else -> load prod IDs from config and add a regression test
- Evidence: `kaedra/control/policy.py`, `kaedra/services/notion_service.py`, `kaedra/control/orchestrator_runtime.py`
- Lens: tool-abuse · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra/control/policy.py:33,42 shows prod detection literally gated on '2e7ca671' in db_id or 'C_PUBLIC' channel prefix with comments '# Example IDs' / '# Hypothetical public channel prefix', confirming the ID mismatch against a different UNIVERSE_DB_ID.

### WG-0385 · P1 · defend · effort M

**Reconcile the hi_probe fleet roster after the 09-11 rewrite silently reverted the 08-04 prune**

- Failure surface: Commit c9f3ae8 (2026-08-04) pruned closed Cloud Run projects and pointed KAEDRA at kaedra-agent-api in the Whovisions Fleet project, but HEAD's FLEET_CLOUDRUN again lists the six dead URLs, so the probe reports OFFLINE for services that do not exist and never checks the live one.
- First fork: if you observe git log -S 'kaedra-agent-api' shows the URL removed by a later commit -> restore the pruned roster and add a roster test; else -> the prune never landed on main, re-apply it
- Evidence: `tools/kaedra_hi_probe.py`, `CHANGELOG.md`
- Lens: toolchain-drift · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: tools/kaedra_hi_probe.py and CHANGELOG.md exist; the specific commit c9f3ae8 and FLEET_CLOUDRUN roster reversion were not independently verified via git log -S in this pass, but the claim is a reasonable inference from the probe's roster-handling code.
- #550 families: 38

### WG-0401 · P1 · defend · effort M

**Give kaedra a real readiness signal so /health stops lying to hi_probe and A2A peers**

- Failure surface: /health returns a static ok while state.agent is None; hi_probe polls with a 1.2s timeout against a scale-to-zero service so cold starts always read OFFLINE, and PR #5's response.status fix took six weeks to merge while the fleet reported 500/503.
- First fork: if you observe /health 200 while /v1/chat returns 503 -> split liveness from readiness and make readiness depend on state.agent; else -> raise probe timeout and set min-instances 1
- Evidence: `kaedra/api/main.py`, `tools/kaedra_hi_probe.py`
- Lens: health · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: kaedra/api/main.py and tools/kaedra_hi_probe.py exist; a static /health response decoupled from state.agent readiness is consistent with the missing-module ImportError finding in item 2, supporting this claim by inference.
- #550 families: 95

### WG-0417 · P1 · defend · effort M

**Replace the placeholder keymaker token and 0o777 socket in the nougenmsg client and daemon**

- Failure surface: nougenmsg_enhanced_client falls back to the literal 'keymaker_authenticated_token' when no env is set and silently degrades 401s to the unix socket and inbox drops; nougen_socket_pipe_daemon binds /tmp/agy-socks with 0o777 and acks any JSON, so any local process can forge fleet messages to Kaedra or Antigravity.
- First fork: if you observe MsgNode:8766 logs accepting the placeholder token -> the server is not checking either, fix both sides; else -> require keymaker resolution and chmod 0o600 with peer credential checks
- Evidence: `tools/nougenmsg_enhanced_client.py`, `tools/nougen_socket_pipe_daemon.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg_enhanced_client.py:14 shows AUTH_TOKEN falling back to literal 'keymaker_authenticated_token'; tools/nougen_socket_pipe_daemon.py:19 shows os.chmod(sock_path, 0o777), both confirming the claim.

### WG-0433 · P1 · defend · effort M

**Survive the wake daemon's 600s/1800s lifetime expiring mid-mission on a hidden scheduled task**

- Failure surface: kaedra_wake_daemon exits after 10 minutes and antigravity's after 30, relying on the agent to relaunch; run from a visible console (today's blade QuickEdit freeze) or a task with a 72h ExecutionTimeLimit, the watcher dies quietly and Kaedra misses fleet pings for hours.
- First fork: if you observe gaps > 10 min between inbox mtime and any PONG in the relay -> convert to a hidden scheduled task with restart-on-exit and heartbeat; else -> lengthen the loop and shard the heartbeat
- Evidence: `tools/kaedra_wake_daemon.py`, `tools/antigravity_wake_daemon.py`
- Lens: scheduled-tasks · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/kaedra_wake_daemon.py:30-31 confirms a 600-second (10 minute) watch loop; tools/antigravity_wake_daemon.py:106-107 confirms a 1800-second (30 minute) loop, matching the claim exactly.
- #550 families: 26

### WG-0449 · P1 · defend · effort S

**Decide whether the committed .claude/settings.local.json is fleet policy or a permission leak**

- Failure surface: The tracked settings file pre-approves Bash(python3:*) for any Claude lane that clones Kaedra, so a cloned repo silently widens what agents may run; combined with tracked debug_*.py the .gitignore says to exclude, the repo carries policy it does not intend.
- First fork: if you observe other fleet repos also track settings.local.json -> promote to a reviewed settings.json with a documented allowlist; else -> untrack it and add a pre-commit deny
- Evidence: `.claude/settings.local.json`, `.gitignore`
- Lens: committed-files · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: .claude/settings.local.json is tracked and contains exactly {'permissions': {'allow': ['Bash(python3:*)'], ...}}, confirming the pre-approved wildcard Bash permission is committed.

### WG-0464 · P1 · defend · effort M

**Restore or vendor the six orphan gitlinks so voice builds from a fresh clone**

- Failure surface: chatterbox, legacy/chatterbox_legacy, resources/*, temp_hacker_movies and .agent/whisper-flow are 160000 gitlinks with no .gitmodules; cloudshell_setup.sh and run_agents.sh git clone the repo and tts_chatterbox.py imports chatterbox.tts_turbo, so any non-Windows checkout has no voice path and Docker COPY ships empty dirs.
- First fork: if you observe the upstream chatterbox commit ed27b95 is reachable -> add .gitmodules and pin; else -> vendor a wheel and delete the dead links
- Evidence: `kaedra/services/tts_chatterbox.py`, `scripts/cloudshell_setup.sh`, `scripts/run_kaedra_chatterbox.bat`
- Lens: supply-chain · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git ls-files -s confirms 160000 (gitlink) mode entries for chatterbox, legacy/chatterbox_legacy, resources/screenwriting_prompts, resources/writingway, temp_hacker_movies, and .agent/whisper-flow, with no .gitmodules file present, confirming orphan gitlinks.
- #550 families: 35

### WG-0477 · P1 · defend · effort M

**Survive the retirement of preview model IDs hardcoded in kaedra/core/config.py MODELS**

- Failure surface: MODELS pins gemini-3-*-preview, gemini-2.5-flash-preview-09-2025, veo-3.1-generate-preview, llama-4-*-preview and claude-4.5-* publisher paths with MODEL_LOCATION=global and no fallback chain; when Vertex retires a preview ID every /generate path 404s at once and worldbuilder silently uses gemini-2.0-flash.
- First fork: if you observe /v1/models listing IDs that /generate rejects -> add a live model-availability check and alias fallbacks; else -> pin GA IDs and schedule a quarterly registry pass
- Evidence: `kaedra/core/config.py`, `kaedra/skills/worldbuilder.py`, `docs/CREDIT_STRATEGY.md`
- Lens: model-cutover · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra/core/config.py confirms MODEL_LOCATION='global' and MODELS dict pinning gemini-3-*-preview, gemini-2.5-flash-preview-09-2025, llama-4-*-preview, and veo-3.1-generate-preview style preview IDs, matching the claim.
- #550 families: 77

### WG-0490 · P1 · defend · effort M

**Survive a hostile POST to /webhook/notion or /sync mutating the VeilVerse ingestion queue**

- Failure surface: main.py /webhook/notion accepts any JSON with no signature and runs NotionBridge.pull_ingestion_queue, whose _mark_as_imported PATCHes Status=Active on Notion pages; /sync runs sync_all for any world_id. An attacker or a crawler can flip queue state and rewrite lore/worlds/world_bee9d6ac/ingestion.json on the live service.
- First fork: if you observe unsigned POSTs already reaching the endpoint in Cloud Run logs -> disable the route and route Notion to /hooks/notion with HMAC; else -> add the signature check and rate limit before the next deploy
- Evidence: `kaedra/api/main.py`, `tools/sync_notion.py`, `kaedra/api/webhooks.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra/api/main.py:1180 defines POST /webhook/notion calling bridge.pull_ingestion_queue() with no auth decorator; tools/sync_notion.py:282 _mark_as_imported PATCHes status; /sync route also present at main.py:1210.
- #550 families: 20

### WG-0502 · P1 · defend · effort M

**Scope down the Google OAuth token and gate gmail_to_notion before inbox mail lands in Notion**

- Failure surface: tools/google_auth.py requests gmail.modify, drive, calendar, documents, spreadsheets, tasks and contacts and stores a refresh token as plaintext kaedra/config/google_token.json; gmail_to_notion.py copies message bodies into the VeilVerse DB where the leaked Notion tokens (and every shard harvest) can read them.
- First fork: if you observe a google_token.json on any machine with drive scope -> revoke and re-issue readonly scopes; else -> reduce SCOPES and add a dry-run to gmail_to_notion
- Evidence: `tools/google_auth.py`, `tools/gmail_to_notion.py`, `kaedra/services/google_workspace.py`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: google_auth.py SCOPES confirmed: gmail.modify, calendar, drive, documents, spreadsheets, tasks, contacts.readonly; TOKEN_FILE/google_workspace.py both point at kaedra/config/google_token.json.

### WG-0514 · P1 · defend · effort S

**Stop autosync_handoffs from mirroring GCP inventory and LAN topology into Notion**

- Failure surface: autosync_handoffs.py runs sync_handoffs_to_notion.py every 5 minutes, pushing every .agent/handoff/*.md (GCP_INVENTORY with bucket names, kLocalUrl 198.51.100.187, service URLs) into DB 2e7ca671, which the leaked tokens can read.
- First fork: if you observe GCP_INVENTORY content in the Notion handoff DB -> delete those pages and exclude the file; else -> allowlist handoff files and strip infra sections
- Evidence: `scripts/autosync_handoffs.py`, `scripts/sync_handoffs_to_notion.py`, `.agent/handoff/GCP_INVENTORY.md`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: scripts/autosync_handoffs.py, scripts/sync_handoffs_to_notion.py, and .agent/handoff/GCP_INVENTORY.md all exist, consistent with periodic handoff-to-Notion sync of infra inventory files.

### WG-0526 · P1 · defend · effort M

**Survive the 4455 kaedra_gateway token leaking or its tunnel exposing Ollama unauthenticated**

- Failure surface: ops/kaedra/kaedra_gateway.py binds 0.0.0.0:4455 by default and fronts an Ollama that has no auth of its own; kaedra_tools and _agy_live_delivery resolve KAEDRA_GATEWAY_TOKEN via env or keymaker and a 38s cold model load exceeds the 30s MCP timeout, so operators are tempted to tunnel 11434 directly.
- First fork: if you observe an ngrok or cloudflared tunnel pointing at 11434 -> tear it down and route only 4455; else -> rotate the gateway token and add a pinned-model warmup on boot
- Evidence: `/home/user/NouGenShards/ops/kaedra/kaedra_gateway.py`, `/home/user/NouGenShards/src/nougen_shards/kaedra_tools.py`, `/home/user/NouGenShards/tools/_agy_live_delivery.py`
- Lens: ports · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra_gateway.py confirmed to bind 0.0.0.0 by default with PORT defaulting to 4455 (KAEDRA_GATEWAY_PORT env var), matching the claim; companion tool files also exist.
- #550 families: 62

### WG-0538 · P1 · defend · effort S

**Survive the A2A card advertising write endpoints to peers and crawlers**

- Failure surface: /.well-known/agent.json publishes /webhook/notion, /sync, /generate-image and /cowrite as capabilities of a 'Public, unauthenticated' agent (docs/A2A_IMPLEMENTATION.md calls it a feature) and hardcodes the closed kaedra-69017097813 URL, so fleet peers DAV1D/RHEA and anyone indexing the card get the write map and a dead deploy_url.
- First fork: if you observe peer probes still hitting the old URL -> update the card and notify the roster; else -> strip write endpoints from the card until auth ships
- Evidence: `kaedra/api/main.py`, `docs/A2A_IMPLEMENTATION.md`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: main.py has /.well-known/agent.json at line 1131 exposing webhook/sync/generate_image/cowrite endpoints (lines 224-230, 1156-1157) and a hardcoded CLOUD_RUN_URL used in webhook comments (kaedra-69017097813...); docs/A2A_IMPLEMENTATION.md exists.
- #550 families: 20

### WG-0550 · P1 · elevate · effort M

**Move Kaedra secrets to Secret Manager/keymaker with a revocation drill**

- Failure surface: NOTION_TOKEN, LIFX_TOKEN, SLACK_*, STRIPE_SECRET_KEY, SQUARE_ACCESS_TOKEN and WISPR_FLOW_API_KEY are plain env vars set by hand in deploy scripts and .env files across three machines; nobody can prove which values are live, and rotating after the committed-token incident touches every launcher.
- First fork: if you observe --set-env-vars carrying secrets in any deploy script -> convert to --set-secrets and keymaker on machines; else -> inventory env per host and write the rotation runbook first
- Evidence: `kaedra/core/config.py`, `docs/CLOUD_DEPLOYMENT.md`, `scripts/deploy_cloud_run.sh`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: config.py contains plaintext env-var secrets (STRIPE_SECRET_KEY, SQUARE_ENVIRONMENT, etc. confirmed); docs/CLOUD_DEPLOYMENT.md and scripts/deploy_cloud_run.sh exist, consistent with hand-set env vars across deploy scripts.
- #550 families: 76

### WG-0562 · P1 · elevate · effort M

**Finish or delete the BigQuery memory tiers that were never created**

- Failure surface: STORAGE_STATUS.md admits memory_short_term/long_term/knowledge tables were never created due to a bq CLI bug, main.py imports a BigQueryMemoryService that does not exist, and requirements still pull google-cloud-bigquery, pubsub and firestore; either path changes what 'memory' means for Confucius context.
- First fork: if you observe the kaedra_memory dataset is empty in BigQuery -> delete the tier, the deps and the import; else -> create tables by DDL and commit the service with tests
- Evidence: `docs/STORAGE_STATUS.md`, `kaedra/api/main.py`, `requirements.txt`
- Lens: infra · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/STORAGE_STATUS.md exists; kaedra/api/main.py confirmed to import BigQueryMemoryService from kaedra.services.bigquery_memory at line 307 and instantiate it at line 318; requirements.txt confirmed to pin google-cloud-bigquery>=3.17.0.

### WG-0574 · P1 · elevate · effort M

**Cut every Notion client over to the 2025-09-03 data_source API before 2022-06-28 queries stop resolving**

- Failure surface: notion.py already sends Notion-Version 2025-09-03 while notion_service.py, sync_manager.py, story/tools/notion.py and the handoff sync still send 2022-06-28 with databases/{id}/query; debug_notion_raw.py already needs a data source id, so the same workspace is addressed two incompatible ways and a Notion deprecation breaks half the writers.
- First fork: if you observe 2022-06-28 database queries returning multi-source errors on the Universe DB -> migrate sync_manager first (it writes); else -> centralize NOTION_VERSION and migrate read paths behind a compat shim
- Evidence: `kaedra/services/notion.py`, `kaedra/services/sync_manager.py`, `kaedra/services/notion_service.py`
- Lens: toolchain-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: notion.py:28 sets NOTION_VERSION=2025-09-03 and uses databases/{id}/query; notion_service.py:11 and sync_manager.py:26 both hardcode 2022-06-28; debug_notion_raw.py:23 already calls data_sources/{id}/query. Version split verified directly in code.
- #550 families: 77

### WG-0585 · P1 · elevate · effort L

**Un-ignore kaedra_mobile/lib and ship the Flutter app pointed at the live gateway**

- Failure surface: Root .gitignore lib/ swallows the entire Flutter app described in HANDOFF.md; kCloudRunUrl in GCP_INVENTORY points at the closed project and analysis dumps show 103 issues, so 'shipping' means recovering untracked code from a Windows box, retargeting the URL and passing analyze.
- First fork: if you observe kaedra_mobile/lib exists untracked on the Windows tree -> negate the ignore for that path and commit; else -> rebuild from the handoff file list against the new API
- Evidence: `kaedra_mobile/pubspec.yaml`, `.gitignore`, `.agent/handoff/HANDOFF.md`
- Lens: deploy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .gitignore:20 has bare 'lib/' which matches kaedra_mobile/lib; kaedra_mobile/pubspec.yaml exists; .agent/handoff/HANDOFF.md exists.

### WG-0596 · P1 · elevate · effort L

**Stand up a pytest lane for Kaedra that survives pytest 9 and mocks live services**

- Failure surface: tests/ is 64 python-run scripts hitting Gemini, Notion, LIFX and audio devices, 7 import modules moved to legacy/, no pytest config and no CI; NouGenRelay's CI already broke on pytest 9's importorskip change, so a naive pytest lane goes red on day one and gets ignored like the 26-deep handoffs backlog.
- First fork: if you observe pytest --collect-only errors on the 7 legacy imports -> quarantine them and start with an import-smoke suite; else -> mark live tests with a marker and run only offline in Cloud Build
- Evidence: `tests/smoke_test.py`, `pyproject.toml`, `mprocs.yaml`
- Lens: toolchain-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: tests/ contains 64 .py files including tests/smoke_test.py; pyproject.toml and mprocs.yaml exist at repo root; no pytest.ini/pytest config section found in pyproject.toml.

### WG-0607 · P1 · elevate · effort M

**Onboard Kaedra's lore ingestion into NouGenShards behind the capture-secret guard**

- Failure surface: Moving ingestion.json, cache/youtube transcripts and lore/drafts into fleet shards raises evidence density but the same tree holds committed tokens, call transcripts and 300KB Notion id dumps; a bulk capture without the secret guard repeats the 'secrets could reach shards' failure at million-shard scale.
- First fork: if you observe the capture-secret-guard war game is not yet enforced in shards_capture -> ingest only lore/ and worlds/ with a manual review; else -> run a dry capture and diff the guard's rejections
- Evidence: `lore/worlds/world_bee9d6ac/ingestion.json`, `cache/youtube`, `/home/user/NouGenShards/src/nougen_shards/kaedra_tools.py`
- Lens: injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: lore/worlds/world_bee9d6ac/ingestion.json exists (2.7MB); cache/youtube/ contains dozens of transcript files; kaedra_tools.py exists at the NouGenShards path referenced as the capture-secret-guard integration point.

### WG-0618 · P1 · elevate · effort M

**Move hi_probe off the hardcoded Mac path into a hidden scheduled job with a heartbeat shard**

- Failure surface: The 1622-line probe hardcodes ~ paths, runs from a visible console on an AM/PM schedule and prints to stdout; today's blade lesson is that visible consoles freeze the loop and nobody notices for hours, and a silent probe is worse than none because the GM believes it is running.
- First fork: if you observe no probe output shard in the last 24h -> the job is already dead, relaunch hidden and shard each run; else -> convert to launchd with KeepAlive and a shards_capture heartbeat
- Evidence: `tools/kaedra_hi_probe.py`, `rules/00-universal-mantra.md`
- Lens: scheduled-tasks · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/kaedra_hi_probe.py is 1662 lines and hardcodes ~ paths (lines 15, 190); it force-wraps sys.stdout for console printing and checks sys.stdout.isatty(), consistent with a visible-console script; rules/00-universal-mantra.md exists.
- #550 families: 95

### WG-0629 · P1 · elevate · effort M

**Consolidate /webhook/notion and /hooks/notion into one signed handler that actually syncs**

- Failure surface: The signed /hooks/notion only logs events while the unsigned /webhook/notion does the real pull; merging them means the HMAC path must call NotionBridge safely in the background and Notion's subscription must be re-pointed, or lore sync stops silently during the switch.
- First fork: if you observe the Notion webhook subscription still targets /webhook/notion -> add sync to /hooks/notion first, re-point, then delete the old route; else -> delete the unsigned route now
- Evidence: `kaedra/api/main.py`, `kaedra/api/webhooks.py`, `tools/sync_notion.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: main.py:1180 defines @app.post('/webhook/notion') (unsigned) while webhooks.py:117 defines @router.post('/notion') under the /hooks prefix (signed via slack_bolt-style router); tools/sync_notion.py contains the real pull_ingestion_queue logic that main.py's webhook path invokes.
- #550 families: 16, 20

### WG-0640 · P1 · defend · effort M

**Purge committed session transcripts and call recordings and set a retention rule**

- Failure surface: sessions/*.json, kaedra/logs/**/*.jsonl and scratchpad/call_*.txt contain personal conversation content and are tracked despite .gitignore; they ship in the Docker image (no .dockerignore) to a public --allow-unauthenticated service.
- First fork: if you observe git ls-files matching sessions/ or kaedra/logs/ -> route A: git rm, rewrite history, add .dockerignore and a retention cron for KAEDRA_HOME/chat_logs; else route B: only add the ignore rules and the retention job.
- Evidence: `sessions`, `kaedra/logs/default`, `scratchpad`
- Lens: data-integrity/PII · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: sessions/ contains committed session JSON files (e.g. kaedra_session_20251226_123446.json); kaedra/logs/default/ contains committed session_*.jsonl transcripts; scratchpad/ contains call_*.txt recordings (e.g. call_030938.txt) — matching the claim of tracked personal conversation content.
- #550 families: 75

### WG-0651 · P1 · defend · effort M

**Stop all public /v1/chat callers sharing one Vertex Memory Bank user 'kaedra-user-main'**

- Failure surface: MemoryService hardcodes user_id='kaedra-user-main' and KaedraAgent inserts every user and assistant turn into it; on the unauthenticated Cloud Run API any caller's prompts are recalled into any other caller's context.
- First fork: if you observe memories.retrieve(scope user_id=kaedra-user-main) returning content from more than one origin -> route A: key scope by API key/session id and purge the shared bank; else route B: disable insert on the public path until auth exists.
- Evidence: `kaedra/services/memory.py`, `kaedra/agents/kaedra.py`, `kaedra/api/main.py`
- Lens: data-integrity/PII · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: memory.py:35 hardcodes self.user_id = 'kaedra-user-main' with the comment 'Single user mode for now', confirming a single shared Memory Bank user id used across the service.

### WG-0662 · P1 · elevate · effort M

**Build a clean Cloud Run image without losing runtime-read markdown and db files**

- Failure surface: No .dockerignore means .git, 22MB WAVs, sessions and scratchpad ship in the image, while .gcloudignore strips *.md, *.db and *.log so prompts.py's open('lore/co_writing_protocol.md') silently falls back to a one-line protocol on cloud builds.
- First fork: if you observe the deployed container missing lore/co_writing_protocol.md -> route A: whitelist runtime files in .gcloudignore and add .dockerignore; else route B: move runtime lore into the package and load via importlib.resources.
- Evidence: `Dockerfile`, `.gcloudignore`, `kaedra/story/components/prompts.py`
- Lens: data-integrity/storage · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: No .dockerignore file exists in repo root; .gcloudignore has '*.md' (with only README.md excepted), '*.db', '*.log' rules; prompts.py line 147 does open('lore/co_writing_protocol.md',...) which would be stripped on a gcloud-based build.
- #550 families: 35

### WG-0673 · P1 · elevate · effort M

**Wire KaedraOrchestrator into app state (state.orchestrator is never assigned)**

- Failure surface: No code in kaedra/api sets state.orchestrator, so /runs returns 503, /hooks/pubsub ignores everything, and the L1 autonomy plane documented in deploy_autonomy.sh has never executed on Cloud Run.
- First fork: if you observe grep 'state.orchestrator =' returning nothing -> route A: construct KaedraOrchestrator in background_init behind a feature flag; else route B: remove /runs and /hooks/pubsub from the agent card.
- Evidence: `kaedra/api/main.py`, `kaedra/api/app_state.py`, `kaedra/control/orchestrator.py`
- Lens: observability/silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: grep -rn 'state.orchestrator\s*=' across kaedra/ returns zero matches; app_state.py:13 declares orchestrator: Optional[Any]=None with no setter; main.py's /runs endpoints (912,939,947) reference state.orchestrator but nothing assigns it.

### WG-0684 · P1 · defend · effort S

**Use stable idempotency keys for Square invoice create/send (uuid4 per call)**

- Failure surface: SquareProvider generates a fresh uuid4 idempotency_key on every create_invoice/send_invoice call, so a network timeout followed by a retry creates and sends a second real invoice to the customer.
- First fork: if you observe two Square invoices with identical line items minutes apart -> route A: derive the key from (customer_id, items hash, date) and persist it; else route B: add read-before-create and keep uuid4.
- Evidence: `kaedra/services/invoices.py`, `tests/stress_test_invoices.py`
- Lens: concurrency/idempotency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra/services/invoices.py lines 433,470,479 all do 'idempotency_key': str(uuid.uuid4()) generated fresh at call time, never derived from a stable business key or persisted for retry reuse.
- #550 families: 8

### WG-0695 · P1 · defend · effort S

**Give kaedra_wake_daemon seen-state, a single-instance lock and no 600s blind spot**

- Failure surface: kaedra_wake_daemon snapshots ~/.nougen/kaedra_inbox at start, exits after 600s or first hit, keeps no seen-hash cache and no pidfile; pings landing between runs are dropped, pings landing before start are ignored, and two overlapping runs wake twice.
- First fork: if you observe an inbox file older than the daemon start never printed -> route A: port antigravity_wake_daemon's lock + hash cache; else route B: replace with the relay claim/ack protocol.
- Evidence: `tools/kaedra_wake_daemon.py`, `tools/antigravity_wake_daemon.py`
- Lens: concurrency/ack-discipline · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/kaedra_wake_daemon.py:15 get_snapshot(), line 28 initial=get_snapshot(), line 31 'while time.time()-start_time < 600' with no persistent hash cache or pidfile/lock visible in the file, contrasted by antigravity_wake_daemon.py which explicitly implements a hash cache and flock (lines 8, 131+).
- #550 families: 25

### WG-0706 · P1 · defend · effort S

**Stop nougenmsg_enhanced_client dual-delivering via HTTP, socket and inbox fallbacks**

- Failure surface: The client tries MsgNode:8766, then the unix socket, then writes to agy/codex inbox dirs; a slow-but-successful HTTP post followed by fallback delivers the same message twice with no message id, and the placeholder AUTH_TOKEN passes when env is unset.
- First fork: if you observe the same text twice in ~/.nougen/agy_inbox with different filenames -> route A: add a uuid message_id and stop after first confirmed delivery; else route B: fail hard on the placeholder token.
- Evidence: `tools/nougenmsg_enhanced_client.py`
- Lens: concurrency/idempotency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg_enhanced_client.py:8-14 defines MSGNODE_URL http://127.0.0.1:8766/msg, AGY_INBOX_DIR/CODEX_INBOX_DIR fallback paths, AUTH_TOKEN defaults to literal 'keymaker_authenticated_token' when env vars unset (line 14); comment at line 4 confirms fallback chain to socket+inbox with no shared message id across the tiers.
- #550 families: 16

### WG-0717 · P1 · defend · effort S

**Stop the socket pipe daemon from acking every payload as 'ok' without auth or framing**

- Failure surface: nougen_socket_pipe_daemon recv(4096) once, ignores the auth line, replies status ok for any bytes, is single-threaded and chmod 0o777; senders believe a message was delivered when it was truncated or dropped.
- First fork: if you observe a >4096-byte message acked ok but never processed -> route A: length-prefixed framing, auth check, threaded accept; else route B: retire it in favour of MsgNode HTTP.
- Evidence: `tools/nougen_socket_pipe_daemon.py`, `tools/nougenmsg_enhanced_client.py`
- Lens: observability/false-done · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougen_socket_pipe_daemon.py:19 os.chmod(sock_path, 0o777), line 27 data=conn.recv(4096) single call, line 32 responds {'status':'ok',...} unconditionally after parsing the 2-line JSON protocol -- no length-prefix framing or real auth verification visible.
- #550 families: 20, 23

### WG-0728 · P1 · defend · effort M

**Re-fence the NouGenShards Kaedra tool loop, which is no longer read-only**

- Failure surface: kaedra_tools.py's dispatch docstring says read-only but _DISPATCH now includes shards_capture (writes kaedra-authored shards) and nougenmsg_send (fleet pings); a local kaedra:e4b hallucination captures itself into the vault, is recalled next round, and wakes other lanes.
- First fork: if you observe shards tagged kaedra-authored citing other kaedra-authored shards -> route A: mark all Kaedra captures CANDIDATE and exclude from her own recall; else route B: remove the two write tools from Move 3.
- Evidence: `NouGenShards:src/nougen_shards/kaedra_tools.py`, `NouGenShards:src/nougen_shards/agents.py`
- Lens: concurrency/distributed-write · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/src/nougen_shards/kaedra_tools.py:3 docstring 'Six tools, all read-only...' contradicts _DISPATCH (line 307) which includes 'shards_capture': _shards_capture (line 314) and 'nougenmsg_send': _nougenmsg_send (line 315), both of which are write/side-effecting operations.

### WG-0738 · P1 · defend · effort S

**Add a lock to kaedra_hi_probe's failsafe before it killall's Ollama mid-inference**

- Failure surface: The probe runs killall/pkill Ollama whenever gemma looks unresponsive, with no pidfile or lock; two overlapping probe runs (cron + manual) or a probe during a long NouGenShards kaedra:e4b generation kill the model under the gateway and the shards call returns a VRAM error.
- First fork: if you observe two kaedra_hi_probe processes in ps -> route A: flock + 'busy' check on /api/ps before killing; else route B: replace kill with a graceful restart and a cooldown file.
- Evidence: `tools/kaedra_hi_probe.py`
- Lens: concurrency/races · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/kaedra_hi_probe.py:1284 subprocess.run('killall Ollama || true', ...) inside the failsafe recovery block (around line 1279-1284), with no flock/pidfile/lock or busy-check against /api/ps found anywhere in the file.
- #550 families: 56

### WG-0748 · P1 · elevate · effort L

**Restore or remove the phantom memory stack imports in background_init**

- Failure surface: The five missing modules mean no service on Cloud Run has an agent, Slack, StoryEngine or MCP client; the fix is either to resurrect the memory stack the docs describe or to strip background_init to what exists, and each path changes what the fleet can call.
- First fork: if you observe git log showing those modules ever existed -> route A: restore them from history behind tests; else route B: delete the imports, init only PromptService/KaedraAgent, and redeploy with a smoke test.
- Evidence: `kaedra/api/main.py`, `docs/ENHANCED_MEMORY_ARCHITECTURE.md`
- Lens: observability/silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Same import failure confirmed as in #50; docs/ENHANCED_MEMORY_ARCHITECTURE.md exists describing the memory stack the missing modules would implement.

### WG-0758 · P1 · defend · effort M

**Turn the committed failing smoke/validation logs into an enforced pre-deploy gate**

- Failure surface: smoke_test_output.txt records 'Engine failed to init: LightsController has no attribute init', validation_log.txt a traceback, engine_debug.log a StoryEngine crash; all are committed as if passing and no CI exists, so the next deploy ships the same failures.
- First fork: if you observe tests/smoke_test.py still importing universe_text (moved to legacy/) -> route A: fix the 7 legacy imports and run smoke in cloudbuild before deploy; else route B: delete the logs and add a minimal import-check step.
- Evidence: `smoke_test_output.txt`, `validation_log.txt`, `tests/smoke_test.py`
- Lens: observability/silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: smoke_test_output.txt (UTF-16) contains literal '[CRITICAL] Engine failed to init: 'LightsController' object has no attribute 'init''; validation_log.txt contains a StoryEngine init traceback; tests/smoke_test.py:10 does 'from universe_text import StoryEngine, Mode' where universe_text.py lives under legacy/, confirming the stale/broken import path.
- #550 families: 81

### WG-0768 · P1 · elevate · effort M

**Retire the dead Vertex Reasoning Engine path with its two conflicting resource IDs**

- Failure surface: docs/DEPLOYMENT_STATUS.md has the RE deploy failing since 2025-12-14, config.py points at 69017097813/5808320806819725312 while kaedra_local.py points at 627440283840/5765957723313143808; MemoryService still calls agent_engines on one of them and nobody knows which is billed.
- First fork: if you observe gcloud ai reasoning-engines list showing either engine alive -> route A: migrate Memory Bank sessions to the surviving one and delete the other; else route B: delete both IDs, kaedra_local.py and the deploy tools.
- Evidence: `docs/DEPLOYMENT_STATUS.md`, `kaedra_local.py`, `kaedra/core/config.py`
- Lens: observability/stale-done · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/DEPLOYMENT_STATUS.md:8,107 shows project 69017097813, 'Last Updated: 2025-12-14', and a Reasoning Engine startup failure; kaedra/core/config.py:49-51 uses projects/69017097813/.../reasoningEngines/5808320806819725312; kaedra_local.py:20-21 uses projects/627440283840/.../reasoningEngines/5765957723313143808 - two distinct resource IDs confirmed.

### WG-0778 · P1 · elevate · effort L

**Finish or retire the BigQuery memory tier whose tables were never created**

- Failure surface: docs/STORAGE_STATUS.md says memory_short_term/long_term/knowledge tables 'need manual creation' (bq absl.flags bug) and ENHANCED_MEMORY_ARCHITECTURE stores embedding as '[]' to 'embed async later'; the API's background_init imports a BigQueryMemoryService that does not exist, so the memory stack is doc-only.
- First fork: if you observe bq ls kaedra_memory returning the three tables -> route A: wire a real service and backfill embeddings; else route B: delete the BigQuery/pubsub/firestore deps and docs so the fleet stops believing Kaedra has hierarchical memory.
- Evidence: `docs/STORAGE_STATUS.md`, `docs/ENHANCED_MEMORY_ARCHITECTURE.md`, `kaedra/api/main.py`
- Lens: data-integrity/schema · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/STORAGE_STATUS.md documents memory_short_term/long_term tables needing manual creation due to a bq/absl.flags bug; main.py's background_init imports 'from kaedra.services.bigquery_memory import BigQueryMemoryService', but kaedra/services/bigquery_memory.py does not exist in the repo — confirms the memory stack is doc-only / import would fail.

### WG-0788 · P1 · elevate · effort L

**Track kaedra_mobile/lib and define offline-cache conflict rules against ephemeral sessions**

- Failure surface: HANDOFF.md describes a SharedPreferences offline cache and local_cache.dart, but root .gitignore `lib/` swallows the Flutter code, so the sync logic cannot be audited while the server side stores sessions in tmpfs and Firestore with no version field.
- First fork: if you observe kaedra_mobile/lib present on blade but untracked -> route A: un-ignore, commit, and add updated_at/version to /story/session PATCH; else route B: rebuild Phase 1-2 from the handoff with last-write-wins documented.
- Evidence: `.agent/handoff/HANDOFF.md`, `.gitignore`, `kaedra_mobile/pubspec.yaml`
- Lens: concurrency/sync · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .agent/handoff/HANDOFF.md references 'Offline cache using SharedPreferences' and 'core/services/local_cache.dart'; .gitignore:20 has a bare 'lib/' pattern; kaedra_mobile/lib does not exist in this checkout (git ls-files confirms it's not tracked), consistent with the gitignore swallowing it.
- #550 families: 12

### WG-0798 · P1 · elevate · effort M

**Run a fresh-clone restore drill: six gitlinks with no .gitmodules block voice and resources**

- Failure surface: chatterbox, legacy/chatterbox_legacy, resources/screenwriting_prompts, resources/writingway, temp_hacker_movies and .agent/whisper-flow are 160000 gitlinks without .gitmodules; a new machine (or a rebuilt blade) cannot clone tts_chatterbox's dependency and the failure is a silent empty dir.
- First fork: if you observe git submodule status listing no URL for chatterbox -> route A: add .gitmodules pinned to the recorded SHAs and test a clean clone; else route B: vendor or drop each gitlink.
- Evidence: `chatterbox`, `kaedra/services/tts_chatterbox.py`, `resources`
- Lens: data-integrity/restore-drills · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git ls-files -s | grep 160000 shows exactly the six gitlinks named: .agent/whisper-flow, chatterbox, legacy/chatterbox_legacy, resources/screenwriting_prompts, resources/writingway, temp_hacker_movies; no .gitmodules file exists in the repo root.
- #550 families: 35

### WG-0808 · P1 · defend · effort S

**kaedra_mobile/lib is swallowed by the root .gitignore, so the Flutter app source was never committed**

- Failure surface: The repo's root .gitignore excludes `lib/` globally, which also matches kaedra_mobile/lib — the actual Flutter Dart source described as built in .agent/handoff/BLADE_HANDOFF.md is simply absent from every clone; anyone opening the mobile project sees only the unedited template.
- First fork: if a developer trusts BLADE_HANDOFF.md's Phase 1-2 completion claim -> they expect working lib/ code and find none, else if they check git status first -> they discover lib/ was never tracked
- Evidence: `.gitignore:20-21`, `kaedra_mobile/ (lib/ directory absent)`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .gitignore:20-21 has bare `lib/` and `lib64/` patterns (Python venv convention) which also match kaedra_mobile/lib; kaedra_mobile/lib does not exist on disk, confirming it's absent/untracked.

### WG-0818 · P1 · defend · effort M

**Deploy target name drifts between cloudbuild.yaml's `kaedra` and the shell scripts' `kaedra-shadow-tactician`**

- Failure surface: cloudbuild.yaml deploys a Cloud Run service named `kaedra` at 4Gi/3600s timeout, while scripts/deploy_cloud_run.sh, deploy.bat, and docs/CLOUD_DEPLOYMENT.md deploy a differently-named `kaedra-shadow-tactician` at 2Gi/300s; running the 'wrong' deploy path creates or updates a second, differently-resourced public service instead of the intended one.
- First fork: if CI/Cloud Build trigger fires -> updates service `kaedra`, else if someone runs scripts/deploy_cloud_run.sh manually -> it updates/creates the other service `kaedra-shadow-tactician`
- Evidence: `cloudbuild.yaml:17-34`, `scripts/deploy_cloud_run.sh:9`, `scripts/deploy_cloud_run.sh:43-45`
- Lens: docs-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml deploys service name 'kaedra' with --memory 4Gi and --timeout 3600 (lines ~18-34); scripts/deploy_cloud_run.sh:9 sets SERVICE_NAME="kaedra-shadow-tactician" with --memory 2Gi --timeout 300 (lines ~43-45). Confirmed exact mismatch.

### WG-0828 · P1 · defend · effort S

**AGENT_UPGRADE_NOTICE.md still cites a retired Reasoning Engine resource as current guidance**

- Failure surface: AGENT_UPGRADE_NOTICE.md documents projects/627440283840/.../reasoningEngines/5765957723313143808 as 'the' resource, matching the stale ID in kaedra_local.py rather than config.py's live one; a fleet agent following this notice for an upgrade targets a dead resource.
- First fork: if an agent follows AGENT_UPGRADE_NOTICE.md literally -> it operates on the retired engine ID, else if it cross-checks config.py -> it finds the real current one
- Evidence: `AGENT_UPGRADE_NOTICE.md:29`, `kaedra/core/config.py:49-51`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: AGENT_UPGRADE_NOTICE.md:29 states Resource: `projects/627440283840/locations/us-central1/reasoningEngines/5765957723313143808`, matching the stale ID; config.py:49-51 has the different live resource. Confirmed.

### WG-0838 · P1 · defend · effort S

**License metadata says MIT while README says Proprietary for the same repo**

- Failure surface: pyproject.toml classifies the package MIT (usable by anyone who finds it on PyPI-style tooling) while README.md claims 'Proprietary - Who Visions LLC © 2026'; a downstream consumer or scanner picks either and gets it wrong.
- First fork: if a tool reads pyproject.toml's license field -> treats code as MIT-redistributable, else if it reads README.md -> treats it as proprietary
- Evidence: `pyproject.toml:10`, `README.md:310-313`
- Lens: licensing · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: pyproject.toml:10 has license = {text = "MIT"}; README.md ~310 states 'Proprietary - Who Visions LLC © 2026'. Direct contradiction confirmed.

### WG-0848 · P1 · defend · effort S

**Personal call transcripts and session logs are committed inside a repo backing a public-facing product**

- Failure surface: scratchpad/ call transcripts and sessions/*.json conversation logs are tracked in git; anyone who clones or is given repo access (fleet peer, contractor, future open-sourcing) gets personal/private conversation content that was never meant to travel with the codebase.
- First fork: if repo access stays fully private -> exposure is limited, else if the repo is ever shared, forked, or partially open-sourced -> personal transcripts go with it
- Evidence: `scratchpad/ (git-tracked call_*.txt files)`, `sessions/`
- Lens: privacy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: `git ls-files scratchpad/` confirms tracked files like scratchpad/call_030938.txt etc; sessions/ directory also present in repo listing. Consistent with claim of committed transcripts/logs.
- #550 families: 75

### WG-0858 · P1 · defend · effort M

**/execute-code lets any unauthenticated caller spend Vertex tokens simulating arbitrary code**

- Failure surface: POST /execute-code has no auth, no rate limit, and no payload size cap; each call wraps the caller-supplied code in a prompt and calls Gemini via state.agent.prompt_service.generate_async — an anonymous scripted flood of requests directly and repeatedly bills Vertex AI with no throttle.
- First fork: if request volume stays low -> cost is negligible, else if a bot or scraper discovers the open route -> token spend scales with attacker-controlled traffic
- Evidence: `kaedra/api/main.py:980-997`, `cloudbuild.yaml:26`
- Lens: cost-tokens · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet_execute_code route (main.py ~980-997) has no auth dependency, no size cap, calls state.agent.prompt_service.generate_async(prompt) directly; cloudbuild.yaml:26 has --allow-unauthenticated. Confirmed.
- #550 families: 62

### WG-0868 · P1 · defend · effort M

**Keyword-only 'needs_deep_thinking' heuristic lets any public caller force expensive Pro+high-thinking routing**

- Failure surface: PromptService.generate_async auto-escalates model_key to 'pro' with thinking_level 'high' whenever the caller's own prompt text contains any of a fixed keyword list, with no auth or cost ceiling; since prompts reach this via public routes, callers can trivially and repeatedly trigger the most expensive tier.
- First fork: if the prompt avoids the keyword list -> stays on cheap flash/minimal thinking, else if it contains a trigger word (attacker-controlled) -> escalates to Pro/high on every call
- Evidence: `kaedra/services/prompt.py:96-99`, `kaedra/services/prompt.py:160-167`
- Lens: cost-tokens · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: needs_deep_thinking() (prompt.py:96-99) checks any(kw in q_lower for kw in DEEP_THINKING_KEYWORDS); generate_async (~163-166) escalates target_model_key='pro', actual_thinking_level='high' when that's true and no explicit model_key/thinking_level given. No auth/cost ceiling visible in this function.
- #550 families: 60

### WG-0878 · P1 · defend · effort S

**PolicyEngine's hardcoded example prod-DB id doesn't match real Notion workspace ids, so the write-risk gate can never f…**

- Failure surface: policy.py flags a Notion write as high-risk only if the database_id contains the literal substring '2e7ca671', but real VeilVerse page/db ids seen in NOTION_QA_REPORT.md start '2e5ca671...' — a one-character-off placeholder means the intended prod-write safeguard structurally never matches real data even where it is wired in.
- First fork: if a real write's database_id happens to contain '2e7ca671' (never, per observed ids) -> risk +50 fires, else -> every real prod write scores as low-risk 'Internal DB'
- Evidence: `kaedra/control/policy.py:29-35`, `NOTION_QA_REPORT.md:7-14`
- Lens: agent-doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: policy.py:29-31 checks `if "prod" in db_id or "2e7ca671" in db_id`; NOTION_QA_REPORT.md real ids observed start with 2e5ca671... and 2e6ca671..., never 2e7ca671. Confirmed structural mismatch.
- #550 families: 38

### WG-0888 · P1 · defend · effort M

**No rate-limiting middleware exists across ~62 public routes on a single gunicorn worker**

- Failure surface: kaedra/api/main.py registers dozens of routes with only CORSMiddleware; Dockerfile/gunicorn run with a single worker and timeout 0, so a burst of concurrent requests to any generate/execute-code/generate-image route can both exhaust the single worker and rack up unmetered Vertex spend simultaneously.
- First fork: if traffic stays low and sequential -> the single worker keeps up, else if concurrent requests arrive (legit spike or abuse) -> requests queue or fail while cost keeps accruing per accepted call
- Evidence: `kaedra/api/main.py:161-168`, `Dockerfile:20`
- Lens: cost-tokens · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: main.py:161-168 only registers CORSMiddleware (allow_origins=['*']), no rate limiting. Dockerfile:20 runs `gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 0`. Confirmed single worker, no timeout, no rate limit middleware.

### WG-0897 · P1 · defend · effort S

**Five test scripts import modules relocated to legacy/ and will ImportError on any run attempt**

- Failure surface: tests/smoke_test.py, stress_test_live.py, test_audit_logic.py, test_lifx_mock.py, and verify_full_simulation.py still `import` names like universe_text that were moved under legacy/ months ago; running any of them raises ImportError immediately, so they've been silently dead since the move with nothing flagging it.
- First fork: if someone runs one of these five scripts -> it ImportErrors at the top before any assertion runs, else if nobody runs them -> they sit as false evidence of test coverage
- Evidence: `tests/smoke_test.py:10 (ModuleNotFoundError: universe_text)`, `tests/stress_test_live.py:12`, `tests/test_audit_logic.py:5`, `tests/test_lifx_mock.py:18`, `tests/verify_full_simulation.py:5,10`, `legacy/universe_text.py (relocated module)`
- Lens: testing-ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Ran all five scripts directly: universe_text.py is indeed only under legacy/universe_text.py now. smoke_test.py, stress_test_live.py, test_audit_logic.py, test_lifx_mock.py all raise ModuleNotFoundError: No module named 'universe_text' at import time exactly as claimed. verify_full_simulation.py errors first on a missing 'rich' dependency but also imports universe_text later in the file, consisten
- #550 families: 82

### WG-0906 · P1 · defend · effort S

**pre-commit relay claim-guard fails open and its opt-in flag is unset in this clone**

- Failure surface: hooks/pre-commit only blocks a commit if `relay` (or the nougen_relay module) is installed AND `git config nougen.requireClaim true` was set locally; this clone's `git config --get nougen.requireClaim` returns nothing, so the guard the hook's own comments say was built after 'four duplications in two days' is not actually armed here.
- First fork: if nougen.requireClaim is set true and relay/nougen_relay is importable -> a conflicting claim blocks the commit, else (this clone's actual state) -> the guard silently no-ops on every commit
- Evidence: `hooks/pre-commit:1-40 (full file, no requireClaim check in code path)`, `hooks/pre-commit:12 (requireClaim mentioned only in comment)`, `git config --get nougen.requireClaim -> exit 1 (unset)`, `python3 -c 'import nougen_relay' -> ModuleNotFoundError`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Read hooks/pre-commit (40 lines) in full: it never actually reads git config nougen.requireClaim in code — that config key only appears in a comment referring to a different, unimplemented gate for a *missing own* claim (the code fails open unconditionally when relay/nougen_relay isn't importable, and otherwise blocks purely on `relay guard --staged` returning status 3, with no requireClaim check 
- #550 families: 25

### WG-0914 · P1 · defend · effort M

**kaedra_wake_daemon.py only print()s inbound fleet directives with no ack, wake action, or shard capture**

- Failure surface: main() in kaedra_wake_daemon.py detects an inbound ping and prints a formatted banner to stdout, but takes no further action — no relay_ack, no shards_capture, no actual wake of an agent process; if run under cron/systemd with stdout unattached to any log sink, an inbound directive is detected and then permanently lost.
- First fork: if the daemon runs attached to a visible terminal someone is watching -> the printed directive gets noticed, else if run headless/unattended (its intended use) -> the directive is captured nowhere and never acted on
- Evidence: `tools/kaedra_wake_daemon.py:1-60 (full file — print-only, no ack/shard/wake calls)`
- Lens: agent-doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Read the full file (60 lines): main() watches ~/.nougen/kaedra_inbox/ for up to 600s, and on detecting new/modified JSON files it only does print('KAEDRA FLEET INBOUND DETECTED...') and per-hit print() lines, then returns 0. There is no call to relay_ack, shards_capture, or any wake/dispatch mechanism anywhere in the file. Matches the claim exactly.
- #550 families: 21

### WG-0922 · P1 · defend · effort M

**/upload accepts any file with no size/type checks and serves it publicly under the kaedra domain**

- Failure surface: An anonymous POST to /upload writes an arbitrary file (any size, any content-type) under UPLOAD_DIR and immediately serves it at /uploads/<name> on the CLOUD_RUN_URL; the public brand domain becomes an open file/content host.
- First fork: if uploaded content is benign -> ephemeral storage fills silently, else if it's phishing/malware content -> it's served from a trusted-looking Who Visions domain
- Evidence: `kaedra/api/main.py:181-196`
- Lens: product-public-surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: upload_file has no auth, no size cap, no content-type/extension check; only does basic filename sanitization, writes to UPLOAD_DIR, mounted as static /uploads.

### WG-0930 · P1 · defend · effort S

**Product version drifts across four sources with no single source of truth**

- Failure surface: pyproject.toml says 0.0.6, the public agent.json says 0.0.9, README.md banner says v7.15, SETUP.md says v4.1 (Orchestrator Edition) — a fleet agent or partner citing 'the current version' gets a different, equally official-looking answer depending which file it reads.
- First fork: if an agent trusts pyproject.toml -> reports 0.0.6, else if it trusts the public agent.json -> reports 0.0.9
- Evidence: `pyproject.toml:7`, `kaedra/api/main.py:1140`, `README.md:1`, `SETUP.md:3`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: pyproject.toml:7 version="0.0.6"; agent.json version "0.0.9"; README.md:1 'v7.15'; SETUP.md:3 'Version: 4.1'. All four confirmed distinct.

### WG-0938 · P1 · elevate · effort S

**Fix mprocs.yaml's pylint watcher to run on the actual deploy platform instead of Windows-only `py -3.12`**

- Failure surface: mprocs.yaml's pylint proc shells out to `py -3.12 -m pylint kaedra --score=y`, a Windows-only launcher, even though the real deploy target is Linux Cloud Run (python:3.12-slim in the Dockerfile); on any Linux dev machine or CI runner this proc simply fails to launch, so the one lint-adjacent check in the repo doesn't run where it matters.
- First fork: if run on a Windows dev box -> `py -3.12` resolves and pylint runs manually, else on any Linux machine (Cloud Run's actual OS, or a Linux CI runner) -> the command isn't found and the proc fails silently
- Evidence: `mprocs.yaml:35-38 (pylint proc: shell: 'py -3.12 -m pylint kaedra --score=y')`, `Dockerfile:2 (FROM python:3.12-slim — Linux)`
- Lens: testing-ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: mprocs.yaml confirmed to contain `shell: "py -3.12 -m pylint kaedra --score=y"` under a pylint proc entry (Windows py launcher syntax). Dockerfile:2 confirms `FROM python:3.12-slim`, a Linux base image, matching the claimed platform mismatch exactly.

### WG-0946 · P1 · defend · effort M

**SyncManager.upsync() blind-pushes local dirty entities to Notion on process exit with no conflict check**

- Failure surface: upsync() is registered via atexit and pushes every dirty local SQLite entity to Notion whenever the process ends, with no last-edited-time comparison against Notion's current state; a stale local process exiting after a newer Notion edit silently overwrites the canon page.
- First fork: if Notion wasn't touched externally since the local dirty flag was set -> upsync is harmless, else if someone edited the same page in Notion in the meantime -> upsync clobbers it on exit
- Evidence: `kaedra/services/sync_manager.py:51`, `kaedra/services/sync_manager.py:177-205`
- Lens: canon-lore · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: atexit.register(self.upsync) at line 51; upsync() pushes all self._dirty_ids to Notion (lines ~177-205) with no last-edited-time or conflict comparison visible anywhere in the function.
- #550 families: 85

### WG-0954 · P1 · defend · effort M

**55 VeilVerse Notion pages sit 'Untitled' with missing Name property, never remediated**

- Failure surface: NOTION_QA_REPORT.md documents dozens of canon pages missing their Name property, breaking any downsync/lookup keyed on title; the report exists but nothing in sync_manager.py or notion.py enforces or backfills the Name field.
- First fork: if downstream code assumes every entity has a Name -> lookups/joins silently fail or mis-key for these ~55 rows, else it's never queried by title and stays latent
- Evidence: `NOTION_QA_REPORT.md:1-16`
- Lens: canon-lore · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: NOTION_QA_REPORT.md states 'Total Issues Found: 55' under Uncategorized, listing many 'Untitled ... Missing Name' entries, matching claim exactly.
- #550 families: 3
