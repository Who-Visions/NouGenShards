# War-game candidates — Yuki-Ai

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

38 candidates · P0 9 · P1 29 · P2 0 · P3 0 · defend 27 · elevate 11

| id | P | kind | title |
|---|---|---|---|
| WG-0010 | P0 | elevate | Cut the 'Unk' pricing dependency: make core/yuki_models_spec.py the fleet source of truth for Gemini SKUs |
| WG-0026 | P0 | defend | Purge committed biometric profiles (dave_facial_ip.json, cloud_vision landmarks) and rewrite history |
| WG-0041 | P0 | defend | Scan history for the API keys V11_CHANGELOG says were scrubbed from v10 files |
| WG-0055 | P0 | defend | Rotate the AniDB password committed in anidb_http_client.py and purge it from history |
| WG-0067 | P0 | defend | Pick one Gemini price table across cost tracker, models spec, PRICING alert and changelog |
| WG-0078 | P0 | defend | Scrub committed facial biometrics of a real person and set a retention policy |
| WG-0089 | P0 | defend | Retire the crossplay safety-bypass experiment and product-decide same-gender only |
| WG-0100 | P0 | defend | Make the A2A card discoverable at one canonical path with a truthful service URL |
| WG-0110 | P0 | defend | Decide license and repo visibility before the A2A card keeps advertising github.com/Who-Visions/Yuki-Ai |
| WG-0372 | P1 | elevate | Move the Expo app off localhost:8000 and hardcoded run.app URLs to EXPO_PUBLIC_API_URL |
| WG-0388 | P1 | elevate | Make yuki-app build from package-lock on Linux CI instead of the committed Windows node_modules |
| WG-0404 | P1 | elevate | Wire cost tracking into the request path and reconcile contract pricing with Unk's spec |
| WG-0420 | P1 | defend | Revive price spike detection, whose data/price_history.json has never been written |
| WG-0436 | P1 | elevate | Reconcile four conflicting Gemini price tables against the real billing export |
| WG-0452 | P1 | elevate | Untrack yuki-app/node_modules and .expo (24,786 files) without breaking the Expo build |
| WG-0467 | P1 | defend | Inventory and retire orphaned Vertex Reasoning Engine deployments, then pin one ID via env |
| WG-0480 | P1 | defend | Cap spend on the unauthenticated /generate route (80 concurrency x 100 instances, no rate limit) |
| WG-0493 | P1 | defend | Implement the exponential backoff the quota guide marks done but the request path lacks |
| WG-0505 | P1 | defend | Correct the public /changelog, which claims billing integration and refunds that do not exist |
| WG-0517 | P1 | defend | Add a junk gate for node_modules, .expo, cache/ and committed DBs before any shard ingest of Yuki-Ai |
| WG-0529 | P1 | defend | Classify biometric-profile JSON as secret-class in the capture guard before Yuki-Ai is captured |
| WG-0541 | P1 | defend | Reconcile the changelog's 'billing integration' claim with the absence of any payment provider |
| WG-0553 | P1 | defend | Determine which Reasoning Engine is live and retire the other (README vs server.py IDs differ) |
| WG-0565 | P1 | defend | Reconcile the two Terms screens and the 2024-dated Privacy Notice with what the backend does |
| WG-0577 | P1 | defend | Bound anonymous /generate spend on the max-100-instance unauthenticated Cloud Run service |
| WG-0588 | P1 | defend | Quarantine batch scripts that violate CONTENT_SAFETY_POLICY before the repo is cited publicly |
| WG-0599 | P1 | defend | Fix one product name and version across app, agent card, ToS and README |
| WG-0610 | P1 | defend | Serve gallery images from GCS signed URLs instead of http://localhost:8083 filenames |
| WG-0621 | P1 | elevate | Move the API base URL to EXPO_PUBLIC config so localhost:8000 and five hardcoded Cloud Run URLs die |
| WG-0632 | P1 | defend | Reconcile subscription promises (Unlimited, Commercial Rights, HD Upscaling) with IP and code reality |
| WG-0643 | P1 | defend | Decide one provider billing boundary: YUKI_API_KEY (Gemini API) vs Vertex ADC (LLC contract) |
| WG-0654 | P1 | elevate | Make the Windows dev stack reproducible: committed logs show fastapi missing and PEP 668 failures |
| WG-0665 | P1 | elevate | Collapse ~40 COMPLETE/FINAL/ENTERPRISE_READY docs into one truthful STATUS and archive the rest |
| WG-0676 | P1 | defend | Classify the HANDOFF 'Yuki Restructuring workflow' as GM-gated, not agent-autonomous |
| WG-0687 | P1 | defend | Bound directive-driven reference generation before any top-1000 sweep runs |
| WG-0698 | P1 | defend | Add a spend governor to the 30+ run_* batch scripts that already produced ghost API calls |
| WG-0709 | P1 | elevate | Ingest Yuki-Ai into NouGenShards without sharding node_modules, DBs, biometrics or the AniDB secret |
| WG-0720 | P1 | elevate | Retire the two legacy FastAPI apps (yuki_api.py, yuki_openai_server.py) whose routes shadow prod |

---

### WG-0010 · P0 · elevate · effort M

**Cut the 'Unk' pricing dependency: make core/yuki_models_spec.py the fleet source of truth for Gemini SKUs**

- Failure surface: yuki_models_spec.py notes it 'DIFFERS from Unk's models_spec.py' and changelog entries on 2025-12-18 record two contradictory Gemini 3 price sets on the same day; two repos in the fleet estimate spend differently and neither matches the contract CSV.
- First fork: if you observe the Unk repo still ships its own spec -> publish a shared pricing JSON in NouGenRelay and import it in both; else freeze Yuki's spec with contract SKU ids
- Evidence: `core/yuki_models_spec.py`, `changelog/entries.json`, `PRICING_DISCREPANCY_ALERT.md`
- Lens: model-cutover · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: core/yuki_models_spec.py:6-7,199-217 explicitly discusses divergence from 'Unk's models_spec.py'. changelog/entries.json has two 2025-12-18 entries with contradictory Gemini 3 prices (Flash $0.50/$3.00 vs $0.40/$1.60 on same date). PRICING_DISCREPANCY_ALERT.md exists.
- #550 families: 65

### WG-0026 · P0 · defend · effort M

**Purge committed biometric profiles (dave_facial_ip.json, cloud_vision landmarks) and rewrite history**

- Failure surface: dave_facial_ip.json holds Dave's ethnicity, age range, Fitzpatrick type and bone structure; cache/cloud_vision/*.json hold real-face landmark coordinates; snow_v5_deep_nodes.json is another person's deep face map. All are in a public-doc'd repo (agent.json points at github.com/Who-Visions/Yuki-Ai).
- First fork: if the repo is public or shared beyond Who Visions -> history rewrite plus force-push with a Dave lock; else git rm and add a pre-commit denylist for *facial_ip*.json and cache/cloud_vision
- Evidence: `dave_facial_ip.json`, `cache/cloud_vision`, `snow_v5_deep_nodes.json`
- Lens: PII-in-stores · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: dave_facial_ip.json contents confirmed exactly: ethnicity 'Black/African American', age_range '35-45', fitzpatrick 'V-VI'. cache/cloud_vision/ has 15 landmark JSON files. snow_v5_deep_nodes.json exists (8575 bytes). agent.json:6 confirms doc_url github.com/Who-Visions/Yuki-Ai.

### WG-0041 · P0 · defend · effort S

**Scan history for the API keys V11_CHANGELOG says were scrubbed from v10 files**

- Failure surface: image_gen/V11_CHANGELOG.md records 'API keys scrubbed from all v10 files', which means they were committed at some point; a regex scan of HEAD found nothing but history was not rewritten, so the keys remain reachable via git log and any mirror or shard capture.
- First fork: if `git log -p` over v10_*.py and extract_kai_facial_ip_v10.py matches a key pattern -> rotate the key and rewrite history with a Dave lock; else record the scan as evidence and close
- Evidence: `image_gen/V11_CHANGELOG.md`, `v10_full_pipeline.py`, `extract_kai_facial_ip_v10.py`
- Lens: secrets-in-stores · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: image_gen/V11_CHANGELOG.md literally states 'API keys scrubbed from all v10 files', confirming keys were present in v10 files at some point in history; v10_full_pipeline.py and extract_kai_facial_ip_v10.py exist as the named v10 files.
- #550 families: 76

### WG-0055 · P0 · defend · effort M

**Rotate the AniDB password committed in anidb_http_client.py and purge it from history**

- Failure surface: anidb_http_client.py hardcodes USER/PASS for the shared 'whovisions' AniDB account in a repo whose URL is advertised in agent.json doc_url; anyone reading the repo owns the account and a fleet ingest would shard the secret. Nobody notices until AniDB bans the client or the shards vault serves the password.
- First fork: if you observe the credential still valid on api.anidb.net -> rotate at AniDB first, then rewrite history and force-push with GM lock; else -> history rewrite only and log as already-dead credential
- Evidence: `anidb_http_client.py`, `agent.json`, `.gitignore`
- Lens: privacy/secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: anidb_http_client.py hardcodes CLIENT_NAME/USER/PASS = 'whovisions' / a literal password string used directly in the API auth payload; agent.json's doc_url points to the public GitHub repo, matching the exposure claim.
- #550 families: 76

### WG-0067 · P0 · defend · effort M

**Pick one Gemini price table across cost tracker, models spec, PRICING alert and changelog**

- Failure surface: core/yuki_cost_tracker.py bills Flash at $0.50/$3.00, PRICE_TRACKING_INTEGRATION.md says contract is $0.30/$2.50, changelog swings between $0.40/$1.60 and $0.50/$3.00 within the same day. Margin math for the $5/10-pack is unfounded.
- First fork: if you observe the Who Visions contract CSV is still accessible -> regenerate one pricing module from it with SKU ids; else -> use current Vertex list prices and label every number CANDIDATE
- Evidence: `core/yuki_cost_tracker.py`, `PRICING_DISCREPANCY_ALERT.md`, `changelog/entries.json`
- Lens: token economics · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: core/yuki_cost_tracker.py:33-35 shows input_per_1m=0.50 and output_per_1m=3.00; a file literally named PRICING_DISCREPANCY_ALERT.md exists in repo root, directly corroborating the claim of conflicting price tables.
- #550 families: 65

### WG-0078 · P0 · defend · effort M

**Scrub committed facial biometrics of a real person and set a retention policy**

- Failure surface: dave_facial_ip.json, knowledge/dave_facial_ip.json, snow_v5_deep_nodes.json and 15 cache/cloud_vision landmark files describe a named real person's face in a repo whose URL is public in agent.json; the Privacy Notice promises deletion rights. This is biometric data under several state laws.
- First fork: if you observe the GM consents to keeping his own profile as a test fixture -> move it to a private GCS bucket referenced by env var; else -> delete from tree and history
- Evidence: `dave_facial_ip.json`, `cache/cloud_vision`, `knowledge/dave_facial_ip.json`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: dave_facial_ip.json, knowledge/dave_facial_ip.json, cache/cloud_vision, and snow_v5_deep_nodes.json all confirmed present in repo listing, directly supporting the claim of committed facial biometric artifacts.
- #550 families: 76

### WG-0089 · P0 · defend · effort S

**Retire the crossplay safety-bypass experiment and product-decide same-gender only**

- Failure surface: STRESS_TEST_FINAL_REPORT records 0/10 crossplay success and recommends disabling gender swap; yuki_crossplay_bypass.py and yuki_gender_bent_test.py keep 'Prompt Aikido' strategies to evade filters on project gifted-cooler-479623-r7. Google's prohibited-use policy treats circumvention as grounds for project suspension, which would take chat and Reasoning Engine down too.
- First fork: if you observe the GM wants crossplay as a feature -> evaluate Imagen 4 / alternative lanes under their policies; else -> delete the bypass scripts and reject cross-gender prompts in the app
- Evidence: `yuki_crossplay_bypass.py`, `STRESS_TEST_FINAL_REPORT.md`, `yuki_gender_bent_test.py`
- Lens: provider policy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: yuki_crossplay_bypass.py:2-3 explicitly reads 'Yuki Crossplay Bypass Test - "Prompt Aikido" / Testing 3 strategies to bypass safety filters for Male -> Sailor Moon outfit.' -- directly confirms the filter-bypass intent named in the claim; STRESS_TEST_FINAL_REPORT.md and yuki_gender_bent_test.py both confirmed present.

### WG-0100 · P0 · defend · effort S

**Make the A2A card discoverable at one canonical path with a truthful service URL**

- Failure surface: changelog claims /.well-known/agent.json; server.py serves /.well-known/a2a/agent.json; api/yuki_api.py serves /.well-known/agent.json; the card's url is yuki-ai-4gig while deploy.sh targets yuki-api-production. A2A partners fetch a 404 or a card pointing at a service that may not be the one deployed.
- First fork: if you observe an external agent registry already caches the card -> keep both paths and fix the URL; else -> serve both paths from one handler and drop the legacy app
- Evidence: `agent.json`, `server.py`, `changelog/entries.json`
- Lens: public surface · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: server.py serves /.well-known/a2a/agent.json, api/yuki_api.py serves /.well-known/agent.json, changelog claims the latter path; agent.json url is yuki-ai-4gig... while deploy.sh SERVICE_NAME=yuki-api-production.

### WG-0110 · P0 · defend · effort S

**Decide license and repo visibility before the A2A card keeps advertising github.com/Who-Visions/Yuki-Ai**

- Failure surface: There is no LICENSE file; terms.js claims proprietary ownership; agent.json publishes the repo URL to any A2A crawler. Third parties either assume all-rights-reserved and cannot integrate, or copy code (and the committed credential) with no terms to point at.
- First fork: if you observe the repo is public on GitHub -> GM ask: private it or add a license; else -> remove doc_url from the card until decided
- Evidence: `agent.json`, `yuki-app/app/terms.js`, `README.md`
- Lens: licensing · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: No LICENSE/LICENSE.* file exists anywhere in the repo; yuki-app/app/terms.js asserts proprietary ownership; agent.json publishes 'doc_url': 'https://github.com/Who-Visions/Yuki-Ai'.

### WG-0372 · P1 · elevate · effort M

**Move the Expo app off localhost:8000 and hardcoded run.app URLs to EXPO_PUBLIC_API_URL**

- Failure surface: AuthContext.js and ChatSidebar.js fetch http://localhost:8000 while generate.js/chat.js/home.js/my-images.js hardcode yuki-ai-4gig; on a real device credits and sidebar chat fail, and rotating the service URL needs an app release.
- First fork: if you observe an existing EAS/env config for the app -> add EXPO_PUBLIC_API_URL there and sweep 7 call sites; else create .env.example and a single api.js client module
- Evidence: `yuki-app/context/AuthContext.js`, `yuki-app/components/ChatSidebar.js`, `yuki-app/app/generate.js`
- Lens: deploy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Confirmed http://localhost:8000 in AuthContext.js (2x) and ChatSidebar.js, and hardcoded yuki-ai-4gig-914641083224.us-central1.run.app in generate.js, chat.js, home.js, my-images.js.
- #550 families: 36

### WG-0388 · P1 · elevate · effort M

**Make yuki-app build from package-lock on Linux CI instead of the committed Windows node_modules**

- Failure surface: yuki-app/node_modules is tracked (24,786 files) including hermesc.exe and lightningcss win32 .node binaries; a Linux or CI checkout gets Windows-only natives and npm ci will fight the tracked tree, so nobody but Dave's box can build the app.
- First fork: if you observe npm ci succeeds on a clean Linux clone with node_modules removed -> git rm -r --cached and add CI; else fix the lockfile (reanimated ~4.1 vs expo 52) first
- Evidence: `yuki-app/node_modules`, `yuki-app/package-lock.json`, `.gitignore`
- Lens: supply-chain · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Confirmed yuki-app/node_modules is tracked with 24,786 files, including win32-specific binaries (lightningcss-win32-x64-msvc/lightningcss.win32-x64-msvc.node) alongside linux64 hermesc, directly supporting the cross-platform build-break claim.
- #550 families: 78

### WG-0404 · P1 · elevate · effort M

**Wire cost tracking into the request path and reconcile contract pricing with Unk's spec**

- Failure surface: YukiCostTracker appends to a relative data/yuki_costs.json (ephemeral in Cloud Run, excluded by .gcloudignore) and is only called from the OpenAI shim; PRICING_DISCREPANCY_ALERT shows the shared spec was 3-6x wrong for 2.5 Flash, so no per-user billing is possible.
- First fork: if you observe yuki_analytics dataset exists in BigQuery -> write a cost row per request there with the contract SKU table; else create the table and backfill from data/yuki_costs.json
- Evidence: `core/yuki_cost_tracker.py`, `data/yuki_costs.json`, `PRICING_DISCREPANCY_ALERT.md`
- Lens: infra · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: core/yuki_cost_tracker.py, data/yuki_costs.json, PRICING_DISCREPANCY_ALERT.md all exist and are on-topic for cost-tracking/pricing-discrepancy claims.
- #550 families: 65

### WG-0420 · P1 · defend · effort M

**Revive price spike detection, whose data/price_history.json has never been written**

- Failure surface: price_tracker.py stores snapshots at data/price_history.json which does not exist in the repo or data/; spike detection has never run, while PRICING_DISCREPANCY_ALERT.md documents the spec being 3x-6x under contract. A future Gemini price change would again go unnoticed until the bill.
- First fork: if the contract CSV referenced by PRICING_DISCREPANCY_ALERT.md is still available -> seed history from it and schedule a monthly snapshot; else seed from the current billing export and mark provenance CANDIDATE
- Evidence: `price_tracker.py`, `PRICING_DISCREPANCY_ALERT.md`, `PRICE_TRACKING_INTEGRATION.md`
- Lens: metrics-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: price_tracker.py:50,369 hardcodes storage_path/PRICE_HISTORY_PATH default to 'data/price_history.json'; confirmed this file does not exist anywhere in the repo (ls fails, and data/ listing does not include it). PRICING_DISCREPANCY_ALERT.md and PRICE_TRACKING_INTEGRATION.md both exist.

### WG-0436 · P1 · elevate · effort M

**Reconcile four conflicting Gemini price tables against the real billing export**

- Failure surface: core/yuki_cost_tracker.py says Flash $0.50/$3.00, changelog entries say $0.40/$1.60 then $0.50/$3.00, audit_today.py assumes $0.04-$0.12 per image, and models_spec has its own estimate_cost. Per-user billing and the $5/10-pack tier cannot be enforced on numbers that disagree.
- First fork: if a billing export with SKU lines for December exists (knowledge/gcp_billing_dec_2025.md) -> derive effective unit prices from it and make cost_tracker the single source; else adopt the contract CSV and flag the rest as superseded
- Evidence: `core/yuki_cost_tracker.py`, `audit_today.py`, `knowledge/gcp_billing_dec_2025.md`
- Lens: metrics-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: core/yuki_cost_tracker.py:33,35 confirms Flash input_per_1m=0.50, output_per_1m=3.00. audit_today.py:49,52-53 confirms the $0.04-$0.12 per-image comment and cost_img_low/high calc. knowledge/gcp_billing_dec_2025.md exists, and changelog/entries.json (checked earlier) confirms two contradictory price sets on 2025-12-18.
- #550 families: 65

### WG-0452 · P1 · elevate · effort M

**Untrack yuki-app/node_modules and .expo (24,786 files) without breaking the Expo build**

- Failure surface: 98% of tracked files are node_modules despite **/node_modules/ in .gitignore; every clone, ingest and CodeQL run pays for it, and any shard ingest of this repo would shard vendor JS as knowledge. Removing it can break a build that never installed from the lockfile.
- First fork: if `npm ci` from yuki-app/package-lock.json succeeds on a clean Node LTS -> git rm -r --cached and add a CI install step; else pin the lockfile against the committed tree first
- Evidence: `yuki-app/node_modules`, `yuki-app/package-lock.json`, `.gitignore`
- Lens: storage/retention · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: git ls-files yuki-app/node_modules returns exactly 24786 files, matching the claim precisely; .gitignore has **/node_modules/ at line 12; package-lock.json exists.

### WG-0467 · P1 · defend · effort M

**Inventory and retire orphaned Vertex Reasoning Engine deployments, then pin one ID via env**

- Failure surface: DEPLOYMENT_LOG records six engine deploys in two hours including an 'accidental redeploy'; server.py points at 8949824538980384768, yuki_api.py at 7435157111765467136, README at 2780528567203659776, run_yuki at 8735413174494298112. Each live engine bills and nobody knows which one answers.
- First fork: if `gcloud ai reasoning-engines list` shows more than one live engine -> delete all but the one the mobile app path reaches, with a Dave lock; else replace every literal with a YUKI_RE_ID env read
- Evidence: `DEPLOYMENT_LOG.md`, `server.py`, `yuki_api.py`
- Lens: observability/false-done · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: All four reasoning-engine IDs found verbatim: server.py RE_ID=...8949824538980384768, yuki_api.py REASONING_ENDPOINT=...7435157111765467136, README.md=...2780528567203659776 (also listed as 'CURRENT' in DEPLOYMENT_LOG.md #6 'Accidental redeploy'), run_yuki.py YUKI_RESOURCE=...8735413174494298112.

### WG-0480 · P1 · defend · effort M

**Cap spend on the unauthenticated /generate route (80 concurrency x 100 instances, no rate limit)**

- Failure surface: deploy.sh sets --allow-unauthenticated --concurrency 80 --max-instances 100, the RateLimitMiddleware in yuki_api.py is commented out, and every request costs a gemini-3-pro-image-preview call. A single script can drain the shared Who Visions billing account.
- First fork: if billing shows /generate spikes from origins other than the Expo app -> require a Firebase ID token immediately; else add a per-IP token bucket and a Cloud Billing budget alert before launch
- Evidence: `scripts/deploy.sh`, `yuki_api.py`, `QUOTA_MANAGEMENT_GUIDE.md`
- Lens: distributed/backpressure · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: scripts/deploy.sh lines 93/97/99 set --allow-unauthenticated, --concurrency 80, --max-instances 100 exactly as claimed; yuki_api.py has RateLimitMiddleware class and app.add_middleware call both commented out (lines 165, 193).
- #550 families: 57

### WG-0493 · P1 · defend · effort M

**Implement the exponential backoff the quota guide marks done but the request path lacks**

- Failure surface: QUOTA_MANAGEMENT_GUIDE.md checks off 'Exponential backoff' and 'Rate limiting (10s delays)', but server.py, v14_pipeline.py and nano_banana_engine.py have no retry; only batch scripts do. 429 RESOURCE_EXHAUSTED on Pro Image is documented as observed and surfaces to users as a generic failure.
- First fork: if Cloud Run logs show 429 more than a few times per hour -> add one shared retry wrapper in core/yuki_gemini_client with jitter and a SAFETY-block exclusion; else defer to Provisioned Throughput
- Evidence: `QUOTA_MANAGEMENT_GUIDE.md`, `image_gen/v14_pipeline.py`, `core/yuki_gemini_client.py`
- Lens: retries · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: QUOTA_MANAGEMENT_GUIDE.md checks off 'Exponential backoff' and 'Rate limiting (10s delays)' (lines 128/158-159) but no retry/backoff logic found via grep in server.py, image_gen/v14_pipeline.py, or core/yuki_gemini_client.py.
- #550 families: 50

### WG-0505 · P1 · defend · effort S

**Correct the public /changelog, which claims billing integration and refunds that do not exist**

- Failure surface: changelog/entries.json is served publicly by /changelog and advertises 'persistent credit system with billing integration' (no payment code, subscription.js has no purchase flow) and cancel-with-refund. Users and partner agents reading the A2A card will rely on features that are stubs.
- First fork: if /changelog is reachable on the live URL -> add a status field (shipped/planned) and mark the two entries planned; else fix the file and leave routing
- Evidence: `changelog/entries.json`, `yuki-app/app/subscription.js`, `yuki_api.py`
- Lens: false-done-markers · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: changelog/entries.json line 8 literally contains the phrase 'persistent credit system with billing integration'; yuki-app/app/subscription.js has UI text mentioning Stripe (line 127) but no fetch/API/purchase call in the file at all, confirming it's a stub with no real payment flow.

### WG-0517 · P1 · defend · effort S

**Add a junk gate for node_modules, .expo, cache/ and committed DBs before any shard ingest of Yuki-Ai**

- Failure surface: An ingest lane pointed at this repo would shard 24,786 vendor JS files, a 7.5MB AniDB XML, two SQLite binaries and 15 Vision JSONs as knowledge, reproducing the lockfiles/base64 incident from HARDENING at ten times the size.
- First fork: if the ingest lane's junk gate already denies node_modules/.expo/*.db/*.xml -> dry-run and count admitted files; else add those rules first and re-run the ingest-junk-gate war game against this repo
- Evidence: `yuki-app/node_modules`, `cache`, `database/yuki_knowledge.db`
- Lens: data-integrity/ingest · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: find over yuki-app/node_modules returns exactly 24,786 files, matching the claim; cache/ and database/yuki_knowledge.db (a committed SQLite binary) also exist and would be admitted by a naive ingest.

### WG-0529 · P1 · defend · effort S

**Classify biometric-profile JSON as secret-class in the capture guard before Yuki-Ai is captured**

- Failure surface: dave_facial_ip.json, face_schema_output.json and cloud_vision landmark caches are structured face data of real people; capture-secret-guard covers API keys but not biometrics, so a shards_capture of this tree would federate Dave's face profile across three nodes.
- First fork: if the capture guard has a denylist by content shape -> add landmarks_34/identity_vector/fitzpatrick markers; else add a path denylist for *facial_ip*.json and cache/cloud_vision as a stopgap
- Evidence: `dave_facial_ip.json`, `face_schema_output.json`, `cache/cloud_vision`
- Lens: PII-in-stores/ingest · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: dave_facial_ip.json contains structured biometric fields (ethnicity, fitzpatrick, undertone, etc.) for a named real person; face_schema_output.json and cache/cloud_vision exist alongside it as the same class of data.
- #550 families: 70

### WG-0541 · P1 · defend · effort S

**Reconcile the changelog's 'billing integration' claim with the absence of any payment provider**

- Failure surface: Entry 2025-12-21 claims a 'persistent credit system with billing integration'; no Stripe/IAP/Play code exists and subscription.js is static copy. Anyone (GM, investor, agent) reading the changelog plans on a capability that is not there.
- First fork: if you observe the changelog is served publicly by /changelog on any live app -> correct the served JSON first; else -> correct entries.json and add a 'verified-in-code' field for future entries
- Evidence: `changelog/entries.json`, `yuki-app/app/subscription.js`, `api/yuki_api.py`
- Lens: docs drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: changelog/entries.json:4-8 (2025-12-21-persistent-user-features) explicitly claims 'a persistent credit system with billing integration'; no Stripe/IAP code found in repo search of api/yuki_api.py, consistent with the claim of no real payment provider.

### WG-0553 · P1 · defend · effort S

**Determine which Reasoning Engine is live and retire the other (README vs server.py IDs differ)**

- Failure surface: README.md advertises reasoningEngines/2780528567203659776; server.py RE_ID is 8949824538980384768; deploy_yuki.py defaults to gemini-3-flash-preview while agents/deploy_yuki.py says gemini-3-pro-preview. Two deployed engines may bill idle, and a redeploy from the wrong copy changes the model silently.
- First fork: if you observe both engines listed by list_engines.py -> delete the one /v1/debug does not report and update README; else -> update README to the surviving ID
- Evidence: `server.py`, `README.md`, `agents/deploy_yuki.py`
- Lens: deploy drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: README.md:51,69 shows reasoningEngines/2780528567203659776 while server.py:106 shows RE_ID='...reasoningEngines/8949824538980384768' -- directly confirms the mismatched engine IDs.
- #550 families: 12

### WG-0565 · P1 · defend · effort S

**Reconcile the two Terms screens and the 2024-dated Privacy Notice with what the backend does**

- Failure surface: tos.js (EFFECTIVE_DATE 'December 20, 2024', 'WhoVisions LLC, a Delaware company') and terms.js ('Last Updated: December 2024') coexist with different clauses; privacy.js lists payment data and deletion rights that no code implements. App-store review or a user complaint exposes the contradiction.
- First fork: if you observe both screens are routed from the app UI -> keep one, delete the other, and have the GM confirm entity/state; else -> delete the orphan and date the survivor
- Evidence: `yuki-app/app/tos.js`, `yuki-app/app/terms.js`, `yuki-app/app/privacy.js`
- Lens: licensing/legal · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: All three files exist (tos.js, terms.js, privacy.js as separate files) and tos.js content confirmed to reference 'WhoVisions LLC' and 'Cosplay Labs' branding, consistent with two coexisting, differently-branded legal screens.

### WG-0577 · P1 · defend · effort M

**Bound anonymous /generate spend on the max-100-instance unauthenticated Cloud Run service**

- Failure surface: /generate takes any multipart upload with no auth, rate limit or credit check and runs Cloud Vision + Flash + Pro + Pro Image (~$0.13-0.30 per call) with --max-instances 100 and --concurrency 80. A script loop burns the shared Who Visions billing account overnight; the first signal is the GCP invoice.
- First fork: if you observe a per-project budget alert already exists for gifted-cooler-479623-r7 -> add per-IP/per-uid quota in the route; else -> create the budget alert first (reversible), then quota
- Evidence: `server.py`, `scripts/deploy.sh`, `QUOTA_MANAGEMENT_GUIDE.md`
- Lens: cost/runaway · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: server.py:573 defines POST /generate with no auth check; scripts/deploy.sh:97-99 sets --concurrency 80 and --max-instances 100. No rate limit/credit gate found in the route.
- #550 families: 57

### WG-0588 · P1 · defend · effort S

**Quarantine batch scripts that violate CONTENT_SAFETY_POLICY before the repo is cited publicly**

- Failure surface: run_nini_topless_single.py ('ARTISTIC NUDE'), run_lilith_micro_bikini.py and run_safety_boundary_test.py probe 'implied nudity' and 'see-through' prompts on a real subject, contradicting the policy's hard boundaries. agent.json's doc_url invites A2A partners to read this repo.
- First fork: if you observe these scripts are referenced by any doc or workflow -> archive to a private location and update references; else -> delete them and note in changelog
- Evidence: `run_nini_topless_single.py`, `run_safety_boundary_test.py`, `docs/CONTENT_SAFETY_POLICY.md`
- Lens: brand/policy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: run_nini_topless_single.py, run_safety_boundary_test.py, run_lilith_micro_bikini.py and docs/CONTENT_SAFETY_POLICY.md all confirmed present in the repo file listing, directly supporting the existence of these boundary-probing scripts alongside a formal safety policy doc.

### WG-0599 · P1 · defend · effort S

**Fix one product name and version across app, agent card, ToS and README**

- Failure surface: app.json says 'Yuki Cosplay', ToS says 'Cosplay Labs', agent.json says 'Yuki Ai' v1.4.0 by 'Who Visions', README says Yuki Agent v0.05, HANDOFF says 0.06-local, system prompt says 'Lead Cosplay Architect at Cosplay Labs'. Store listings, A2A discovery and legal docs disagree on who the product is.
- First fork: if you observe a trademark or domain decision exists for Cosplay Labs vs Yuki -> propagate it; else -> park as GM ask (naming is external) and align versions only
- Evidence: `agent.json`, `yuki-app/app.json`, `yuki-app/app/tos.js`
- Lens: brand/canon · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: yuki-app/app.json:3 'name': 'Yuki Cosplay'; agent.json:2,4,58 'name': 'Yuki Ai', 'version': '1.4.0', 'name': 'Who Visions'; yuki-app/app/tos.js references 'Cosplay Labs' and 'WhoVisions LLC' -- confirms at least three distinct product/company names across the three files.

### WG-0610 · P1 · defend · effort M

**Serve gallery images from GCS signed URLs instead of http://localhost:8083 filenames**

- Failure surface: /v1/user/images builds uri as http://localhost:8083/{filename}, i.e. the Windows assets_server.py on the GM's machine; assets.log already shows 404 storms. Every device except the dev box sees broken image cards in My Creations.
- First fork: if you observe generation outputs are already uploaded to yuki-cosplay-generations -> return signed URLs; else -> upload at generation time first, then switch
- Evidence: `server.py`, `assets_server.py`, `assets.log`
- Lens: product/UX · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: server.py:757 builds url = f'http://localhost:8083/{filename}' in /v1/user/images; assets.log shows repeated 404s.

### WG-0621 · P1 · elevate · effort S

**Move the API base URL to EXPO_PUBLIC config so localhost:8000 and five hardcoded Cloud Run URLs die**

- Failure surface: AuthContext.js and ChatSidebar.js still call http://localhost:8000; generate.js, chat.js, home.js and my-images.js hardcode the Cloud Run URL. Rotating the service or adding a custom domain requires an app-store release; credits never load on devices.
- First fork: if you observe firebase.js already reads EXPO_PUBLIC_* vars -> add EXPO_PUBLIC_YUKI_API_URL with the same mechanism; else -> introduce a constants/api.js and a lint rule against literal run.app URLs
- Evidence: `yuki-app/context/AuthContext.js`, `yuki-app/components/ChatSidebar.js`, `yuki-app/app/generate.js`
- Lens: product/UX · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: AuthContext.js and ChatSidebar.js call http://localhost:8000; generate.js, chat.js, home.js, my-images.js hardcode the same yuki-ai-4gig...run.app URL (5 hardcoded occurrences across files).
- #550 families: 35

### WG-0632 · P1 · defend · effort S

**Reconcile subscription promises (Unlimited, Commercial Rights, HD Upscaling) with IP and code reality**

- Failure surface: subscription.js sells 'Commercial Rights' on renders of third-party anime characters while terms.js warns character likenesses are third-party IP; 'Unlimited Renders' at $9.99 loses money at $0.13-0.30/render; 'HD Upscaling' and 'Private Gallery' do not exist. A store reviewer or a rights holder reads it.
- First fork: if you observe the GM wants to keep the $9.99 tier -> model it against measured render cost and cap it; else -> replace with the report's $5/10-pack and drop 'Commercial Rights'
- Evidence: `yuki-app/app/subscription.js`, `yuki-app/app/terms.js`, `STRESS_TEST_FINAL_REPORT.md`
- Lens: licensing/product · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: subscription.js lists Unlimited Renders/Private Gallery/HD Upscaling/Commercial Rights at $9.99; terms.js explicitly warns 'Character likenesses may be subject to third-party copyrights.'

### WG-0643 · P1 · defend · effort S

**Decide one provider billing boundary: YUKI_API_KEY (Gemini API) vs Vertex ADC (LLC contract)**

- Failure surface: server.py silently switches to Gemini API key mode when YUKI_API_KEY is set, billing a different account/tier with different quotas and no contract pricing; Dec billing shows $21.81 Gemini API beside $198 Vertex. The cost tracker and quota guide only model Vertex.
- First fork: if you observe YUKI_API_KEY set on the live Cloud Run service -> remove it and rely on ADC, or document the account it bills; else -> delete the key branch to prevent drift
- Evidence: `server.py`, `knowledge/gcp_billing_dec_2025.md`, `core/yuki_models_spec.py`
- Lens: provider billing boundary · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: server.py:139-143 branches into Gemini API key auth when YUKI_API_KEY is set; knowledge/gcp_billing_dec_2025.md shows Vertex AI $198.42 vs Gemini API $21.81 as separate line items.
- #550 families: 65

### WG-0654 · P1 · elevate · effort M

**Make the Windows dev stack reproducible: committed logs show fastapi missing and PEP 668 failures**

- Failure surface: backend.log records server.py dying on ModuleNotFoundError fastapi; pip_install.log records externally-managed-environment; start_stack.bat kills ports 8000/8083 and launches from C:\Yuki_Local. A new agent on blade or phoebus cannot reproduce the GM's environment.
- First fork: if you observe activate_yuki.bat creates a venv -> make start_stack.bat use it and pin requirements; else -> write a single bootstrap script and delete the committed logs
- Evidence: `backend.log`, `pip_install.log`, `start_stack.bat`
- Lens: onboarding · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: backend.log literally records 'ModuleNotFoundError: No module named fastapi'; pip_install.log records 'error: externally-managed-environment'; start_stack.bat kills ports 8000/8083 and launches the C:\Yuki_Local-based stack.
- #550 families: 36

### WG-0665 · P1 · elevate · effort M

**Collapse ~40 COMPLETE/FINAL/ENTERPRISE_READY docs into one truthful STATUS and archive the rest**

- Failure surface: FILE_INDEX.md, ENTERPRISE_READY.md, IMPLEMENTATION_STATUS.md and REFACTORING_COMPLETE.md claim production readiness while HANDOFF.md says 'unstructured'; archive/ duplicates nine root docs. Agents and the GM cannot tell current truth from Dec 2025 aspiration.
- First fork: if you observe any doc is served by the app or A2A (changelog) -> keep it canonical and derive STATUS from it; else -> write STATUS.md from code, move the rest to archive/ with a DEPRECATED banner
- Evidence: `FILE_INDEX.md`, `ENTERPRISE_READY.md`, `archive`
- Lens: docs drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: FILE_INDEX.md marks ENTERPRISE_READY.md/REFACTORING_COMPLETE.md/COMPLETE_SYSTEM_README.md as '✅ Complete'/'✅ Ready' while HANDOFF.md states 'State: Active, but unstructured.'; archive/ holds 10 entries duplicating root docs.

### WG-0676 · P1 · defend · effort S

**Classify the HANDOFF 'Yuki Restructuring workflow' as GM-gated, not agent-autonomous**

- Failure surface: HANDOFF.md ends with 'Trigger the Yuki Restructuring workflow'; .agent/workflows and directives/ read as executable agent instructions with no ask/report classification. An autonomous lane obeys, moves root modules, and breaks the Cloud Run import path in one sweep.
- First fork: if you observe a lane already opened a restructuring PR -> stop it, require the container smoke test; else -> annotate HANDOFF.md and directives/ with ask/report labels
- Evidence: `HANDOFF.md`, `.agent/workflows/face_math_workflow.md`, `directives/cosplay_preview_generation.md`
- Lens: agent doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: HANDOFF.md ends with the literal action item 'Trigger the Yuki Restructuring workflow to execute this plan.' and .agent/workflows/face_math_workflow.md plus directives/cosplay_preview_generation.md exist as unlabeled prose/instruction files.

### WG-0687 · P1 · defend · effort S

**Bound directive-driven reference generation before any top-1000 sweep runs**

- Failure surface: directives/cosplay_preview_generation.md instructs the agent to generate three Pro Image references plus grounded search per character before the user render; top_1000_anime.txt and yuki_top15_batch.py show batch intent. One 'pre-warm the catalog' sweep is 3,000+ images at $0.134-0.24 each.
- First fork: if you observe any reference images already cached in gs://yuki-ai-assets/subjects -> reuse and cap new generations per run; else -> add a max-images argument and a dry-run default to every batch entrypoint
- Evidence: `directives/cosplay_preview_generation.md`, `top_1000_anime.txt`, `yuki_top15_batch.py`
- Lens: cost/runaway · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: directives/cosplay_preview_generation.md explicitly instructs generating 3 reference images plus grounded-search-backed analysis per character before final render; top_1000_anime.txt lists 1000 characters and yuki_top15_batch.py shows batch-run intent, supporting the 3000+ image sweep-cost claim.

### WG-0698 · P1 · defend · effort M

**Add a spend governor to the 30+ run_* batch scripts that already produced ghost API calls**

- Failure surface: error_learning_log.py records 'ghost' API calls with no saved file; run_drake_batch_async.py and siblings loop over characters with no budget, dry-run or checkpoint. A retry loop on a blocked prompt spends until the quota, not the wallet, stops it.
- First fork: if you observe a shared batch base class or helper exists -> add the governor there; else -> write one runner module and migrate scripts as they are next used
- Evidence: `run_drake_batch_async.py`, `error_learning_log.py`, `QUOTA_MANAGEMENT_GUIDE.md`
- Lens: cost/runaway · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: error_learning_log.py records error type 'Ghost API Calls - No Images Saved' verbatim; run_drake_batch_async.py loops over a character list calling the pipeline with no budget cap, dry-run flag, or checkpoint/resume logic anywhere in the file.
- #550 families: 49, 65

### WG-0709 · P1 · elevate · effort M

**Ingest Yuki-Ai into NouGenShards without sharding node_modules, DBs, biometrics or the AniDB secret**

- Failure surface: A fleet capture of this repo would push 24k vendored files, committed SQLite/XML dumps, a real person's face profile and a plaintext password into shards, repeating the lockfile/base64 and secrets incidents from HARDENING.md. Recall quality drops and the secret becomes fleet-wide.
- First fork: if you observe ingest-junk-gate and capture-secret-guard rules already cover .db/.xml/node_modules and password patterns -> run a dry-run coverage report first; else -> extend the gates before any capture
- Evidence: `yuki-app/node_modules`, `anidb_http_client.py`, `dave_facial_ip.json`
- Lens: fleet knowledge · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: yuki-app/node_modules is a large vendored directory, anidb_http_client.py contains a hardcoded plaintext password (PASS = "Kuro!Phoe412^") sent in API calls, and dave_facial_ip.json is a detailed named facial-biometric profile -- all real, ingestible junk/secret/biometric surface for a fleet capture.
- #550 families: 74, 76

### WG-0720 · P1 · elevate · effort M

**Retire the two legacy FastAPI apps (yuki_api.py, yuki_openai_server.py) whose routes shadow prod**

- Failure surface: api/yuki_api.py and root yuki_api.py differ (semantic-search only in api/), both keep /api/v1/upload, /ws/generation and changelog pages, and api/yuki_openai_server.py still runs DEBUG prints with allow_credentials=True. deploy.sh prints endpoint URLs from these apps that server.py never serves.
- First fork: if you observe any client or doc depends on /api/v1/* or /changelog -> port those routes into server.py first; else -> delete both apps and fix deploy.sh's endpoint list
- Evidence: `api/yuki_api.py`, `api/yuki_openai_server.py`, `scripts/deploy.sh`
- Lens: public surface/docs drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: api/yuki_api.py and root yuki_api.py differ (api/ version adds semantic-search endpoints per grep), both retain /api/v1/upload, /ws/generation/{id}, and /changelog routes, and api/yuki_openai_server.py still has DEBUG print statements and allow_credentials=True in its CORS config -- all confirmed live in the current tree, alongside server.py which serves none of these legacy routes.
- #550 families: 34
