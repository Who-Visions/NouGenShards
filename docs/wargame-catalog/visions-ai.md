# War-game candidates — Visions-ai

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

76 candidates · P0 18 · P1 58 · P2 0 · P3 0 · defend 54 · elevate 22

| id | P | kind | title |
|---|---|---|---|
| WG-0006 | P0 | defend | Rotate and purge the committed AI Studio key without breaking the three files that use it |
| WG-0022 | P0 | elevate | Resolve the split-brain GCP project (endless-duality vs mineral-subject vs who-visions-dav1d) end to end |
| WG-0037 | P0 | elevate | Cut the Dockerfile CMD over to visions/api/app.py without breaking /query callers |
| WG-0051 | P0 | defend | Survive the next fleet-wide model-id sweep without rewriting router.py's RETIRED entries again |
| WG-0063 | P0 | defend | Pin one Python across blade, phoebus, whoart and the container: 3.14 bytecode is already committed |
| WG-0074 | P0 | defend | Rotate the committed AI Studio key and purge it from code, tests and docs/logs history |
| WG-0085 | P0 | defend | Refresh docs/CREDITS_AND_COSTS.md before it drives a real spend decision |
| WG-0096 | P0 | elevate | Wire usage_tracker.py's cost accounting into the production API path, not just the CLIs |
| WG-0106 | P0 | defend | Stop AGENTS.md from sending every agent lane to run live-billing tests |
| WG-0116 | P0 | defend | Rotate the committed AI Studio key and stop Config.validate() from re-requiring one |
| WG-0124 | P0 | defend | Move sentinel_loop.py's heartbeat writes off the production interaction_logs table |
| WG-0132 | P0 | elevate | Add a test step to cloudbuild.yaml before it deploys straight to public Cloud Run |
| WG-0140 | P0 | elevate | Enable .githooks/prepare-commit-msg by default so fresh clones don't commit unstamped |
| WG-0148 | P0 | defend | Fix the dormant "unrecognized machine" guard that only activates after the first handoff leg |
| WG-0156 | P0 | defend | Stop pooling anonymous callers into the shared "user"/"default_user" memory bucket |
| WG-0164 | P0 | elevate | Confirm visions/core/router.py's audit() actually runs somewhere before the next model-id sweep |
| WG-0172 | P0 | defend | Correct A2A_IMPLEMENTATION.md's "Optional" bearer auth to "none, ever" |
| WG-0180 | P0 | defend | Reconcile root app.py's real surface with the A2A/Bandit docs that describe visions/api/app.py |
| WG-0367 | P1 | elevate | Put an auth gate on public /query without cutting off fleet peers that send no ID token |
| WG-0383 | P1 | defend | Run any Visions deploy script on blade without flipping gcloud's global account and project for other fleet repos |
| WG-0399 | P1 | elevate | Add a secret-scanning gate to the .githooks path that all fleet lanes commit through |
| WG-0415 | P1 | elevate | Retire the Vertex Reasoning Engine path or make deploy.py stop minting a new engine per run |
| WG-0431 | P1 | defend | Stop the sentinel writing STATUS_CHECK rows into production interaction_logs every five minutes |
| WG-0447 | P1 | elevate | Add a test + router.audit gate to Cloud Build without blocking on live-API tests |
| WG-0462 | P1 | elevate | Wire router.route()/escalate() into agent.query before gemini-3-flash-preview's two-week retirement notice lands |
| WG-0475 | P1 | defend | Purge committed runtime artifacts (.pyc, SYNAPSE.log, os.devnull, .db, watch HTML) without breaking the indexer cache |
| WG-0488 | P1 | defend | Remove the knowledge_base/temp_repo gitlink that has no .gitmodules before it trips relay clones and Cloud Build |
| WG-0500 | P1 | defend | Pull the billing exports with credit IDs out of the repo and out of the FAISS index |
| WG-0512 | P1 | defend | Stop AgentConnector from downgrading to unauthenticated POSTs and guessing endpoints when a peer moves |
| WG-0524 | P1 | elevate | Move fleet peer discovery from ten hardcoded Cloud Run URLs to agent cards plus the relay registry |
| WG-0536 | P1 | elevate | Deploy from a tagged, audited ref instead of `git pull origin main` on Cloud Shell |
| WG-0548 | P1 | defend | Bring the second fleet machine into the handoff registry without a refused commit at 2 AM |
| WG-0560 | P1 | defend | Reconcile Bandit's cross-project IAM: the integration doc grants roles in mineral-subject while deploys target endless-… |
| WG-0572 | P1 | defend | Refresh or retire the frozen handoff docs that mislead Gemini agents about topology (Firestore, Reasoning Engine, 2025-… |
| WG-0583 | P1 | defend | Pin VERTEX_PROJECT_ID in cloudbuild.yaml so Cloud Run memory does not land in the wrong project's buckets |
| WG-0594 | P1 | elevate | Collapse four pricing tables into one registry keyed by router.py model ids |
| WG-0605 | P1 | elevate | Ship or retire the Firestore hot layer that README, .gemini and firestore.rules promise |
| WG-0616 | P1 | defend | Make /v1/chat/completions carry user_id so fleet peers stop sharing one memory row |
| WG-0627 | P1 | defend | Give talk_to_agent honest failure, retries and idempotency before Visions relays fleet answers |
| WG-0638 | P1 | elevate | Migrate fleet peer discovery from 10 hardcoded Cloud Run URLs to A2A agent cards and the relay registry |
| WG-0649 | P1 | defend | Normalize memory timestamps to UTC across blade, phoebus, whoart and Cloud Run writers |
| WG-0660 | P1 | defend | Purge Sentinel heartbeat rows from interaction_logs, GCS logs/ and the markdown journal |
| WG-0671 | P1 | defend | Make deploy.py update the Reasoning Engine in place and reap the 18 orphaned engines |
| WG-0682 | P1 | defend | Make ralph_watchdog and Deep Scour actually import what they certify |
| WG-0693 | P1 | defend | Make /health reflect set_up failure and memory tier state instead of a constant 'online' |
| WG-0704 | P1 | defend | Audit COMPLETE/READY done-markers against live evidence and demote the false ones |
| WG-0715 | P1 | elevate | Stand up real alerting (5xx, 429, cold-start, spend) for visions-assistant-service |
| WG-0726 | P1 | defend | Make fleet_dashboard derive node status from live A2A probes instead of constants |
| WG-0736 | P1 | defend | Stop two infra scripts from regenerating tracked firestore.rules and visions-api.yaml with conflicting content |
| WG-0746 | P1 | defend | Scrub the committed visions_short_term.db and CURRENT_SESSION.md and fence memory writes from git |
| WG-0756 | P1 | defend | Add a guard that fails when router.py RETIRED entries become self-referential after a sweep |
| WG-0766 | P1 | elevate | Retire the Reasoning Engine path or the Cloud Run path so one memory/RAG topology is live |
| WG-0776 | P1 | defend | Stop last-deployer-wins overwrites of the shared GCS vector_store from blade, phoebus and whoart |
| WG-0786 | P1 | defend | Point visions-api.yaml's backend at the same Cloud Run revision the fleet actually uses |
| WG-0796 | P1 | defend | Gate the keyword-triggered image-generation branch behind cost/rate controls |
| WG-0806 | P1 | defend | Make the JS tiered rate limiter fail closed, not open, and actually wire it in |
| WG-0816 | P1 | elevate | Trim .gcloudignore so curriculum/exams/transcripts/council don't ship into every Cloud Run build |
| WG-0826 | P1 | elevate | Wire the Cloud Tasks rate-limiting queues fix_visions_infrastructure.sh creates into the request path |
| WG-0836 | P1 | defend | Version or gate deploy.py's Reasoning Engine creation so it stops silently forking spend |
| WG-0846 | P1 | defend | Loosen-safety-settings decision needs a documented governance sign-off |
| WG-0856 | P1 | defend | Add root app.py to ralph_watchdog's REQUIRED_MODULES list |
| WG-0866 | P1 | defend | Reconcile README/firestore.rules Firestore memory claims with the SQLite+GCS+BQ code |
| WG-0876 | P1 | defend | Make ralph_watchdog actually import required modules, not just resolve their spec |
| WG-0886 | P1 | defend | Separate live/paid test scripts from the pytest-safe suite before anyone runs `pytest tests/` |
| WG-0895 | P1 | defend | Declare memory_cloud.py's real dependencies (bigquery, etc.) in requirements.txt |
| WG-0904 | P1 | defend | Stop committing os.devnull as if it were meaningful test evidence |
| WG-0912 | P1 | elevate | Add a regression test replaying the rebase scenario that once corrupted commit trailers |
| WG-0920 | P1 | defend | Point AGENTS.md's Memory System section at the real memory_cloud.py path |
| WG-0928 | P1 | defend | Surface tools/agent_connect.py's silent auth-downgrade instead of logging a warning and continuing |
| WG-0936 | P1 | defend | Block client-supplied image_path/video_path from reading arbitrary container files |
| WG-0944 | P1 | defend | Resolve the GCP project split-brain before it silently misroutes memory or billing |
| WG-0952 | P1 | defend | Make the triage failure path preserve is_high_risk uncertainty instead of defaulting to false |
| WG-0960 | P1 | defend | Give agent.py's tool loop a real terminal response instead of a generic apology after 3 turns |
| WG-0967 | P1 | defend | Reconcile visions-api.yaml's single documented tier route with the 5-tier pricing it claims to gate |
| WG-0974 | P1 | elevate | Decide and document one deploy target between Cloud Run and Vertex Reasoning Engine |
| WG-0980 | P1 | defend | Add a LICENSE before shipping vendored transcripts and other-model writing samples |

---

### WG-0006 · P0 · defend · effort M

**Rotate and purge the committed AI Studio key without breaking the three files that use it**

- Failure surface: AIzaSy... key is live in structured_gemini.py __main__, tests/test_ai_studio.py (executes at import, so pytest collection burns quota) and a doc; anyone with repo read can drain the AI Studio free tier or attach billing abuse to the account. Dave notices via an AI Studio quota alert or a surprise invoice.
- First fork: if you observe the key still accepted by genai.Client(api_key=...) -> rotate in AI Studio first, then purge history (filter-repo) and force-push with a fleet-wide reclone notice; else (already revoked) -> purge history only and add the pattern to a pre-commit scan
- Evidence: `visions/modules/genai/structured_gemini.py`, `tests/test_ai_studio.py`, `docs/logs/SESSION_SUMMARY.md`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Key AIzaSy[REDACTED] literally present in all three files (structured_gemini.py:219, tests/test_ai_studio.py:11, docs/logs/SESSION_SUMMARY.md:224); test file calls genai.Client(api_key=API_KEY) at module top level.
- #550 families: 76

### WG-0022 · P0 · elevate · effort L

**Resolve the split-brain GCP project (endless-duality vs mineral-subject vs who-visions-dav1d) end to end**

- Failure surface: config.py defaults mineral-subject; .env.example, deploy.py, all deploy_*.sh/ps1, create_bq_schema, vision_tools default endless-duality; visions_memory_gcp_sync.py targets who-visions-dav1d; config hardcodes project number 885670388176 in REASONING_ENGINE_RESOURCE. Buckets, BQ and quotas silently split.
- First fork: if you observe live traffic in both projects' Cloud Run/BQ -> pick the one holding memory data, migrate the other's buckets, then delete defaults everywhere; else -> set one default and fail Config.validate() when VERTEX_PROJECT_ID is unset
- Evidence: `visions/core/config.py`, `.env.example`, `scripts/visions_memory_gcp_sync.py`
- Lens: infra · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified three-way project split: config.py defaults mineral-subject-487519-v6; .env.example, deploy.py, deploy_visions_saas.sh, create_bq_schema.py, and multiple tools/*.py default to endless-duality-480201-t3; scripts/visions_memory_gcp_sync.py defaults to who-visions-dav1d; config.py also hardcodes project number 885670388176 in REASONING_ENGINE_RESOURCE, matching agent_connect.py's Cloud Run U
- #550 families: 12

### WG-0037 · P0 · elevate · effort M

**Cut the Dockerfile CMD over to visions/api/app.py without breaking /query callers**

- Failure surface: Cloud Run serves root app.py (/health, /query) while A2A_IMPLEMENTATION.md, the agent card, /v1/chat/completions and /render live only in visions/api/app.py; peers hitting /chat get 404 and AgentConnector's fallback chain guesses endpoints. Past 'Fix: Dockerfile Gunicorn entry point path' shows this already bit once.
- First fork: if you observe /query traffic from peers in logs -> mount both routers in one app and keep /query as alias; else -> switch CMD to visions.api.app and delete root app.py
- Evidence: `app.py`, `visions/api/app.py`, `Dockerfile`
- Lens: deploy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Dockerfile:37 CMD ["python","app.py"] serves the root app.py which only has /health and /query, while visions/api/app.py (not the served entrypoint) has /chat, /v1/chat, /v1/chat/completions, /agent-card, /render, matching A2A_IMPLEMENTATION.md's documented endpoints -- confirming the entrypoint mismatch.
- #550 families: 32

### WG-0051 · P0 · defend · effort S

**Survive the next fleet-wide model-id sweep without rewriting router.py's RETIRED entries again**

- Failure surface: A sed sweep on 2026-08-02 turned the registry's RETIRED ids into self-references; router.py now carries only an in-band comment as protection. The next lane doing a bump on blade or phoebus repeats it.
- First fork: if you observe test_router.py lacking a test that RETIRED entries reference ids absent from STABLE/PREVIEW -> add it and a pre-commit check that router.py diffs require a trailer; else -> add a .gitattributes merge=ours marker and document in AGENTS.md
- Evidence: `visions/core/router.py`, `tests/test_router.py`, `AGENTS.md`
- Lens: model-cutover · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: router.py's own comments explicitly document the past incident ('that happened once, during the merge that added these lines... the report said gemini-3.6-flash was shut down in favour of gemini-3.6-flash') and warn 'DO NOT run a model-id find-and-replace over this file' as the only protection; tests/test_router.py has no test asserting RETIRED replacement ids are non-retired/existing, matching th

### WG-0063 · P0 · defend · effort S

**Pin one Python across blade, phoebus, whoart and the container: 3.14 bytecode is already committed**

- Failure surface: Committed memory_cloud.cpython-314.pyc proves a machine runs Python 3.14 while Dockerfile is 3.12-slim and fix_python_version.bat exists; faiss-cpu/langchain wheels lag new Pythons so local tests pass or fail depending on which box committed.
- First fork: if you observe `py -0` on blade listing 3.14 as default -> add .python-version 3.12 and make the .bat launchers use py -3.12; else -> add .python-version and a ralph check on sys.version
- Evidence: `visions/modules/mem_store/__pycache__`, `fix_python_version.bat`, `Dockerfile`
- Lens: toolchain · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: git-tracked visions/modules/mem_store/__pycache__/memory_cloud.cpython-314.pyc proves a 3.14 build occurred; Dockerfile pins python:3.12-slim; fix_python_version.bat exists and recreates a venv to fix a Python version mismatch (targets 3.13 in the script, still evidencing the cross-machine version drift).
- #550 families: 79

### WG-0074 · P0 · defend · effort M

**Rotate the committed AI Studio key and purge it from code, tests and docs/logs history**

- Failure surface: AIzaSy… is live in structured_gemini.py, tests/test_ai_studio.py and docs/logs/SESSION_SUMMARY.md, and Dockerfile ships all three into the image; anyone with repo or image read can burn the 250 RPD image quota and the AI Studio fallback that QUOTA_MANAGEMENT.md relies on.
- First fork: if the key still authenticates -> rotate first, then purge via filter-repo and add a secret-scan hook; else -> purge and add the hook
- Evidence: `visions/modules/genai/structured_gemini.py`, `tests/test_ai_studio.py`, `docs/logs/SESSION_SUMMARY.md`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: The literal key 'AIzaSy[REDACTED]' is committed verbatim in visions/modules/genai/structured_gemini.py:219, tests/test_ai_studio.py:11, and docs/logs/SESSION_SUMMARY.md:224, exactly as claimed.
- #550 families: 76

### WG-0085 · P0 · defend · effort S

**Refresh docs/CREDITS_AND_COSTS.md before it drives a real spend decision**

- Failure surface: The doc ("Last Updated 2025-12-07") lists $1,584.58 in credits with expiries of 2026-03-03 and 2026-03-05 — both already past as of 2026-09-25 — yet nothing in code re-checks real billing state before the public endpoint keeps serving; anyone who reads this doc to gauge runway is working from a 6-month-stale, now-false budget.
- First fork: if you observe the doc still cited after its own expiry dates -> pull live billing via the Cloud Billing API instead of a static markdown table; else if credits were renewed -> update the doc with the new grant and expiry.
- Evidence: `docs/CREDITS_AND_COSTS.md`
- Lens: Cost/quota/token economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/CREDITS_AND_COSTS.md dated 2025-12-07, lists $1584.58 total across 3 credits with two expiries (2026-03-03, 2026-03-05) that are indeed past as of 2026-09-25.
- #550 families: 65

### WG-0096 · P0 · elevate · effort M

**Wire usage_tracker.py's cost accounting into the production API path, not just the CLIs**

- Failure surface: get_tracker()/DAILY_LIMITS is only imported by visions/cli/cli.py, cli_enhanced.py and cli_visual.py; app.py, visions/api/app.py and agent.py — the code that actually serves the public, --allow-unauthenticated Cloud Run traffic — never records a single call's cost or checks a daily limit.
- First fork: if you observe production spend with zero rows in the tracker's daily-usage store -> call record_usage() from inside VisionsAgent.query()/generate_image() on the hot path; else if a separate BQ-based tracker is preferred -> route through memory_cloud.py's existing BQ writer instead.
- Evidence: `usage_tracker.py`, `visions/core/agent.py`, `app.py`
- Lens: Cost/quota/token economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: grep shows usage_tracker/get_tracker/DAILY_LIMITS only imported by visions/cli/cli*.py and usage_tracker.py itself; no import in visions/core/agent.py or app.py.
- #550 families: 65

### WG-0106 · P0 · defend · effort S

**Stop AGENTS.md from sending every agent lane to run live-billing tests**

- Failure surface: AGENTS.md's Development Workflow says "Run tests using python tests/test_name.py" with no caveat; tests/test_veo3*.py generate real $1.20-$3.20 Veo clips and tests/test_ai_studio.py generates a real $0.134 image using a hardcoded, already-leaked API key — a lane following this doctrine literally burns money and quota on a compromised key every time it "runs the tests".
- First fork: if you observe an agent lane invoking tests/test_veo3.py or test_ai_studio.py to "verify tests pass" -> mark these scripts clearly as paid/manual-only and exclude from any "run tests" instruction; else if they're meant as live smoke tests -> require an explicit opt-in flag before they call the API.
- Evidence: `AGENTS.md`, `tests/test_veo3.py`, `tests/test_ai_studio.py`
- Lens: Cost/quota/token economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: AGENTS.md:24 says 'Run tests using python tests/test_name.py' with no caveat; tests/test_veo3.py and tests/test_ai_studio.py exist, latter has hardcoded API key.

### WG-0116 · P0 · defend · effort S

**Rotate the committed AI Studio key and stop Config.validate() from re-requiring one**

- Failure surface: A live-looking Google API key is committed in visions/modules/genai/structured_gemini.py, tests/test_ai_studio.py and docs/logs/SESSION_SUMMARY.md; Config.validate() hard-requires a key whenever ENABLE_AI_STUDIO_FALLBACK (hardcoded True) is set, so simply revoking the leaked key without also supplying a fresh one breaks startup validation and the documented 429 fallback path simultaneously.
- First fork: if you observe the key still valid -> rotate it, purge all 3 references, and make ENABLE_AI_STUDIO_FALLBACK configurable so validate() doesn't hard-fail without one; else if already rotated -> confirm the 3 files were actually updated, not just the live key revoked.
- Evidence: `visions/modules/genai/structured_gemini.py`, `tests/test_ai_studio.py`, `visions/core/config.py`
- Lens: Cost/quota/token economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Same literal API key AIzaSy[REDACTED] found in all 3 files; config.py:121 ENABLE_AI_STUDIO_FALLBACK=True hardcoded, validate() at line 160 requires key when fallback enabled.
- #550 families: 76

### WG-0124 · P0 · defend · effort S

**Move sentinel_loop.py's heartbeat writes off the production interaction_logs table**

- Failure surface: pulse_check() calls CloudMemoryManager.save_interaction every 5 minutes if run continuously, writing into the same BigQuery visions_memory.interaction_logs table and GCS bucket as real user conversations, with no tag distinguishing synthetic heartbeats — docs/logs/CURRENT_SESSION.md already shows "sentinel"/"HEARTBEAT_DEEP_SCOUR" rows interleaved with real test turns under the same log, confirming the comingling happens.
- First fork: if you observe heartbeat_* rows in interaction_logs or the shared journal -> route sentinel writes to a separate table/prefix; else if sentinel isn't actually running in prod -> document that clearly so nobody schedules it as-is.
- Evidence: `sentinel_loop.py`, `docs/logs/CURRENT_SESSION.md`, `visions/modules/mem_store/memory_cloud.py`
- Lens: Cost/quota/token economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: sentinel_loop.py pulse_check() calls self.memory.save_interaction(user_id='sentinel_system',...); docs/logs/CURRENT_SESSION.md shows sentinel_system and HEARTBEAT_DEEP_SCOUR entries interleaved with real turns.

### WG-0132 · P0 · elevate · effort M

**Add a test step to cloudbuild.yaml before it deploys straight to public Cloud Run**

- Failure surface: cloudbuild.yaml has exactly 3 steps — docker build, push, gcloud run deploy --allow-unauthenticated — with no test/lint step anywhere, and there is no .github/workflows directory either; a change that breaks agent.py's import (as already happened once per .handoffs/README.md) deploys straight to the public URL with nothing in the pipeline to catch it.
- First fork: if you observe a deploy following a change that fails `python -c "import visions.api.app"` -> add that check (and ideally tests/test_router.py) as a cloudbuild step that blocks the push on failure; else if speed is prioritized over safety -> at minimum alert on deploy so someone watches.
- Evidence: `cloudbuild.yaml`, `.handoffs/README.md`
- Lens: Testing/CI gaps · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml has exactly 3 build/push/deploy steps with --allow-unauthenticated and no test/lint step; no .github/workflows directory exists; .handoffs/README.md references agent.py import breakage.
- #550 families: 81

### WG-0140 · P0 · elevate · effort S

**Enable .githooks/prepare-commit-msg by default so fresh clones don't commit unstamped**

- Failure surface: The Machine/Agent commit-trailer doctrine only activates after a human runs `git config core.hooksPath .githooks`, which "cannot be committed" per the README's own text; every fresh clone (a new fleet machine, a CI runner, a new agent lane) commits with zero attribution until someone remembers that one command, defeating the exact problem ("nothing announced, because nothing was watching") the hook was built to solve.
- First fork: if you observe a commit landing with unknown-machine/unknown-agent trailers after a fresh clone -> add a repo-level bootstrap (Makefile target, post-clone script docs step, or a CI check that fails unattributed commits) rather than relying on memory; else if core.hooksPath truly can't be defaulted -> add a pre-flight check in AGENTS.md's own onboarding step.
- Evidence: `.githooks/prepare-commit-msg`, `README.md`
- Lens: Agent doctrine/multi-agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .githooks/prepare-commit-msg exists and implements the trailer-stamping logic; README.md exists. The core claim (hooksPath must be manually configured, not committable) is a standard git limitation consistent with the doc's framing; evidence supports it.

### WG-0148 · P0 · defend · effort S

**Fix the dormant "unrecognized machine" guard that only activates after the first handoff leg**

- Failure surface: prepare-commit-msg's guard checks `KNOWN=$(ls .handoffs | ...)` and only refuses an unrecognized machine when `$KNOWN` is non-empty; .handoffs/ currently holds only README.md (no leg files yet), so KNOWN is empty and the entire refuse-unknown-machine safeguard is silently inert today. The moment the first leg lands, some previously-fine machine could suddenly start being refused if its name was never in that first leg.
- First fork: if you observe the first handoff leg get created -> immediately audit which machine names are now "known" versus which real machines exist, and seed all current fleet machines before relying on the guard; else if the guard is meant to bootstrap loosely -> document that today's inert state is expected, not a bug waiting to surprise someone.
- Evidence: `.githooks/prepare-commit-msg`, `.handoffs/README.md`
- Lens: Agent doctrine/multi-agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .githooks/prepare-commit-msg confirmed: KNOWN=$(ls "$DIR" ...) and the guard 'if [ -n "$KNOWN" ] && ! ... ' only fires when KNOWN is non-empty (lines 105-106); .handoffs/ confirmed contains only README.md, no leg files, so KNOWN is currently empty and the guard is inert exactly as claimed.
- #550 families: 20

### WG-0156 · P0 · defend · effort M

**Stop pooling anonymous callers into the shared "user"/"default_user" memory bucket**

- Failure surface: app.py defaults QueryRequest.user_id to "user" and visions_assistant/agent.py defaults get_chat_response's user_id to "default_user"; every caller who omits the field reads/writes the same SQLite row, GCS blob prefix and BigQuery rows, so one caller's get_recent_context() can surface another caller's prior prompts/responses. docs/logs/CURRENT_SESSION.md shows exactly this: unrelated test/sentinel/user turns interleaved under the same "user" identity.
- First fork: if you observe two distinct callers both omitting user_id -> require a real, server-issued id and reject the request otherwise; else if defaults must stay for back-compat -> namespace them per-session, never per-deployment.
- Evidence: `app.py`, `visions_assistant/agent.py`, `docs/logs/CURRENT_SESSION.md`
- Lens: Privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py:21 defaults user_id='user'; visions_assistant/agent.py:28 defaults user_id='default_user'; docs/logs/CURRENT_SESSION.md exists with sentinel/user interleaving.

### WG-0164 · P0 · elevate · effort M

**Confirm visions/core/router.py's audit() actually runs somewhere before the next model-id sweep**

- Failure surface: router.py carries an in-band "DO NOT sweep this file" warning after a prior find-and-replace corrupted its own RETIRED entries into self-references (commit c365303); audit() exists to scan the codebase for retired/unknown model ids, but only tests/test_router.py imports router.py at all — nothing calls audit() as part of any deploy or CI step, so the exact class of bug that already happened twice (per known_failures) has no automated tripwire before a third occurrence.
- First fork: if you observe a new model-id sweep planned or in progress -> run router.audit() first and make it a required cloudbuild/CI step going forward; else if audit() is already scheduled somewhere not found in this scan -> confirm it and point AGENTS.md at it explicitly.
- Evidence: `visions/core/router.py`, `tests/test_router.py`
- Lens: Agent doctrine/multi-agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions/core/router.py confirmed contains explicit sweep-exclusion warnings ('a sweep will rewrite those entries', 'Exclude this path from any sweep.' near lines 62-66) and a real audit() function at line 243; tests/test_router.py confirmed to exist as the only importer found via repo-wide grep for 'audit(' outside router.py itself, supporting the claim that nothing but the test suite calls audit(
- #550 families: 100

### WG-0172 · P0 · defend · effort S

**Correct A2A_IMPLEMENTATION.md's "Optional" bearer auth to "none, ever"**

- Failure surface: The doc lists Authentication as Optional for /v1/chat/completions, but cloudbuild.yaml/deploy_cloud_run.ps1 deploy with --allow-unauthenticated and neither app.py nor visions/api/app.py ever reads an Authorization header; an integrator who reads "optional" as "can be enforced if I want" gets no enforcement at all.
- First fork: if you observe no auth code path in either FastAPI app -> fix the doc to say "none"; else if bearer checking exists elsewhere -> point the doc at it.
- Evidence: `A2A_IMPLEMENTATION.md`, `visions/api/app.py`, `cloudbuild.yaml`
- Lens: Product/UX/public surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: A2A_IMPLEMENTATION.md line 60 literally says 'Authentication: Optional (Bearer token for Cloud Run)'; cloudbuild.yaml and deploy_cloud_run.ps1 both use --allow-unauthenticated; no Authorization header read in either app.py.

### WG-0180 · P0 · defend · effort M

**Reconcile root app.py's real surface with the A2A/Bandit docs that describe visions/api/app.py**

- Failure surface: Dockerfile's CMD runs root app.py (only /health, /query); A2A_IMPLEMENTATION.md and BANDIT_INTEGRATION.md document /.well-known/agent.json, /chat, /v1/chat/completions which live only in visions/api/app.py. A fleet peer or SaaS customer integrating per those docs against the deployed Cloud Run URL gets 404 on every documented route but /health.
- First fork: if you observe the deployed image responds 404 to /.well-known/agent.json -> switch Dockerfile CMD to visions/api/app.py or merge the routes; else if root app.py is the intended contract -> rewrite the docs to match it.
- Evidence: `Dockerfile`, `app.py`, `A2A_IMPLEMENTATION.md`
- Lens: Product/UX/public surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Dockerfile CMD runs root app.py (only /health,/query); /.well-known/agent.json only exists in visions/api/app.py, documented in A2A_IMPLEMENTATION.md/BANDIT_INTEGRATION.md.

### WG-0367 · P1 · elevate · effort L

**Put an auth gate on public /query without cutting off fleet peers that send no ID token**

- Failure surface: cloudbuild.yaml deploys --allow-unauthenticated and root app.py has zero auth; AgentConnector peers fall back to unauthenticated POSTs when fetch_id_token fails, so turning on auth silently breaks Bandit/Rhea/Kam calls while leaving Visions an open Gemini Pro proxy today.
- First fork: if you observe peers already sending Authorization: Bearer <ID token> (Cloud Run logs show audience) -> flip to --no-allow-unauthenticated and grant run.invoker per peer SA; else -> add an app-level shared-secret header first, migrate peers, then flip IAM
- Evidence: `app.py`, `cloudbuild.yaml`, `tools/agent_connect.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml:29 has --allow-unauthenticated; app.py has no auth decorators/Depends on /query; agent_connect.py fetch_id_token wrapped in try/except that falls through to unauthenticated on failure (line 34-40), Authorization header only set when token obtained.
- #550 families: 20

### WG-0383 · P1 · defend · effort S

**Run any Visions deploy script on blade without flipping gcloud's global account and project for other fleet repos**

- Failure surface: deploy_visions_saas.sh and fix_visions_infrastructure.sh run `gcloud config set project endless-duality...` and `gcloud config set account whoentertains@gmail.com`; the next NouGenShards or Bandit deploy from the same shell targets the wrong project.
- First fork: if you observe `gcloud config get project` differing from the repo you are in after a Visions deploy -> switch scripts to --project/--account flags or a named configuration; else -> do it preemptively and add a post-run restore
- Evidence: `deploy_visions_saas.sh`, `fix_visions_infrastructure.sh`
- Lens: infra · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both deploy_visions_saas.sh:15-16 and fix_visions_infrastructure.sh:15-16 run gcloud config set project/account globally rather than scoping via --project/--account flags.

### WG-0399 · P1 · elevate · effort M

**Add a secret-scanning gate to the .githooks path that all fleet lanes commit through**

- Failure surface: The only hook is prepare-commit-msg (identity trailers); .gitignore lists credential filenames but nothing scans content, which is how AIzaSy... reached three files. Five agent lanes on three machines commit here.
- First fork: if you observe core.hooksPath set on every clone (relay init) -> add a pre-commit scanner in .githooks with the same POSIX constraints the existing hook documents; else -> put the scan in a Cloud Build/CI step first
- Evidence: `.githooks/prepare-commit-msg`, `.gitignore`, `tests/test_ai_studio.py`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: .githooks/prepare-commit-msg only stamps identity trailers (no content scanning visible in its header/body); .gitignore lists only credential filenames like service_account_key.json, not content patterns -- consistent with how the AIzaSy key in tests/test_ai_studio.py went uncaught.
- #550 families: 76

### WG-0415 · P1 · elevate · effort M

**Retire the Vertex Reasoning Engine path or make deploy.py stop minting a new engine per run**

- Failure surface: deploy.py calls ReasoningEngine.create() every run (orphan engines billed), REASONING_ENGINE_ID drifts three ways (config 7709..., .env.example and setup_env 5424...), and cloud_shell_deploy.sh ends with 'update agent.py manually'. vertexai.preview.reasoning_engines is the deprecated surface.
- First fork: if you observe more than one engine in tools/list_reasoning_engines.py output -> delete orphans, switch to update-in-place or drop the path for Cloud Run; else -> pin one id in Config and delete the dead env examples
- Evidence: `deploy.py`, `cloud_shell_deploy.sh`, `tools/list_reasoning_engines.py`
- Lens: deploy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: deploy.py:78 calls reasoning_engines.ReasoningEngine.create() unconditionally on each run; REASONING_ENGINE_ID differs between config.py (7709761240314150912) and .env.example/setup_env.py (542433066447011840), matching the claimed drift.
- #550 families: 29

### WG-0431 · P1 · defend · effort S

**Stop the sentinel writing STATUS_CHECK rows into production interaction_logs every five minutes**

- Failure surface: pulse_check calls save_interaction(user_id='sentinel_system') on a 300s interval, filling BQ, GCS logs/sentinel_system/ and CURRENT_SESSION.md with heartbeat noise that later feeds consolidation scripts and any recall.
- First fork: if you observe sentinel_system rows outnumbering real users in interaction_logs -> purge them and route heartbeats to a separate table; else -> add a heartbeat flag column and filter in consolidation
- Evidence: `sentinel_loop.py`, `docs/logs/CURRENT_SESSION.md`, `scripts/consolidate_visions_memory.py`
- Lens: runtime · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: sentinel_loop.py runs pulse_check on a 300s interval calling save_interaction(user_id='sentinel_system', prompt='STATUS_CHECK', ...), which writes to SQL, GCS, and markdown log per save_interaction's implementation; docs/logs/ contains session markdown files and scripts/consolidate_visions_memory.py exists as the consolidation path.

### WG-0447 · P1 · elevate · effort M

**Add a test + router.audit gate to Cloud Build without blocking on live-API tests**

- Failure surface: cloudbuild.yaml builds and deploys with no test step, no .github/workflows exists, and most tests/ hit live Veo/Gemini; a deploy of unimportable agent.py went live before. The pure tests (test_router.py, test_smart_router.py) are the only safe gate.
- First fork: if you observe test_router.py and test_smart_router.py pass in a fresh venv with mocks -> add them plus router.audit over visions/ tools/ as a Cloud Build step; else -> fix collection first, then gate
- Evidence: `cloudbuild.yaml`, `tests/test_router.py`, `test_smart_router.py`
- Lens: toolchain · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml has only docker build/push/deploy steps, no test step; no .github/workflows directory exists; tests/test_router.py and test_smart_router.py both exist at the given paths.

### WG-0462 · P1 · elevate · effort M

**Wire router.route()/escalate() into agent.query before gemini-3-flash-preview's two-week retirement notice lands**

- Failure surface: Config.MODEL_FLASH = gemini-3-flash-preview (PREVIEW rung 25) drives triage, grounding and Tiers 1-4; router.py has the registry and escalate() but zero production callers. When the preview is pulled every query 404s, exactly as the 36 shut-down ids did.
- First fork: if you observe router.route(Lane.TEXT) returning a STABLE id that passes the existing tool-loop test -> replace Config string constants in agent.py with route() and escalate on 404; else -> add a startup audit that refuses to boot on RETIRED ids
- Evidence: `visions/core/router.py`, `visions/core/config.py`, `visions/core/agent.py`
- Lens: model-cutover · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: visions/core/config.py sets MODEL_FLASH = 'gemini-3-flash-preview'; a repo-wide grep for router.route/router.escalate usage outside visions/core/router.py and tests found zero production callers, confirming the router.py registry/escalate() exist but are unwired.

### WG-0475 · P1 · defend · effort S

**Purge committed runtime artifacts (.pyc, SYNAPSE.log, os.devnull, .db, watch HTML) without breaking the indexer cache**

- Failure surface: Force-tracked __pycache__ (cpython-312 and -314), SYNAPSE.log, a captured unittest run named os.devnull, a binary SQLite db and a saved YouTube page are in git; they ship in the image and collide on every merge across machines.
- First fork: if you observe indexing_cache.json needed by build_index.py on the fleet box that runs the indexer -> keep it, purge the rest and add *.pyc/*.db to force-untrack; else -> purge all incl. the cache and rebuild once
- Evidence: `visions/modules/mem_store/__pycache__`, `os.devnull`, `temp_video/watch`
- Lens: hygiene · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git ls-files confirms tracked __pycache__/*.pyc files (both cpython-312 and cpython-314) under visions/modules/mem_store and other modules, plus SYNAPSE.log, os.devnull, and temp_video/watch all committed to git.

### WG-0488 · P1 · defend · effort S

**Remove the knowledge_base/temp_repo gitlink that has no .gitmodules before it trips relay clones and Cloud Build**

- Failure surface: A mode-160000 gitlink at knowledge_base/temp_repo with no .gitmodules makes `git submodule update`, some clone tooling and gcloud builds submit warn or fail, and the dir checks out empty so any ingester walking knowledge_base sees a phantom.
- First fork: if you observe git submodule status erroring on a fresh clone -> git rm --cached the gitlink and commit; else -> same, plus a test that no gitlinks exist
- Evidence: `knowledge_base/temp_repo`, `.gcloudignore`, `scripts/ingest_universal.py`
- Lens: toolchain · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: git ls-files -s shows knowledge_base/temp_repo as a mode-160000 gitlink entry, and no .gitmodules file exists in the repo root.

### WG-0500 · P1 · defend · effort S

**Pull the billing exports with credit IDs out of the repo and out of the FAISS index**

- Failure surface: knowledge_base/csv/ holds 'Credits - My Billing Account.csv' with credit IDs and 'Pricing for My Billing Account.csv'; build_index.py walks knowledge_base so these get embedded and uploaded to GCS vector_store, then surface in RAG answers to public callers.
- First fork: if you observe billing rows in vector_store index.pkl (grep after load) -> rebuild index without csv/ and re-upload before purging git; else -> purge from git and add csv/ to the indexer exclude list
- Evidence: `knowledge_base/csv`, `scripts/build_index.py`, `indexing_cache.json`
- Lens: secrets · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: knowledge_base/csv contains 'Credits - My Billing Account.csv' and 'Pricing for My Billing Account.csv'; scripts/build_index.py SOURCE_DIRS includes 'knowledge_base' and os.walk's it, so csv/ is swept in.
- #550 families: 76

### WG-0512 · P1 · defend · effort S

**Stop AgentConnector from downgrading to unauthenticated POSTs and guessing endpoints when a peer moves**

- Failure surface: On fetch_id_token failure the connector sends the prompt with no Authorization; on 404 it replays the message to /, /generate, /query, /api/chat. A rotated Cloud Run URL or a squatter on an old one receives fleet prompts with no error surfaced beyond a print.
- First fork: if you observe 'Auth Warning' prints in Cloud Logging -> fail closed on missing token and drop the fallback chain; else -> fail closed and log a structured peer-unreachable event to the relay
- Evidence: `tools/agent_connect.py`, `fleet_dashboard.py`, `test_fleet_connectivity.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/agent_connect.py calls google.oauth2.id_token.fetch_id_token wrapped in try/except that only prints '⚠️ Auth Warning' on failure (implying the request proceeds without a token), and has explicit fallback endpoint lists including '/generate', '/query', '/chat', '/v1/chat', '/api/chat'.
- #550 families: 20

### WG-0524 · P1 · elevate · effort M

**Move fleet peer discovery from ten hardcoded Cloud Run URLs to agent cards plus the relay registry**

- Failure surface: AGENTS dict in agent_connect.py bakes project numbers for kronos, dav1d, rhea, yuki, bandit, kaedra, kam, iris, unk and visions_cloud; each peer's endpoint shape is special-cased by name. Any peer redeploy to a new project silently breaks fleet_dashboard and the talk_to_agent tool.
- First fork: if you observe every peer serving /.well-known/agent.json (A2A card) -> resolve endpoint and payload shape from the card with a cached registry file; else -> move URLs to env/relay config and keep per-peer shape until cards exist
- Evidence: `tools/agent_connect.py`, `visions/api/app.py`, `A2A_IMPLEMENTATION.md`
- Lens: deploy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/agent_connect.py defines an AGENTS dict (confirmed at line 14) with per-peer special-casing (e.g. comments distinguishing KRONOS's /generate endpoint from others' /chat), matching the claim of hardcoded per-peer URLs and endpoint shapes.

### WG-0536 · P1 · elevate · effort S

**Deploy from a tagged, audited ref instead of `git pull origin main` on Cloud Shell**

- Failure surface: cloud_shell_deploy.sh pulls main and deploys whatever is there; main carried an unimportable agent.py and ~90 nonexistent model ids for months. No tag, no rollback pointer, no way to know which commit is live.
- First fork: if you observe no git tags on the repo -> tag the last known-good commit, make the script take a ref and run router.audit before deploy; else -> add the audit gate and a rollback note in HANDOFF
- Evidence: `cloud_shell_deploy.sh`, `.handoffs/README.md`, `visions/core/router.py`
- Lens: deploy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: cloud_shell_deploy.sh runs `git pull origin main` then `python deploy.py` with no ref pinning, tag check, or audit gate, exactly as described.

### WG-0548 · P1 · defend · effort S

**Bring the second fleet machine into the handoff registry without a refused commit at 2 AM**

- Failure surface: .handoffs/ has only README.md; rule 2 in prepare-commit-msg refuses a NEW commit from a machine not seen in .handoffs once any leg exists. The first leg from blade means phoebus/whoart's next commit is refused unless NOUGEN_IDENTITY_OK=1, and core.hooksPath must be set per clone.
- First fork: if you observe zero leg files after the first relay create -> have each machine write its introductory leg in the same session; else -> document the NOUGEN_IDENTITY_OK path in AGENTS.md and the relay README
- Evidence: `.githooks/prepare-commit-msg`, `.handoffs/README.md`, `AGENTS.md`
- Lens: governance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: .handoffs/ contains only README.md (no leg files); .githooks/prepare-commit-msg contains the NOUGEN_IDENTITY_OK=1 override logic and refuses new commits from unknown-agent/machine, matching the described refusal mechanism.

### WG-0560 · P1 · defend · effort S

**Reconcile Bandit's cross-project IAM: the integration doc grants roles in mineral-subject while deploys target endless-…**

- Failure surface: BANDIT_INTEGRATION.md tells the Bandit SA to get run.invoker in mineral-subject-487519-v6, but the Cloud Run service peers call lives under project number 885670388176 and the deploy scripts target endless-duality; when Visions goes authenticated, Bandit is denied in the project that matters.
- First fork: if you observe `gcloud projects describe` mapping 885670388176 to mineral-subject -> update the doc and grant there; else -> grant in the project that actually hosts visions-assistant-service and fix the doc
- Evidence: `BANDIT_INTEGRATION.md`, `tools/agent_connect.py`, `cloudbuild.yaml`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: BANDIT_INTEGRATION.md:27 names mineral-subject-487519-v6 for the role grant; tools/agent_connect.py:21 shows the Cloud Run URL with number 885670388176; create_bq_schema.py references endless-duality-480201-t3 as the actual deploy project, confirming the mismatch.
- #550 families: 38

### WG-0572 · P1 · defend · effort S

**Refresh or retire the frozen handoff docs that mislead Gemini agents about topology (Firestore, Reasoning Engine, 2025-…**

- Failure surface: HANDOFF.md and CHANGELOG.md stop at 2025-12-26, .gemini (SECURITY_LEVEL: HIGH, dated 2025-12-24) tells Antigravity/Gemini CLI the deploy is Reasoning Engine in endless-duality with Firestore memory; an agent lane acting on it deploys to the wrong target or 'fixes' memory toward Firestore.
- First fork: if you observe another lane's commit referencing Firestore or the Reasoning Engine as current -> rewrite .gemini/HANDOFF to the Cloud Run + SQLite/GCS/BQ truth and mark old logs archived; else -> rewrite anyway and add a 'last verified' date
- Evidence: `.gemini`, `HANDOFF.md`, `README.md`
- Lens: docs-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: .gemini:5,7 shows 'SECURITY_LEVEL: HIGH' and 'DATE: 2025-12-24', line 11 references Reasoning Engine deployment target and line 46 Firestore hot layer; HANDOFF.md and CHANGELOG.md both dated 2025-12-26, confirming stale/misleading docs.

### WG-0583 · P1 · defend · effort S

**Pin VERTEX_PROJECT_ID in cloudbuild.yaml so Cloud Run memory does not land in the wrong project's buckets**

- Failure surface: config.py defaults to mineral-subject-487519-v6, deploy_cloud_run.ps1 sets endless-duality-480201-t3, cloudbuild.yaml sets nothing; depending on which path deployed, memory and RAG buckets ({project}-visions-memory, {project}-reasoning-artifacts) differ and one deploy's data is invisible to the other.
- First fork: if `gcloud run services describe visions-assistant-service` shows no VERTEX_PROJECT_ID env -> set it explicitly in cloudbuild.yaml and verify both buckets exist in that project; else -> reconcile config.py default to match
- Evidence: `visions/core/config.py`, `cloudbuild.yaml`, `deploy_cloud_run.ps1`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: config.py:24 defaults VERTEX_PROJECT_ID to mineral-subject-487519-v6; deploy_cloud_run.ps1:2 hardcodes endless-duality-480201-t3 and passes it as env var; cloudbuild.yaml sets no VERTEX_PROJECT_ID -- three-way mismatch confirmed.
- #550 families: 36

### WG-0594 · P1 · elevate · effort M

**Collapse four pricing tables into one registry keyed by router.py model ids**

- Failure surface: usage_tracker.DAILY_LIMITS, cost/pricing.py, cost/cost_tracker.py and docs/COST_ANALYSIS.md each carry their own prices; the 2026-08-02 fix found flash-image 42% under in one table only. The next model sweep will desync them again.
- First fork: if router.py can carry a price field per Model without breaking test_router.py -> move prices there and derive the others; else -> single pricing.json read by all four
- Evidence: `usage_tracker.py`, `visions/modules/cost/pricing.py`, `visions/core/router.py`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: usage_tracker.py:27 defines its own DAILY_LIMITS dict with cost/rpd fields; visions/modules/cost/pricing.py independently defines its own PRICING table with price_per_1k values; router.py holds model ids separately -- multiple independent pricing tables confirmed to exist, supporting the desync claim (docs/COST_ANALYSIS.md and cost_tracker.py not independently verified but consistent with the patt

### WG-0605 · P1 · elevate · effort L

**Ship or retire the Firestore hot layer that README, .gemini and firestore.rules promise**

- Failure surface: Docs, firestore.rules and test_memory_cloud.py describe a Firestore session layer with remember_message/get_context_for_model/end_session; no Python touches Firestore and those methods do not exist, so the root test crashes at import. Deploying firestore.rules alone leaves users/ writable by any authed uid with nothing behind it.
- First fork: if Dave wants session memory shared across Cloud Run instances -> implement Firestore hot layer behind CloudMemoryManager and make test_memory_cloud.py real; else -> delete firestore.rules, test_memory_cloud.py, and fix README/.gemini/AGENTS.md
- Evidence: `firestore.rules`, `test_memory_cloud.py`, `.gemini`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: firestore.rules exists describing users/ hot layer; test_memory_cloud.py exists; .gemini:46 references 'Hot Layer (Firestore)'; grep for Firestore usage in Python found none outside test/docs, consistent with the claim that no Python code implements it.

### WG-0616 · P1 · defend · effort S

**Make /v1/chat/completions carry user_id so fleet peers stop sharing one memory row**

- Failure surface: The OpenAI-compatible endpoint drops everything but the last message and calls get_chat_response with the default user, so every A2A caller (Kam, Cursor, ChatGPT) writes to and would read from user 'default_user'; memory becomes a cross-tenant blender.
- First fork: if fleet peers send an identifiable header or 'user' field -> map it to user_id and reject anonymous writes; else -> derive user_id from caller ID token audience
- Evidence: `visions/api/app.py`, `visions_assistant/agent.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions/api/app.py:48 defaults user_id to 'user' but visions_assistant/agent.py:28 get_chat_response defaults user_id='default_user', and the OpenAI-compatible endpoint path (app.py chat handling) does not surface a per-caller id distinctly enough to prevent collapsing onto the default -- confirms the shared-identity risk.
- #550 families: 18

### WG-0627 · P1 · defend · effort M

**Give talk_to_agent honest failure, retries and idempotency before Visions relays fleet answers**

- Failure surface: AgentConnector silently falls back to unauthenticated requests when fetch_id_token fails, has no retry, and on 404 walks a list of endpoints with different payload shapes, returning whatever JSON field it finds; a peer's error body or HTML can be returned to the user as the peer's answer.
- First fork: if test_fleet_connectivity shows any peer 'connected' with a body lacking response/text -> tighten parsing and require token; else -> add bounded retry with jitter and a request id
- Evidence: `tools/agent_connect.py`, `test_fleet_connectivity.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/agent_connect.py:34 calls fetch_id_token wrapped in a try/except (line 36) that swallows the exception -- consistent with silent unauthenticated fallback; no retry loop visible in the file -- confirms claim.
- #550 families: 8, 23

### WG-0638 · P1 · elevate · effort L

**Migrate fleet peer discovery from 10 hardcoded Cloud Run URLs to A2A agent cards and the relay registry**

- Failure surface: AGENTS in agent_connect.py embeds project numbers and service names for kronos, dav1d, rhea, yuki, bandit, kaedra, kam, iris, unk; a redeploy to a new project or a rename silently re-routes A2A traffic to a dead or wrong host and fleet_dashboard keeps reporting the old node.
- First fork: if each peer serves /.well-known/agent.json -> build a discovery table with TTL and fall back to the static map; else -> move the map to env/relay and add a daily reachability probe
- Evidence: `tools/agent_connect.py`, `visions/api/app.py`, `A2A_IMPLEMENTATION.md`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/agent_connect.py:14-24 AGENTS dict hardcodes Cloud Run URLs for kronos, dav1d, rhea, yuki, bandit, kaedra, unk, kam, iris -- exact match to the 9 named peers (title says 10 hardcoded URLs; 9 confirmed present, close enough to not contradict) -- confirms the hardcoded discovery claim.

### WG-0649 · P1 · defend · effort S

**Normalize memory timestamps to UTC across blade, phoebus, whoart and Cloud Run writers**

- Failure surface: SQLite stores time.time(), GCS stores naive datetime.now().isoformat(), BigQuery gets naive isoformat too; writers on three Windows boxes in Eastern and Cloud Run in UTC interleave, so ordering across sources is wrong by hours and any HLC-style federation read misorders evidence.
- First fork: if BQ rows show gaps or inversions around 4-5h between hosts -> switch to datetime.now(timezone.utc) everywhere and add a host field; else -> still switch and backfill a host column
- Evidence: `visions/modules/mem_store/memory_cloud.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: memory_cloud.py:89 uses time.time() for the sqlite/local timestamp and lines 116/131 use naive datetime.datetime.now().isoformat() for GCS/BQ paths -- confirms inconsistent naive timestamps across storage tiers as claimed.
- #550 families: 13

### WG-0660 · P1 · defend · effort S

**Purge Sentinel heartbeat rows from interaction_logs, GCS logs/ and the markdown journal**

- Failure surface: sentinel_loop.py and sentinel_deep_scour.py write a STATUS_CHECK/HEARTBEAT interaction every 5 minutes (288/day) into the same BQ table, GCS prefix and CURRENT_SESSION.md as real users; docs/logs/CURRENT_SESSION.md already shows sentinel_system rows interleaved with 'Mock Response' test rows. Analytics and any future context read are polluted.
- First fork: if `SELECT COUNT(*) WHERE user_id IN ('sentinel_system','sentinel','diag_user','user')` dominates the table -> route heartbeats to a separate health table and DELETE the old rows outside the streaming buffer; else -> just add a user_id denylist to get_recent_context
- Evidence: `sentinel_loop.py`, `sentinel_deep_scour.py`, `docs/logs/CURRENT_SESSION.md`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: sentinel_loop.py:50-52 calls save_interaction with user_id='sentinel_system', prompt='STATUS_CHECK'; sentinel_deep_scour.py:97 calls save_interaction('sentinel','HEARTBEAT_DEEP_SCOUR','OK'); docs/logs/CURRENT_SESSION.md shows many interleaved STATUS_CHECK/HEARTBEAT_DEEP_SCOUR entries, directly confirming pollution.
- #550 families: 68

### WG-0671 · P1 · defend · effort M

**Make deploy.py update the Reasoning Engine in place and reap the 18 orphaned engines**

- Failure surface: Every deploy.py run creates a new ReasoningEngine and prints an ID to hand-edit into config; .env.example (5424...) and config.py (7709...) already disagree and QUOTA_MANAGEMENT shows 18/100 engine entities. Traffic quietly stays on an old engine with an old vector_store.
- First fork: if `list_engines.py` shows >1 engine with display_name Visions-AI-Reasoning-Agent -> add update() path keyed on REASONING_ENGINE_ID and delete the rest with Dave's ok; else -> just add update()
- Evidence: `deploy.py`, `cloud_shell_deploy.sh`, `.env.example`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: deploy.py:75-78 calls reasoning_engines.ReasoningEngine.create() (no update/list-then-update path visible); .env.example:11 REASONING_ENGINE_ID=542433066447011840 while config.py:29 defaults REASONING_ENGINE_ID to '7709761240314150912' -- the two IDs disagree exactly as claimed (the '18 orphaned engines' figure from QUOTA_MANAGEMENT was not independently verified but the core mismatch and create-o
- #550 families: 29

### WG-0682 · P1 · defend · effort S

**Make ralph_watchdog and Deep Scour actually import what they certify**

- Failure surface: Both use importlib.util.find_spec, which resolves a path without executing the module; visions/core/agent.py was unimportable on main for months while the watchdog printed GO. The gate that exists to catch that class of failure cannot see it.
- First fork: if importing visions.core.agent in a fresh venv raises -> the watchdog must import (with SDK stubs) and fail; else -> switch to real import anyway and run it in cloudbuild before deploy
- Evidence: `ralph_watchdog.py`, `sentinel_deep_scour.py`, `.handoffs/README.md`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: ralph_watchdog.py:53 and sentinel_deep_scour.py:51 both use `importlib.util.find_spec(...)` rather than actually importing the module, which per Python semantics can succeed even if the module raises on actual import -- confirms the verification-gap claim exactly.
- #550 families: 82

### WG-0693 · P1 · defend · effort S

**Make /health reflect set_up failure and memory tier state instead of a constant 'online'**

- Failure surface: app.py catches any exception from agent.set_up() at startup and /health still returns online; visions/api/app.py's /health/detailed returns dependencies 'verified' as a literal. Cloud Run routes traffic to an instance whose every /query 500s, and fleet_dashboard shows it green.
- First fork: if set_up raised on the last deploy (check logs for 'Startup Failed') -> gate /health on a readiness flag and tier status; else -> add readiness flag anyway
- Evidence: `app.py`, `visions/api/app.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py:28 calls agent.set_up() in a try/except at startup while /health (line 33) returns online unconditionally; visions/api/app.py's /health/detailed returns dependencies: 'verified' as a hardcoded literal (line 78). Evidence confirmed as given.
- #550 families: 95

### WG-0704 · P1 · defend · effort S

**Audit COMPLETE/READY done-markers against live evidence and demote the false ones**

- Failure surface: docs/logs/GEMINI_3_MEMORY_COMPLETE.md says the Sentinel runs 24/7 and memory is online; HANDOFF.md says READY FOR TESTING (2025-12-26); sentinel.log is untracked and nothing proves either. A new agent reading these skips verification and builds on air.
- First fork: if no sentinel.log exists on any of blade/phoebus/whoart -> mark the memory doc STALE with a date and pointer; else -> attach the last pulse timestamp to the doc
- Evidence: `docs/logs/GEMINI_3_MEMORY_COMPLETE.md`, `HANDOFF.md`, `docs/logs/PHASE_1_COMPLETE.md`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/logs/GEMINI_3_MEMORY_COMPLETE.md:34 calls sentinel_loop.py 'The 24/7 validation script'; HANDOFF.md:1,3 shows 'Handoff Notes - 2025-12-26' and 'Status: READY FOR TESTING'; docs/logs/PHASE_1_COMPLETE.md exists. No tracked sentinel.log was found, consistent with the claim.
- #550 families: 100

### WG-0715 · P1 · elevate · effort M

**Stand up real alerting (5xx, 429, cold-start, spend) for visions-assistant-service**

- Failure surface: ops/setup_monitoring.sh only alerts on IAM SetIamPolicy, uses an unset $GOOGLE_CLOUD_PROJECT in its filter and a default email; QUOTA_MANAGEMENT.md describes quota alerts as manual console clicks and Config.ENABLE_QUOTA_ALERTS is read by nothing. A public unauthenticated Gemini Pro proxy has no page when it burns.
- First fork: if the project has zero alert policies mentioning visions -> create policies for Cloud Run 5xx rate, Vertex 429, and daily spend with Dave's channel; else -> extend existing
- Evidence: `ops/setup_monitoring.sh`, `docs/QUOTA_MANAGEMENT.md`, `visions/core/config.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: ops/setup_monitoring.sh's filter only covers SetIamPolicy audit events and references an interpolated $GOOGLE_CLOUD_PROJECT variable (line 17); docs/QUOTA_MANAGEMENT.md and visions/core/config.py exist as referenced.

### WG-0726 · P1 · defend · effort S

**Make fleet_dashboard derive node status from live A2A probes instead of constants**

- Failure surface: MISSION_MD hardcodes 'NODES: 10 Detected' and 'STATUS: ACTIVE', and the topology tree lists agents regardless of reachability; an operator watching the dashboard on blade sees green while kam or rhea is down.
- First fork: if the dashboard renders all nodes green with the network unplugged -> wire AgentConnector probes with timeouts and last-seen ages; else -> only add last-seen
- Evidence: `fleet_dashboard.py`, `tools/agent_connect.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: fleet_dashboard.py hardcodes 'STATUS: ACTIVE' and 'NODES: 10 Detected' (lines 52-53) and logs 'MESH STABILIZED. 10 NODES SYNCED.' (line 182) without evident liveness probing shown; tools/agent_connect.py exists as the probing module to wire in.
- #550 families: 95

### WG-0736 · P1 · defend · effort S

**Stop two infra scripts from regenerating tracked firestore.rules and visions-api.yaml with conflicting content**

- Failure surface: deploy_visions_saas.sh and fix_visions_infrastructure.sh both cat > visions_rate_limiter.js, firestore.rules and visions-api.yaml with different tier limits (30/100/500 vs 60/300/1000) and non-idempotent gcloud mutations; whichever ran last decides what is in git, and a rerun silently reverts the other.
- First fork: if `git diff` after running either script is non-empty -> make the files the source and the scripts read them; else -> delete the generators
- Evidence: `deploy_visions_saas.sh`, `fix_visions_infrastructure.sh`, `visions_rate_limiter.js`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: visions_rate_limiter.js defines TIER_LIMITS business=500/enterprise=1000 while fix_visions_infrastructure.sh's generated copy defines business=1000/enterprise=10000, and deploy_visions_saas.sh shows yet another 60/300/1000/10000 scheme -- confirming conflicting tier tables written by different scripts to the same tracked files.
- #550 families: 85

### WG-0746 · P1 · defend · effort S

**Scrub the committed visions_short_term.db and CURRENT_SESSION.md and fence memory writes from git**

- Failure surface: A live SQLite memory file and a markdown journal of prompt/response pairs (with user_ids) are tracked at repo root and docs/logs/, and Dockerfile COPY . . ships them into every Cloud Run image. Any real user text that lands in them becomes PII in git history and Artifact Registry.
- First fork: if `sqlite3 visions_short_term.db 'select count(*) from interactions'` is non-zero or the journal has non-test users -> purge history (filter-repo) and rotate; else -> git rm, add to .gitignore/.gcloudignore, and make memory_cloud refuse to write inside the repo tree
- Evidence: `visions_short_term.db`, `docs/logs/CURRENT_SESSION.md`, `Dockerfile`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git ls-files confirms both visions_short_term.db and docs/logs/CURRENT_SESSION.md are tracked in git; Dockerfile has 'COPY . .' which would ship them into the image.
- #550 families: 75

### WG-0756 · P1 · defend · effort S

**Add a guard that fails when router.py RETIRED entries become self-referential after a sweep**

- Failure surface: The 2026-08 model-id find-and-replace rewrote router.py's own RETIRED rows into their replacements, corrupting the registry that exists to prevent routing to dead ids; the only defense now is a comment saying DO NOT sweep this file.
- First fork: if test_router.py already asserts every RETIRED id differs from its replacement -> add it as a pre-commit/cloudbuild step; else -> write that assertion first
- Evidence: `visions/core/router.py`, `tests/test_router.py`, `.githooks/prepare-commit-msg`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: visions/core/router.py:61 contains a literal comment 'DO NOT run a model-id find-and-replace over this file' directly above the RETIRED model table, corroborating the claimed prior incident; tests/test_router.py and .githooks/prepare-commit-msg exist as proposed guard locations.
- #550 families: 36

### WG-0766 · P1 · elevate · effort L

**Retire the Reasoning Engine path or the Cloud Run path so one memory/RAG topology is live**

- Failure surface: deploy.py ships VisionsAgent to Vertex Reasoning Engine with its own requirements list and cloudpickled state, while cloudbuild.yaml ships app.py to Cloud Run; both write to the same buckets and BQ table from different code versions and dependency sets, so the memory store receives rows from two divergent agents.
- First fork: if the Reasoning Engine has served a query in the last 30 days (Vertex logs) -> plan a cutover with a shared write-schema check; else -> delete deploy.py/cloud_shell_deploy.sh and REASONING_ENGINE_* config
- Evidence: `deploy.py`, `cloudbuild.yaml`, `visions/core/config.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy.py imports vertexai.preview.reasoning_engines and calls reasoning_engines.ReasoningEngine.create() with its own requirements_list (lines 3,49,78-80), while cloudbuild.yaml is the separate Cloud Run deploy path and visions/core/config.py holds related config, confirming two divergent deploy topologies.
- #550 families: 12

### WG-0776 · P1 · defend · effort M

**Stop last-deployer-wins overwrites of the shared GCS vector_store from blade, phoebus and whoart**

- Failure surface: Both deploy.py and build_index.sync_to_gcs upload the local vector_store/ directory to the same prefix (and build_index also to the memory bucket); a stale index on one machine silently replaces a fresh one built on another, and the running agent never re-syncs because _sync_from_gcs skips when the local dir is non-empty.
- First fork: if `gsutil ls -a` shows multiple generations with different sizes in the last month -> introduce dated prefixes plus a 'current' pointer and a build-host trailer; else -> at minimum make upload conditional on a newer indexing_cache.json hash
- Evidence: `deploy.py`, `scripts/build_index.py`, `visions/core/agent.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy.py:40-41 uploads local vector_store/ to GCS; build_index.py builds/saves to the same local INDEX_DIR then presumably syncs; agent.py's _sync_from_gcs (line 42) is referenced, supporting the last-writer-wins concurrency claim.
- #550 families: 84

### WG-0786 · P1 · defend · effort S

**Point visions-api.yaml's backend at the same Cloud Run revision the fleet actually uses**

- Failure surface: The API Gateway spec for the paid tiers backends to Cloud Run suffix 620633534056, while tools/agent_connect.py's visions_cloud entry (used by the internal fleet mesh and fleet_dashboard.py) points at suffix 885670388176 — a different deployed service. Paying API-Gateway customers and the internal fleet are silently talking to two different backends.
- First fork: if you observe the two suffixes resolve to different live services -> pick one and repoint the other; else if 620633534056 is already decommissioned -> API Gateway customers are already 404ing and this is urgent.
- Evidence: `visions-api.yaml`, `tools/agent_connect.py`
- Lens: Cost/quota/token economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions-api.yaml:12 uses suffix 620633534056; tools/agent_connect.py:21 uses suffix 885670388176 for visions_cloud - two distinct Cloud Run backends confirmed.
- #550 families: 38

### WG-0796 · P1 · defend · effort M

**Gate the keyword-triggered image-generation branch behind cost/rate controls**

- Failure surface: visions_assistant/agent.py auto-calls engine.generate_image (a $0.134-$0.24 Gemini image call) whenever a message contains any of 4 keyword phrases plus "image"; reachable from the public unauthenticated /chat endpoint with no rate limit, confirmation, or per-caller cap — a script sending the phrase in a loop drives real, uncapped image-generation spend.
- First fork: if you observe repeated generate_image triggers from one caller within a short window -> throttle/require confirmation; else if traffic looks organic -> allow but log to the (currently unwired) usage tracker.
- Evidence: `visions_assistant/agent.py`, `usage_tracker.py`
- Lens: Cost/quota/token economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions_assistant/agent.py:51-55 has exactly 4 gen_triggers phrases plus 'image' check that calls engine.generate_image unconditionally.

### WG-0806 · P1 · defend · effort M

**Make the JS tiered rate limiter fail closed, not open, and actually wire it in**

- Failure surface: visions_rate_limiter.js is the only code enforcing the x-user-id/x-tier per-minute caps, but on any Firestore read error it returns {allowed:true, warning:...} ("fail open"), and neither app.py nor visions/api/app.py ever calls it — a Firestore outage or the missing integration both silently remove all rate limiting on the public endpoint.
- First fork: if you observe this function is never invoked from the request path -> wire it into visions/api/app.py's middleware; else if it is invoked and Firestore errors -> fail closed (429) instead of open.
- Evidence: `visions_rate_limiter.js`, `visions/api/app.py`
- Lens: Cost/quota/token economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions_rate_limiter.js returns {allowed:true,...,warning:'Rate limit service error'} on catch (fail open); no reference to visions_rate_limiter in visions/api/app.py or app.py.

### WG-0816 · P1 · elevate · effort S

**Trim .gcloudignore so curriculum/exams/transcripts/council don't ship into every Cloud Run build**

- Failure surface: .gcloudignore excludes only caches/venvs; Dockerfile's `COPY . .` plus Cloud Build's default context therefore ship curriculum/, exams/, knowledge_base/transcripts/ (307 files) and the vendored tools/council/ app into every build and every deployed image, inflating build time, image size and attack surface on every single deploy.
- First fork: if you observe the built image containing curriculum/exams/transcripts/council paths -> add them to .gcloudignore and a slimmer .dockerignore; else if any of it is runtime-required -> split it into a separate data bucket fetched at startup instead of baked in.
- Evidence: `.gcloudignore`, `Dockerfile`
- Lens: Cost/quota/token economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: .gcloudignore only excludes caches/venvs/build artifacts, no curriculum/exams/transcripts/council entries; Dockerfile line 31 does COPY . . which would include them.
- #550 families: 75

### WG-0826 · P1 · elevate · effort M

**Wire the Cloud Tasks rate-limiting queues fix_visions_infrastructure.sh creates into the request path**

- Failure surface: fix_visions_infrastructure.sh provisions visions-free/basic/pro-queue with per-tier dispatch-rate caps matching the SaaS tiers, but no import or call of cloudtasks appears in app.py or visions/api/app.py — the infrastructure exists and presumably costs to keep provisioned, but the actual FastAPI request path never enqueues through it, so the documented per-tier ceiling is enforced nowhere.
- First fork: if you observe requests bypassing Cloud Tasks entirely -> route incoming /query or /chat calls through the matching tier queue; else if Cloud Tasks was abandoned for another mechanism -> tear the queues down to stop paying for unused infra.
- Evidence: `fix_visions_infrastructure.sh`, `visions/api/app.py`
- Lens: Cost/quota/token economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: fix_visions_infrastructure.sh creates visions-free/basic/pro-queue Cloud Tasks queues with per-tier dispatch rates; no cloudtasks import/call found in app.py or visions/api/app.py.

### WG-0836 · P1 · defend · effort M

**Version or gate deploy.py's Reasoning Engine creation so it stops silently forking spend**

- Failure surface: deploy.py re-uploads local vector_store/ to the shared GCS bucket and creates a brand-new Vertex Reasoning Engine on every run without deleting the previous one; the new REASONING_ENGINE_ID must then be hand-copied into config.py (cloud_shell_deploy.sh literally says "update agent.py"), so a forgotten manual step leaves an orphaned, still-billing Reasoning Engine nobody points traffic at.
- First fork: if you observe more Reasoning Engine entities than intended in the GCP console -> add cleanup of the prior engine to deploy.py; else if multiple engines are intentional (blue/green) -> document the convention so the manual ID step isn't a silent trap.
- Evidence: `deploy.py`, `cloud_shell_deploy.sh`
- Lens: Cost/quota/token economics · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy.py uploads vector_store to GCS and creates a new Reasoning Engine each run; cloud_shell_deploy.sh literally instructs 'Copy the new Resource ID above and update agent.py!' confirming the manual step.
- #550 families: 29

### WG-0846 · P1 · defend · effort M

**Loosen-safety-settings decision needs a documented governance sign-off**

- Failure surface: agent.py's main generation call sets all 4 HarmCategory thresholds to BLOCK_ONLY_HIGH ("Allowing Creative Freedom") on the public, unauthenticated Cloud Run endpoint; nothing in the repo documents who approved this policy or under what tier/age-gating it applies, so the most permissive Gemini safety setting is the default for every anonymous caller.
- First fork: if you observe abuse reports or content-policy complaints traceable to this endpoint -> tighten thresholds or gate creative-freedom mode behind an authenticated/paid tier; else if this is an accepted product decision -> record it in a policy doc so it isn't mistaken for an oversight.
- Evidence: `visions/core/agent.py`
- Lens: Product/UX/public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions/core/agent.py lines 368-374 set all 4 HarmCategory thresholds to BLOCK_ONLY_HIGH with comment '(Allowing Creative Freedom)'; no governance/policy doc found referencing this decision.

### WG-0856 · P1 · defend · effort S

**Add root app.py to ralph_watchdog's REQUIRED_MODULES list**

- Failure surface: ralph_watchdog.py's REQUIRED_MODULES checks visions.api.app, visions.core.agent, visions_assistant.agent, memory_cloud and config — but never root app.py, which is the actual Dockerfile CMD entrypoint; the watchdog can report "all required modules resolved" while the one module Cloud Run actually runs is broken.
- First fork: if you observe app.py break while ralph_watchdog still reports all-green -> add "app" to REQUIRED_MODULES; else if app.py is meant to be deprecated in favor of visions.api.app -> make that the Dockerfile CMD instead.
- Evidence: `ralph_watchdog.py`, `Dockerfile`
- Lens: Testing/CI gaps · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: ralph_watchdog.py REQUIRED_MODULES list (lines 15-21) contains visions.api.app, visions.core.agent, visions_assistant.agent, memory_cloud, config but not root 'app' module; Dockerfile CMD runs app.py.
- #550 families: 35

### WG-0866 · P1 · defend · effort M

**Reconcile README/firestore.rules Firestore memory claims with the SQLite+GCS+BQ code**

- Failure surface: README's memory-architecture diagram and firestore.rules promise a Firestore short-term layer with security rules; memory_cloud.py never imports google.cloud.firestore, so any auditor or customer trusting firestore.rules to govern real user data is wrong, and no code path enforces those rules.
- First fork: if you observe no firestore import anywhere in *.py -> rewrite README/remove firestore.rules or implement the layer; else if Firestore is planned -> land it before the docs ship again.
- Evidence: `README.md`, `firestore.rules`, `visions/modules/mem_store/memory_cloud.py`
- Lens: Product/UX/onboarding docs drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: README.md and firestore.rules exist; memory_cloud.py has no firestore import (grep confirms) - verified all 3 evidence paths.

### WG-0876 · P1 · defend · effort S

**Make ralph_watchdog actually import required modules, not just resolve their spec**

- Failure surface: check_imports() only calls importlib.util.find_spec() (path resolution), never a real import; a module that resolves on disk but raises at import time — exactly the historical duplicated bare `try:` bug that made agent.py unimportable on main — would still print "✅ Module Resolved" from this watchdog.
- First fork: if you observe find_spec() succeed on a module that actually raises on `import` -> switch to importlib.import_module() inside a try/except; else if find_spec is intentional for speed -> add a second, slower full-import pass before deploy.
- Evidence: `ralph_watchdog.py`
- Lens: Testing/CI gaps · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: ralph_watchdog.py check_imports() (line 40) uses importlib.util.find_spec() only (line 53), never importlib.import_module(), so it cannot catch import-time exceptions.
- #550 families: 82

### WG-0886 · P1 · defend · effort M

**Separate live/paid test scripts from the pytest-safe suite before anyone runs `pytest tests/`**

- Failure surface: Of 25 files under tests/, only test_router.py is a self-contained mockable suite; the rest (test_veo3*.py, test_generation.py, test_ai_studio.py, etc.) require live ADC/API keys and real quota. Running `pytest tests/` in a fresh clone reproduces the 16 collection errors already observed in commit b1f2694 — "run the test suite" is not actually a supported operation today.
- First fork: if you observe a fresh `pytest tests/` invocation still collecting 16+ errors -> move live-API scripts to tests/manual/ or gate them behind an env flag/marker so pytest skips them by default; else if that's already been done -> verify with a clean venv, not from memory.
- Evidence: `tests/`, `tests/test_router.py`
- Lens: Testing/CI gaps · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Ran python3 -m pytest tests/ --collect-only -q in the repo and reproduced exactly 16 collection errors (ModuleNotFoundError: No module named 'google') matching the claim precisely; tests/test_router.py collects cleanly among 23 tests/ files.

### WG-0895 · P1 · defend · effort S

**Declare memory_cloud.py's real dependencies (bigquery, etc.) in requirements.txt**

- Failure surface: requirements.txt lists only 17 packages and omits google-cloud-bigquery even though memory_cloud.py (imported by agent.py, imported by both app.py and visions/api/app.py) does `from google.cloud import bigquery` at module load — a from-scratch `pip install -r requirements.txt` followed by starting either FastAPI app can fail at import time with nothing in CI to catch the drift before deploy.
- First fork: if you observe ImportError for bigquery/firebase-admin/websockets/pystray/youtube_transcript_api on a clean install -> add every actually-imported package to requirements.txt (or split into a pyproject with extras); else if google-cloud-aiplatform happens to pull bigquery transitively today -> that's fragile and should be pinned explicitly, not assumed.
- Evidence: `requirements.txt`, `visions/modules/mem_store/memory_cloud.py`
- Lens: Testing/CI gaps · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: requirements.txt confirmed has no google-cloud-bigquery entry (17 lines, only google-cloud-aiplatform/storage/logging present); memory_cloud.py confirmed does 'from google.cloud import bigquery' at module top (line 9) and instantiates bigquery.Client. Evidence directly supports the import-time drift claim.

### WG-0904 · P1 · defend · effort S

**Stop committing os.devnull as if it were meaningful test evidence**

- Failure surface: A file literally named `os.devnull` is committed at the repo root holding a captured unittest run ("Ran 1 test in 13.404s OK"); it collides in name with the real os.devnull path constant, is never regenerated, and stands as permanently stale "proof" of one historical test run that nothing in the repo re-validates.
- First fork: if you observe this file still referenced or trusted as evidence of test health -> delete it and rely on a real CI artifact instead; else if it was an accidental commit -> remove it and add a .gitignore rule for stray redirect targets.
- Evidence: `os.devnull`
- Lens: Testing/CI gaps · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: os.devnull confirmed committed at repo root containing literal captured unittest output ('Ran 1 test in 13.404s OK'), matching the claim exactly.
- #550 families: 100

### WG-0912 · P1 · elevate · effort M

**Add a regression test replaying the rebase scenario that once corrupted commit trailers**

- Failure surface: The hook's own comment documents a real incident ("measured 2026-07-31: git rebase origin/main on blade rewrote phoebus/claude-cli into blade1tb/unknown-agent") and claims rule 1 now fixes it, but no test file replays a rebase against the hook to confirm the fix holds under future edits to prepare-commit-msg.
- First fork: if you observe prepare-commit-msg being edited again -> require the rebase-replay scenario pass before merging; else if no such test exists yet -> write one (a scripted git rebase in a scratch repo) as the very next hardening step for this hook.
- Evidence: `.githooks/prepare-commit-msg`
- Lens: Agent doctrine/multi-agent governance · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: .githooks/prepare-commit-msg exists and is the right file; the incident comment and rule-1 fix language weren't directly quoted in my check but the file structure (KNOWN/machine detection logic) is consistent with such a fix existing. No dedicated rebase-replay test file found in the repo, supporting the 'no test exists' half of the claim as a reasonable inference.
- #550 families: 15

### WG-0920 · P1 · defend · effort S

**Point AGENTS.md's Memory System section at the real memory_cloud.py path**

- Failure surface: AGENTS.md (the top-level doctrine every agent lane reads first) says memory lives at "memory.py, memory_cloud.py" using Firestore/Vector stores; neither path exists at repo root (real path is visions/modules/mem_store/memory_cloud.py, and it's SQLite+GCS+BQ, not Firestore) — an agent lane bootstrapping from AGENTS.md's own directions is misdirected before writing a line of code.
- First fork: if you observe a lane searching for root-level memory.py per AGENTS.md and not finding it -> update AGENTS.md's Key Directories/Memory System section to the real path and stack; else if AGENTS.md is regenerated from a template -> fix the template so this doesn't recur on the next repo it's applied to.
- Evidence: `AGENTS.md`, `visions/modules/mem_store/memory_cloud.py`
- Lens: Agent doctrine/multi-agent governance · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: AGENTS.md confirmed lines 18-20: 'Memory System / Location: memory.py, memory_cloud.py / Purpose: ... Firestore/Vector stores' — no root-level memory.py exists (only visions/modules/mem_store/memory_cloud.py, using bigquery/GCS not Firestore per bf34 check). Evidence directly confirms the stale-path and wrong-stack claim.

### WG-0928 · P1 · defend · effort S

**Surface tools/agent_connect.py's silent auth-downgrade instead of logging a warning and continuing**

- Failure surface: _get_id_token catches any failure to mint a Google ID token, logs "⚠️ Auth Warning", and returns None; the class's docstring promises "secure communication with other AI Agents" via ID tokens, but a caller of talk_to_agent has no visible signal that this particular call went out unauthenticated instead of failing — the fleet's A2A security contract degrades silently under exactly the kind of local-ADC hiccup the comment anticipates.
- First fork: if you observe fetch_id_token failing intermittently in production -> raise/return a typed error the caller must handle instead of silently falling back to no auth; else if unauthenticated fallback is acceptable for public peers -> make that explicit in the docstring, not implicit in a warning log.
- Evidence: `tools/agent_connect.py`
- Lens: Agent doctrine/multi-agent governance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/agent_connect.py confirmed contains bearer_token minting via create_proxy/_get_id_token pattern (Authorization: Bearer header at line 106, bearer_token generation/fallback at lines 172-176) consistent with an auth path that can silently degrade; file directly supports the claim's mechanics.

### WG-0936 · P1 · defend · effort M

**Block client-supplied image_path/video_path from reading arbitrary container files**

- Failure surface: visions_assistant/agent.py's get_chat_response opens `image_path` directly off the container filesystem (`open(image_path,'rb')`) with no path validation, reachable from the unauthenticated, CORS-* /chat and /v1/chat endpoints in visions/api/app.py; any caller can request an arbitrary local file be base64-read and forwarded to Gemini.
- First fork: if you observe image_path resolving outside an expected uploads dir -> reject the request; else if it's inside the sandboxed dir -> proceed.
- Evidence: `visions_assistant/agent.py`, `visions/api/app.py`
- Lens: Privacy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions_assistant/agent.py:39 open(image_path,'rb') with no path validation; visions/api/app.py has CORS allow_origins=['*'] and /chat, /v1/chat routes.
- #550 families: 71

### WG-0944 · P1 · defend · effort M

**Resolve the GCP project split-brain before it silently misroutes memory or billing**

- Failure surface: config.py/QUOTA_MANAGEMENT.md/BANDIT_INTEGRATION.md target project mineral-subject-487519-v6 while .env.example, deploy.py, deploy_cloud_run.ps1, deploy_visions_saas.sh and fix_visions_infrastructure.sh all target endless-duality-480201-t3; running any deploy or infra script against the "wrong" project for the current runtime config would create resources, quotas and alerts that the running service never actually uses (or worse, expose memory/billing to a project no one is monitoring).
- First fork: if you observe a script run producing resources in a project the live Config doesn't read from -> pick one canonical project and update every script/doc to match; else if two projects are intentionally split (dev vs prod) -> label them as such everywhere instead of leaving the split implicit.
- Evidence: `visions/core/config.py`, `.env.example`, `deploy_visions_saas.sh`
- Lens: Cost/quota/token economics · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: visions/core/config.py, .env.example, and deploy_visions_saas.sh all confirmed to exist. A project-id split between config/docs and deploy scripts is plausible given the repo's documented history of drift (per other items like bf40/bf59), though the exact project id strings were not independently re-grepped here.
- #550 families: 12

### WG-0952 · P1 · defend · effort S

**Make the triage failure path preserve is_high_risk uncertainty instead of defaulting to false**

- Failure surface: _triage_query's except-clause returns {is_high_risk: False, complexity: 5, needs_search: True} on ANY exception (timeout, malformed JSON, API error) — a genuinely high-risk query that happens to trip a Flash JSON-parsing edge case is silently routed to the ordinary Tier 3 path instead of the Tier 6 'God Mode' high-risk lane, defeating the one purpose the triage step exists for.
- First fork: if you observe triage exceptions correlating with content that should have been high-risk -> change the failure default to fail-safe (treat unknown as high-risk) rather than fail-open; else if triage failures are rare and low-stakes -> at minimum log/alert on every triage exception so the blind spot is visible.
- Evidence: `visions/core/agent.py`
- Lens: Agent doctrine/multi-agent governance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions/core/agent.py confirmed: _triage_query defined at line 226, with 'except Exception:' at line 240 immediately preceding/within it — a bare catch-all around triage. Directly consistent with a fail-open default on any exception.
- #550 families: 2

### WG-0960 · P1 · defend · effort S

**Give agent.py's tool loop a real terminal response instead of a generic apology after 3 turns**

- Failure surface: max_tool_turns=3; if the model keeps invoking tools for all 3 turns without ever emitting plain text, the user has paid for 3 full generations plus every tool execution and gets back only "Tool loop exceeded max turns. Please simplify your request." — discarding whatever partial/useful content the model actually produced across those turns.
- First fork: if you observe the loop exhausting max_tool_turns in production logs -> synthesize a best-effort answer from the accumulated tool results/text_parts instead of a generic string; else if this path is rare -> at least surface it as a distinct error code so cost/quality dashboards can track it.
- Evidence: `visions/core/agent.py`
- Lens: Product/UX/public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions/core/agent.py confirmed: max_tool_turns = 3 (line 379), loop 'for turn in range(max_tool_turns)' (line 384), and the literal fallback string 'Tool loop exceeded max turns. Please simplify your request.' (line 469). Directly matches the claim.

### WG-0967 · P1 · defend · effort M

**Reconcile visions-api.yaml's single documented tier route with the 5-tier pricing it claims to gate**

- Failure surface: visions-api.yaml's title promises a "Tier-based AI API for Visions SaaS (Free, Basic, Pro, Business, Enterprise)" but defines only one path, /v1/generate, with no per-tier routing, auth, or quota config visible in the spec itself — the tiering visions_rate_limiter.js implements separately isn't reflected in the API Gateway contract that's supposed to be the public entry point for it.
- First fork: if you observe a paying customer hitting /v1/generate with no tier enforcement at the gateway layer -> add the x-user-id/x-tier gating (or a Cloud Endpoints quota config) directly to visions-api.yaml; else if tiering is enforced downstream only -> update the spec's description so it doesn't overpromise gateway-level tiering.
- Evidence: `visions-api.yaml`, `visions_rate_limiter.js`
- Lens: Product/UX/public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: visions-api.yaml confirmed: title 'Visions-AI API' and a single path entry '/v1/generate' (line 8) under paths: (line 7), with no other paths found. visions_rate_limiter.js confirmed to exist as the separate tiering implementation. Directly supports the single-path-vs-5-tier claim.

### WG-0974 · P1 · elevate · effort L

**Decide and document one deploy target between Cloud Run and Vertex Reasoning Engine**

- Failure surface: Both the Cloud Run path (cloudbuild.yaml, Dockerfile) and the Vertex AI Reasoning Engine path (deploy.py, cloud_shell_deploy.sh, REASONING_ENGINE_ID) are actively maintained with divergent dependency lists and entrypoints for what is nominally the same agent; paying to keep both live (Reasoning Engine entities plus Cloud Run instances) without a stated reason doubles infra cost and doubles the number of places a fix has to land.
- First fork: if you observe both targets still receiving deploys with no documented reason for keeping both -> pick one as canonical and deprecate the other (freeing its GCP resources); else if there's a real reason (e.g. reasoning engine for a different customer segment) -> document it so it isn't mistaken for undecided drift.
- Evidence: `deploy.py`, `cloudbuild.yaml`, `cloud_shell_deploy.sh`
- Lens: Cost/quota/token economics · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: deploy.py, cloudbuild.yaml, and cloud_shell_deploy.sh all confirmed to exist; deploy.py confirmed targets Vertex Reasoning Engine deployment (requirements_list/extra_packages_list pattern for agent deployment) while cloudbuild.yaml is the separate Cloud Run build config, consistent with two parallel deploy targets.

### WG-0980 · P1 · defend · effort S

**Add a LICENSE before shipping vendored transcripts and other-model writing samples**

- Failure surface: 849 tracked files include no LICENSE while README brands the project as a public SaaS with tiers/pricing; knowledge_base/transcripts (307 YouTube transcripts) and writing_template (graded samples from other AI models) ship with no stated terms governing reuse, redistribution, or commercial use of that content.
- First fork: if you observe a reuse/redistribution question with no LICENSE to answer it -> add one scoped to the repo's actual rights; else if content is third-party and can't be relicensed -> exclude it from the container/build.
- Evidence: `knowledge_base/transcripts`, `writing_template`, `README.md`
- Lens: Licensing/brand · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: No LICENSE file in repo root; knowledge_base/transcripts has 307 files; writing_template exists.
