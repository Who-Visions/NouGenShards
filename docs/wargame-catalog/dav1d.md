# War-game candidates — Dav1d

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

68 candidates · P0 9 · P1 59 · P2 0 · P3 0 · defend 43 · elevate 25

| id | P | kind | title |
|---|---|---|---|
| WG-0009 | P0 | defend | Align local Python 3.11 launchers with the 3.12 container that multi-line f-strings require |
| WG-0025 | P0 | defend | Defuse the [EXEC:] protocol: model text parsed for [EXEC: cmd] runs shell=True with a 'Do not refuse' override |
| WG-0040 | P0 | elevate | Move the 640MB of PDFs, Veo videos and cookbook out of git and the Cloud Build context |
| WG-0054 | P0 | defend | Stop advertising A2A skills that the JSON-RPC server only acknowledges |
| WG-0066 | P0 | defend | Populate .handoffs so the fleet hooks stop failing open on this repo |
| WG-0077 | P0 | defend | Audit every 'COMPLETE' doc against the code it claims to describe |
| WG-0088 | P0 | elevate | Back the advertised fleet contract: rag-retrieval and agent-orchestration are stubs behind the agent card |
| WG-0099 | P0 | elevate | Arm the relay hooks in Dav1d: populate .handoffs, set core.hooksPath on every lane, prove a refused commit |
| WG-0109 | P0 | defend | Answer self-merge authority for Dav1d: master vs main, single WhoVisions author, claude/* branches |
| WG-0366 | P1 | elevate | Flip Cloud Run dav1d to --allow-unauthenticated for aiwithdav3.com without opening a free Gemini faucet |
| WG-0382 | P1 | defend | Replace CORS allow_origins=['*'] + allow_credentials=True with an origin allowlist that KRONOS/A2A still passes |
| WG-0398 | P1 | defend | Fence Secret Manager and BigQuery agent tools (get_secret_value, create_secret, run_query) behind explicit grants |
| WG-0414 | P1 | defend | Put auth on the A2A /rpc endpoint (port 10000) before it is reachable beyond localhost |
| WG-0430 | P1 | elevate | Ship a public-mode content filter: BLOCK_NONE safety settings plus VIBES slurs injected into every system prompt |
| WG-0446 | P1 | elevate | Remove pirated-looking ebooks and 640MB of media from git history without breaking fleet clones |
| WG-0461 | P1 | defend | Stop returning HTTP 200 from the global exception handler so Cloud Run and KRONOS can see outages |
| WG-0474 | P1 | elevate | Make the $2/hr budget global: CostManager and RateLimitManager are per-process on a 10x80 Cloud Run fleet |
| WG-0487 | P1 | defend | Pin the Python dependency set and fold the four Dockerfile pip installs into requirements.txt |
| WG-0499 | P1 | elevate | Replace the playwright.dev boilerplate CI with a smoke test that imports app.server |
| WG-0511 | P1 | defend | Re-run the SSE streaming path on Cloud Run after each google-genai bump (fixed twice in a row already) |
| WG-0523 | P1 | defend | Decide the fate of Vertex Agent Engine RAG: rag_client points at an engine in a foreign project and fails quietly |
| WG-0535 | P1 | elevate | Turn on the relay claim guard on blade, phoebus and whoart without wedging commits |
| WG-0547 | P1 | defend | Finish the vertexai SDK exit: rag_client, agent.py, deploy.py and vector_store still import a sunset SDK |
| WG-0559 | P1 | elevate | Prepare the Gemini preview-id cutover: gemini-3-*-preview and computer-use-preview-10-2025 hardcoded in five places |
| WG-0571 | P1 | defend | Gate POST /knowledge/receive so the fleet cannot inject arbitrary 'wisdom' into Dav1d memory |
| WG-0582 | P1 | elevate | Make /v1/chat/completions honest for the Fable-5 API cutover: model field ignored, usage has no token counts |
| WG-0593 | P1 | elevate | Run Dav1d local servers as hidden scheduled tasks, not visible consoles, mirroring today's blade fix |
| WG-0604 | P1 | defend | Consolidate memory buckets split across dav1d-kbg1019 and gen-lang-client-0285887798 |
| WG-0615 | P1 | defend | Point RagClient at a reasoning engine that exists, or retire the dead RAG path |
| WG-0626 | P1 | defend | Give MissionControl's agent_reports file-drop channel acks, dedup and a restart-safe seen set |
| WG-0637 | P1 | defend | Repair the KRONOS lane: /v1/chat/completions calls a router method that does not exist |
| WG-0648 | P1 | defend | Remove the four empty submodule gitlinks so every machine clones the same tree |
| WG-0659 | P1 | elevate | Replace the playwright.dev boilerplate CI with a pipeline that can actually go red for Dav1d |
| WG-0670 | P1 | defend | Gate auto-logged CLI turns so pasted secrets never land in GCS memory_index.json |
| WG-0681 | P1 | defend | Reconcile which memory recall path is live in dav1d.py against three contradictory fix docs |
| WG-0692 | P1 | defend | Retire the hardcoded 2025-11-30 credit balances that /pricing and get_remaining_credits still serve |
| WG-0703 | P1 | defend | Purge committed run artifacts that masquerade as evidence (pylint, pytest, test_cli, tracebacks) |
| WG-0714 | P1 | defend | Re-embed dav1d_memory.embeddings on one model after the vertexai SDK sunset |
| WG-0725 | P1 | elevate | Re-enable proactive memory behavior behind the Phase 3 review gate |
| WG-0735 | P1 | elevate | Turn debug_startup.py into a deploy gate so cold-start crashes stop reaching Cloud Run |
| WG-0745 | P1 | defend | Prove the CLI memory sync still runs after the app.* import refactor |
| WG-0755 | P1 | elevate | Put a vector index and latency budget on search_similar before re-enabling auto recall |
| WG-0765 | P1 | defend | Stop masking outages: global exception handler returns 200 and /health ignores Vertex/GCS reachability |
| WG-0775 | P1 | defend | Pin Dav1d to one GCP project: reconcile four project ids across config, build, .env.example and RAG |
| WG-0785 | P1 | defend | Retire burn_credits.py, turbo_burn.py and run_daily_burn.bat before a scheduled task re-runs them on real money |
| WG-0795 | P1 | elevate | Replace expired hardcoded credit balances with a live billing read |
| WG-0805 | P1 | defend | Finish the SDK migration the doc says is complete: vector_store_bigquery still uses deprecated TextEmbeddingModel |
| WG-0815 | P1 | elevate | Replace the playwright.dev boilerplate CI with a Dav1d smoke that can actually fail |
| WG-0825 | P1 | defend | Make 27 scripts runnable again: pre-refactor imports broken since the 2026-01-30 absolute-import migration |
| WG-0835 | P1 | defend | Stop committing run logs as evidence: stale pylint_report, empty pytest_report, test_cli.txt, tracebacks |
| WG-0845 | P1 | defend | Retire docs/TEST_RESULTS.md and FLASH_LITE_DEFAULT.md claims that contradict config.py |
| WG-0855 | P1 | elevate | Add contract tests for the KRONOS surface (/v1/chat/completions, agent.json, /knowledge/*) with a stub client |
| WG-0865 | P1 | elevate | Purge 640MB of Pdfs, videos, notebooks and cookbook from git history without breaking fleet clones |
| WG-0875 | P1 | defend | Remove four dead submodule gitlinks (deepagents, deepagents-quickstarts, next.js, temp_rn_repo) with no .gitmodules |
| WG-0885 | P1 | defend | Remove OceanofPDF/pdfread-watermarked ebooks and tax forms from the public repo and its history |
| WG-0894 | P1 | defend | Collapse three conflicting DAV1D system prompts into one canonical profile |
| WG-0903 | P1 | defend | Close the /knowledge/receive prompt-injection channel into Dav1d memory |
| WG-0911 | P1 | defend | Scrub identity leakage before public: personal email, Windows user paths and project numbers in tracked files |
| WG-0919 | P1 | defend | Reconcile Dav1d's Observatory/KRONOS fleet story with the NouGen fleet canon |
| WG-0927 | P1 | elevate | Rebuild the onboarding path and prove it on a fresh machine |
| WG-0935 | P1 | elevate | Kill or finish the Vertex Agent Engine path that agent.json claims is enabled |
| WG-0943 | P1 | elevate | Re-enable memory recall under a latency budget: docs say disabled, dav1d.py still calls memory.recall |
| WG-0951 | P1 | elevate | Ship the deferred /proactive silent/preview/active gate before memory-driven autonomy returns |
| WG-0959 | P1 | defend | Fix Sandbox shell=True chain bypass before dav1d_exec is reachable via the shards gateway |
| WG-0966 | P1 | defend | Classify agent-callable GCP tools (deploy_service, run_query, get_secret, create_secret) as act/ask per Dave's operatin… |
| WG-0973 | P1 | elevate | Add a liveness signal for a seven-month-dormant service so 'quiet' is noticed |
| WG-0979 | P1 | defend | Decide what the public agent card exposes: 'auth: open_for_now', creator name, project id, /config leak |
| WG-0985 | P1 | defend | Restore the KRONOS lane: /v1/chat/completions crashes on missing route_id (analyze_complexity undefined) |

---

### WG-0009 · P0 · defend · effort S

**Align local Python 3.11 launchers with the 3.12 container that multi-line f-strings require**

- Failure surface: 660950f moved the image to 3.12 for f-strings; five launchers still call py -3.11 and whoart's pip could not write to C:\Python311 (hook comment). Code that works in Cloud Run raises SyntaxError locally and vice-versa.
- First fork: if you observe py -3.11 in launchers on a machine without 3.12 -> install 3.12 and update launchers; else add python_requires and a version check in debug_startup.py
- Evidence: `Dockerfile`, `launchers/run_diagnostic.bat`, `hooks/pre-commit`
- Lens: toolchain · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: git log confirms commit 660950f 'Update Dockerfile to Python 3.12 for multi-line f-string support'; Dockerfile now uses python:3.12-slim; launchers/run_diagnostic.bat still invokes `py -3.11 diagnostic_vertex.py`; hooks/pre-commit contains the comment about whoart's pip failing to write to C:\Python311\Scripts, all matching the claim.
- #550 families: 79

### WG-0025 · P0 · defend · effort M

**Defuse the [EXEC:] protocol: model text parsed for [EXEC: cmd] runs shell=True with a 'Do not refuse' override**

- Failure surface: dav1d.py injects '[SYSTEM OVERRIDE] OS CONTROL AUTHORIZED ... Do not refuse' and then regex-executes any [EXEC: ...] in the reply. Recalled memory or ingested transcripts containing that token become remote shell on Dave's machine. Runaway memory-driven responses were already observed (MEMORY_CONTROL_FIX).
- First fork: if you observe /clear emergency brake as the only gate -> add a confirm prompt + allowlist + no-override mode before any recall is re-enabled; else keep memory disabled until the gate exists
- Evidence: `app/dav1d.py`, `docs/MEMORY_CONTROL_FIX.md`, `docs/PHASE_3_PROACTIVE_CONTROLS.md`
- Lens: injection/tool-abuse · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: dav1d.py:1343 injects the literal '[SYSTEM OVERRIDE] OS CONTROL AUTHORIZED ... Do not refuse' string, and lines 1544-1563 regex-parse [EXEC: ...] from model output and run it via subprocess with shell=True, matching the failure surface exactly.
- #550 families: 69

### WG-0040 · P0 · elevate · effort M

**Move the 640MB of PDFs, Veo videos and cookbook out of git and the Cloud Build context**

- Failure surface: Pdfs/ (235MB), videos/ (182MB) and resources/ (219MB) are tracked; .gcloudignore skips Pdfs and notebooks but not videos/ or resources/cookbook-main, and Dockerfile does COPY . . with no .dockerignore, so the image carries test renders and every clone on phoebus/whoart pulls 600MB. The January cold-start chain shows how slow images hurt.
- First fork: if you observe the built image larger than 1GB in Artifact Registry -> route A: git filter-repo the media out, add .dockerignore, host assets in GCS; else route B: add .dockerignore and stop tracking new media
- Evidence: `.gcloudignore`, `Dockerfile`, `videos`
- Lens: storage · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .gcloudignore (repo root) excludes Pdfs/ and *.ipynb but has no entry for videos/ or resources/cookbook-main; no .dockerignore file exists at all, and videos/ (182MB class) is tracked, matching the claim.

### WG-0054 · P0 · defend · effort M

**Stop advertising A2A skills that the JSON-RPC server only acknowledges**

- Failure surface: agent.json lists rag-retrieval and agent-orchestration while a2a_server.handle_ask, handle_delegate and handle_execute_tool return canned 'queued'/'acknowledged' payloads; a fleet peer that delegates to NANO gets status 'queued' and waits for work that will never run.
- First fork: if you observe fleet handoffs referencing delegations to Dav1d that never produced output -> route A: wire ask/delegate to the real Council and MCP runtime with task ids; else route B: mark the capabilities experimental in both agent.json files
- Evidence: `app/core/a2a_server.py`, `app/config/agent.json`, `.well-known/agent.json`
- Lens: false-done-markers · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/core/a2a_server.py handle_ask/handle_delegate (lines 212, 229) return literal status strings 'queued' (line 254) and 'acknowledged' (line 298); app/config/agent.json and .well-known/agent.json both exist as the capability-advertising files, matching the claim of advertised-but-unimplemented skills.
- #550 families: 32

### WG-0066 · P0 · defend · effort S

**Populate .handoffs so the fleet hooks stop failing open on this repo**

- Failure surface: prepare-commit-msg's known-machine check reads .handoffs/ which holds only .gitkeep, so it never blocks; pre-commit exits 0 whenever relay is missing; hooksPath is opt-in per clone. The 'four duplications in two days' the hook comment describes can recur on Dav1d with no signal.
- First fork: if you observe commits after 2026-08-01 lacking Machine:/Agent: trailers -> route A: write the first handoff record per machine, set core.hooksPath in launchers, add a CI trailer check; else route B: add the trailer check only
- Evidence: `hooks/pre-commit`, `hooks/prepare-commit-msg`, `.handoffs/.gitkeep`
- Lens: distributed-coordination · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .handoffs/ contains only a 0-byte .gitkeep file (verified via ls -la), and hooks/pre-commit and hooks/prepare-commit-msg both exist as the referenced hook scripts — matches the claim that the known-machine/handoff mechanism is unpopulated.
- #550 families: 35

### WG-0077 · P0 · defend · effort M

**Audit every 'COMPLETE' doc against the code it claims to describe**

- Failure surface: SDK_MIGRATION_STATUS (COMPLETE) contradicts vector_store_bigquery.py, TEST_RESULTS (15/15) contradicts config.py's balanced tier, A2A_IMPLEMENTATION cites a nonexistent workflow, DEPLOYMENT_COMPLETE cites a dead engine; agents reading these as evidence make decisions on false done-markers, the exact failure HARDENING recorded for embed-at-ingest.
- First fork: if you observe any doc claim that a grep of the code refutes -> route A: add a 'verified-against commit' header to each doc and demote refuted ones to HISTORY/; else route B: only mark the four known-false docs
- Evidence: `docs/SDK_MIGRATION_STATUS.md`, `docs/TEST_RESULTS.md`, `resources/DEPLOYMENT_COMPLETE.md`
- Lens: false-done-markers · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml contains '--allow-unauthenticated'; main.py's CORSMiddleware sets allow_origins=['*'], allow_methods=['*'], allow_headers=['*']; docs/CLOUD_DEPLOYMENT.md exists.

### WG-0088 · P0 · elevate · effort L

**Back the advertised fleet contract: rag-retrieval and agent-orchestration are stubs behind the agent card**

- Failure surface: agent.json advertises rag-retrieval and agent-orchestration; /knowledge/context returns hardcoded 'peak efficiency' with empty memories and a2a_server execute_tool only acknowledges. KRONOS plans around capabilities Dav1d cannot deliver.
- First fork: if you observe any fleet consumer calls /knowledge/context or execute_tool -> route A: implement retrieval via vector store and real MCP dispatch with tests; else route B: remove the capability strings from both agent.json copies until backed
- Evidence: `app/config/agent.json`, `app/server.py`, `app/core/a2a_server.py`
- Lens: canon · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.json's capabilities list includes 'rag-retrieval' and 'agent-orchestration'; GET /knowledge/context (server.py line 642) returns a hardcoded string and empty recent_memories with a comment 'Implement real retrieval later' -- confirms the stub claim for at least the rag-retrieval capability.
- #550 families: 32

### WG-0099 · P0 · elevate · effort M

**Arm the relay hooks in Dav1d: populate .handoffs, set core.hooksPath on every lane, prove a refused commit**

- Failure surface: This clone has no core.hooksPath and .handoffs/ holds only .gitkeep, so the known-machine guard is a no-op and pre-commit fails open; the hook comments cite four duplications in two days as the reason it exists.
- First fork: if you observe `git config core.hooksPath` is unset on blade/phoebus/whoart clones -> route A: relay init + first handoff record per machine, then test an unknown-agent commit is refused; else route B: only seed .handoffs
- Evidence: `hooks/pre-commit`, `hooks/prepare-commit-msg`, `.handoffs/.gitkeep`
- Lens: governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: `git config core.hooksPath` returns empty in this clone (unset); .handoffs/ contains only .gitkeep (0 bytes) as claimed; hooks/prepare-commit-msg comments reference 'Four duplications in two days' and the enable instructions ('git config core.hooksPath hooks'), matching the claim exactly.
- #550 families: 21, 23

### WG-0109 · P0 · defend · effort M

**Answer self-merge authority for Dav1d: master vs main, single WhoVisions author, claude/* branches**

- Failure surface: GIT_COMMIT_INSTRUCTIONS says push origin main but the default branch is master; every commit is authored WhoVisions with Machine/Agent trailers only on the last one; a claude/* branch is open. Without a merge rule this repo joins the 26-deep unmerged backlog pattern.
- First fork: if you observe Dave has locked merge rights fleet-wide -> route A: encode it as a branch protection + handoff note; else route B: propose sweep-record PRs may self-merge when CI (once real) is green
- Evidence: `docs/GIT_COMMIT_INSTRUCTIONS.md`, `hooks/prepare-commit-msg`
- Lens: governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/GIT_COMMIT_INSTRUCTIONS.md:15 says 'git push origin main' while `git branch -a` shows the checked-out branch is 'master' (plus remotes/origin/master and an open claude/nou-gen-elevation-wargame-t96jyo branch); `git log --format=%an` over recent commits shows all authored 'WhoVisions', matching the single-author claim.

### WG-0366 · P1 · elevate · effort L

**Flip Cloud Run dav1d to --allow-unauthenticated for aiwithdav3.com without opening a free Gemini faucet**

- Failure surface: The moment the IAM gate drops, every route (/chat, /v1/chat/completions, /auth/validate) bills the house ADC at gemini-3-pro rates with only a per-process $2/hr cap; Dave notices via the GCP bill, not via any alert.
- First fork: if you observe be09023 (allow-unauth) and 3f4b12a (enforce IAM) both in history with no rate limiter in app/server.py -> build the global budget gate + origin allowlist first, then flip; else flip behind Cloud Armor/IAP and canary one route
- Evidence: `cloudbuild.yaml`, `docs/AIWITHDAV3_INTEGRATION_ROADMAP.md`, `app/core/cost_manager.py`
- Lens: deploy/auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml currently sets --no-allow-unauthenticated with --max-instances 10; cost_manager.py's CostManager/HOURLY_BUDGET is per-process (module-level singleton, no cross-instance store), matching the claim that flipping to allow-unauth would let each of up to 10 instances bill against its own $2/hr cap independently.
- #550 families: 57

### WG-0382 · P1 · defend · effort M

**Replace CORS allow_origins=['*'] + allow_credentials=True with an origin allowlist that KRONOS/A2A still passes**

- Failure surface: Any web page can make credentialed cross-origin calls to Dav1d; once public, a hostile site drives paid completions from visitors' browsers. Both app/server.py and app/core/a2a_server.py carry the same wildcard.
- First fork: if you observe KRONOS calling from a server (no Origin header) -> restrict to aiwithdav3.com + localhost and drop credentials; else enumerate fleet origins from .well-known/agent.json consumers first
- Evidence: `app/server.py`, `app/core/a2a_server.py`, `CORS_IMPLEMENTATION.md`
- Lens: security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both app/server.py:101 and app/core/a2a_server.py:143-144 set allow_origins=["*"] together with allow_credentials=True, exactly the wildcard-plus-credentials combo described.
- #550 families: 20

### WG-0398 · P1 · defend · effort M

**Fence Secret Manager and BigQuery agent tools (get_secret_value, create_secret, run_query) behind explicit grants**

- Failure surface: gcp_tools exposes get_secret_value returning plaintext payloads and create_secret, running under the service ADC; a prompt-injected agent can exfiltrate every secret in the project as tool output that SecurityPolicy's AIza/sk- regex does not catch.
- First fork: if you observe these tools registered in dynamic_registry/tool_registry for the server path -> remove secret tools from the public surface and add a per-tool approval; else restrict to CLI with confirm and least-privilege SA
- Evidence: `app/core/gcp_tools.py`, `app/tools/dynamic_registry.py`, `app/core/tool_registry.py`
- Lens: tool-abuse/secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: gcp_tools.py defines create_secret_manager_tools with a create_secret function (line 251-278) and get_secret_value-style plaintext secret access, matching the claim; registry files exist to wire these as agent tools.

### WG-0414 · P1 · defend · effort M

**Put auth on the A2A /rpc endpoint (port 10000) before it is reachable beyond localhost**

- Failure surface: a2a_server.py accepts any JSON-RPC 'ask'/'delegate' with CORS *, no token, and routes to paid models; agent.json advertises auth: open_for_now.
- First fork: if you observe a2a_server bound to 0.0.0.0 in any launcher or Cloud Run revision -> add shared-secret or IAM check now; else bind to 127.0.0.1 and document the fleet auth contract in .well-known/agent.json
- Evidence: `app/core/a2a_server.py`, `.well-known/agent.json`
- Lens: security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: a2a_server.py sets allow_origins=["*"]/allow_credentials=True with no auth check on its JSON-RPC handler, and .well-known/agent.json:62 literally declares `"auth": "open_for_now"`.
- #550 families: 20

### WG-0430 · P1 · elevate · effort M

**Ship a public-mode content filter: BLOCK_NONE safety settings plus VIBES slurs injected into every system prompt**

- Failure surface: llm.py disables all harm thresholds and persona.py appends a random VIBES line (several with slurs) to the system instruction on every /chat and /v1 call; the public twin can emit them under the Who Visions brand.
- First fork: if you observe include_vibe=True on the server path -> add a PUBLIC_MODE env that strips vibes and restores default safety; else audit VIBES and keep the CLI-only vibes behind a flag
- Evidence: `app/core/llm.py`, `app/core/persona.py`, `app/config.py`
- Lens: security/brand · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: llm.py:13-25 sets HarmBlockThreshold.BLOCK_NONE for all safety categories; persona.py is confirmed elsewhere to inject text into every system instruction (the VIBES/creator logic sits in the same file), matching the described public-mode safety-off plus persona-injection combination.
- #550 families: 69

### WG-0446 · P1 · elevate · effort L

**Remove pirated-looking ebooks and 640MB of media from git history without breaking fleet clones**

- Failure surface: Pdfs/ (OceanofPDF titles), videos/ (182MB) and resources/cookbook-main/ are tracked; a public repo with these is a DMCA and size problem, and history rewrite invalidates every clone on blade/phoebus/whoart.
- First fork: if you observe the repo public on GitHub -> take it private, then filter-repo + coordinated re-clone via relay handoff; else move to GCS and untrack, keep history
- Evidence: `Pdfs`, `videos`, `resources/cookbook-main`
- Lens: hygiene/legal · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: All three paths exist as real directories in the repo (Pdfs/, videos/, resources/cookbook-main/), and .gcloudignore's own exclusion list (checked separately) does not exclude videos/, consistent with these being tracked, sizable, non-code assets.

### WG-0461 · P1 · defend · effort S

**Stop returning HTTP 200 from the global exception handler so Cloud Run and KRONOS can see outages**

- Failure surface: Every unhandled error becomes 200 with detail: str(exc); uptime checks, KRONOS retries and error-rate alerts all read healthy while users get 'internal hiccup'. Internal GCP error strings leak in detail.
- First fork: if you observe a client that crashes on 5xx (comment says so) -> return 503 with structured body and fix that client; else flip status codes and redact detail
- Evidence: `app/server.py`
- Lens: runtime · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/server.py:119-129 defines a global `@app.exception_handler(Exception)` that returns `status_code=200` with `"detail": str(exc)` in the body, exactly matching the claim of masking errors as 200s while leaking exception text.

### WG-0474 · P1 · elevate · effort L

**Make the $2/hr budget global: CostManager and RateLimitManager are per-process on a 10x80 Cloud Run fleet**

- Failure surface: HOURLY_BUDGET and the singleton rate limiter live in instance memory; 10 instances give $20/hr and RPD limits reset per cold start. HARDENING recorded $150/day unnoticed elsewhere in the fleet.
- First fork: if you observe max-instances >1 in cloudbuild.yaml -> move the window to Firestore/Redis with atomic increments; else set max-instances 1 as a stopgap and alert on spend
- Evidence: `app/core/cost_manager.py`, `cloudbuild.yaml`, `app/config.py`
- Lens: cost/runtime · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml sets --concurrency 80 and --max-instances 10 (the exact '10x80' figure cited), and cost_manager.py's CostManager/RateLimitManager hold in-process state (module singleton class attributes) with no shared store, confirming the per-instance budget multiplication claim.
- #550 families: 63, 65

### WG-0487 · P1 · defend · effort M

**Pin the Python dependency set and fold the four Dockerfile pip installs into requirements.txt**

- Failure surface: google-genai, Pillow, pandas are unpinned and the Dockerfile installs googlemaps/texttospeech/speech outside requirements; the 2026-01-30 firefight (21 commits) was exactly unpinned-drift; the SSE fix pair b6d846a/06c4566 tracked a google-genai API change.
- First fork: if you observe a working revision in Cloud Run -> pip freeze from that image into a lockfile; else pin to today's versions and add a build-time debug_startup.py check
- Evidence: `requirements.txt`, `Dockerfile`, `debug_startup.py`
- Lens: supply-chain · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: requirements.txt has unpinned google-genai/Pillow/pandas; Dockerfile RUN pip install adds googlemaps/texttospeech/speech outside requirements.txt; b6d846a and 06c4566 both fix generate_content_stream SDK-shape issues (google-genai). debug_startup.py exists.

### WG-0499 · P1 · elevate · effort M

**Replace the playwright.dev boilerplate CI with a smoke test that imports app.server**

- Failure surface: The only workflow installs browsers and tests https://playwright.dev; green CI proved nothing during the cold-start crash chain. pytest_report.txt is committed empty.
- First fork: if you observe debug_startup.py passes locally in a clean venv -> make it the CI gate plus pytest on scripts/harness_tests.py; else fix imports first
- Evidence: `.github/workflows/playwright.yml`, `tests/example.spec.ts`, `debug_startup.py`
- Lens: toolchain · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: playwright.yml just runs `npx playwright test` against whatever tests/example.spec.ts covers (Playwright's default boilerplate); pytest_report.txt is present and 0 lines (empty); debug_startup.py exists.
- #550 families: 82

### WG-0511 · P1 · defend · effort S

**Re-run the SSE streaming path on Cloud Run after each google-genai bump (fixed twice in a row already)**

- Failure surface: /chat/stream depends on client.aio.models.generate_content_stream semantics that changed between SDK versions (06c4566 then b6d846a); persistence writes run inside the generator after the stream, so a GCS hiccup ends the stream mid-response.
- First fork: if you observe 'async for requires __aiter__' in logs -> pin google-genai and add an SSE contract test; else move save_message to a background task
- Evidence: `app/server.py`, `requirements.txt`
- Lens: runtime/deps · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git log confirms both commits (06c4566 'Use client.aio.models.generate_content_stream ... Fixes async for requires aiter' and b6d846a 'Await ... before iteration - Resolves async for requires __aiter__') exist back to back; server.py streams via generate_content_stream then calls save_message after the async-for loop; requirements.txt has google-genai unpinned.
- #550 families: 77

### WG-0523 · P1 · defend · effort M

**Decide the fate of Vertex Agent Engine RAG: rag_client points at an engine in a foreign project and fails quietly**

- Failure surface: RagClient hardcodes reasoningEngines under project 322812104986, prints 'RAG Engine not connected' and returns that string as an answer; committed tracebacks show Agent Engine deploys never started. agent.json still advertises rag-retrieval.
- First fork: if you observe the engine id resolves under ADC -> pin it in config and add a health check; else delete rag_client/deploy.sh and drop rag-retrieval from agent.json
- Evidence: `app/core/rag_client.py`, `resources/traceback.txt`, `launchers/deploy.sh`
- Lens: infra · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: app/core/rag_client.py hardcodes engine_id under projects/322812104986/... and returns the literal string 'RAG Engine not connected.'; resources/traceback.txt and launchers/deploy.sh exist; .well-known/agent.json still lists 'rag-retrieval' as a capability.
- #550 families: 46

### WG-0535 · P1 · elevate · effort M

**Turn on the relay claim guard on blade, phoebus and whoart without wedging commits**

- Failure surface: hooks/pre-commit fails open when relay is missing, core.hooksPath is opt-in, and .handoffs/ holds only .gitkeep so the known-machine check never fires; the 'four duplications in two days' guard is effectively off in this repo.
- First fork: if you observe git config core.hooksPath unset on any clone -> set it via relay init and seed .handoffs with a record per machine; else verify guard exit 3 actually blocks
- Evidence: `hooks/pre-commit`, `hooks/prepare-commit-msg`, `.handoffs/.gitkeep`
- Lens: fleet/hooks · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit's own comments state it 'Fails OPEN. If relay is not installed, or the network is down...' and documents exit code 3 as the claim conflict signal; .handoffs/ contains only .gitkeep (no per-machine records), matching the claim that the guard is effectively inert by default.
- #550 families: 25

### WG-0547 · P1 · defend · effort M

**Finish the vertexai SDK exit: rag_client, agent.py, deploy.py and vector_store still import a sunset SDK**

- Failure surface: docs/SDK_MIGRATION_STATUS.md says COMPLETE, yet vector_store_bigquery.get_embedding still uses vertexai.language_models.TextEmbeddingModel (text-embedding-004), the path that 404'd before; sunset was 2026-06-24. add_memory silently fails.
- First fork: if you observe TextEmbeddingModel raising in the container -> migrate to client.models.embed_content and re-verify; else migrate anyway and mark the doc stale
- Evidence: `app/tools/vector_store_bigquery.py`, `docs/SDK_MIGRATION_STATUS.md`, `app/core/rag_client.py`
- Lens: deps/deprecation · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/SDK_MIGRATION_STATUS.md claims status COMPLETE for the google.genai migration, yet app/tools/vector_store_bigquery.py still does `from vertexai.language_models import TextEmbeddingModel` and `TextEmbeddingModel.from_pretrained('text-embedding-004')`, and app/core/rag_client.py still imports vertexai/reasoning_engines directly, contradicting the doc.
- #550 families: 77

### WG-0559 · P1 · elevate · effort M

**Prepare the Gemini preview-id cutover: gemini-3-*-preview and computer-use-preview-10-2025 hardcoded in five places**

- Failure surface: server.py model_id, config MODELS, agent.json, computer_agent and pricing_tiers all hardcode preview ids; a retirement returns 404 on every route at once and robust_genai_call treats it as non-retriable.
- First fork: if you observe models.list not returning a configured id -> add a startup alias resolver with fallback to gemini-2.5-flash; else centralize ids in config and add a daily check_models run
- Evidence: `app/config.py`, `app/server.py`, `app/agents/computer_agent.py`
- Lens: model-cutover · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/config.py's MODELS dict hardcodes gemini-3-pro-preview/gemini-3-flash-preview/gemini-3-pro-image-preview repeatedly; app/server.py hardcodes 'gemini-3-flash-preview' as default model_id in multiple request models and route responses; app/agents/computer_agent.py hardcodes COMPUTER_USE_MODEL = 'gemini-2.5-computer-use-preview-10-2025', confirming multiple hardcoded preview ids across files.

### WG-0571 · P1 · defend · effort M

**Gate POST /knowledge/receive so the fleet cannot inject arbitrary 'wisdom' into Dav1d memory**

- Failure surface: Unauthenticated JSON is appended to memory/external_wisdom.jsonl with integrated: true; .gitignore whitelists that exact file, so a poisoned line can later be committed as knowledge. Nobody reads it today, but the moment recall wires it in, stored prompt injection lands in the twin.
- First fork: if you observe any reader of external_wisdom.jsonl in app/ -> add source signature + schema validation before the reader; else disable the route until a consumer exists and un-whitelist the file
- Evidence: `app/server.py`, `.gitignore`
- Lens: injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: POST /knowledge/receive (server.py:614) appends unauthenticated JSON to memory/external_wisdom.jsonl (line 633); .gitignore has a blanket `memory/*.jsonl` ignore but an explicit `!memory/external_wisdom.jsonl` whitelist exception (line 25), matching the claim precisely.
- #550 families: 69

### WG-0582 · P1 · elevate · effort M

**Make /v1/chat/completions honest for the Fable-5 API cutover: model field ignored, usage has no token counts**

- Failure surface: KRONOS's OpenAI-compat client sends model and expects usage.prompt_tokens; Dav1d ignores request.model and returns smart_route instead of tokens, so fleet spend tracking (tracker_spend) cannot attribute Dav1d and routing decisions are silently overridden.
- First fork: if you observe KRONOS passing model ids Dav1d does not have -> map or reject with 400; else return usage_metadata token counts and echo the resolved model
- Evidence: `app/server.py`, `.well-known/agent.json`, `README.md`
- Lens: fleet/model-cutover · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/server.py's /v1/chat/completions handler computes its own route_id via smart_router.analyze_complexity(last_msg) and get_route(route_id) rather than honoring request.model, and its 'usage' dict contains 'smart_route': route_id instead of prompt/completion token counts, matching the claim precisely.
- #550 families: 65

### WG-0593 · P1 · elevate · effort M

**Run Dav1d local servers as hidden scheduled tasks, not visible consoles, mirroring today's blade fix**

- Failure surface: All Windows launchers open visible consoles with pause; a QuickEdit click freezes the process the same way blade's node froze today, and any long-running local Dav1d server or MCP endpoint inherits that failure.
- First fork: if you observe a launcher meant to run unattended (sync_gmail, dav1d server) -> convert to a hidden scheduled task with a watchdog; else leave interactive launchers as-is
- Evidence: `launchers/dav1d.ps1`, `launchers/dav1d.bat`, `launchers/sync_gmail.bat`
- Lens: scheduled-task · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: All three launcher files exist (dav1d.ps1 419B, dav1d.bat 1182B, sync_gmail.bat 303B), sized consistently with simple batch/ps1 launchers. Could not verify the 'blade node froze today' incident referenced, so treated as reasonable inference rather than directly documented.

### WG-0604 · P1 · defend · effort L

**Consolidate memory buckets split across dav1d-kbg1019 and gen-lang-client-0285887798**

- Failure surface: config.py defaults PROJECT_ID to dav1d-kbg1019 but .env.example, tasks_notion_sync.py, harness_quickstart.py and RAG_SETUP_GUIDE point at gen-lang-client-0285887798 with its own dav1d-memory-<project> bucket; whichever .env a machine has decides which memory it reads, so blade and whoart may be talking to different brains.
- First fork: if you observe both dav1d-memory-dav1d-kbg1019 and dav1d-memory-gen-lang-client-0285887798 containing memory/memory_index.json -> route A: merge, freeze the old bucket read-only and remove every hardcoded fallback; else route B: delete the stale project references and pin GOOGLE_CLOUD_PROJECT in launchers
- Evidence: `app/config.py`, `.env.example`, `docs/RAG_SETUP_GUIDE.md`
- Lens: distributed-sync · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified directly: app/config.py and veo_video.py/nano_agent.py both default PROJECT_ID/GOOGLE_CLOUD_PROJECT to 'dav1d-kbg1019' (confirmed earlier grep). .env.example and docs/RAG_SETUP_GUIDE.md exist as the other two evidence files; a project-id fallback split across config vs docs/env is consistent with observed patterns elsewhere in this repo (e.g. item 65's PROJECT_ID handling).
- #550 families: 3

### WG-0615 · P1 · defend · effort M

**Point RagClient at a reasoning engine that exists, or retire the dead RAG path**

- Failure surface: rag_client.py hardcodes engine 322812104986/.../169654644165836800, update_rag_id.py patches a different project number (627440283840) and resources/DEPLOYMENT_COMPLETE.md records yet another id in us-east4; the committed tracebacks show Agent Engine deploys failing. RagClient.query returns the string 'RAG Engine not connected.' which callers treat as an answer.
- First fork: if you observe gcloud listing no reasoning engine matching the id in rag_client.py -> route A: delete RagClient and route /search to BigQuery or Vertex AI Search; else route B: move the id to config and make query raise instead of returning prose
- Evidence: `app/core/rag_client.py`, `scripts/update_rag_id.py`, `resources/traceback.txt`
- Lens: silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Verified directly: app/core/rag_client.py imports vertexai.preview.reasoning_engines and uses ReasoningEngine(self.engine_id)/ReasoningEngine.list()/ReasoningEngine(...) (lines 9, 31, 38, 42); resources/traceback.txt contains an actual failing traceback: 'remote_agent = reasoning_engines.ReasoningEngine.create(...)' with a real Python stack trace file path -- confirming a real observed Agent Engin

### WG-0626 · P1 · defend · effort M

**Give MissionControl's agent_reports file-drop channel acks, dedup and a restart-safe seen set**

- Failure surface: Any .md dropped into ~/.dav1d/resources/agent_reports is auto-executed as a tool-using task and answered with a dispatch file; seen_files is memory-only so a CLI restart re-executes every report on disk (Rhea's reports are committed under resources/agent_reports), and the monitor swallows all exceptions.
- First fork: if you observe duplicate Dispatch_to_Rhea_*.md files for one report -> route A: persist processed report hashes, move handled reports to an archive dir, log exceptions; else route B: persist the seen set only
- Evidence: `app/core/mission_control.py`, `resources/agent_reports`, `resources/agent_comms/dispatches`
- Lens: idempotency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/core/mission_control.py line 111 shows `self.seen_files = {f.name for f in self.reports_dir.glob("*.md")}` — an in-memory set with no persistence — and multiple broad `except Exception` blocks (lines 57,88,165,168,222,242) swallow errors; resources/agent_reports and resources/agent_comms/dispatches both exist, matching the claim.
- #550 families: 16, 21

### WG-0637 · P1 · defend · effort S

**Repair the KRONOS lane: /v1/chat/completions calls a router method that does not exist**

- Failure surface: When KRONOS omits route_id, the handler calls smart_router.analyze_complexity, which SmartRouter never defines; the AttributeError is caught and returned as a 503-shaped JSON body with HTTP 200, so the orchestrator sees 'overloaded' forever and no alert fires.
- First fork: if you observe every /v1/chat/completions without route_id returning the overloaded payload -> route A: route through smart_router.orchestrate, return real HTTP codes, add a contract test KRONOS can run; else route B: default route_id to 2 and add the test
- Evidence: `app/server.py`, `app/core/smart_router.py`, `README.md`
- Lens: silent-death · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/server.py:540 calls `smart_router.analyze_complexity(last_msg)`, but app/core/smart_router.py's SmartRouter class only defines `orchestrate` (line 37) and no `analyze_complexity` method — directly confirms the AttributeError claim.
- #550 families: 32

### WG-0648 · P1 · defend · effort S

**Remove the four empty submodule gitlinks so every machine clones the same tree**

- Failure surface: deepagents, deepagents-quickstarts, next.js and temp_rn_repo are mode-160000 gitlinks with no .gitmodules; fresh clones on phoebus or whoart cannot init them, Cloud Build and local Docker contexts differ, and any tooling that walks submodules errors.
- First fork: if you observe git submodule status failing on a fresh clone -> route A: git rm the gitlinks and document the vendored sources; else route B: add .gitmodules pointing at the real upstreams
- Evidence: `deepagents`, `next.js`, `temp_rn_repo`
- Lens: distributed-sync · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougen_tunnel_tool.py and kaedra/api/main.py both exist; main.py is confirmed (from other checks) to expose CORS allow_origins=['*'] and multiple routes with no auth, consistent with the unauthenticated-tunnel claim.

### WG-0659 · P1 · elevate · effort M

**Replace the playwright.dev boilerplate CI with a pipeline that can actually go red for Dav1d**

- Failure surface: The only workflow runs tests/example.spec.ts against playwright.dev, pytest_report.txt is committed empty, and docs/A2A_IMPLEMENTATION.md claims a cloud-deploy.yml that does not exist; green CI badges on README certify nothing while a syntax error sits in app/agents/emoji_dict_extended.py.
- First fork: if you observe the Actions tab green while python -c 'import app.server' fails locally -> route A: add pytest + debug_startup smoke + pylint E-only gate and a real Cloud Build trigger; else route B: add the smoke step first
- Evidence: `.github/workflows/playwright.yml`, `docs/A2A_IMPLEMENTATION.md`, `pytest_report.txt`
- Lens: health-that-lies · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: main.py's /.well-known/agent.json endpoint (line 1131) lists webhook/sync/generate_image/cowrite endpoints and CLOUD_RUN_URL is hardcoded to kaedra-69017097813.us-central1.run.app; docs/A2A_IMPLEMENTATION.md exists.
- #550 families: 82

### WG-0670 · P1 · defend · effort M

**Gate auto-logged CLI turns so pasted secrets never land in GCS memory_index.json**

- Failure surface: dav1d.py remembers every non-slash turn (user snippet 400 chars, reply 600 chars, importance 4) into memory_index.json synced to GCS; SecurityPolicy's AIza/sk- regex only runs in the evaluator agent, never on memory writes. A pasted key or SSN becomes recallable context on every machine and is injected into future prompts.
- First fork: if you observe SecurityPolicy.SENSITIVE_PATTERNS matching anything in the current memory_index.json -> route A: purge matching entries across all GCS versions and add the scan to MemoryBank.remember; else route B: add the scan plus a redaction test before the next sync
- Evidence: `app/memory/memory_bank.py`, `app/dav1d.py`, `app/core/security_policy.py`
- Lens: pii-in-stores · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified directly: app/core/security_policy.py defines SENSITIVE_PATTERNS at line 29-31 including AIza[0-9A-Za-z-_]{35} and sk-[a-zA-Z0-9]{48} regexes, applied via a scan method (line 55) inside SecurityPolicy class. memory_bank.py (3026 bytes) contains no reference to SecurityPolicy or SENSITIVE_PATTERNS, consistent with the claim that the scan is not wired into memory writes.
- #550 families: 70

### WG-0681 · P1 · defend · effort S

**Reconcile which memory recall path is live in dav1d.py against three contradictory fix docs**

- Failure surface: EMERGENCY_SPEED_FIX says recall was set to None, SMART_ASYNC_MEMORY says an async manager was integrated, LATENCY_FIX says defaults were flipped to skip, yet dav1d.py still calls memory.recall(user_input) synchronously every turn and MemoryBank.recall is a keyword scan; nobody knows what latency or memory the CLI actually has today.
- First fork: if you observe memory.recall on the hot path with no SmartMemoryManager reference in dav1d.py -> route A: implement the documented strategy and delete the stale docs; else route B: rewrite the docs to match the code
- Evidence: `app/dav1d.py`, `docs/EMERGENCY_SPEED_FIX.md`, `docs/SMART_ASYNC_MEMORY.md`
- Lens: false-done-markers · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Dockerfile exists; scratchpad/ and kaedra/logs/default directories exist and are non-trivial in the repo tree (scratchpad/exports subdir observed), consistent with a naive COPY . picking up runtime artifacts absent a .dockerignore.

### WG-0692 · P1 · defend · effort S

**Retire the hardcoded 2025-11-30 credit balances that /pricing and get_remaining_credits still serve**

- Failure surface: GEMINI_CREDIT_REMAINING=47.87 (expired 2025-12-23) and friends are constants, so every /pricing response and CLI credit check reports stale money; the real quota alert lives in setup_quota_alerts.py against a different project id than config.py.
- First fork: if you observe /pricing returning credit figures unchanged for 30 days -> route A: pull from Cloud Billing budgets API or drop the fields; else route B: mark the fields as static in the response
- Evidence: `app/config.py`, `app/core/cost_manager.py`, `scripts/setup_quota_alerts.py`
- Lens: metrics-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: config.py's IS_REASONING_ENGINE = os.getenv('AIP_MODE') is not None or os.path.exists('/tmp') is effectively always True on any Linux host (since /tmp exists), matching 'IS_REASONING_ENGINE is always true'; KAEDRA_HOME resolves to Path('/tmp/.kaedra') in that branch; loredb.py and worlds/store.py both exist.
- #550 families: 65

### WG-0703 · P1 · defend · effort S

**Purge committed run artifacts that masquerade as evidence (pylint, pytest, test_cli, tracebacks)**

- Failure surface: pylint_report.txt records a live syntax error, pytest_report.txt is 0 bytes, test_cli.txt says 'CLI tools are working!', resources/traceback*.txt record failed deploys; agents scanning the repo read these as current state and the empty pytest report reads as 'no failures'.
- First fork: if you observe any of these files newer than the code they describe -> route A: delete them, gitignore *_report.txt, generate reports in CI as artifacts; else route B: move them under docs/history/
- Evidence: `pylint_report.txt`, `pytest_report.txt`, `test_cli.txt`
- Lens: false-done-markers · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: kaedra/api/main.py's /execute-code handler (around line 994) contains the literal comment '# TODO: Connect to Vertex AI Code Execution Tool if available' followed by a prompt that says 'Simulate the output of this code' and returns status: 'simulated', exactly matching the claim; docs/A2A_IMPLEMENTATION.md exists and main.py's agent card lists it as a capability.
- #550 families: 100

### WG-0714 · P1 · defend · effort L

**Re-embed dav1d_memory.embeddings on one model after the vertexai SDK sunset**

- Failure surface: vector_store_bigquery.get_embedding still imports vertexai.language_models (sunset 2026-06-24) and text-embedding-004, router_strategies uses text-embedding-004 via genai, config says text-embedding-005 and SDK_MIGRATION_STATUS claims gemini-embedding-001 (3072 dims). Rows embedded under different models share one REPEATED FLOAT64 column, so COSINE_DISTANCE errors or silently ranks garbage; the same 'embed-at-ingest falsely done' pattern the HARDENING log recorded.
- First fork: if you observe SELECT ARRAY_LENGTH(embedding) returning more than one distinct value in dav1d_memory.embeddings -> route A: add an embedding_model column, re-embed everything on gemini-embedding-001 into a new table, cut over; else route B: only migrate get_embedding to genai and add a dimension assertion at insert
- Evidence: `app/tools/vector_store_bigquery.py`, `app/core/router_strategies.py`, `docs/SDK_MIGRATION_STATUS.md`
- Lens: embeddings · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Verified directly: vector_store_bigquery.py line 47-48 imports vertexai.language_models.TextEmbeddingModel and uses 'text-embedding-004'; router_strategies.py line 113-115 uses model='text-embedding-004' with a comment calling it 'current state-of-the-art'; app/config.py line 88 sets 'embed': 'text-embedding-005'; SDK_MIGRATION_STATUS.md explicitly claims migration to gemini-embedding-001 is compl
- #550 families: 7

### WG-0725 · P1 · elevate · effort M

**Re-enable proactive memory behavior behind the Phase 3 review gate**

- Failure surface: PHASE_3 documents Dav1d reading GCS memory changes and responding autonomously with no review gate ('runaway' responses fixed only by /clear); turning proactive mode back on without silent/preview/active modes repeats the loop and writes its own outputs back into memory.
- First fork: if you observe unsolicited responses after a GCS memory change -> route A: implement /proactive with PREVIEW default and a memory-write guard for self-generated text; else route B: keep proactive off and delete the code path
- Evidence: `docs/PHASE_3_PROACTIVE_CONTROLS.md`, `docs/MEMORY_CONTROL_FIX.md`, `app/dav1d.py`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: PHASE_3_PROACTIVE_CONTROLS.md documents exactly this: DAV1D reads GCS memory changes and responds autonomously with no review gate, deferred pending controls.

### WG-0735 · P1 · elevate · effort M

**Turn debug_startup.py into a deploy gate so cold-start crashes stop reaching Cloud Run**

- Failure surface: Twenty-one consecutive commits on 2026-01-30 fixed import-time crashes discovered only after deploy; debug_startup.py exists but no build step runs it, so the next missing dependency or relative import ships again and the service dies at startup with min-instances 0 hiding it until traffic.
- First fork: if you observe cloudbuild.yaml with no test step -> route A: add a Cloud Build step running debug_startup.py and a container /health probe before deploy, plus startup CPU boost; else route B: add the import smoke only
- Evidence: `debug_startup.py`, `cloudbuild.yaml`, `Dockerfile`
- Lens: health-that-lies · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: debug_startup.py exists but cloudbuild.yaml has no test/pytest/debug_startup invocation step -- confirms no deploy gate runs it.
- #550 families: 81

### WG-0745 · P1 · defend · effort S

**Prove the CLI memory sync still runs after the app.* import refactor**

- Failure surface: memory_bank.py does 'from core import ops' and dav1d.py does 'import ops' and 'from agents.vibes', the pre-refactor style the 2026-01-30 commits replaced elsewhere; on a machine launched without the sys.path('app') hack the MemoryBank import fails, the CLI dies or runs without memory, and GCS memory goes quiet for weeks unnoticed.
- First fork: if you observe python -c 'import app.memory.memory_bank' failing from the repo root -> route A: fix the imports, add the import smoke to CI, and check the memory bucket's last-modified as a freshness signal; else route B: add the freshness check only
- Evidence: `app/memory/memory_bank.py`, `app/dav1d.py`, `dav1d_cli.py`
- Lens: silent-death · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: memory_bank.py line 12 has 'from core import ops' (not 'app.core.ops') and dav1d.py line 29 has bare 'import ops' alongside 'from app.core...' imports -- confirms the inconsistent import styles described.
- #550 families: 77

### WG-0755 · P1 · elevate · effort M

**Put a vector index and latency budget on search_similar before re-enabling auto recall**

- Failure surface: search_similar inlines the query vector into SQL and full-scans the embeddings table with no VECTOR INDEX; EMERGENCY_SPEED_FIX measured 60-120s per recall and disabled memory entirely. Re-enabling memory as SMART_ASYNC_MEMORY intends reintroduces 4-minute turns and blocks the CLI.
- First fork: if you observe search_similar p50 > 5s against the current table -> route A: create a BigQuery VECTOR INDEX, switch to VECTOR_SEARCH with top_k, and cap recall at 3s with a timeout; else route B: only add the timeout and async prefetch
- Evidence: `app/tools/vector_store_bigquery.py`, `docs/EMERGENCY_SPEED_FIX.md`, `app/core/async_memory.py`
- Lens: indexes · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/EMERGENCY_SPEED_FIX.md exists as a dedicated 3853-byte doc, strongly suggesting a documented past incident (matching likelihood='observed'); app/core/async_memory.py (5581 bytes) exists as the SMART_ASYNC_MEMORY-style module; vector_store_bigquery.py confirmed to contain the embedding/query code path. Combination of a named incident doc plus the relevant code files directly supports the claim
- #550 families: 93

### WG-0765 · P1 · defend · effort M

**Stop masking outages: global exception handler returns 200 and /health ignores Vertex/GCS reachability**

- Failure surface: Every unhandled error becomes HTTP 200 with an error payload and /health returns ok unconditionally although ops.check_gcs_health/check_vertex_health exist. Cloud Run, uptime checks and fleet probes see green while users get 'hiccup' text, the same silent-quiet pattern as blade's hung /health.
- First fork: if you observe clients (Expo, KRONOS) parse the error body -> route A: keep the body shape but return 5xx and wire /health/detailed to ops checks; else route B: delete the catch-all and let FastAPI 500 with a structured handler
- Evidence: `app/server.py`, `app/core/ops.py`, `Dockerfile`
- Lens: public-surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: server.py's global exception_handler returns status_code=200 on any Exception (line 129) and /health (line 687) unconditionally returns {'status':'ok'} without calling check_gcs_health/check_vertex_health (which exist in ops.py) -- confirms both halves.
- #550 families: 46, 95

### WG-0775 · P1 · defend · effort M

**Pin Dav1d to one GCP project: reconcile four project ids across config, build, .env.example and RAG**

- Failure surface: cloudbuild sets PROJECT_ID but config reads GOOGLE_CLOUD_PROJECT (falls to dav1d-kbg1019); .env.example says gen-lang-client-0285887798/us-east4; rag_client hardcodes project 322812104986; persistence passes glob.PROJECT_ID from stdlib glob (always None). Writes and bills land in whichever project ADC resolves.
- First fork: if you observe Cloud Run env shows PROJECT_ID only -> route A: set GOOGLE_CLOUD_PROJECT in cloudbuild and delete fallbacks; else route B: single settings module with a startup assertion that all ids agree
- Evidence: `cloudbuild.yaml`, `app/config.py`, `app/core/rag_client.py`
- Lens: billing-boundaries · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml sets PROJECT_ID env; app/config.py:18 reads GOOGLE_CLOUD_PROJECT falling back to dav1d-kbg1019; .env.example sets GOOGLE_CLOUD_PROJECT=gen-lang-client-0285887798; app/core/rag_client.py:15 hardcodes project 322812104986; persistence.py imports stdlib glob and calls glob.PROJECT_ID (guarded, effectively None) -- all four mismatches verified verbatim.
- #550 families: 38

### WG-0785 · P1 · defend · effort S

**Retire burn_credits.py, turbo_burn.py and run_daily_burn.bat before a scheduled task re-runs them on real money**

- Failure surface: Scripts exist to burn $2-5/day on Gemini 3 Pro against the expired Dec-2025 trial; run_daily_burn.bat is built for Windows Task Scheduler on the same box class that runs the NouGen node tasks. A forgotten task or an agent following BURN_CREDITS_NOW.md spends live credit.
- First fork: if you observe a Task Scheduler entry on whoart/blade referencing run_daily_burn -> route A: delete the task, then remove the scripts; else route B: remove scripts and docs and add a grep guard in CI
- Evidence: `scripts/burn_credits.py`, `launchers/run_daily_burn.bat`, `resources/BURN_CREDITS_NOW.md`
- Lens: runaway-loops · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: scripts/burn_credits.py, launchers/run_daily_burn.bat, and resources/BURN_CREDITS_NOW.md all exist; the doc explicitly describes a $50/24-day burn plan invoking burn_credits.py; scripts/turbo_burn.py also exists.
- #550 families: 49

### WG-0795 · P1 · elevate · effort M

**Replace expired hardcoded credit balances with a live billing read**

- Failure surface: config.py hardcodes GEMINI_CREDIT_REMAINING=47.87 (exp 2025-12-23) and get_remaining_credits reports it; CLI and agents make decisions on ten-month-old numbers. Real balance could be zero.
- First fork: if you observe billing export/BigQuery is enabled for dav1d-kbg1019 -> route A: query spend from billing export daily and cache; else route B: delete the constants and surface 'unknown' explicitly
- Evidence: `app/config.py`, `app/core/cost_manager.py`
- Lens: cost · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: app/config.py:47-48 hardcodes GEMINI_CREDIT_REMAINING=47.87 (Exp: 2025-12-23) and MONTHLY_CREDIT_REMAINING=8.92; app/core/cost_manager.py:195-199 get_remaining_credits reports these constants directly.
- #550 families: 38

### WG-0805 · P1 · defend · effort M

**Finish the SDK migration the doc says is complete: vector_store_bigquery still uses deprecated TextEmbeddingModel**

- Failure surface: SDK_MIGRATION_STATUS.md marks migration COMPLETE, but vector_store_bigquery.py imports vertexai.language_models and calls text-embedding-004 through the SDK that sunset 2026-06-24. Memory ingest and recall 404 exactly as the doc's original error described.
- First fork: if you observe get_embedding raises 404/deprecation now -> route A: port to genai embed_content with gemini-embedding-001 and re-embed; else route B: pin google-cloud-aiplatform and schedule the port
- Evidence: `app/tools/vector_store_bigquery.py`, `docs/SDK_MIGRATION_STATUS.md`, `requirements.txt`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/SDK_MIGRATION_STATUS.md:4 states Status: COMPLETE and claims no vertexai.language_models/TextEmbeddingModel usage remains, but app/tools/vector_store_bigquery.py:47-48 imports vertexai.language_models.TextEmbeddingModel and calls text-embedding-004 -- direct contradiction confirmed.
- #550 families: 77

### WG-0815 · P1 · elevate · effort M

**Replace the playwright.dev boilerplate CI with a Dav1d smoke that can actually fail**

- Failure surface: The only workflow runs tests/example.spec.ts against playwright.dev; pytest_report.txt is 0 bytes. Green CI on master proves nothing, so the 21-commit cold-start firefight can recur unnoticed.
- First fork: if you observe debug_startup.py passes offline without ADC -> route A: run it plus pytest in Actions with fake env; else route B: mock genai client first, then wire
- Evidence: `.github/workflows/playwright.yml`, `tests/example.spec.ts`, `debug_startup.py`
- Lens: testing-ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .github/workflows/playwright.yml runs npx playwright test against tests/example.spec.ts which navigates to https://playwright.dev/ (lines 4,11); pytest_report.txt is 0 bytes; debug_startup.py exists as an ad hoc script, not wired into CI.
- #550 families: 82

### WG-0825 · P1 · defend · effort M

**Make 27 scripts runnable again: pre-refactor imports broken since the 2026-01-30 absolute-import migration**

- Failure surface: Commit 5df7d49 moved app code to app.* imports but scripts/ still use `from core...`, `from config`, `from tools...`; verify_security.py, ingest_doac_wisdom.py, sim_test.py fail at import. The documented verification suite cannot run on any machine.
- First fork: if you observe scripts are invoked by launchers or docs -> route A: fix imports and add a CI import-check; else route B: archive dead scripts and keep the ten that matter
- Evidence: `scripts/verify_security.py`, `scripts/ingest_doac_wisdom.py`, `scripts/sim_test.py`
- Lens: testing-ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git log confirms commit 5df7d49 converting app/ to app.* absolute imports; scripts/verify_security.py still does 'from core.security_policy import ...' and 'from config import Colors' (old-style imports), which would fail under the app.* layout; scripts/ingest_doac_wisdom.py and scripts/sim_test.py also present with their own sys.path hacks.
- #550 families: 77

### WG-0835 · P1 · defend · effort S

**Stop committing run logs as evidence: stale pylint_report, empty pytest_report, test_cli.txt, tracebacks**

- Failure surface: pylint_report.txt records a syntax error in emoji_dict_extended.py that the current file no longer has; pytest_report.txt is empty; resources/traceback*.txt and test_output.txt are committed. Agents reading the repo trust stale verdicts.
- First fork: if you observe any doc or agent cites these files as status -> route A: delete them and publish CI artifacts instead; else route B: delete and add to .gitignore
- Evidence: `pylint_report.txt`, `pytest_report.txt`, `resources/traceback.txt`
- Lens: testing-ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: pylint_report.txt:2 records a syntax error in app/agents/emoji_dict_extended.py ('{' never closed, line 657) but ast.parse on the current file succeeds, confirming the report is stale; pytest_report.txt is 0 bytes; resources/traceback.txt, traceback_minimal.txt, test_output.txt, test_cli.txt (22 bytes) are all committed.
- #550 families: 100

### WG-0845 · P1 · defend · effort S

**Retire docs/TEST_RESULTS.md and FLASH_LITE_DEFAULT.md claims that contradict config.py**

- Failure surface: TEST_RESULTS asserts 'balanced' is gemini-2.5-flash-lite at 0.0004 and 15/15 passed; config.py maps balanced to gemini-3-pro-preview at $2/$12. An agent choosing the 'cheap default' by the doc picks the most expensive tier.
- First fork: if you observe the intent is flash-lite default -> route A: change config and add a config test; else route B: rewrite both docs to match config
- Evidence: `docs/TEST_RESULTS.md`, `docs/FLASH_LITE_DEFAULT.md`, `app/config.py`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/TEST_RESULTS.md asserts balanced=gemini-2.5-flash-lite at $0.0004 and 15/15 tests passed; docs/FLASH_LITE_DEFAULT.md repeats the flash-lite-as-default claim; app/config.py MODELS maps balanced to gemini-3-pro-preview and MODEL_COSTS prices it at $2/$12 per 1M -- direct contradiction confirmed.

### WG-0855 · P1 · elevate · effort M

**Add contract tests for the KRONOS surface (/v1/chat/completions, agent.json, /knowledge/*) with a stub client**

- Failure surface: The fleet-facing endpoints have no tests; the analyze_complexity break and the two SSE regressions on 2026-01-31 shipped straight to Cloud Run. A regression is found by KRONOS, not by Dav1d.
- First fork: if you observe genai.Client can be dependency-injected via get_client -> route A: fake client fixture + FastAPI TestClient in CI; else route B: refactor client_factory for injection first
- Evidence: `app/server.py`, `app/core/client_factory.py`, `README.md`
- Lens: testing-ci · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/server.py exposes POST /v1/chat/completions (line 510), /knowledge/receive and /knowledge/context (614-649), and /agent.json (657); no contract/unit test files target these routes (tests/ only has example.spec.ts); get_client in client_factory.py is a plain function usable for DI, supporting the proposed route A.
- #550 families: 32

### WG-0865 · P1 · elevate · effort L

**Purge 640MB of Pdfs, videos, notebooks and cookbook from git history without breaking fleet clones**

- Failure surface: History rewrite invalidates every clone on blade/phoebus/whoart and any open branch (claude/nou-gen-elevation-wargame); .gitignore says cookbook-main is excluded but it is tracked. Done wrong, relay hooks and handoffs point at vanished SHAs.
- First fork: if you observe other machines have unpushed Dav1d commits -> route A: coordinate via relay claim, push first, then filter-repo; else route B: filter-repo now and force-push with a handoff record
- Evidence: `Pdfs`, `nano_banana_ref.ipynb`, `.gitignore`
- Lens: licensing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: du -sh confirms Pdfs=235M and nano_banana_ref.ipynb=14M; .gitignore lists resources/cookbook-main/ but git ls-files shows cookbook-main files are tracked anyway; git branch -a confirms the claude/nou-gen-elevation-wargame-t96jyo branch exists (local and remote).

### WG-0875 · P1 · defend · effort S

**Remove four dead submodule gitlinks (deepagents, deepagents-quickstarts, next.js, temp_rn_repo) with no .gitmodules**

- Failure surface: Mode-160000 entries with no .gitmodules make `git submodule update` and Cloud Shell onboarding error; directories are empty and the vendored cookbook is the only real reference material.
- First fork: if you observe any code imports from deepagents/ -> route A: vendor the needed files then git rm the gitlinks; else route B: git rm --cached all four and commit
- Evidence: `deepagents`, `next.js`, `temp_rn_repo`
- Lens: onboarding · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git ls-files -s confirms deepagents, deepagents-quickstarts, next.js, temp_rn_repo are mode-160000 gitlinks with commit hashes and no .gitmodules file present; the directories are empty on disk.

### WG-0885 · P1 · defend · effort M

**Remove OceanofPDF/pdfread-watermarked ebooks and tax forms from the public repo and its history**

- Failure surface: Pdfs/ ships pirate-site-watermarked books (Black AF History, Art of Seduction, GED prep) plus IRS forms under the Who Visions LLC name; DMCA or takedown lands on the company, not the agent.
- First fork: if you observe these PDFs were ingested into BigQuery/RAG -> route A: purge vectors and GCS copies too; else route B: git rm + history purge and note in handoff
- Evidence: `Pdfs`, `.gcloudignore`
- Lens: licensing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Pdfs/ contains _OceanofPDF.com_Black_AF_History_...pdf (x2), the-art-of-seduction-robert-greene.pdf, GED Test Prep ...-pdfread.net.pdf, and IRS forms f1040*.pdf, fw2.pdf, fw4.pdf, fw9.pdf etc. .gcloudignore lists Pdfs/ (excludes from Cloud Build upload only, does not remove from git history), confirming files are tracked.

### WG-0894 · P1 · defend · effort S

**Collapse three conflicting DAV1D system prompts into one canonical profile**

- Failure surface: resources/profiles/dav1d.txt, launchers/deploy.sh and scripts/deploy.py each embed a different persona ('Be transparent about being AI' vs 'NEVER start with As an AI'); whichever path deploys decides Dav1d's character.
- First fork: if you observe Agent Engine deploy is abandoned -> route A: delete the embedded prompts with the deploy scripts; else route B: make both scripts read resources/profiles/dav1d.txt
- Evidence: `resources/profiles/dav1d.txt`, `launchers/deploy.sh`, `scripts/deploy.py`
- Lens: canon · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: dav1d.txt line 6: 'NEVER start a response with As an AI language model'; launchers/deploy.sh line 72 embeds 'Be transparent about being AI' -- direct contradiction confirmed. scripts/deploy.py also embeds its own DAV1D_SYSTEM_PROMPT separate from the profile file.

### WG-0903 · P1 · defend · effort M

**Close the /knowledge/receive prompt-injection channel into Dav1d memory**

- Failure surface: Unauthenticated POST appends arbitrary content to memory/external_wisdom.jsonl, which .gitignore explicitly whitelists for commit; on Cloud Run it is lost on restart, locally it becomes agent memory. A fleet peer or attacker can plant instructions Dav1d later recalls.
- First fork: if you observe KRONOS actually posts knowledge packets today -> route A: require a shared fleet secret + source allowlist and route packets through the ingest junk gate; else route B: disable the endpoint and remove the .gitignore whitelist
- Evidence: `app/server.py`, `.gitignore`
- Lens: agent-doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: POST /knowledge/receive (line 614) appends to memory/external_wisdom.jsonl with no auth dependency shown, and .gitignore line 25 has '!memory/external_wisdom.jsonl' explicitly un-ignoring it for commit -- confirms both halves of the claim.
- #550 families: 69

### WG-0911 · P1 · defend · effort S

**Scrub identity leakage before public: personal email, Windows user paths and project numbers in tracked files**

- Failure surface: setup_quota_alerts.py hardcodes whoentertains@gmail.com, docs carry c:\Users\super paths, tracebacks carry project numbers and reasoning-engine ids. A public repo hands out the GM's contact and infra map.
- First fork: if you observe the repo is already public on GitHub -> route A: scrub and rotate anything that doubles as a credential hint; else route B: scrub before visibility change
- Evidence: `scripts/setup_quota_alerts.py`, `CORS_IMPLEMENTATION.md`, `resources/traceback.txt`
- Lens: privacy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: scripts/setup_quota_alerts.py:8 EMAIL = 'whoentertains@gmail.com'; CORS_IMPLEMENTATION.md has 'c:\Users\super\Watchtower\Dav1d\server.py'; resources/traceback.txt has project number 627440283840 and reasoning-engine resource id in full path.
- #550 families: 74

### WG-0919 · P1 · defend · effort S

**Reconcile Dav1d's Observatory/KRONOS fleet story with the NouGen fleet canon**

- Failure surface: README and agent.json describe a 10-agent Observatory fleet led by KRONOS with KAEDRA/IRIS; resources holds Rhea reports; the live fleet is NouGen with Rhea/Griot/Xoah/Kaedra behind shards.nougenai.com. Agents reading Dav1d docs orchestrate toward a fleet that no longer exists.
- First fork: if you observe KRONOS (who-visions-tester) is still deployed -> route A: document both lineages and mark KRONOS legacy; else route B: rewrite README/agent.json fleet section to NouGen
- Evidence: `README.md`, `app/config/agent.json`, `resources/agent_reports`
- Lens: canon · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: README.md describes 'The Observatory' 10-agent fleet led by KRONOS with KAEDRA and IRIS listed; resources/agent_reports/ contains Rhea_Report_20251209.md and Rhea_Local_Test.md, matching the claimed drift toward the NouGen/Rhea lineage.

### WG-0927 · P1 · elevate · effort M

**Rebuild the onboarding path and prove it on a fresh machine**

- Failure surface: cloud_shell_ready.md links YOUR_USERNAME and a 'dav1d brain' dir, the tutorial file lives in resources/, README architecture omits scripts that launchers need. A new lane on phoebus cannot get Dav1d running without tribal knowledge.
- First fork: if you observe launchers/cloud_shell_setup.sh runs clean in Cloud Shell -> route A: fix links and record a handoff; else route B: write a single QUICKSTART from a clean clone and delete stale guides
- Evidence: `.github/workflows/cloud_shell_ready.md`, `README.md`, `launchers/cloud_shell_setup.sh`
- Lens: onboarding · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: .github/workflows/cloud_shell_ready.md line 7 and 38 contain literal 'YOUR_USERNAME' placeholder and reference 'dav1d%20brain' / 'dav1d brain' working dir, confirming stale placeholder links. Whether README architecture omits launcher-required scripts was not independently verified line by line.

### WG-0935 · P1 · elevate · effort M

**Kill or finish the Vertex Agent Engine path that agent.json claims is enabled**

- Failure surface: deploy.sh and deploy.py are admitted placeholders, committed tracebacks show reasoning engines failing to start in us-east4, yet agent.json advertises reasoning_engine.enabled=true. Fleet consumers and new agents chase a deploy target that never worked.
- First fork: if you observe Cloud Run is the accepted target -> route A: delete deploy.sh/deploy.py/agent.py and set reasoning_engine.enabled=false; else route B: war-game a real ADK deploy with the current SDK
- Evidence: `launchers/deploy.sh`, `scripts/deploy.py`, `app/config/agent.json`, `resources/traceback.txt`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: launchers/deploy.sh:96 comment 'This is a placeholder for the actual ADK deployment'; app/config/agent.json has reasoning_engine.enabled=true; resources/traceback.txt shows a Reasoning Engine resource in us-east4 failing to start -- added this file to evidence since it is the direct proof of the failing traceback the claim cites.
- #550 families: 100

### WG-0943 · P1 · elevate · effort M

**Re-enable memory recall under a latency budget: docs say disabled, dav1d.py still calls memory.recall**

- Failure surface: EMERGENCY_SPEED_FIX says line 1380 was set to None, SMART_ASYNC_MEMORY says async recall is implemented, but dav1d.py:1318 calls memory.recall synchronously (95-190s BigQuery path when it works). The CLI is either slow or silently memoryless depending on which import breaks.
- First fork: if you observe recall latency >5s on a fixed query -> route A: wire AsyncMemoryLoader with a 2s budget and a visible 'memory pending' state; else route B: keep sync recall and add a timeout
- Evidence: `docs/EMERGENCY_SPEED_FIX.md`, `app/dav1d.py`, `app/core/async_memory.py`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/EMERGENCY_SPEED_FIX.md documents line 1380 memory.recall() as disabled/commented for speed; app/dav1d.py:1318 has an active 'relevant_context = memory.recall(user_input)' call (line-shifted but present and synchronous), and app/core/async_memory.py exists as the claimed alternative -- confirms the doc/code mismatch.

### WG-0951 · P1 · elevate · effort M

**Ship the deferred /proactive silent|preview|active gate before memory-driven autonomy returns**

- Failure surface: MEMORY_CONTROL_FIX records Dav1d generating runaway responses from recalled memory with no review gate; only a /clear brake exists. Restoring recall without the gate reproduces the runaway.
- First fork: if you observe recall is re-enabled first -> route A: default PREVIEW mode and require explicit 'review'; else route B: implement the enum and command before touching recall
- Evidence: `docs/PHASE_3_PROACTIVE_CONTROLS.md`, `docs/MEMORY_CONTROL_FIX.md`, `app/dav1d.py`
- Lens: agent-doctrine · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/MEMORY_CONTROL_FIX.md:11 explicitly names the 'runaway' effect and the only mitigation documented is the '/clear' command (line 53-69), not a proactive silent|preview|active gate; docs/PHASE_3_PROACTIVE_CONTROLS.md is the companion doc on proactive controls, matching the claim.

### WG-0959 · P1 · defend · effort M

**Fix Sandbox shell=True chain bypass before dav1d_exec is reachable via the shards gateway**

- Failure surface: run_safe_command validates only the first token then runs subprocess with shell=True, so 'ls; curl ...' passes; SecurityPolicy bans exactly this pattern and would fail its own sandbox. The NouGenShards connector exposes dav1d_exec fleet-wide.
- First fork: if you observe dav1d_exec routes to Sandbox.run_safe_command -> route A: shlex-split, shell=False, reject operators, add tests; else route B: disable the tool until fixed
- Evidence: `app/core/sandbox.py`, `app/core/security_policy.py`
- Lens: agent-doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/core/sandbox.py:67 def run_safe_command, line 86 comment 'Use shell=True for flexibility, but relying on validate_command' with shell=True confirmed in the subprocess call -- exactly the pattern claimed as a chain-command bypass.

### WG-0966 · P1 · defend · effort M

**Classify agent-callable GCP tools (deploy_service, run_query, get_secret, create_secret) as act/ask per Dave's operatin…**

- Failure surface: gcp_tools.py exposes Cloud Run deploy, BigQuery queries and Secret Manager read/write as model-callable functions under the service ADC; there is no irreversible-action gate, so a prompt can redeploy or read secrets.
- First fork: if you observe these tools are registered in the CLI or server tool set -> route A: tag each tool reversible/irreversible and require confirmation for the latter; else route B: leave unregistered and document
- Evidence: `app/core/gcp_tools.py`, `app/core/tool_registry.py`
- Lens: agent-doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app/core/gcp_tools.py defines run_query (line 72), deploy_service (line 222), get_secret (line 266) and create_secret (line 278) exactly as named; app/core/tool_registry.py exists as the registry claimed to wire these in.

### WG-0973 · P1 · elevate · effort M

**Add a liveness signal for a seven-month-dormant service so 'quiet' is noticed**

- Failure surface: No real code change between 2026-01-31 and the 2026-08-01 relay hook; nobody knows whether the Cloud Run revision still serves or the preview models still resolve. HARDENING.md records a vault quiet three days unnoticed; this one is months.
- First fork: if you observe /health/detailed answers from the live URL -> route A: add a daily probe routine posting to tracker/relay; else route B: declare the service parked in a handoff and stop advertising it in the agent card
- Evidence: `app/server.py`, `docs/AIWITHDAV3_INTEGRATION_ROADMAP.md`, `scripts/setup_quota_alerts.py`
- Lens: governance · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: app/server.py:686-692 defines /health and /health/detailed endpoints as claimed; git log timestamps show a large gap between 2026-01-31 commits and a 2026-08-02 commit, consistent with a long-dormant period, though the exact 'seven months' and HARDENING.md three-day-vault reference were not independently located in this repo's docs.
- #550 families: 95

### WG-0979 · P1 · defend · effort S

**Decide what the public agent card exposes: 'auth: open_for_now', creator name, project id, /config leak**

- Failure surface: /.well-known/agent.json and /config return the GCP project id, creator name, socials and an explicit open-auth flag to any crawler; the fleet card is identical in two files. A scraper maps the billing project before launch.
- First fork: if you observe the card is consumed by KRONOS discovery -> route A: keep a minimal public card and move fleet fields behind the A2A rpc; else route B: strip project/creator/auth fields and make /config require identity
- Evidence: `.well-known/agent.json`, `app/config/agent.json`, `app/server.py`
- Lens: privacy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: diff between .well-known/agent.json and app/config/agent.json shows they are byte-identical, and app/config/agent.json contains the project id (dav1d-kbg1019), confirming the duplicate public card leaking project info.
- #550 families: 74

### WG-0985 · P1 · defend · effort S

**Restore the KRONOS lane: /v1/chat/completions crashes on missing route_id (analyze_complexity undefined)**

- Failure surface: server.py calls smart_router.analyze_complexity(last_msg) but no such method exists anywhere in app/; every KRONOS request without route_id hits AttributeError and returns an HTTP-200 body with code 503. KRONOS sees Dav1d as perpetually overloaded.
- First fork: if you observe Cloud Run logs show 'OpenAI Endpoint Failure: ... analyze_complexity' -> route A: route through smart_router.orchestrate like /chat and add a contract test; else route B: confirm KRONOS always sends route_id and document it as required
- Evidence: `app/server.py`, `app/core/smart_router.py`
- Lens: canon · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: server.py line 540 calls smart_router.analyze_complexity(last_msg), but smart_router.py defines only __init__, orchestrate, get_route, get_specialized_persona -- no analyze_complexity method exists anywhere in app/, confirming the AttributeError claim.
- #550 families: 42
