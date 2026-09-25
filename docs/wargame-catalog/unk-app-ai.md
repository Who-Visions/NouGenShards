# War-game candidates — unk-app-ai

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

48 candidates · P0 3 · P1 45 · P2 0 · P3 0 · defend 34 · elevate 14

| id | P | kind | title |
|---|---|---|---|
| WG-0014 | P0 | defend | Stop deploying Cloud Run with --allow-unauthenticated while every router uses get_optional_user |
| WG-0030 | P0 | defend | Stop trading bot dev/test runs from writing to the live Firestore/BigQuery/Notion production targets |
| WG-0045 | P0 | defend | Reconcile gemini_agent/models_spec.py's pricing table against actual GCP billing |
| WG-0371 | P1 | defend | Rotate and purge the plaintext Robinhood API key and Ed25519 private key from history |
| WG-0387 | P1 | defend | Repoint run_trader.bat and supervisor.py at the post-refactor CLI path |
| WG-0403 | P1 | defend | Rewrite the 58 files still importing the pre-refactor services.brokers.* path |
| WG-0419 | P1 | defend | Consolidate the two divergent FastAPI entrypoints (deploy.py vs services/deploy.py) |
| WG-0435 | P1 | defend | Tighten CORS from allow_origins=['*'] + allow_credentials=True on both FastAPI entrypoints |
| WG-0451 | P1 | elevate | Pin all requirements.txt dependencies instead of unbounded >= ranges |
| WG-0466 | P1 | elevate | Add CI (pytest + import smoke test) so broken imports are caught before merge, not after 8 months |
| WG-0479 | P1 | defend | Confirm scripts/setup_gcp.sh's default project id doesn't drift from the actual deployed project |
| WG-0492 | P1 | defend | Rotate the hardcoded NewsData.io API key fallback |
| WG-0504 | P1 | defend | Purge committed loredb.sqlite and both trades.sqlite copies containing real operational data |
| WG-0516 | P1 | elevate | Add rate-limit/abuse protection to the unauthenticated /agent/chat endpoint |
| WG-0528 | P1 | defend | Fix or remove the broken panic-sell safety valve before it's needed under fire |
| WG-0540 | P1 | defend | Stop unk_trader_cli.py writing live news sentiment into another repo's public site data folder |
| WG-0552 | P1 | elevate | Replace LoreDB's fire-and-forget asyncio.create_task sync with a durable queue |
| WG-0564 | P1 | elevate | Add a real test for order placement, SafeGovernor gating and PAPER_TRADE enforcement |
| WG-0576 | P1 | defend | Stop LoreDB syncs from staying 'pending' forever |
| WG-0587 | P1 | elevate | Drain or delete LoreDB's dead get_pending_sync retry queue |
| WG-0598 | P1 | defend | Point scripts/clear_test_trades.py at the database TradingMemory actually writes |
| WG-0609 | P1 | defend | Repair scripts/reconcile_state.py's import so the drift-detection tool actually runs |
| WG-0620 | P1 | defend | Stop cloud_sync.push_state() from silently clobbering trading_bot/global_state across bots |
| WG-0631 | P1 | elevate | Make enterprise_throttle actually shared across bot processes, not just threads |
| WG-0642 | P1 | defend | Wire up or remove the dead /lore trigger_sync endpoint |
| WG-0653 | P1 | defend | Back /lore/worlds with the real LoreDB instead of a hardcoded fixture |
| WG-0664 | P1 | defend | Un-hardcode the permanent skip of betting.py regeneration in generate_services_layer |
| WG-0675 | P1 | elevate | Turn update_system_prompts() from a no-op into real prompt management |
| WG-0686 | P1 | elevate | Wire configs/trading.yaml into the strategies that should read it, or delete it |
| WG-0697 | P1 | elevate | Implement BrokerInterface so backtest fills and live fills can be compared at all |
| WG-0708 | P1 | defend | Point Cloud Run's /health at real GeminiAgent readiness, not a static string |
| WG-0719 | P1 | defend | Fix supervisor.py and run_trader.bat's path before trusting the auto-restart watchdog |
| WG-0730 | P1 | defend | Reconcile market_sentiment.json's committed-vs-gitignored status before it hides real drift |
| WG-0740 | P1 | defend | Fix panic_sell_all.py's broken import before relying on it as an emergency stop |
| WG-0750 | P1 | defend | Rotate and purge the plaintext Robinhood key pair from git history |
| WG-0760 | P1 | defend | Retire or cap the unbounded Cloud Run maxScale=100 with no cost guardrail |
| WG-0770 | P1 | elevate | Add enforcement to data/credit_burn_analysis.txt's manual GCP credit tracking |
| WG-0780 | P1 | defend | Fix the duplicated .gitignore body that may mask which patterns actually apply |
| WG-0790 | P1 | elevate | Add CI to catch the Jan-18 refactor's import breakage before it recurs |
| WG-0800 | P1 | defend | Fix checks/startup_verification.py targeting services.deploy while Docker ships deploy.py |
| WG-0810 | P1 | defend | Consolidate the two diverging FastAPI entrypoints before adding any more routers |
| WG-0820 | P1 | elevate | Decide retirement vs. revival for the stale (8-month, single-author) repo as a whole |
| WG-0830 | P1 | defend | Unskip or replace the only real test module, currently gated on pandas availability |
| WG-0840 | P1 | defend | Stop treating test_robinhood.py as a test file; it's a live scanner with embedded creds |
| WG-0850 | P1 | defend | Remove committed __pycache__, venv_trash and multi-megabyte log/diff files from git |
| WG-0860 | P1 | defend | Confirm which GCP/Firebase project trading writes actually land in during dev runs |
| WG-0870 | P1 | elevate | Add a CI import-and-lint pass covering the 15 broker/one-off script import breakages together |
| WG-0880 | P1 | defend | Repair 59 files' services.brokers.* imports left by the Jan-18 refactor |

---

### WG-0014 · P0 · defend · effort M

**Stop deploying Cloud Run with --allow-unauthenticated while every router uses get_optional_user**

- Failure surface: cloudbuild.yaml deploys unk-agent with --allow-unauthenticated, and every FastAPI dependency is get_optional_user, which downgrades any missing/invalid Firebase token to an anonymous free user instead of rejecting the request — there is no code path in production that actually enforces auth.
- First fork: if a route needs to be paid/premium-gated (per ROADMAP) -> anonymous users get free-tier access to everything anyway; else current state is fully open by design (still a risk under changing intent)
- Evidence: `cloudbuild.yaml`, `routers/dependencies.py:72-84`, `deploy.py`
- Lens: Attack & Operate / security · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml:22 has `--allow-unauthenticated`; routers/dependencies.py's get_optional_user catches HTTPException from verify_token and returns UserContext(user_id="anonymous", plan="free") instead of raising -- confirms fail-open auth.

### WG-0030 · P0 · defend · effort S

**Stop trading bot dev/test runs from writing to the live Firestore/BigQuery/Notion production targets**

- Failure surface: TradingMemory and cloud_sync.py default project_id to the hardcoded 'unk-app-480102' and write to Firestore collections unk_trades/trading_bot/global_state with no dev/prod separation flag; the committed data/trades.sqlite already shows a 'Testing Notion Triple Sync' row proving dev runs hit the same targets as production.
- First fork: if a developer runs unk_trader_cli.py locally without overriding GOOGLE_CLOUD_PROJECT -> test trades/logs land in the same Firestore/BigQuery/Notion destinations that real trading uses; else an explicit override isolates them
- Evidence: `trading/integrations/memory.py:75`, `trading/integrations/cloud_sync.py:27`
- Lens: Attack & Operate / infra · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: trading/integrations/memory.py:75 hardcodes project_id default 'unk-app-480102' via os.getenv fallback, and the committed data/trades.sqlite already contains 'Testing Notion Triple Sync Integration' rows, directly evidencing dev/test writes hitting the same target as documented.

### WG-0045 · P0 · defend · effort M

**Reconcile gemini_agent/models_spec.py's pricing table against actual GCP billing**

- Failure surface: docs/CLAUDE.md's own Known Issues list flags 'Pricing mismatch - models_spec.py has outdated prices vs CSV'; estimate_cost() in models_spec.py is used to route between cost_saver/premium tiers and likely feeds cost dashboards, so stale per-1M-token rates mean every cost estimate and tier-routing decision is quietly wrong.
- First fork: if the mismatch under-prices premium models -> smart_router picks premium too often, real spend exceeds estimates; if it over-prices -> unnecessary downgrades to cost_saver hurt quality for no savings
- Evidence: `docs/CLAUDE.md:41`, `gemini_agent/models_spec.py:309-315`
- Lens: cost-quota-billing · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified: docs/CLAUDE.md:41 explicitly lists 'Pricing mismatch - models_spec.py has outdated prices vs CSV' as a known issue; models_spec.py's estimate_cost() (around line 309) uses spec['pricing'] rates that feed cost/tier decisions.
- #550 families: 65

### WG-0371 · P1 · defend · effort M

**Rotate and purge the plaintext Robinhood API key and Ed25519 private key from history**

- Failure surface: Anyone with repo read access (or a future public fork/leak) can sign Robinhood Crypto orders directly against the live account; the key has been sitting in 18+ committed files for 8 months of inactivity with no rotation.
- First fork: if key still validates against Robinhood API -> treat as live-compromised, rotate immediately + force-push history scrub; else -> key already dead, just scrub history and add pre-commit secret scan
- Evidence: `test_robinhood.py:5-6`, `scripts/dip_scanner.py:12-13`, `scripts/buy_pepe.py`
- Lens: Attack & Operate / secrets · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: All three files contain the literal api_key 'rh-api-1dc5a886-...' and private_key_base64 'bByzmdzZcHSEJOMeAo40Gk8CX21yL8gPWijXI0CaWo0=' verbatim, confirmed by direct read.
- #550 families: 76

### WG-0387 · P1 · defend · effort S

**Repoint run_trader.bat and supervisor.py at the post-refactor CLI path**

- Failure surface: Both launchers hardcode `scripts/unk_trader_cli.py`, which the Jan-18 'minimize root' refactor moved to trading/core/unk_trader_cli.py; the auto-restart supervisor loop will crash-loop forever trying to launch a file that doesn't exist.
- First fork: if the Windows box reboots and run_trader.bat/supervisor.py auto-starts -> infinite fast crash-restart loop consuming resources with zero trading happening (fails safe but silently); else operator notices immediately on manual launch
- Evidence: `run_trader.bat:8`, `scripts/supervisor.py:8`
- Lens: Attack & Operate / operate · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: run_trader.bat:8 runs `venv\Scripts\python.exe scripts\unk_trader_cli.py`; supervisor.py:8 sets `BOT_SCRIPT = r"scripts/unk_trader_cli.py"`; the real file only exists at trading/core/unk_trader_cli.py, and scripts/unk_trader_cli.py does not exist.
- #550 families: 38

### WG-0403 · P1 · defend · effort M

**Rewrite the 58 files still importing the pre-refactor services.brokers.* path**

- Failure surface: 58 scripts/modules import `services.brokers.robinhood_crypto`, which no longer exists after brokers moved to trading/api/brokers; any of these run during an incident (panic sell, reconcile, validate) and immediately ModuleNotFoundError instead of doing their job.
- First fork: if operator reaches for any of the 58 broken scripts under time pressure -> instant failure with a confusing traceback instead of the intended safety action; else caught ahead of time via smoke test
- Evidence: `test_robinhood.py:2`, `scripts/panic_sell_all.py`, `scripts/reconcile_state.py`
- Lens: Attack & Operate / operate · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: grep for services.brokers.* imports across the repo returns 59 matching files (close to the claimed 58); the services/brokers package does not exist, so all these imports fail. All three cited evidence files are among the matches.
- #550 families: 77

### WG-0419 · P1 · defend · effort M

**Consolidate the two divergent FastAPI entrypoints (deploy.py vs services/deploy.py)**

- Failure surface: Dockerfile's CMD runs the minimal deploy.py (3 endpoints, lazy unk_api router) while docs/ARCHITECTURE and checks/startup_verification.py assume the full services/deploy.py router set is live in prod — anything gated behind routers only mounted in services/deploy.py (auth, lore, tools, a2a) never actually exists in the deployed container.
- First fork: if a client calls a route documented in ARCHITECTURE.md but only defined in services/deploy.py -> 404 in production despite docs/tests saying it should work; else client only hits the 3 real endpoints
- Evidence: `Dockerfile:71`, `deploy.py`, `services/deploy.py`
- Lens: Attack & Operate / deploy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Corrected evidence line: Dockerfile's CMD is at line 71 (`CMD ["python", "deploy.py"]`), not 74. deploy.py has only /health, /, /agent/chat plus a lazily-included unk_router, while services/deploy.py mounts core/models/chat/a2a/tools/lore/orchestrator/auth/threads routers -- confirming the divergence.
- #550 families: 34

### WG-0435 · P1 · defend · effort S

**Tighten CORS from allow_origins=['*'] + allow_credentials=True on both FastAPI entrypoints**

- Failure surface: Both deploy.py and services/deploy.py set CORSMiddleware allow_origins=['*'] together with allow_credentials=True, a combination browsers are supposed to reject but that misconfigured proxies/older clients may still honor, letting any origin read authenticated responses.
- First fork: if a browser or proxy in the request path honors the wildcard+credentials combo -> cross-origin credentialed reads possible; else modern browsers block it and only non-browser clients are exposed
- Evidence: `deploy.py:14-20`, `services/deploy.py:85-92`
- Lens: Attack & Operate / security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy.py:16-17 and services/deploy.py:88-89 both set allow_origins=["*"] and allow_credentials=True together, exactly as claimed.

### WG-0451 · P1 · elevate · effort M

**Pin all requirements.txt dependencies instead of unbounded >= ranges**

- Failure surface: Every entry in requirements.txt uses '>=' with no upper bound and there is no lockfile; a fresh Cloud Build install can silently pull a breaking or compromised newer release of fastapi/google-genai/firebase-admin with no reproducibility between the last successful deploy and the next one.
- First fork: if a dependency ships a breaking change or is compromised upstream between deploys -> next cloudbuild.yaml build installs it unnoticed; else builds happen to land on the same versions by luck
- Evidence: `requirements.txt`
- Lens: Attack & Operate / supply chain · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Full read of requirements.txt shows every dependency pinned only with '>=' (fastapi>=0.115.0, google-genai>=0.6.0, firebase-admin>=6.5.0, etc), no upper bounds, and no lockfile (requirements.lock/poetry.lock) present in the repo.
- #550 families: 77

### WG-0466 · P1 · elevate · effort M

**Add CI (pytest + import smoke test) so broken imports are caught before merge, not after 8 months**

- Failure surface: There is no .github/, pytest.ini, or pyproject.toml; checks/startup_verification.py exists as an import-smoke script but nothing runs it automatically, which is exactly how 58 broken services.brokers imports and two dead launcher paths went undetected for 8 months.
- First fork: if a PR reintroduces a broken import -> merges clean with no CI signal, discovered only at runtime (as happened with the Jan-18 refactor); else a CI gate running checks/startup_verification.py catches it pre-merge
- Evidence: `checks/startup_verification.py`, `requirements.txt`
- Lens: Attack & Operate / supply chain · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: No .github directory, pytest.ini, or pyproject.toml exists in the repo root; checks/startup_verification.py exists as a standalone script with no CI wiring found.
- #550 families: 81

### WG-0479 · P1 · defend · effort S

**Confirm scripts/setup_gcp.sh's default project id doesn't drift from the actual deployed project**

- Failure surface: setup_gcp.sh defaults PROJECT_ID to 'who-visions-llc' while cloudbuild.yaml and every hardcoded default in the codebase use 'unk-app-480102' — running setup_gcp.sh without explicitly exporting GOOGLE_CLOUD_PROJECT would provision IAM bindings and APIs in the wrong GCP project.
- First fork: if operator runs setup_gcp.sh without exporting GOOGLE_CLOUD_PROJECT -> IAM roles and API enablement land on 'who-visions-llc' instead of the actual serving project 'unk-app-480102'; else explicit env var used and it's fine
- Evidence: `scripts/setup_gcp.sh:12`, `cloudbuild.yaml`
- Lens: Attack & Operate / deploy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: setup_gcp.sh:12 is exactly `PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-who-visions-llc}"`; grep across the codebase shows 'unk-app-480102' hardcoded as the default project id in services/cli.py, reasoning_engine.py, gemini_agent.py, etc, confirming the drift.
- #550 families: 38

### WG-0492 · P1 · defend · effort S

**Rotate the hardcoded NewsData.io API key fallback**

- Failure surface: news_sentiment.py falls back to a literal committed key ('pub_4fded9...') when NEWSDATA_API_KEY is unset, so the credential is exposed and usable by anyone with repo access, potentially exhausting the account's quota.
- First fork: if env var is set in prod -> literal key unused but still exposed; else -> literal key is actively used by every unconfigured run
- Evidence: `trading/analysis/news_sentiment.py:20`
- Lens: Attack & Operate / secrets · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Line 20 is exactly `NEWSDATA_API_KEY = os.getenv('NEWSDATA_API_KEY', 'pub_4fded9b3d86342fa94a5484b626f4486')`.
- #550 families: 76

### WG-0504 · P1 · defend · effort S

**Purge committed loredb.sqlite and both trades.sqlite copies containing real operational data**

- Failure surface: loredb.sqlite (238 rows) and data/trades.sqlite (9 rows incl. 'Testing Notion Triple Sync') are committed database files; anyone cloning the repo gets a snapshot of memory/trade history that should be runtime state, and future writes risk merge conflicts or accidental data leakage across environments.
- First fork: if a contributor clones the repo and runs the app pointed at these committed DBs -> test/stale data mixes with real Notion/Firestore/BigQuery syncs (memory.py, cloud_sync.py); else DBs are ignored and regenerated fresh
- Evidence: `loredb.sqlite`, `data/trades.sqlite`, `trading/integrations/memory.py:49`
- Lens: Attack & Operate / secrets · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: loredb.sqlite contains exactly 238 rows in its memories table; data/trades.sqlite contains exactly 9 rows including multiple 'Testing Notion Triple Sync Integration' entries, matching the claim precisely.
- #550 families: 75

### WG-0516 · P1 · elevate · effort M

**Add rate-limit/abuse protection to the unauthenticated /agent/chat endpoint**

- Failure surface: deploy.py's POST /agent/chat has no auth requirement (not even get_optional_user) and no rate limiting; an anonymous client can drive unlimited Gemini calls against app.state.base_agent, running up GCP billing with no per-caller throttle.
- First fork: if a bad actor scripts repeated calls to /agent/chat -> unlimited billed Gemini invocations with no per-IP/user cap; else normal light traffic never triggers a cost concern
- Evidence: `deploy.py:47-53`
- Lens: Attack & Operate / security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy.py:47-53 shows POST /agent/chat with no auth dependency (not even get_optional_user) and no rate limiting, directly supporting the claim.

### WG-0528 · P1 · defend · effort S

**Fix or remove the broken panic-sell safety valve before it's needed under fire**

- Failure surface: scripts/panic_sell_all.py imports the pre-refactor `services.brokers.robinhood_crypto` path which no longer exists, so the one no-confirmation emergency liquidation script raises ModuleNotFoundError exactly when someone needs it most.
- First fork: if operator runs panic_sell_all.py during a live incident -> immediate crash with no liquidation, wasted seconds while account keeps bleeding; else caught in a dry run first
- Evidence: `scripts/panic_sell_all.py`, `trading/api/brokers/robinhood_crypto.py`
- Lens: Attack & Operate / infra · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: panic_sell_all.py imports `from services.brokers.robinhood_crypto import RobinhoodCryptoAPI`; `services/brokers/` does not exist in the repo (only trading/api/brokers/robinhood_crypto.py does), so this import fails.

### WG-0540 · P1 · defend · effort S

**Stop unk_trader_cli.py writing live news sentiment into another repo's public site data folder**

- Failure surface: unk_trader_cli.py:310 writes news_feed.json directly into `HQ_Blade\AiwithDav3_site\public\data\` — a public-facing site's data directory — creating an undocumented cross-repo write dependency with no access control or schema contract between the trading bot and that site's deploy pipeline.
- First fork: if AiwithDav3_site's build pipeline reads news_feed.json expecting a specific schema and the trading bot's format changes -> the public site silently breaks or displays stale/malformed data; else the coupling stays invisible until someone touches either side
- Evidence: `trading/core/unk_trader_cli.py:308-315`
- Lens: Attack & Operate / infra · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: trading/core/unk_trader_cli.py:310 contains the exact literal path `C:\Users\super\Watchtower\HQ_Blade\AiwithDav3_site\public\data\news_feed.json`, matching the claim's line and content precisely.
- #550 families: 75

### WG-0552 · P1 · elevate · effort L

**Replace LoreDB's fire-and-forget asyncio.create_task sync with a durable queue**

- Failure surface: Every memory write triggers `asyncio.create_task()` fire-and-forget syncs to Firestore/BigQuery/Notion with no retry or dead-letter handling; the committed loredb.sqlite shows 238 rows stuck at sync_status='pending', meaning failed syncs are currently invisible and unrecoverable.
- First fork: if the process exits or a sync task raises before completion -> that memory permanently stays 'pending' with no retry, silently diverging local SQLite from the cloud stores; else all syncs happen to complete before any interruption
- Evidence: `services/loredb.py:62`, `loredb.sqlite`
- Lens: Attack & Operate / infra · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: services/loredb.py's sync_memory (around line 62) fires three asyncio.create_task() calls with no retry/dead-letter handling; querying loredb.sqlite confirms all 238 rows have sync_status='pending', directly matching the claim.
- #550 families: 21

### WG-0564 · P1 · elevate · effort L

**Add a real test for order placement, SafeGovernor gating and PAPER_TRADE enforcement**

- Failure surface: The only real test file (tests/test_youtube_strategies.py) is unrelated to trading and is itself skipped when pandas is missing; none of the governor rate-gate bug, the can_trade positional-arg bug, the place_order kwarg mismatch, or PAPER_TRADE gating have any test coverage, which is exactly why four independently-shipped bugs compound in the same code path undetected.
- First fork: if a future PR touches trading_tools.py or governor.py -> no test suite exists to catch a regression before it reaches the live-by-default trading path; else manual review is the only safety net
- Evidence: `tests/test_youtube_strategies.py:22`, `services/llm/trading_tools.py`, `trading/core/governor.py`
- Lens: Attack & Operate / operate · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: tests/test_youtube_strategies.py:22 confirms pytestmark skipif(not PANDAS_AVAILABLE); grep across services/llm/trading_tools.py and trading/core/governor.py shows no test references anywhere in repo. No coverage of governor/trading_tools bugs exists.

### WG-0576 · P1 · defend · effort S

**Stop LoreDB syncs from staying 'pending' forever**

- Failure surface: Notion and BigQuery syncs in LoreDB never call update_sync_status even when they succeed, so memories.sync_status stays 'pending' indefinitely with no way to distinguish success from silence.
- First fork: if a memory's Firestore sync succeeds -> sync_status flips to 'synced'; if Notion/BigQuery sync succeeds -> nothing updates status, indistinguishable from a sync that never ran.
- Evidence: `services/loredb.py:67-146`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: services/loredb.py: _sync_notion (lines ~67-114) and _sync_bigquery never call update_sync_status in either success or failure branches, while _sync_firestore (lines 117-146) does call it on both success ('synced') and failure ('failed_firestore'). Directly confirms the claim.
- #550 families: 21

### WG-0587 · P1 · elevate · effort S

**Drain or delete LoreDB's dead get_pending_sync retry queue**

- Failure surface: get_pending_sync() finds memories awaiting retry but no scheduler, cron, or endpoint ever calls it, so failed/never-synced memories accumulate with zero remediation path.
- First fork: if a scheduled job calls get_pending_sync() and retries -> backlog drains; if nothing calls it (current state) -> backlog grows unbounded.
- Evidence: `services/loredb.py:252`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: get_pending_sync (services/loredb.py:252) exists; repo-wide grep for 'get_pending_sync' finds only its own definition, no callers anywhere, confirming the dead retry-queue claim.

### WG-0598 · P1 · defend · effort S

**Point scripts/clear_test_trades.py at the database TradingMemory actually writes**

- Failure surface: TradingMemory writes to trading/data/trades.sqlite, but clear_test_trades.py opens data/trades.sqlite, a stale committed copy with 9 old rows — 'clearing test trades' leaves the real table untouched.
- First fork: if an operator runs clear_test_trades.py expecting to reset history before a live run -> it silently no-ops on the real table.
- Evidence: `scripts/clear_test_trades.py:4`, `trading/integrations/memory.py:49,74`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: scripts/clear_test_trades.py:4 opens sqlite3.connect("data/trades.sqlite"); trading/integrations/memory.py:49 defines TRADES_DB_PATH as os.path.join(..., "..", "data", "trades.sqlite") relative to trading/integrations, resolving to trading/data/trades.sqlite — a different file from the repo-root data/trades.sqlite, confirming the mismatch. Both files exist on disk.

### WG-0609 · P1 · defend · effort S

**Repair scripts/reconcile_state.py's import so the drift-detection tool actually runs**

- Failure surface: reconcile_state.py imports from services.brokers.robinhood_crypto, a path removed by the Jan-18 refactor — the one script meant to catch drift between trading_state.json and real broker holdings fails at import before comparing anything.
- First fork: if the import path is fixed -> reconciliation can compare broker holdings vs local state; today -> ImportError every time and nobody can measure drift.
- Evidence: `scripts/reconcile_state.py:9`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: scripts/reconcile_state.py:9 has 'from services.brokers.robinhood_crypto import RobinhoodCryptoAPI' — this module path does not exist (actual location is trading/api/brokers/robinhood_crypto.py), confirming the broken import.
- #550 families: 30

### WG-0620 · P1 · defend · effort M

**Stop cloud_sync.push_state() from silently clobbering trading_bot/global_state across bots**

- Failure surface: push_state() writes a single Firestore doc with no bot-identifier field and swallows every exception with a bare except:pass; if multiple bot processes sync concurrently, whichever writes last wins and any failed write vanishes with zero log line.
- First fork: if only one bot process syncs -> global_state reflects it faithfully; if two+ sync concurrently -> last-writer-wins with no way to tell which bot survived, indistinguishable from a failed write.
- Evidence: `trading/integrations/cloud_sync.py:38-57`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: trading/integrations/cloud_sync.py:38-57 push_state() writes to db.collection("trading_bot").document("global_state") with a single fixed document id and no bot-identifier field, and wraps the write in try/except Exception with no re-raise, confirming both the last-writer-wins and silent-failure claims.
- #550 families: 85

### WG-0631 · P1 · elevate · effort M

**Make enterprise_throttle actually shared across bot processes, not just threads**

- Failure surface: The module comment claims enterprise_throttle is a global singleton shared across bot and AI tools, but it's only a threading.Lock inside one process; each separately launched bot gets its own independent 30 CPM budget, so running two bots doubles the real request rate.
- First fork: if only one bot process runs -> the 30 CPM budget holds; if two+ run simultaneously -> combined rate can exceed 30 CPM unnoticed, risking a Robinhood-side rate limit during live trading.
- Evidence: `trading/core/shared.py:10,26`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: trading/core/shared.py:10 uses threading.Lock() and line 26 comment states 'Global singleton to ensure both bot and AI tools share the same 30 CPM limit', but the lock is only process-local (threading, not multiprocessing/file-based), confirming separate processes would each get their own independent throttle instance.

### WG-0642 · P1 · defend · effort S

**Wire up or remove the dead /lore trigger_sync endpoint**

- Failure surface: trigger_sync() has a full SyncRequest body and token-selection logic but no @router decorator, so it's never registered as an HTTP route — the only manual-resync entry point looks complete but is unreachable dead code.
- First fork: if an operator POSTs to the expected sync route -> FastAPI 404s with no hint the handler exists in source.
- Evidence: `routers/lore.py`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: routers/lore.py:29-45 defines async def trigger_sync(...) with no @router.post/get decorator above it (unlike every other handler in the file, e.g. notion_webhook at line 49), so it is never registered as a route.

### WG-0653 · P1 · defend · effort S

**Back /lore/worlds with the real LoreDB instead of a hardcoded fixture**

- Failure surface: list_worlds() always returns the same two hardcoded worlds regardless of what's actually stored, so any client using it to discover real partitions gets fake, unchanging data.
- First fork: if a caller uses /lore/worlds to pick a world_id for other lore endpoints -> it can never discover a real world outside the two hardcoded IDs.
- Evidence: `routers/lore.py`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: routers/lore.py:61-68 list_worlds() returns a static list of two hardcoded worlds (w1, w2), no LoreDB query.

### WG-0664 · P1 · defend · effort S

**Un-hardcode the permanent skip of betting.py regeneration in generate_services_layer**

- Failure surface: generate_services_layer() has a comment-only decision that permanently disables regenerating services/betting.py, with the actual safe_write() call commented out — the pipeline reports success while this artifact is frozen indefinitely.
- First fork: if repos/analyses change in a way that should affect betting.py -> nothing happens, silently, because the write call is dead code.
- Evidence: `antigravity_runner.py`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: antigravity_runner.py:325-329 shows betting_py = services_dir / 'betting.py' followed by comments explaining the manual refactor and the line '# safe_write(betting_py, self.render_betting_services_py())' commented out.

### WG-0675 · P1 · elevate · effort M

**Turn update_system_prompts() from a no-op into real prompt management**

- Failure surface: update_system_prompts() prints 'Updating managed prompts...' but the entire loop body is a bare pass; every run with prompt updates enabled logs success while doing nothing, and the committed .antigravity/state.json's prompt_updates list reflects a run from before this was neutered.
- First fork: if a human trusts the stdout log or state.json's prompt_updates list -> they believe managed prompt files are being kept in sync; in the current code they never are.
- Evidence: `antigravity_runner.py`, `.antigravity/state.json`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: antigravity_runner.py:421-441 update_system_prompts() prints 'Updating managed prompts...' then in the for-loop over managed_files ends with a bare 'pass' after comments explaining legacy logic is disabled. .antigravity/state.json exists in repo root confirming the state-file claim.

### WG-0686 · P1 · elevate · effort M

**Wire configs/trading.yaml into the strategies that should read it, or delete it**

- Failure surface: services/config_loader.py is the only reader of configs/trading.yaml and nothing imports config_loader anywhere — every strategy uses hardcoded thresholds instead, so operator edits to trading.yaml silently have zero runtime effect.
- First fork: if an operator assumes trading.yaml governs live strategy behavior -> their edits do nothing; only reading strategy source reveals the real hardcoded values.
- Evidence: `services/config_loader.py`, `configs/trading.yaml`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Both files exist; grep -rn 'config_loader' across all .py files (excluding the module itself) returned zero matches, confirming config_loader.py is never imported anywhere in the repo.

### WG-0697 · P1 · elevate · effort L

**Implement BrokerInterface so backtest fills and live fills can be compared at all**

- Failure surface: broker_interface.py defines an abstract BrokerInterface with zero implementations; PaperBroker and RobinhoodCryptoAPI share no common interface, so there is no way to run the same strategy through both and measure backtest-vs-live drift.
- First fork: if a strategy only runs through PaperBroker -> backtest looks good with no live check; if wired directly to RobinhoodCryptoAPI (as live bots are) -> nothing compares live fills back against backtest predictions.
- Evidence: `services/execution/broker_interface.py`, `services/execution/paper_broker.py`, `trading/api/brokers/robinhood_crypto.py`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: services/execution/broker_interface.py:8 defines ABC with several @abstractmethod (lines 114-149); services/execution/paper_broker.py:46 'class PaperBroker(ExecutionClient):' — inherits ExecutionClient, NOT BrokerInterface; trading/api/brokers/robinhood_crypto.py:123 'class RobinhoodCryptoAPI:' — no base class at all. Confirms zero implementations of BrokerInterface.

### WG-0708 · P1 · defend · effort S

**Point Cloud Run's /health at real GeminiAgent readiness, not a static string**

- Failure surface: /health always returns a static healthy response with no dependency on app.state.base_agent, even though /agent/chat itself checks hasattr(app.state,'base_agent') and errors when it's missing — a container stuck without a working agent still gets marked healthy and keeps receiving traffic.
- First fork: if GeminiAgent() construction succeeds -> /health and /agent/chat agree the service is up; if it fails or partially succeeds -> /health still reports healthy while /agent/chat errors on every real request.
- Evidence: `deploy.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy.py:28-30 '@app.get("/health") async def health_check(): return {"status": "healthy", "service": "unk-agent"}' — static, no state check. Lines 44/49-51 show app.state.base_agent = GeminiAgent() and a separate hasattr(app.state,'base_agent') check used only in the chat path, confirming the described gap.
- #550 families: 95

### WG-0719 · P1 · defend · effort S

**Fix supervisor.py and run_trader.bat's path before trusting the auto-restart watchdog**

- Failure surface: supervisor.py hardcodes BOT_SCRIPT='scripts/unk_trader_cli.py' and run_trader.bat runs the same stale path; the real file moved to trading/core/unk_trader_cli.py, so the watchdog meant to auto-restart a crashed live trading bot can never launch it.
- First fork: running supervisor.py -> it checks os.path.exists and exits loudly with an error; running run_trader.bat -> it loops printing 'bot stopped or crashed' every 10 seconds forever without the bot ever having started, unattended.
- Evidence: `scripts/supervisor.py`, `run_trader.bat`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: scripts/supervisor.py:8 BOT_SCRIPT = r'scripts/unk_trader_cli.py', and line 46 checks os.path.exists(BOT_SCRIPT). run_trader.bat:8 runs 'scripts\unk_trader_cli.py'. Confirmed scripts/unk_trader_cli.py does NOT exist while trading/core/unk_trader_cli.py does, verifying the stale-path claim.

### WG-0730 · P1 · defend · effort S

**Reconcile market_sentiment.json's committed-vs-gitignored status before it hides real drift**

- Failure surface: market_sentiment.json is both tracked in git and listed in .gitignore, so git status never shows changes to it even though unk_trader_cli.py actively rewrites it as a 3-minute cache — a fresh clone starts from a stale committed snapshot invisible to normal diffing.
- First fork: if the local file is never re-added -> local writes stay invisible to git (matching gitignore intent, but inconsistent with it being tracked); if someone runs a broad git add -> the committed snapshot silently updates to whatever stale cache that machine had.
- Evidence: `market_sentiment.json`, `.gitignore`, `trading/core/unk_trader_cli.py`
- Lens: data-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .gitignore:144 lists 'market_sentiment.json', and 'git ls-files market_sentiment.json' shows it IS tracked — confirming the tracked-yet-ignored contradiction. trading/core/unk_trader_cli.py exists as the writer file named.
- #550 families: 38

### WG-0740 · P1 · defend · effort S

**Fix panic_sell_all.py's broken import before relying on it as an emergency stop**

- Failure surface: panic_sell_all.py imports from services.brokers.robinhood_crypto, a path removed by the Jan-18 refactor (like 50 other scripts) — the one script meant to liquidate everything during an emergency fails at import before it can sell a single position.
- First fork: if someone runs this mid-emergency expecting immediate liquidation -> ImportError, no sells happen, and the loss keeps compounding while they debug the traceback instead of stopping the bleeding.
- Evidence: `scripts/panic_sell_all.py`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: scripts/panic_sell_all.py:9 'from services.brokers.robinhood_crypto import RobinhoodCryptoAPI' — but the real module lives at trading/api/brokers/robinhood_crypto.py, and services/brokers/ does not exist as a package here, confirming the broken import path. Did not independently verify the 'Jan-18 refactor / 50 other scripts' detail but the core broken-import claim is directly confirmed.

### WG-0750 · P1 · defend · effort M

**Rotate and purge the plaintext Robinhood key pair from git history**

- Failure surface: Anyone with repo read access (or a future public fork/clone) can extract the live Robinhood Crypto API key and Ed25519 private key and place real orders against the account; the keys are already committed, not just at risk.
- First fork: if git history purge (filter-repo) is reversible-and-safe for this single-author repo -> do it and rotate keys immediately; else -> rotate keys first (kills the leak's value) and park history-scrubbing as a separate, riskier op
- Evidence: `test_robinhood.py:5-6`, `scripts/dip_scanner.py:12-13`
- Lens: money-on-the-line/credentials · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Verified: test_robinhood.py:5-6 contains live-looking Robinhood API key + Ed25519 private key in plaintext; scripts/dip_scanner.py:12-13 has the same hardcoded credentials.
- #550 families: 76

### WG-0760 · P1 · defend · effort M

**Retire or cap the unbounded Cloud Run maxScale=100 with no cost guardrail**

- Failure surface: docs/ARCHITECTURE.md documents `autoscaling.knative.dev/maxScale: "100"` for the unk-agent Cloud Run service, but cloudbuild.yaml's actual `gcloud run deploy` step sets no --max-instances flag at all, so the documented ceiling may not even be the one enforced in the real deploy, and ROADMAP's 'Budget enforcement' checkbox is still unchecked.
- First fork: if the annotation is applied via a separate service.yaml not in this repo -> doc and deploy agree by luck; if cloudbuild.yaml is the sole deploy path -> the actual scale ceiling is whatever Cloud Run's platform default is, undocumented and unbudgeted
- Evidence: `docs/ARCHITECTURE.md:80,428`, `cloudbuild.yaml:11-23`, `docs/ROADMAP.md:177`
- Lens: cost-quota-billing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified: docs/ARCHITECTURE.md:80,428 document `autoscaling.knative.dev/maxScale: "100"`; cloudbuild.yaml's `gcloud run deploy` step (lines ~10-23) sets no --max-instances flag; docs/ROADMAP.md:177 'Budget enforcement' is unchecked.

### WG-0770 · P1 · elevate · effort M

**Add enforcement to data/credit_burn_analysis.txt's manual GCP credit tracking**

- Failure surface: data/credit_burn_analysis.txt is a static, manually-generated snapshot of GCP credit usage ($31.50/week burn against $1268.50 available) with no automated alerting or hard stop tied to it; credits can be exhausted between manual checks with no code-level circuit breaker.
- First fork: if someone remembers to regenerate and read this file weekly -> burn is visible in time; if not -> credits run out mid-week with no automated warning before Vertex/Gemini calls start failing or billing to a real card
- Evidence: `data/credit_burn_analysis.txt:1-12`
- Lens: cost-quota-billing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified: data/credit_burn_analysis.txt is a static snapshot showing $31.50/week burn against $1268.50 available, with no code-level alerting/circuit-breaker tied to it anywhere in the repo.
- #550 families: 65

### WG-0780 · P1 · defend · effort S

**Fix the duplicated .gitignore body that may mask which patterns actually apply**

- Failure surface: The repo's .gitignore has its entire Python/secrets/logs block duplicated verbatim (two copies of the same ~40 lines) before the trading-specific section; a future edit to only one copy creates silent drift where a pattern is 'removed' from one block but still active from the other, or vice versa.
- First fork: if someone edits only the first copy expecting it to take effect -> the second copy's identical pattern still governs, change appears to have no effect; if both copies are edited consistently by habit -> no visible bug, but the file stays confusing for the next editor
- Evidence: `.gitignore`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .gitignore has duplicate entries (e.g. venv/, venv_backup/, wheels/, verification.txt each appear twice) confirming a duplicated body.
- #550 families: 36

### WG-0790 · P1 · elevate · effort M

**Add CI to catch the Jan-18 refactor's import breakage before it recurs**

- Failure surface: There is no .github/ workflow, pytest.ini, or pyproject.toml anywhere in the repo; the 59-file services.brokers.* breakage and the scripts/unk_trader_cli.py path breakage both shipped and sat undetected for ~8 months because nothing runs checks/startup_verification.py or an import smoke test automatically.
- First fork: if CI runs checks/startup_verification.py on every push -> the next refactor's broken imports fail the build immediately; if CI stays absent -> the next refactor repeats this exact failure mode silently
- Evidence: `checks/startup_verification.py:1-40`, `docs/ROADMAP.md`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: No .github/ dir, pytest.ini, or pyproject.toml found in repo root; checks/startup_verification.py exists exactly as described and is not wired into any CI.
- #550 families: 81, 82

### WG-0800 · P1 · defend · effort M

**Fix checks/startup_verification.py targeting services.deploy while Docker ships deploy.py**

- Failure surface: startup_verification.py's modules_to_check list imports routers.core, routers.tools, routers.orchestrator, routers.auth, routers.threads and services.deploy — the full router set used by services/deploy.py — but the Dockerfile's actual CMD runs the minimal deploy.py (only /health, /, /agent/chat), so a green run of this check gives false confidence about what's actually deployed to Cloud Run.
- First fork: if this script is treated as CI's pre-deploy gate -> it validates the wrong entrypoint and misses breakage in deploy.py's own lazy unk_api router import; if both entrypoints are checked -> real coverage of what ships
- Evidence: `checks/startup_verification.py:24-38`, `Dockerfile:68,71`, `deploy.py`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: startup_verification.py's modules_to_check list (lines ~25-38) includes routers.core, routers.tools, routers.orchestrator, routers.auth, routers.threads, services.deploy; Dockerfile CMD (line 71) runs ['python','deploy.py'] which is the 3-endpoint minimal file, not services/deploy.py.

### WG-0810 · P1 · defend · effort L

**Consolidate the two diverging FastAPI entrypoints before adding any more routers**

- Failure surface: deploy.py (3 endpoints, Dockerfile's CMD) and services/deploy.py (9 routers incl. auth/orchestrator/tools/threads, Firebase init, LoreDB lifespan) have fully diverged; any new router or auth fix applied to services/deploy.py never reaches production because the container runs deploy.py, and docs/tests that assume services/deploy.py describe a service that isn't actually live.
- First fork: if a security fix (e.g. tightening CORS or auth) lands only in services/deploy.py -> production (deploy.py) stays vulnerable while docs/checks report it as fixed; if fixed in both -> consistent, but doubles every future maintenance cost
- Evidence: `deploy.py:11-49`, `services/deploy.py:76-114`, `Dockerfile:71`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: deploy.py has exactly 3 endpoints (/health, /, /agent/chat) plus lazy unk_api include; services/deploy.py includes 9 routers (core, models, chat, a2a, tools, lore, orchestrator, auth, threads) with Firebase/LoreDB lifespan; Dockerfile CMD runs deploy.py confirming the divergence and which one ships.
- #550 families: 34

### WG-0820 · P1 · elevate · effort L

**Decide retirement vs. revival for the stale (8-month, single-author) repo as a whole**

- Failure surface: 22 total commits, last on 2026-01-18 (git log), single author, with a live Robinhood account still linked via leaked credentials and pnl_report.txt showing real losses; the repo sits in a state where reviving it (fixing 59 broken imports, wrong governor config, PAPER_TRADE defaults) or retiring it (revoking API access, archiving) are both real options but neither has been decided.
- First fork: if the Robinhood account behind these credentials is still funded and connected -> retirement without revocation leaves a live financial exposure open indefinitely; if revival is chosen -> the fix list (items above) becomes a real, ordered project rather than scattered bugs
- Evidence: `pnl_report.txt`, `test_robinhood.py:1-7`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git log shows last commit 2026-01-18 with a small, single-author history; pnl_report.txt contains real-looking filled buy/sell rows with tiny dollar amounts consistent with real losses; test_robinhood.py embeds a live-looking rh-api key and base64 private key inline.

### WG-0830 · P1 · defend · effort S

**Unskip or replace the only real test module, currently gated on pandas availability**

- Failure surface: tests/test_youtube_strategies.py — the repo's sole real test file — is wrapped in `pytestmark = pytest.mark.skipif(not PANDAS_AVAILABLE, ...)`; with no CI and no pinned requirements, a fresh environment missing pandas silently skips all tests and `pytest` reports success with zero assertions actually run.
- First fork: if pandas is installed in whatever environment runs `pytest` -> tests execute for real; if not (e.g. a minimal CI image, or the Dockerfile's slim production image) -> 100% skip rate reported as a clean pass
- Evidence: `tests/test_youtube_strategies.py:10-21`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: tests/test_youtube_strategies.py lines 10-21 exactly match: try/except pandas import with pytestmark = pytest.mark.skipif(not PANDAS_AVAILABLE, ...).
- #550 families: 81

### WG-0840 · P1 · defend · effort S

**Stop treating test_robinhood.py as a test file; it's a live scanner with embedded creds**

- Failure surface: test_robinhood.py sits at repo root looking like a pytest test (by name and location) but is actually a live Robinhood scanner with the API key/private key embedded inline and (per the repo map) a broken import; a CI job that naively globs `test_*.py` would either hit real credentials or fail on collection.
- First fork: if a future CI setup runs `pytest` without excluding this file -> collection either executes live-account code or errors on the broken import; if explicitly excluded/renamed -> removed from the test surface entirely
- Evidence: `test_robinhood.py:1-7`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: test_robinhood.py sits at repo root, named like a pytest file, but is a live scanner script with an inline rh-api-... key and base64 private key on lines 4-6.
- #550 families: 76

### WG-0850 · P1 · defend · effort S

**Remove committed __pycache__, venv_trash and multi-megabyte log/diff files from git**

- Failure surface: The repo has committed __pycache__/*.pyc (two Python ABI versions), venv_trash/Scripts/python.exe with hardcoded C:\Users\super paths, and logs/diffs/*.txt totaling ~2MB; any future CI checkout, clone, or fleet-wide code search pays this weight repeatedly, and the committed venv can mask real dependency issues if accidentally added to PYTHONPATH.
- First fork: if venv_trash/python.exe is ever picked up by a PATH/PYTHONPATH misconfiguration on a Windows box -> runs against a broken, foreign venv instead of the real one; if just dead weight -> pure repo bloat and clone-time cost
- Evidence: `venv_trash/pyvenv.cfg`, `venv_trash/Scripts/python.exe`, `logs/diffs/`, `__pycache__/`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: venv_trash/Scripts/python.exe and venv_trash/pyvenv.cfg exist, with pyvenv.cfg literally containing C:\Users\super\... paths; __pycache__ contains .pyc files for two different CPython ABI versions (312 and 314); logs/diffs totals ~2MB.

### WG-0860 · P1 · defend · effort M

**Confirm which GCP/Firebase project trading writes actually land in during dev runs**

- Failure surface: trading/integrations/cloud_sync.py prints 'Connected to who-visions-tester' on init, rebuilding Firebase Admin creds from FIREBASE_ADMIN_PRIVATE_KEY, while other modules (loredb.py, memory.py) default to project unk-app-480102; a local dev run of the trading bot could write real-looking trade/global-state documents into a 'tester' Firestore project that fleet dashboards might still read from, or vice versa.
- First fork: if FIREBASE_ADMIN_PROJECT_ID is unset locally -> falls back to whatever default the SDK picks, possibly the wrong project; if explicitly set to who-visions-tester during dev -> test runs' global_state writes could be mistaken for real bot state by anything else reading that collection
- Evidence: `trading/integrations/cloud_sync.py:12-29`, `routers/config.py:23`
- Lens: money-on-the-line/data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: trading/integrations/cloud_sync.py prints "[CloudSync] Firebase Connected to 'who-visions-tester'" on init (line 29) while numerous other modules (services/cli.py, reasoning_engine.py, routers/config.py, etc.) default GOOGLE_CLOUD_PROJECT to 'unk-app-480102', confirming the project-mismatch risk.

### WG-0870 · P1 · elevate · effort M

**Add a CI import-and-lint pass covering the 15 broker/one-off script import breakages together**

- Failure surface: Beyond the 59 services.brokers.* imports, individual scripts (watch_recovery.py, scan_gainers.py, active_scalp.py per the repo map) independently reference the pre-refactor module layout; without one CI job that imports every script in scripts/, each broken script is only discovered the day someone happens to run it.
- First fork: if a single `python -c "import scripts.X"` sweep is added to CI for every file in scripts/ -> all ~59+ breakages surface in one PR; if left as-is -> each is discovered independently, months apart, exactly as the current state shows
- Evidence: `scripts/active_scalp.py:30,34`, `scripts/scan_gainers.py:14`, `checks/startup_verification.py`
- Lens: testing-ci-stale-repo · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: services/brokers/ does not exist anywhere in the repo (confirmed via find), yet scripts/active_scalp.py and scripts/scan_gainers.py both import from services.brokers.robinhood_crypto, reproducing the exact broken-import pattern described; no CI import sweep exists.
- #550 families: 81

### WG-0880 · P1 · defend · effort M

**Repair 59 files' services.brokers.* imports left by the Jan-18 refactor**

- Failure surface: scripts/panic_sell_all.py, scripts/fire_sale.py, scripts/execute_90_percent_xtz.py and 56 more still `from services.brokers.robinhood_crypto import RobinhoodCryptoAPI`, a module that no longer exists (moved to trading/api/brokers); any operator reaching for the emergency liquidation script during a real incident gets an ImportError instead of a sold position.
- First fork: if the operator tests the script before an emergency -> caught in advance; else -> discovered mid-incident when panic_sell_all.py is needed most and fails to even import
- Evidence: `scripts/panic_sell_all.py:9`, `scripts/fire_sale.py:11`, `scripts/execute_90_percent_xtz.py:13`
- Lens: money-on-the-line/execution · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Verified: 55 files under scripts/ still `from services.brokers.robinhood_crypto import RobinhoodCryptoAPI`, a module that no longer exists (real path is trading/api/brokers/robinhood_crypto.py). Count is 55, not exactly 59, but the claim's substance holds; corrected line numbers for fire_sale.py (11) and execute_90_percent_xtz.py (13).
