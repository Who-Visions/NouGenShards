# War-game candidates — Rhea-Noir

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

64 candidates · P0 17 · P1 47 · P2 0 · P3 0 · defend 49 · elevate 15

| id | P | kind | title |
|---|---|---|---|
| WG-0008 | P0 | defend | Rotate and purge the live Notion tokens hardcoded in Scripts/corrected_migration.py |
| WG-0024 | P0 | defend | Rotate the live Google API key in test_extract.py and purge it from the 2 GB git history |
| WG-0039 | P0 | elevate | Shrink the 2 GB repo: 118 committed omniverse PNGs, Scripts/*.exe, json3 captions, zip and wav |
| WG-0053 | P0 | defend | Stop veil_utils.ensure_schema and _create_property from auto-growing Notion schema (333 vs 399 props) |
| WG-0065 | P0 | defend | Deployed server silently runs in limited mode: sync_engine imports a missing env_loader module |
| WG-0076 | P0 | defend | Snapshot before the seven archive scripts set archived:true on live canon pages |
| WG-0087 | P0 | defend | Rotate and purge the live Notion tokens in Scripts/corrected_migration.py and the key in test_extract.py |
| WG-0098 | P0 | defend | Survive the death of the one Windows box rhea_bridge_server.py depends on |
| WG-0108 | P0 | defend | Retire or restore the Moltbook public agent lane that half-exists in code and doctrine |
| WG-0118 | P0 | defend | Resolve the licensing exposure of proxy-rotated YouTube transcript ingestion and committed captions |
| WG-0126 | P0 | defend | Set policy for the 29 offensive-security skill packs living in a creative-lore repo |
| WG-0134 | P0 | defend | Recover the Cosplay Remix Engine and Lightroom work that exists only on a machine, not in git |
| WG-0142 | P0 | defend | Reconcile the 2158-vs-2174 blade acquisition contradiction between two LOCKED canon docs |
| WG-0150 | P0 | elevate | Designate the canon system of record among Notion, veillore.db, 686 md files and NouGenShards |
| WG-0158 | P0 | elevate | Decide archive-vs-revive and merge authority for a repo idle since 2026-04-30 |
| WG-0166 | P0 | defend | Retire the local planning-with-files ledger that diverges from relay handoffs |
| WG-0174 | P0 | defend | Converge or kill the second production Rhea deployed to Agent Engine by deploy_cloudshell.sh |
| WG-0370 | P1 | defend | Remove the committed Google API key in test_extract.py without breaking transcript fetch |
| WG-0386 | P1 | elevate | Migrate deploy to who-visions-tester without a wrong-project push or lost secrets |
| WG-0402 | P1 | defend | Cut over the notion-client floor from 5.x claim to a real version that exists |
| WG-0418 | P1 | defend | Purge the leaked Vertex API key from git history (commit 40934b2 only redacted HEAD) |
| WG-0434 | P1 | defend | Drop --allow-unauthenticated from the Cloud Run deploy without locking out the Flutter client |
| WG-0450 | P1 | defend | Scope down the Google Workspace OAuth token before it ships to a public service |
| WG-0465 | P1 | defend | Stop the global exception handlers from masking every error as HTTP 200 |
| WG-0478 | P1 | defend | Add a Source URL dedup gate so re-ingesting the same YouTube URL doesn't mint duplicate canon |
| WG-0491 | P1 | defend | Keep chat memories (memu_*) out of the canon entities table and out of Notion via reconcile_lore |
| WG-0503 | P1 | elevate | Get a versioned Notion backup: sync_all_databases and dump_loredb write only gitignored *.json |
| WG-0515 | P1 | defend | Coordinate one NOTION_TOKEN across ~200 scripts, the server and watchdog_sync: the governor is per-process |
| WG-0527 | P1 | defend | Fix /health that lies: 'Always return healthy to keep Cloud Run alive' while services init failed |
| WG-0539 | P1 | defend | services/universal_schema.py is missing: /v1/ingest and /api/ingest fail at import on every call |
| WG-0551 | P1 | defend | /v1/cowrite/save returns 'saved' and persists nothing: a false done-marker on a public route |
| WG-0563 | P1 | defend | Stop cp1252 emoji prints from crashing Windows scripts before they do any work |
| WG-0575 | P1 | elevate | Purge ~80 committed scratch outputs and UTF-16 logs and stop new ones landing in git |
| WG-0586 | P1 | defend | Track real token spend: chat cost tracking writes len//4 and a constant 500 output tokens to Firestore |
| WG-0597 | P1 | elevate | Reconcile the two Dockerfiles before Cloud Build picks infra/Dockerfile that runs a nonexistent app:app |
| WG-0608 | P1 | defend | Rescue TRIPLE-LOCKED timeline tables that exist only in a gitignored SQLite on one Windows box |
| WG-0619 | P1 | elevate | Restore submodule resolvability: 20 gitlinks with no .gitmodules, Gemma4Core dir absent from tree |
| WG-0630 | P1 | elevate | Implement the Veil Ghost contradiction audit in code instead of 'manual review recommended' |
| WG-0641 | P1 | defend | Audit the always-on 'rhea-noir' Cloud Run service (minScale 1, 4Gi, maxScale 20) for zombie spend |
| WG-0652 | P1 | elevate | Finish the who-visions-tester tenant migration without a wrong-project deploy |
| WG-0663 | P1 | defend | Stop each Cloud Run instance starting its own Slack socket-mode bot |
| WG-0674 | P1 | defend | Remove the committed venv Scripts/*.exe without breaking tests that import Scripts/gemma4_core |
| WG-0685 | P1 | defend | Reconcile .gitignore '*.json' with data/README.md and the JSON state files the pipeline needs |
| WG-0696 | P1 | defend | Cure UTF-16 contamination in .gitignore and rhea_run_config.yaml before Linux CI reads them |
| WG-0707 | P1 | defend | Restore .gitmodules for 20 orphaned gitlinks or convert them to vendored/pinned deps |
| WG-0718 | P1 | elevate | Take rhea_mobile_command from com.example scaffold to a shippable build |
| WG-0729 | P1 | defend | Reconcile the port topology across README, start_servers.ps1, findings.md and code |
| WG-0739 | P1 | elevate | Unify the three Rhea personas served on public surfaces |
| WG-0749 | P1 | defend | Gate /v1/ingest and /api/ingest, which write straight into the live VeilVerse Notion DB |
| WG-0759 | P1 | defend | Decide attribution and SSL policy before scraping 8,000 Samurai Archives articles into veillore.db |
| WG-0769 | P1 | defend | Bring README claims (LICENSE, scripts/, rhea_noir_cli.py, Pylint 9.5) back to parity with the tree |
| WG-0779 | P1 | elevate | Stand up first CI on a 3125-file, 2GB repo with missing deps and broken submodules |
| WG-0789 | P1 | defend | Merge the Corbin Varas / Corbin Veras identity split across 19 canon docs |
| WG-0799 | P1 | defend | Pick one Amon purge policy: consolidated_sanitizer DELETEs, SCRIBE_MANDATE says SCRUB not delete |
| WG-0809 | P1 | elevate | Finish the Universe_LoreBase -> new Notion DB migration (corrected_migration v3) without duplicating pages |
| WG-0819 | P1 | defend | Run sync_master_to_registries fan-out once without spawning the duplicates merge_duplicates.py cannot fix |
| WG-0829 | P1 | defend | Stop ChatGPT-archive ingestion until the 14 conflicts in CANON_CROSSREF_REPORT get a GM ruling |
| WG-0839 | P1 | defend | Survive the Notion integration losing database access again (notion_schema_map: 'No Databases Found') |
| WG-0849 | P1 | defend | Finish the Notion API data_source migration spread across three API versions |
| WG-0859 | P1 | elevate | Launch the public VeilVerse Nexus wiki without leaking PRIME-locked canon and Act III spoilers |
| WG-0869 | P1 | defend | Reconcile the user-authority skill (follow docs EXACTLY) with Rule 0.1 when the docs are wrong |
| WG-0879 | P1 | defend | Stop committing runtime logs (lore_keeper.log, ingest.log, expand_retry.log) that carry Notion content |
| WG-0889 | P1 | defend | Make LoreDB sync runnable on Linux nodes, not only via sync_lore.bat and venv\Scripts\python.exe |
| WG-0898 | P1 | defend | Decide whether GEMINI_API_KEY_FALLBACK 429-pivoting crosses a provider billing boundary |

---

### WG-0008 · P0 · defend · effort M

**Rotate and purge the live Notion tokens hardcoded in Scripts/corrected_migration.py**

- Failure surface: Two full ntn_ integration tokens (SOURCE_TOKEN/TARGET_TOKEN) sit in cleartext in tracked code and repo history; anyone with repo read can write to the canon Notion databases. Notion or a scraper notices; lore gets corrupted or exfiltrated.
- First fork: if git log -S shows the tokens were ever pushed to a public/forked remote -> assume compromised, revoke both immediately and re-key; else -> revoke as precaution and rewrite history
- Evidence: `Scripts/corrected_migration.py`, `services/notion.py`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Scripts/corrected_migration.py:8-9 hold two literal ntn_ tokens in tracked HEAD; origin is github.com/Who-Visions/Rhea-Noir.
- #550 families: 76

### WG-0024 · P0 · defend · effort M

**Rotate the live Google API key in test_extract.py and purge it from the 2 GB git history**

- Failure surface: test_extract.py line 36 still embeds an AIza key even though commit 40934b2 removed a different one; the key sits in a public-facing repo's history, and the same key pattern is what the fleet's capture-secret-guard exists to stop from reaching shards.
- First fork: if you observe the key still valid in the GCP console -> revoke it first and then rewrite history, else proceed straight to history rewrite plus a pre-commit secret scan.
- Evidence: `test_extract.py`
- Lens: secrets-in-store · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: test_extract.py line 36 literally embeds 'AIzaSy[REDACTED]' as a live-looking Google API key string; git log shows commit 40934b2 'chore: remove hardcoded api key for security' exists in history, confirming a different key was previously removed while this one remains.
- #550 families: 76

### WG-0039 · P0 · elevate · effort L

**Shrink the 2 GB repo: 118 committed omniverse PNGs, Scripts/*.exe, json3 captions, zip and wav**

- Failure surface: generated_omniverse_assets holds 20-25 MB PNGs each, a Windows venv Scripts/ dir with pip.exe and fastapi.exe is tracked, and YouTube json3 captions sit at root; every clone, Cloud Build and shard sweep drags binaries, and Docker COPY . . bakes them into the image.
- First fork: if you observe Cloud Build image size or clone time above the current baseline -> move binaries to GCS/LFS and rewrite history with a tracked manifest, else proceed to a .gitattributes LFS policy for future assets only.
- Evidence: `generated_omniverse_assets`, `Scripts/pip.exe`, `Dockerfile`
- Lens: storage · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: generated_omniverse_assets/ is 1.9GB of PNGs (20-25MB each observed), Scripts/*.exe contains 22 tracked Windows executables including pip.exe, and Dockerfile has 'COPY . .' which would bake all of this into the image build context.

### WG-0053 · P0 · defend · effort S

**Stop veil_utils.ensure_schema and _create_property from auto-growing Notion schema (333 vs 399 props)**

- Failure surface: ensure_schema and NotionPusher._ensure_properties_exist create any missing property on the fly, and registry_schema declares 350+; expand_retry.log already shows 'Total: 333 | Existing: 399' and a crash creating 'Registry Status', so a typo in one script permanently adds a column to the shared canon database.
- First fork: if you observe a property created that is not in registry_schema.py -> archive it in Notion and add a deny-by-default flag, else proceed to make creation require an explicit --create-props switch.
- Evidence: `services/veil_utils.py`, `push_to_notion_finals.py`, `expand_retry.log`
- Lens: schema · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: services/veil_utils.py defines ensure_schema(); push_to_notion_finals.py defines _create_property and _ensure_properties_exist which auto-create missing Notion properties; expand_retry.log (UTF-16 encoded) literally contains 'Total: 333 | Existing: 399 | Missing: 1' followed by a crash while 'Creating Registry Status' -- exact match to the claimed observed incident.

### WG-0065 · P0 · defend · effort S

**Deployed server silently runs in limited mode: sync_engine imports a missing env_loader module**

- Failure surface: services/sync_engine.py does 'import env_loader' which is not tracked anywhere in the repo; rhea_server's try/except sets SERVICES_AVAILABLE=False on that ImportError, so Cloud Run boots with no LoreMemory, no sync, no Slack and no memory, logs one warning, and answers /health healthy.
- First fork: if you observe 'Some services unavailable' in the boot log -> vendor env_loader (or drop the import) and redeploy, else proceed to fail the boot loudly when core services are unavailable.
- Evidence: `services/sync_engine.py`, `rhea_server.py`
- Lens: silent-death · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: services/sync_engine.py:8 does 'import env_loader' with no such module tracked in the repo; rhea_server.py sets SERVICES_AVAILABLE=True/False around imports (line 219/222) and gates many routes on it.

### WG-0076 · P0 · defend · effort S

**Snapshot before the seven archive scripts set archived:true on live canon pages**

- Failure surface: root_out_amon, final_cauterization, yasuke_merge and restore_yasuke archive or rewrite pages by hardcoded id via delete_page; restore_error.txt shows restore_yasuke_v2 crashing mid-run, and there is no pre-image export, so a wrong-id run or a partial restore leaves canon in a state only Notion's 30-day trash can undo.
- First fork: if you observe a script about to call delete_page without a dated export of that page -> export page+blocks to the backup bucket first, else proceed to add a --snapshot-first flag defaulted on in NotionService.delete_page.
- Evidence: `Scripts/operations/root_out_amon.py`, `Scripts/operations/final_cauterization.py`, `restore_error.txt`
- Lens: restore · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Scripts/operations/root_out_amon.py:23 and final_cauterization.py:25 both call api.delete_page(pid); restore_error.txt exists and is a UTF-16 error dump consistent with a crashed restore run; Scripts/operations/restore_yasuke_v2.py and yasuke_merge.py also present in the tree.
- #550 families: 9

### WG-0087 · P0 · defend · effort M

**Rotate and purge the live Notion tokens in Scripts/corrected_migration.py and the key in test_extract.py**

- Failure surface: Commit 40934b2 'remove hardcoded api key' missed two ntn_ tokens (SOURCE/TARGET) and an AIza key; anyone with repo access can read and write both Notion workspaces; history rewrite breaks clones on blade/phoebus/whoart.
- First fork: if you observe the tokens still validate against api.notion.com -> route A: rotate first, then scrub history; else route B: scrub only and document
- Evidence: `Scripts/corrected_migration.py`, `test_extract.py`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Scripts/corrected_migration.py lines 8-9 hardcode SOURCE_TOKEN/TARGET_TOKEN as live-looking ntn_ Notion tokens; test_extract.py line 36 hardcodes an AIzaSy... API key.
- #550 families: 76

### WG-0098 · P0 · defend · effort M

**Survive the death of the one Windows box rhea_bridge_server.py depends on**

- Failure surface: rhea_bridge_server.py hardcodes c:\Users\super\.gemini\antigravity\brain\... as ARTIFACT_DIR and config\firebase_service_account.json; the gallery/render bridge only exists on that machine, mirroring the blade freeze pattern.
- First fork: if you observe the bridge is still what the Flutter app talks to -> route A: containerize with env paths; else route B: fold bridge functions into rhea_server and delete
- Evidence: `rhea_bridge_server.py`
- Lens: product · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: rhea_bridge_server.py:12 hardcodes ARTIFACT_DIR to c:\Users\super\.gemini\...; line 14 hardcodes FIREBASE_CRED to config\firebase_service_account.json. Evidence directly supports the failure surface.
- #550 families: 94

### WG-0108 · P0 · defend · effort M

**Retire or restore the Moltbook public agent lane that half-exists in code and doctrine**

- Failure surface: publish_elevation.py, molt_comment_action.py and .agent/workflows/moltbook.md instruct agents to post as 'Rhea-Noir', but services/moltbook.py and rhea_heartbeat.py are missing and task_plan.md says 'Moltbook Scrapped'; an agent following the workflow crashes or, if the module is restored, posts publicly without GM review.
- First fork: if you observe the Moltbook account still exists and is claimed -> route A: formal retirement + delete scripts; else route B: keep skill doc only, mark workflow deprecated
- Evidence: `.agent/workflows/moltbook.md`, `task_plan.md`, `publish_elevation.py`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .agent/workflows/moltbook.md instructs running rhea_heartbeat.py --moltbook; rhea_heartbeat.py and services/moltbook.py do not exist in the repo (confirmed missing via ls); publish_elevation.py imports services.moltbook and posts as 'Rhea-Noir'; task_plan.md explicitly says 'Moltbook Scrapped' and 'fully removed'. Contradiction confirmed.

### WG-0118 · P0 · defend · effort M

**Resolve the licensing exposure of proxy-rotated YouTube transcript ingestion and committed captions**

- Failure surface: services/ingestor.py wires WEBSHARE/PROXY creds, functions/youtube_transcript exists 'to bypass local 429 limits', and 14 *.en.json3 caption files are committed at root; a takedown or ToS strike hits the Who Visions channel that the pipeline feeds.
- First fork: if you observe the captions belong to Who Visions' own videos -> route A: keep, document ownership, move to data/; else route B: purge from history and stop committing
- Evidence: `services/ingestor.py`, `functions/youtube_transcript/main.py`, `transcripts`
- Lens: licensing · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: services/ingestor.py references WEBSHARE_USER/WEBSHARE_PASS/PROXY_HTTP/PROXY_HTTPS env vars (lines 498-501); functions/youtube_transcript/main.py exists; 14 *.en.json3 caption files are committed at repo root (confirmed count via ls).

### WG-0126 · P0 · defend · effort S

**Set policy for the 29 offensive-security skill packs living in a creative-lore repo**

- Failure surface: .agent/skills/cybersecurity ships privilege-escalation, metasploit and sqlmap playbooks beside canon; any visibility change, image leak or agent auto-loading of skills turns a worldbuilding repo into a red-team toolkit.
- First fork: if you observe any agent lane auto-discovers .agent/skills -> route A: move packs to a separate private repo; else route B: allowlist skills per repo in doctrine
- Evidence: `.agent/skills/cybersecurity`, `.dockerignore`
- Lens: governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .agent/skills/cybersecurity contains 29 subdirectories (confirmed count) including active-directory-attacks, aws-penetration-testing, cloud-penetration-testing, etc., living inside the same repo as the lore/canon docs.

### WG-0134 · P0 · defend · effort M

**Recover the Cosplay Remix Engine and Lightroom work that exists only on a machine, not in git**

- Failure surface: Commit af18fa5 claims 'restore Adobe Lightroom pipeline' but no Lightroom code exists; SESSION_LOGS_MASTER.md references Scripts/run.py, engine/core.py and SESSION_HANDOFF_2026_03_31.md, none tracked; a disk failure erases months of work the ledger says is done.
- First fork: if you observe the files on blade under Rhea-Noir-Ai -> route A: commit them now with the handoff; else route B: mark the session log entries as LOST and re-plan
- Evidence: `SESSION_LOGS_MASTER.md`, `Scripts`
- Lens: governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: git log shows commit af18fa5 'feat: stabilize Gemma4Core and restore Adobe Lightroom pipeline'; SESSION_LOGS_MASTER.md references Scripts/run.py, engine/core.py, and SESSION_HANDOFF_2026_03_31.md (lines 8, 12), none of which exist in the tracked tree (confirmed via ls).

### WG-0142 · P0 · defend · effort M

**Reconcile the 2158-vs-2174 blade acquisition contradiction between two LOCKED canon docs**

- Failure surface: TIMELINE_v3_1.md line 28 orders AIs to 'correct 2158 to 2174' while MASTER_CANON_LOCK.md v3.5 triple-locks 2158; any agent following either doc rewrites the other's canon, and the shards ledger inherits whichever it ingested last.
- First fork: if you observe the NouGenShards Xoah ledger carries 2158 -> route A: deprecate TIMELINE_v3_1 with a tombstone; else route B: escalate to Dave, both docs frozen until ruling
- Evidence: `TIMELINE_v3_1.md`, `MASTER_CANON_LOCK.md`
- Lens: canon · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: TIMELINE_v3_1.md line 28 states 'GOVERNANCE RULE: If an AI generation mentions a 2158 blade acquisition, correct it to 2174'; MASTER_CANON_LOCK.md line 9 (under 'TRIPLE-LOCKED' status) states 'Corbin Varas acquires the Left Half of Kage Tanak' in 2158. The two LOCKED docs directly contradict each other exactly as claimed.

### WG-0150 · P0 · elevate · effort L

**Designate the canon system of record among Notion, veillore.db, 686 md files and NouGenShards**

- Failure surface: Four stores disagree (Notion 2e5ca671, gitignored SQLite, MASTER_CANON_LOCK.md, the shards Xoah ledger); Dave lock 9/10 says vaults are independent evidence, so a contradiction-strict Destiny #2 retrieval will surface four answers for one fact.
- First fork: if you observe shards_recall for 'Kage Tanak acquisition' returns conflicting shards -> route A: shards as truth, md/Notion as derived exports; else route B: Notion stays truth and shards ingest from it with provenance
- Evidence: `MASTER_CANON_LOCK.md`, `services/notion.py`, `VEILVERSE_COMPLETE_CANON.md`
- Lens: canon · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: MASTER_CANON_LOCK.md, services/notion.py (DATABASE_ID 2e5ca671...), and VEILVERSE_COMPLETE_CANON.md all exist as independent canon stores, consistent with the four-way system-of-record conflict described (Notion, gitignored SQLite, locked markdown, and the external shards ledger).
- #550 families: 12

### WG-0158 · P0 · elevate · effort S

**Decide archive-vs-revive and merge authority for a repo idle since 2026-04-30**

- Failure surface: 50 commits, last on 2026-04-30, while the fleet works in shards and handoffs; no branch protection or CODEOWNERS, so any lane can push to main, and nobody knows whether canon fixes belong here or in NouGenShards.
- First fork: if you observe Dave lock names Rhea-Noir as archived -> route A: freeze main, redirect canon to shards; else route B: set up merge rules and a revive plan
- Evidence: `README.md`, `MASTER_CANON_LOCK.md`
- Lens: governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: README.md and MASTER_CANON_LOCK.md exist; repo has exactly 50 commits as claimed, supporting the idle/ungoverned-repo claim.

### WG-0166 · P0 · defend · effort S

**Retire the local planning-with-files ledger that diverges from relay handoffs**

- Failure surface: progress.md, task_plan.md and findings.md carry duplicated entries and contradictory state ('Moltbook Scrapped' while workflows remain), forming a second ledger agents read instead of NouGenRelay .handoffs; two truths about what is done.
- First fork: if you observe any lane still appends to progress.md -> route A: migrate to relay and tombstone files; else route B: delete files
- Evidence: `progress.md`, `task_plan.md`, `findings.md`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: progress.md, task_plan.md, and findings.md all exist as separate root-level tracking files alongside the relay/handoff system, supporting the dual-ledger claim.
- #550 families: 38

### WG-0174 · P0 · defend · effort M

**Converge or kill the second production Rhea deployed to Agent Engine by deploy_cloudshell.sh**

- Failure surface: infra/deploy_cloudshell.sh generates a separate ADK agent (gemini-2.5-flash, coding-assistant persona, tools=[]) and Scripts/utils/deploy_agent.py deploys via SDK; two Rheas answer differently and both bill.
- First fork: if you observe an Agent Engine reasoning engine still listed in endless-duality -> route A: delete it; else route B: remove scripts and document
- Evidence: `infra/deploy_cloudshell.sh`, `Scripts/utils/deploy_agent.py`, `rhea_noir/agent.py`
- Lens: deploy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: All 3 paths exist; infra/deploy_cloudshell.sh literally defines model='gemini-2.5-flash' and tools=[] for a separate ADK agent, directly matching the failure_surface.
- #550 families: 29

### WG-0370 · P1 · defend · effort S

**Remove the committed Google API key in test_extract.py without breaking transcript fetch**

- Failure surface: A literal AIzaSy... Android key is committed at test_extract.py:36 and still tracked; key abuse or quota theft on the endless-duality project. Google or billing alerts notice.
- First fork: if the key is a public InnerTube key -> document as non-secret and delete anyway; else -> rotate in GCP and scrub history
- Evidence: `test_extract.py`
- Lens: secrets · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: test_extract.py:36 has literal AIzaSy... key labeled '# Android key' in tracked HEAD.
- #550 families: 76

### WG-0386 · P1 · elevate · effort L

**Migrate deploy to who-visions-tester without a wrong-project push or lost secrets**

- Failure surface: infra/migrate_to_visions.sh switches gcloud config to who-visions-tester, deploys --source with --allow-unauthenticated, and hard-exits if .env is absent; the service name stays endless-duality-480201-t3 and env var name flips to PROJECT_ID. A half-run leaves two projects serving or a broken secret contract. GM notices split traffic/billing.
- First fork: if the tester project has Secret Manager + service identities wired -> stage a canary deploy and cut over; else -> provision secrets first, park the migration
- Evidence: `infra/migrate_to_visions.sh`, `cloudbuild.yaml`
- Lens: deploy-migration · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: infra/migrate_to_visions.sh sets project who-visions-tester, exits if .env missing, deploys endless-duality-480201-t3 --allow-unauthenticated with PROJECT_ID env; cloudbuild uses GOOGLE_CLOUD_PROJECT default.

### WG-0402 · P1 · defend · effort S

**Cut over the notion-client floor from 5.x claim to a real version that exists**

- Failure surface: requirements.txt pins notion-client>=5.0.0 but the current PyPI release is 3.1.0; the floor can never be satisfied, so a fresh pip install of the image fails outright. First clean Docker build breaks.
- First fork: if any code actually needs 5.x APIs -> confirm they exist on 3.x and lower the floor; else -> pin to 3.1.0
- Evidence: `requirements.txt`, `services/notion.py`
- Lens: supply-chain · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: PyPI notion-client latest is 3.1.0 (checked live); requirements.txt notion-client>=5.0.0 is unsatisfiable.
- #550 families: 77

### WG-0418 · P1 · defend · effort M

**Purge the leaked Vertex API key from git history (commit 40934b2 only redacted HEAD)**

- Failure surface: Commit 40934b2 replaced a live AQ.Ab8... Vertex key with an env var but the secret remains reachable in history at the prior blob; a clone still yields it. Auditor/attacker notices via git log.
- First fork: if the key is still valid when checked -> revoke then filter-repo; else -> filter-repo to shrink exposure
- Evidence: `test_vertex_key.py`
- Lens: secrets · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git show 40934b2 diff removes literal AQ.Ab8... key from test_vertex_key.py; prior blob still in history.
- #550 families: 76

### WG-0434 · P1 · defend · effort L

**Drop --allow-unauthenticated from the Cloud Run deploy without locking out the Flutter client**

- Failure surface: Both cloudbuild.yaml and infra/cloudbuild.yaml deploy endless-duality-480201-t3 with --allow-unauthenticated; every route (chat, generate-image, admin/*, sync, render) is world-callable. Anyone on the internet can burn Gemini spend or trigger renders. Billing notices first.
- First fork: if the mobile/web clients can carry an identity token or X-API-Key -> gate the service and update clients; else -> put Cloud Run behind IAP/API gateway first
- Evidence: `cloudbuild.yaml`, `infra/cloudbuild.yaml`, `rhea_server.py`
- Lens: deploy-auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml:23 and infra/cloudbuild.yaml:28 both pass --allow-unauthenticated for service endless-duality-480201-t3; rhea_server.py has no Depends() auth.

### WG-0450 · P1 · defend · effort M

**Scope down the Google Workspace OAuth token before it ships to a public service**

- Failure surface: google_workspace.py requests full drive, gmail.modify and calendar scopes and loads a long-lived token from /secrets or env; on the --allow-unauthenticated service, any path that reaches workspace_service can read/send the owner's Gmail and Drive. A compromised route becomes account takeover.
- First fork: if only calendar+read is needed -> reduce SCOPES and re-consent; else -> keep scopes but require auth on every workspace route
- Evidence: `services/google_workspace.py`, `rhea_server.py`
- Lens: token-scope · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: services/google_workspace.py SCOPES include full drive, gmail.modify, calendar; cloudbuild.yaml / infra/migrate_to_visions.sh deploy with --allow-unauthenticated.
- #550 families: 76

### WG-0465 · P1 · defend · effort M

**Stop the global exception handlers from masking every error as HTTP 200**

- Failure surface: Four handlers force status_code=200 for all HTTPException/validation/unhandled errors and /health always returns 'healthy'; Cloud Run, watchdogs and clients cannot tell a dead service from a live one. A silent outage goes unnoticed (fleet history: vault quiet 3 days unnoticed).
- First fork: if downstream clients truly parse the {status:error} body -> keep body but restore real status codes on non-health routes; else -> return correct codes everywhere
- Evidence: `rhea_server.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Four @app.exception_handler blocks at rhea_server.py:366-411 all set status_code=200; /health at 567-570 returns healthy unconditionally.

### WG-0478 · P1 · defend · effort M

**Add a Source URL dedup gate so re-ingesting the same YouTube URL doesn't mint duplicate canon**

- Failure surface: ingest_transcript always calls notion.create_entity with Source URL as a property but never checks for an existing page with that URL; every retry, replay or second /api/ingest call creates another page. The repo already carries audit_duplicates.py, merge_duplicates.py and Notion 'Duplicate Of' properties, which is the observed aftermath.
- First fork: if you observe query_veilverse filtered by Source URL returning a hit -> update that page instead of creating, else proceed to create and record the URL in a local ingest ledger.
- Evidence: `services/ingestor.py`, `Scripts/diagnostics/audit_duplicates.py`, `Scripts/maintenance/merge_duplicates.py`
- Lens: dedup · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: services/ingestor.py:158,186 both call notion.create_entity with additional_properties={'Source URL': {...}} directly, with no preceding existence/dedup query visible in the file; Scripts/diagnostics/audit_duplicates.py and Scripts/maintenance/merge_duplicates.py both exist in the repo as the described cleanup tooling.
- #550 families: 8

### WG-0491 · P1 · defend · effort M

**Keep chat memories (memu_*) out of the canon entities table and out of Notion via reconcile_lore**

- Failure surface: ActiveMemoryService.memorize upserts LLM-extracted user facts into entities with notion_id 'memu_<hex>' and the raw interaction as content; search_semantic feeds them into the ingestor's canon context and reconcile_lore.py migrates every entities row into lore_finals for push to Notion, so private chat lands in the shared lore database.
- First fork: if you observe entities WHERE notion_id LIKE 'memu_%' -> move them to a separate memories table and exclude from search_lore/reconcile, else proceed to gate memorize behind an explicit opt-in per caller.
- Evidence: `services/active_memory.py`, `reconcile_lore.py`, `services/ingestor.py`
- Lens: pii · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: active_memory.py memorize() writes notion_id=f'memu_{hex}' rows into entities (services/active_memory.py:219-223); ingestor.py calls memory.search_semantic feeding canon context; reconcile_lore.py migrates all entities rows into lore_finals for Notion push. Evidence matches exactly.

### WG-0503 · P1 · elevate · effort M

**Get a versioned Notion backup: sync_all_databases and dump_loredb write only gitignored *.json**

- Failure surface: sync_all_databases.py dumps 34 databases to data/notion_sync/databases/*.json and dump_loredb.py to loredb_full.json, both excluded by the blanket *.json gitignore, so there is no restorable, dated snapshot anywhere off Dave's disk despite seven archive scripts and lock scripts mutating Notion directly.
- First fork: if you observe no snapshot newer than the last archive-script run -> take one now and store it in GCS with the date, else proceed to a scheduled dump with a checksum manifest and a tracked index.
- Evidence: `Scripts/sync/sync_all_databases.py`, `Scripts/maintenance/dump_loredb.py`, `.gitignore`
- Lens: backup · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Scripts/sync/sync_all_databases.py writes to SYNC_DIR = Path('data/notion_sync/databases') and dump_loredb.py writes loredb_full.json; .gitignore contains a bare '*.json' rule (with a single carve-out for /.well-known/agent.json), so both dumps are excluded from version control as claimed.

### WG-0515 · P1 · defend · effort M

**Coordinate one NOTION_TOKEN across ~200 scripts, the server and watchdog_sync: the governor is per-process**

- Failure surface: NotionGovernor is a module global sized to 3 req/s, but every root script, the Cloud Run server and the 30-second watchdog loop each run their own; against one integration token they collectively exceed Notion's limit, trigger jail states in one process while another keeps hammering, and 429 storms show up as dead-letter growth.
- First fork: if you observe rate_limited climbing in watchdog metrics while a root script is running -> pause the watchdog and finish the script, else proceed to a shared token-bucket (file lock or the shards gateway) or per-lane tokens.
- Evidence: `services/notion.py`, `watchdog_sync.py`, `push_to_notion_finals.py`
- Lens: coordination · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: services/notion.py defines GOVERNOR = NotionGovernor(capacity=3.0, fill_rate=3.0) as a module-level global (3 req/sec, matching Notion's documented limit); watchdog_sync.py and push_to_notion_finals.py are separate processes/scripts that each import services.notion independently, giving each its own governor instance against one shared NOTION_TOKEN.
- #550 families: 63

### WG-0527 · P1 · defend · effort S

**Fix /health that lies: 'Always return healthy to keep Cloud Run alive' while services init failed**

- Failure surface: health_detailed hardcodes status 'healthy' with a comment saying why, and /health does not even consult ServiceManager; a deploy whose _init_background raised keeps serving 200s, routes 503 on lore_memory, and no probe or human sees it.
- First fork: if you observe initialization=='failed' in /health/detailed -> add a /ready that returns 503 until _is_initialized and point the Cloud Run startup probe at it, else proceed to expose init age and error as metrics.
- Evidence: `rhea_server.py`
- Lens: health-lies · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: rhea_server.py:600 literally has status:"healthy", # Always return healthy to keep Cloud Run alive; simple /health at line 568-570 returns healthy unconditionally without consulting ServiceManager.
- #550 families: 95

### WG-0539 · P1 · defend · effort S

**services/universal_schema.py is missing: /v1/ingest and /api/ingest fail at import on every call**

- Failure surface: services/ingestor.py imports UniversalNormalizedObject from services.universal_schema, which does not exist in the tree; both ingest routes import IngestorService inside the handler, so /v1/ingest 500s and /api/ingest returns 'started' then logs a background ImportError nobody reads.
- First fork: if you observe ModuleNotFoundError for services.universal_schema in logs -> restore the module from Dave's machine or re-derive the Pydantic model from _render_to_markdown, else proceed to a CI import-smoke test for every services module.
- Evidence: `services/ingestor.py`, `rhea_server.py`
- Lens: silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: services/ingestor.py:10 imports UniversalNormalizedObject from services.universal_schema; no services/universal_schema.py file exists anywhere in the repo tree.
- #550 families: 30

### WG-0551 · P1 · defend · effort S

**/v1/cowrite/save returns 'saved' and persists nothing: a false done-marker on a public route**

- Failure surface: cowrite_save logs the first 50 chars and returns {'status':'saved'}; Flutter and web clients treat that as durable, so cowriting sessions are lost while the UI shows success, the same false-done pattern HARDENING recorded for embed-at-ingest.
- First fork: if you observe clients calling /v1/cowrite/save in production traffic -> implement storage (Notion page or Firestore doc keyed by session_id) before the next client release, else proceed to return 501 so the client stops trusting it.
- Evidence: `rhea_server.py`
- Lens: false-done · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: rhea_server.py /v1/cowrite/save handler (line ~795-800) logs req.content[:50] and immediately returns {"status": "saved"} with no persistence call.
- #550 families: 100

### WG-0563 · P1 · defend · effort S

**Stop cp1252 emoji prints from crashing Windows scripts before they do any work**

- Failure surface: ingest.log and data/empty_db_verification.txt both end in UnicodeEncodeError from an emoji print on the first line of ensure_schema and verify_empty_databases; the scripts exit before touching Notion, redirected logs are UTF-16 garbage, and a scheduled run would look like a normal exit code.
- First fork: if you observe 'charmap codec can't encode' in any log -> set PYTHONUTF8=1 in the task definitions and wrap console output, else proceed to strip emoji from print paths in services/veil_utils.py and Scripts/diagnostics.
- Evidence: `ingest.log`, `data/empty_db_verification.txt`, `services/veil_utils.py`
- Lens: silent-death · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Both ingest.log and data/empty_db_verification.txt end with 'UnicodeEncodeError: charmap codec can't encode character' tracebacks; services/veil_utils.py contains emoji characters (🧠, ⚠) in print statements.

### WG-0575 · P1 · elevate · effort S

**Purge ~80 committed scratch outputs and UTF-16 logs and stop new ones landing in git**

- Failure surface: debug_log*.txt, restore_error.txt, expand_retry.log, exhaustive_*_results.txt and data/logs dumps are tracked (several UTF-16 with BOMs); they ship in the Docker image, pollute grep and shard ingestion as knowledge, and the pattern means real failure evidence is scattered across throwaway files nobody reads.
- First fork: if you observe any of these files referenced by a script -> move the data under logs/ (dockerignored) and fix the reference, else proceed to git rm plus .gitignore rules for *.log and *_out.txt.
- Evidence: `restore_error.txt`, `expand_retry.log`, `debug_log.txt`
- Lens: logs · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: `file` confirms restore_error.txt, expand_retry.log and debug_log.txt are all UTF-16 little-endian text; repo root also has many other debug_log_*.txt/exhaustive_*_results.txt scratch files tracked alongside them.

### WG-0586 · P1 · defend · effort S

**Track real token spend: chat cost tracking writes len//4 and a constant 500 output tokens to Firestore**

- Failure surface: After every chat the server schedules firebase.track_usage_cost with input_tokens=len(text)//4 and output_tokens=500 regardless of model or thinking level; the Firestore spend ledger drifts from reality and cannot catch the ~$150/day pattern the fleet already hit, while the Fable-to-API cutover makes accuracy matter.
- First fork: if you observe usage_metadata on the Gemini response -> record those counts and reconcile Firestore against the GCP billing export weekly, else proceed to mark the ledger as estimate-only in tracker_spend.
- Evidence: `rhea_server.py`, `services/firebase.py`
- Lens: metrics-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: rhea_server.py:752-753 has input_tokens = len(last_msg_text) // 4 and output_tokens = 500 (hardcoded), then passes both into firebase.track_usage_cost as a background task.
- #550 families: 65

### WG-0597 · P1 · elevate · effort S

**Reconcile the two Dockerfiles before Cloud Build picks infra/Dockerfile that runs a nonexistent app:app**

- Failure surface: Root Dockerfile runs rhea_server:app with ffmpeg and STATIC_PATH; infra/Dockerfile runs uvicorn app:app, which does not exist, and infra/cloudbuild.yaml is a near-copy of the root one; a trigger pointed at infra/ builds fine and crash-loops at runtime with the health probe passing on the previous revision.
- First fork: if you observe the Cloud Build trigger configured with infra/ as build root -> delete infra/Dockerfile and point the trigger at root, else proceed to make infra/ a symlink-free single source and add a container smoke test.
- Evidence: `infra/Dockerfile`, `Dockerfile`, `infra/cloudbuild.yaml`
- Lens: deploy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: infra/Dockerfile:19 CMD is uvicorn app:app (no app.py module exists in infra/), while root Dockerfile:34 correctly runs uvicorn rhea_server:app; both cloudbuild.yaml files exist confirming duplication.

### WG-0608 · P1 · defend · effort M

**Rescue TRIPLE-LOCKED timeline tables that exist only in a gitignored SQLite on one Windows box**

- Failure surface: finalize_canon_v3_5.py and normalize_canon_v3_1.py write the canon spine (timeline_locked, career_phases, vol1_cast) straight into veillore.db, which .gitignore excludes and no script dumps; MASTER_CANON_LOCK.md is the only other copy and it is dated Feb 2026. One disk failure on Dave's machine loses the locked state.
- First fork: if you observe timeline_locked rows that disagree with MASTER_CANON_LOCK.md -> freeze both, adjudicate under a Dave lock, then export, else proceed to export those tables to tracked JSONL/markdown and re-derive the DB from them.
- Evidence: `finalize_canon_v3_5.py`, `normalize_canon_v3_1.py`, `MASTER_CANON_LOCK.md`
- Lens: backup · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: finalize_canon_v3_5.py:4,9,27,44 connects to veillore.db, creates/writes timeline_locked and updates vol1_cast; normalize_canon_v3_1.py:4,13,29 connects to the same db and creates career_phases; both write straight into a *.db file that .dockerignore/.gitignore treat as excluded/local-only, and MASTER_CANON_LOCK.md is dated Feb 11 2026 as the only markdown mirror.
- #550 families: 12

### WG-0619 · P1 · elevate · effort M

**Restore submodule resolvability: 20 gitlinks with no .gitmodules, Gemma4Core dir absent from tree**

- Failure surface: git ls-files -s shows 160000 entries for notion-mcp-server, temp_memu, temp_stitch_skills, awesome-nanobanana-pro, .agent/tools/gsd and 13 resources/* but no .gitmodules exists, so fresh clones and Cloud Build get empty directories, the last commit's 'stabilize Gemma4Core' refers to a path that is not tracked, and the scout's photoreal pipeline is unreachable.
- First fork: if you observe git submodule status listing entries with no URL -> reconstruct .gitmodules from Dave's local .git/config or convert each to a vendored copy, else proceed to drop the dead gitlinks.
- Evidence: `notion-mcp-server`, `temp_memu`, `.agent/tools/gsd`
- Lens: repo-integrity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git ls-files -s shows exactly 20 mode-160000 gitlink entries (notion-mcp-server, temp_memu, .agent/tools/gsd, awesome-nanobanana-pro, 13 resources/*, .agent/skills/planning-with-files, Reproducible-Photorealistic-..., temp_banana_prompts, temp_stitch_skills) and no .gitmodules file exists in the repo root.
- #550 families: 35, 36

### WG-0630 · P1 · elevate · effort L

**Implement the Veil Ghost contradiction audit in code instead of 'manual review recommended'**

- Failure surface: CANON_GOVERNANCE_RULES.md mandates flag-don't-overwrite for PRIME/CORE contradictions, but veilverse_tools.check_contradiction returns a note that it 'requires RAG backend'; ingestion and lock scripts overwrite Description fields freely, so the strict contradiction resolution Destiny #2 needs has no enforcement point.
- First fork: if you observe an incoming entity whose timeline_year conflicts with timeline_locked for the same name -> write it as canon_status=Contradicted and never update the original, else proceed to a similarity-based check against Canon Locked pages before any create/update.
- Evidence: `services/veilverse_tools.py`, `CANON_GOVERNANCE_RULES.md`, `models/veilverse.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: services/veilverse_tools.py:89 literally returns note: 'Automated contradiction check requires RAG backend. Manual review recommended for now.' inside check_contradiction (line 57); CANON_GOVERNANCE_RULES.md and models/veilverse.py both exist as supporting evidence.

### WG-0641 · P1 · defend · effort S

**Audit the always-on 'rhea-noir' Cloud Run service (minScale 1, 4Gi, maxScale 20) for zombie spend**

- Failure surface: rhea_run_config.yaml shows a third project (rhea-noir, ns 145241643240) with minScale 1 and 2 vCPU/4Gi; a stale service from Dec 2025 may still bill every hour while nobody calls it.
- First fork: if you observe the rhea-noir project still has the service revision serving -> route A: scale to zero / delete; else route B: purge the yaml and record the retirement
- Evidence: `rhea_run_config.yaml`
- Lens: cost · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: rhea_run_config.yaml (UTF-16) shows name: rhea-noir, namespace: '145241643240' (line 21), autoscaling minScale '1' / maxScale '20' (lines 26-27), cpu 2000m / memory 4Gi (lines 54-55) -- matches the claim's specifics exactly.
- #550 families: 65

### WG-0652 · P1 · elevate · effort L

**Finish the who-visions-tester tenant migration without a wrong-project deploy**

- Failure surface: cloudbuild.yaml deploys to endless-duality-480201-t3, infra/migrate_to_visions.sh sets who-visions-tester, rhea_run_config.yaml is project rhea-noir; PROJECT_ID vs GOOGLE_CLOUD_PROJECT env names differ, so the same code can land in three projects with different IAM and secrets.
- First fork: if you observe gcloud config on the deploying machine already points at who-visions-tester -> route A: retire old projects and single-source the project ID; else route B: gate every deploy script on an explicit --project check
- Evidence: `cloudbuild.yaml`, `infra/migrate_to_visions.sh`, `rhea_run_config.yaml`
- Lens: deploy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml deploys service 'endless-duality-480201-t3' with GOOGLE_CLOUD_PROJECT=$PROJECT_ID; infra/migrate_to_visions.sh sets `gcloud config set project who-visions-tester` and `--set-env-vars PROJECT_ID=who-visions-tester`; rhea_run_config.yaml is a separate project 'rhea-noir' (ns 145241643240) -- three distinct projects/env-var names confirmed.

### WG-0663 · P1 · defend · effort M

**Stop each Cloud Run instance starting its own Slack socket-mode bot**

- Failure surface: rhea_server lifespan and _init_background both create_task(slack_service.start()); with maxScale 20 every instance opens a socket-mode connection and each @mention gets N replies, and Slack rate-limits the app.
- First fork: if you observe duplicate replies in Slack history -> route A: move the bot to a single-instance worker; else route B: gate on an env flag only set on one revision
- Evidence: `rhea_server.py`, `services/slack_bot.py`, `rhea_run_config.yaml`
- Lens: product · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: rhea_server.py calls asyncio.create_task(self.slack_service.start()) in both _init_background (line 275) and lifespan (line 327); services/slack_bot.py uses AsyncSocketModeHandler; rhea_run_config.yaml confirms maxScale '20'.
- #550 families: 29

### WG-0674 · P1 · defend · effort S

**Remove the committed venv Scripts/*.exe without breaking tests that import Scripts/gemma4_core**

- Failure surface: 23 Windows .exe (pip.exe, uvicorn.exe, pyrsa-*.exe) are tracked and documented in Scripts/README.md; tests/test_gemma4_core.py sys.path-inserts Scripts/, so Scripts is simultaneously a venv bin dir and a source package.
- First fork: if you observe any script shells out to Scripts/*.exe -> route A: rename package to scripts_src and fix imports; else route B: git rm the exes and add a .gitignore rule
- Evidence: `Scripts/README.md`, `tests/test_gemma4_core.py`
- Lens: ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Scripts/README.md documents distro.exe, dotenv.exe, pip.exe, etc. as tracked files in Scripts/; Scripts/ directory contains 20+ .exe files (pip.exe, uvicorn.exe, pyrsa-*.exe, etc.); tests/test_gemma4_core.py inserts SCRIPTS_DIR onto sys.path and imports gemma4_core from Scripts/, confirming Scripts is used as both a venv bin dir and a source package.

### WG-0685 · P1 · defend · effort M

**Reconcile .gitignore '*.json' with data/README.md and the JSON state files the pipeline needs**

- Failure surface: data/README.md documents backfill_progress.json, loredb_full.json etc. that do not exist in git; migration_v3.json progress and rhea_noir/.agent_engine_config.json are silently ignored, so a fresh clone restarts migrations from zero and re-writes Notion pages.
- First fork: if you observe migration_v3.json on blade with done>0 -> route A: commit progress files as tracked state; else route B: move state to GCS and update README
- Evidence: `.gitignore`, `data/README.md`, `Scripts/corrected_migration.py`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: data/README.md documents backfill_progress.json, loredb_full.json, etc.; .gitignore line 13 has a blanket `*.json` rule; migration_v3.json and rhea_noir/.agent_engine_config.json do not exist anywhere in the current checkout, consistent with being gitignored/untracked state files.

### WG-0696 · P1 · defend · effort S

**Cure UTF-16 contamination in .gitignore and rhea_run_config.yaml before Linux CI reads them**

- Failure surface: .gitignore contains a UTF-16 mangled 'f i r e b a s e - s e r v i c e - a c c o u n t . j s o n' line and rhea_run_config.yaml is UTF-16 with BOM; yaml parsers and grep on linux nodes fail, and the firebase ignore rule is not actually applied.
- First fork: if you observe firebase-service-account.json in git history -> route A: purge + rotate SA key; else route B: normalize encodings and add a pre-commit encoding check
- Evidence: `.gitignore`, `rhea_run_config.yaml`
- Lens: ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .gitignore contains a visibly space-separated 'f i r e b a s e - s e r v i c e - a c c o u n t . j s o n' line (UTF-16 mangling artifact) among otherwise normal lines; `file` on rhea_run_config.yaml reports 'Unicode text, UTF-16, little-endian text, with CRLF line terminators'.
- #550 families: 36

### WG-0707 · P1 · defend · effort M

**Restore .gitmodules for 20 orphaned gitlinks or convert them to vendored/pinned deps**

- Failure surface: 20 gitlinks (nano-banana prompt libs, notion-mcp-server, .agent/skills/planning-with-files, 13 resources/*) exist with no .gitmodules; fresh clones and Cloud Build get empty directories, so prompt libraries and the MCP bridge silently vanish.
- First fork: if you observe the upstream URLs are recoverable from blade's .git/config -> route A: write .gitmodules and pin; else route B: drop gitlinks and vendor the few files actually imported
- Evidence: `Reproducible-Photorealistic-Nano-Banana-Pro-JSON-Prompts`, `notion-mcp-server`, `.agent/skills/planning-with-files`
- Lens: ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: `git ls-files -s | grep ^160000` lists 20 gitlink entries (Reproducible-Photorealistic-Nano-Banana-Pro-JSON-Prompts, notion-mcp-server, .agent/skills/planning-with-files, 13 resources/*, plus awesome-nanobanana-pro/temp_banana_prompts/temp_memu/temp_stitch_skills) and no .gitmodules file exists in the repo root.

### WG-0718 · P1 · elevate · effort L

**Take rhea_mobile_command from com.example scaffold to a shippable build**

- Failure surface: applicationId is com.example.rhea_mobile_command, README is the Flutter boilerplate, base URL defaults to localhost:8080 while settings UI says 8081; a store or TestFlight submission is rejected and testers hit a dead server.
- First fork: if you observe a Play/App Store listing already reserved for Who Visions -> route A: rename package and wire prod URL; else route B: internal APK lane only, fix URL config
- Evidence: `rhea_mobile_command/android/app/build.gradle`, `rhea_mobile_command/lib/main.dart`, `rhea_mobile_command/README.md`
- Lens: ux · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: rhea_mobile_command/android/app/build.gradle sets applicationId = 'com.example.rhea_mobile_command' (line 24); rhea_mobile_command/README.md is the unedited Flutter boilerplate ('A new Flutter project.'); main.dart defaults kBridgeUrl-style constant to http://localhost:8080 (line 43) while a UI subtitle elsewhere in main.dart says 'localhost:8081' (line 1757), and settings_view.dart also shows bot

### WG-0729 · P1 · defend · effort S

**Reconcile the port topology across README, start_servers.ps1, findings.md and code**

- Failure surface: README says bridge :8081, start_servers.ps1 launches rhea_server 'on 8081' and bridge 'on 8000', findings.md says 8081 via 8000, code binds rhea_server 8080 and bridge 8082; a new operator follows docs and nothing connects.
- First fork: if you observe the Flutter settings screen lets users edit the URL -> route A: fix docs to 8080/8082; else route B: add a single ports config consumed by all launchers
- Evidence: `README.md`, `start_servers.ps1`, `rhea_bridge_server.py`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: README.md shows FastAPI @ :8081 (line 60) and API docs link at localhost:8081/docs (line 134); start_servers.ps1 says 'Starting Rhea Logic Server (Port 8081)' and 'Starting Rhea Bridge Server (Port 8000)'; findings.md line 6 says mobile app connects to localhost:8081 via localhost:8000; but rhea_server.py's own default PORT env is 8080 and rhea_bridge_server.py hardcodes PORT = 8082 (line 10) -- f
- #550 families: 38

### WG-0739 · P1 · elevate · effort M

**Unify the three Rhea personas served on public surfaces**

- Failure surface: rhea_noir/persona.py PRIME_DIRECTIVE is a 23-year-old cosplay content creator, rhea_server Config.RHEA_NOIR_INSTRUCTION is 'Command & Control for Watchtower', infra/deploy_cloudshell.sh deploys an 'AI coding assistant'; Slack, mobile and Agent Engine users meet different characters.
- First fork: if you observe web/app.py and rhea_server both import get_system_prompt -> route A: make persona.py the single source and delete inline strings; else route B: pick per-surface modes explicitly in persona.py
- Evidence: `rhea_noir/persona.py`, `rhea_server.py`, `infra/deploy_cloudshell.sh`
- Lens: brand · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: persona.py PRIME_DIRECTIVE (line 16) is the cosplay-creator persona; rhea_server.py Config.RHEA_NOIR_INSTRUCTION (line 62-63) is the Watchtower C&C persona; infra/deploy_cloudshell.sh line 32 describes an 'AI coding assistant'. Three distinct personas confirmed across the three cited files.

### WG-0749 · P1 · defend · effort M

**Gate /v1/ingest and /api/ingest, which write straight into the live VeilVerse Notion DB**

- Failure surface: Both routes are unauthenticated and call services/ingestor.py which creates pages in DATABASE_ID 2e5ca671-311e-811f-b3d7-c7f3b9150afe; a stranger or a runaway agent can inject non-canon entries that later get scored and promoted.
- First fork: if you observe pages in the master DB with unknown creators in the last 90 days -> route A: quarantine + gate; else route B: gate and add an 'ingested_by' property
- Evidence: `rhea_server.py`, `services/ingestor.py`, `services/notion.py`
- Lens: canon · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: rhea_server.py has @app.post('/v1/ingest') (line 1327) and @app.post('/api/ingest') (line 1601); services/notion.py DATABASE_ID = '2e5ca671-311e-811f-b3d7-c7f3b9150afe' (line 89) matches exactly the DB cited.
- #550 families: 34

### WG-0759 · P1 · defend · effort M

**Decide attribution and SSL policy before scraping 8,000 Samurai Archives articles into veillore.db**

- Failure surface: wiki_ingestion_plan.md plans verify=False scraping and Scripts/ingest/samurai_scraper.py already does it; scraped wikitext lands in canon without license or source fields, and MITM on an unverified TLS session can poison lore.
- First fork: if you observe samurai-archives content already in veillore.db or Notion -> route A: add source/license properties retroactively; else route B: pin cert fingerprint and add provenance before first run
- Evidence: `wiki_ingestion_plan.md`, `Scripts/ingest/samurai_scraper.py`
- Lens: licensing · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: wiki_ingestion_plan.md line 8 states 'Bypasses SSL verification (verify=False)'; Scripts/ingest/samurai_scraper.py lines 38 and 70 both call requests.get(..., verify=False), confirming the plan is already implemented in code.

### WG-0769 · P1 · defend · effort M

**Bring README claims (LICENSE, scripts/, rhea_noir_cli.py, Pylint 9.5) back to parity with the tree**

- Failure surface: README links a LICENSE that does not exist, cites scripts/ingestion and scripts/visuals (real dir is Scripts/), rhea_noir_cli.py (absent) and Pylint scores nobody can reproduce; agents under user-authority follow it and fail.
- First fork: if you observe pylint actually runs clean on rhea_noir today -> route A: regenerate README from the tree; else route B: strip claims and add a truthful status section
- Evidence: `README.md`, `Scripts/README.md`, `rhea_cli.py`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: README.md line 18 links a LICENSE badge but no LICENSE file exists in the repo; README references scripts/ingestion and scripts/visuals (lines 273-274, 294, 299) while the real directory is capitalized 'Scripts/'; rhea_noir_cli.py is referenced (line 289) but does not exist (only rhea_cli.py does); Pylint 9.5+ badge and claims (lines 17, 268) cannot be verified. All drift points confirmed.

### WG-0779 · P1 · elevate · effort M

**Stand up first CI on a 3125-file, 2GB repo with missing deps and broken submodules**

- Failure surface: No .github/workflows exist; watchdog, tqdm, bs4 and functions-framework are imported but absent from requirements.txt, submodules cannot init, and checkout alone may exceed runner disk; the first green pipeline will be a lie unless scoped.
- First fork: if you observe a shallow clone without assets stays under 500MB -> route A: sparse checkout CI on rhea_noir/ services/ tests/; else route B: asset purge first
- Evidence: `requirements.txt`, `services/sync_engine.py`, `lore_keeper.py`
- Lens: ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: No .github/workflows directory exists in the repo; grep of requirements.txt shows no watchdog, tqdm, bs4/beautifulsoup, or functions-framework entries, while functions/youtube_transcript/main.py, Scripts/corrected_migration.py, Scripts/ingest/debug_html.py, and rhea_noir/skills/movies/actions.py import at least one of these, confirming the missing-dependency claim.

### WG-0789 · P1 · defend · effort S

**Merge the Corbin Varas / Corbin Veras identity split across 19 canon docs**

- Failure surface: CORBIN_VARAS_PROFILE.md and CORBIN_VERAS_LOGIC.md coexist; 3 docs use Veras, 16 use Varas, and TIMELINE_v3_1 uses Veras; entity extraction (rhea_canon_validator NAME_PATTERN) creates two anchor nodes and retrieval splits importance scores.
- First fork: if you observe Notion has two Corbin pages -> route A: merge pages then fix docs; else route B: sed the docs and add a validator alias table
- Evidence: `CORBIN_VARAS_PROFILE.md`, `CORBIN_VERAS_LOGIC.md`, `rhea_canon_validator.py`
- Lens: canon · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Both CORBIN_VARAS_PROFILE.md and CORBIN_VERAS_LOGIC.md exist as separate files; grep across *.md shows 16 files containing 'Corbin Varas' vs 2 containing 'Corbin Veras', confirming the spelling split; rhea_canon_validator.py contains a NAME_PATTERN regex (line 10) that would extract these as separate name strings.

### WG-0799 · P1 · defend · effort M

**Pick one Amon purge policy: consolidated_sanitizer DELETEs, SCRIBE_MANDATE says SCRUB not delete**

- Failure surface: consolidated_sanitizer.py deletes 'Amon' entities from veillore.db while SCRIBE_MANDATE.md (verified by Dav3) forbids deleting pages and requires replacing with Yasuke; agents obeying the code destroy Yasuke backstory the mandate protects.
- First fork: if you observe entities named Amon still in the DB -> route A: run scrub per mandate and retire the sanitizer; else route B: sanitizer already ran, audit what was lost against the jsonl export
- Evidence: `consolidated_sanitizer.py`, `SCRIBE_MANDATE.md`, `CANON_PROPOSALS.md`
- Lens: canon · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: consolidated_sanitizer.py lines 17-19 run 'DELETE FROM entities WHERE name LIKE %Amon (Yasuke%...' etc., confirming deletion; SCRIBE_MANDATE.md lines 6-7 explicitly forbid deleting Amon pages and require SCRUB-and-replace with Yasuke instead. Direct policy contradiction confirmed in code vs. doc.
- #550 families: 11

### WG-0809 · P1 · elevate · effort L

**Finish the Universe_LoreBase -> new Notion DB migration (corrected_migration v3) without duplicating pages**

- Failure surface: Scripts/corrected_migration.py copies DB 2e5ca671 to 34ee56f0 under a different token with progress in gitignored migration_v3.json; every service still points at the old ID, so a half-migrated target and a live source diverge and reruns re-create pages.
- First fork: if you observe target DB page count < source -> route A: resume with progress file and dedupe by title; else route B: flip NOTION_DB_ID in services and freeze the source
- Evidence: `Scripts/corrected_migration.py`, `services/notion.py`
- Lens: canon · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Scripts/corrected_migration.py lines 10-13 define SOURCE_DB='2e5ca671311e811fb3d7c7f3b9150afe', TARGET_DB='34ee56f0-6927-809b-9480-f7fd6ca6e494', and PROGRESS='migration_v3.json', confirming the exact DB IDs and progress-file mechanism described; services/notion.py still defaults to the source DB ID.
- #550 families: 8

### WG-0819 · P1 · defend · effort M

**Run sync_master_to_registries fan-out once without spawning the duplicates merge_duplicates.py cannot fix**

- Failure surface: sync_master_to_registries.py pushes master pages into three registries (CHR/LOC/FAC) against a 350-property schema; Scripts/maintenance/merge_duplicates.py still has 'TODO: Update canonical page with merged content', so a rerun creates duplicates no tool can merge.
- First fork: if you observe duplicate_audit output shows >0 dupes today -> route A: finish merge tool first; else route B: add idempotency key (master page id) before any sync
- Evidence: `sync_master_to_registries.py`, `Scripts/maintenance/merge_duplicates.py`, `services/registry_schema.py`
- Lens: canon · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: sync_master_to_registries.py lines 10-12 define CHR_REG_ID/LOC_REG_ID/FAC_REG_ID and lines 166-167 sync CHARACTER/LOCATION categories into them; Scripts/maintenance/merge_duplicates.py line 75 contains the literal comment '# TODO: Update canonical page with merged content', confirming the unfinished merge tool.
- #550 families: 8, 16

### WG-0829 · P1 · defend · effort M

**Stop ChatGPT-archive ingestion until the 14 conflicts in CANON_CROSSREF_REPORT get a GM ruling**

- Failure surface: CANON_CROSSREF_REPORT.md (2026-02-04) lists 14 conflicts and 16 missing items 'resolve before ingesting', CANON_RECONCILIATION is 'PENDING REVIEW', yet services/chatgpt_sync.py and crossref_chatgpt_canon.py can run unattended and promote old lore.
- First fork: if you observe chatgpt_sync has written rows after 2026-02-04 -> route A: diff and quarantine; else route B: gate the sync behind a resolved-conflicts checklist
- Evidence: `CANON_CROSSREF_REPORT.md`, `CANON_RECONCILIATION_CHATGPT_VS_2026.md`, `services/chatgpt_sync.py`
- Lens: governance · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: CANON_CROSSREF_REPORT.md (dated 2026-02-04) states '🚨 Conflicts: 14 (Resolve before ingesting)' and '❌ Missing: 16 (Safe to add)'; CANON_RECONCILIATION_CHATGPT_VS_2026.md line 5 states 'Status: PENDING REVIEW'; services/chatgpt_sync.py and crossref_chatgpt_canon.py both exist and are runnable. All specifics confirmed exactly.

### WG-0839 · P1 · defend · effort M

**Survive the Notion integration losing database access again (notion_schema_map: 'No Databases Found')**

- Failure surface: notion_schema_map.md records a scan where the token saw pages but no databases; NotionService falls back to hardcoded IDs and most scripts assume access, so a share revocation or token rotation turns every ingest into silent 404s.
- First fork: if you observe /health/detailed notion=true is derived from getattr default True -> route A: make the check hit the DB; else route B: add a startup DB-access probe with alert
- Evidence: `notion_schema_map.md`, `services/notion.py`, `rhea_server.py`
- Lens: product · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: notion_schema_map.md line 3 heading is literally '## Accessible Pages (No Databases Found)', confirming the scan result; rhea_server.py line 586 shows 'notion_active = getattr(services.lore_memory, "is_connected", True)', confirming the default-True health-check fallback described.
- #550 families: 6

### WG-0849 · P1 · defend · effort M

**Finish the Notion API data_source migration spread across three API versions**

- Failure surface: Commit cf2bab2 moved to Notion-Version 2025-09-03, corrected_migration.py pins 2026-03-11, services/notion.py mixes database_id and data_source IDs; a version sunset breaks queries in only some scripts.
- First fork: if you observe raw httpx calls with older Notion-Version headers in root scripts -> route A: centralize the header in NotionService; else route B: pin one version repo-wide
- Evidence: `services/notion.py`, `Scripts/corrected_migration.py`
- Lens: product · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git log shows commit cf2bab2 'Upgrade Notion integration to 2025-09-03 API'; services/notion.py mixes 'Notion-Version 2025-09-03' commentary (line 86) with NOTION_VERSION = '2026-03-11' (line 90) actually sent in headers, and Scripts/corrected_migration.py is a separate script also touching Notion IDs, confirming version fragmentation across files as described.
- #550 families: 32

### WG-0859 · P1 · elevate · effort M

**Launch the public VeilVerse Nexus wiki without leaking PRIME-locked canon and Act III spoilers**

- Failure surface: 27 wiki_templates plus TEMPLATE_22_WIKI_HOME and ingest_templates_to_notion.py scaffold a public wiki, but MASTER_CANON_LOCK says 'Shadow Blade' is never spoken until Act III; template ingestion has no canon-status filter.
- First fork: if you observe Notion pages carry a Canon Status property (CanonStatus in models/veilverse.py) -> route A: publish only CORE/atmospheric; else route B: add the property before ingest
- Evidence: `wiki_templates/TEMPLATE_22_WIKI_HOME.md`, `ingest_templates_to_notion.py`, `MASTER_CANON_LOCK.md`
- Lens: product · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: All 3 paths exist; ingest_templates_to_notion.py hardcodes CanonStatus.CANON_LOCKED for every template with no check against MASTER_CANON_LOCK spoiler rules (e.g. Shadow Blade line), confirming no canon-status filter despite the property existing in models/veilverse.py.
- #550 families: 75

### WG-0869 · P1 · defend · effort S

**Reconcile the user-authority skill (follow docs EXACTLY) with Rule 0.1 when the docs are wrong**

- Failure surface: .agent/skills/core/user-authority (priority 100) orders agents to follow user documentation exactly, but README paths, ports and TIMELINE_v3_1 are wrong; agents propagate stale docs into code and canon instead of fighting the mission on paper first.
- First fork: if you observe agents cite user-authority in handoffs when overriding evidence -> route A: amend skill with an evidence-conflict clause; else route B: lower priority below doctrine
- Evidence: `.agent/skills/core/user-authority/SKILL.md`, `README.md`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Both files exist; did not verify specific wrong paths/ports/TIMELINE_v3_1 claims in README.md but the doctrine tension (user-authority vs Rule 0.1) is a reasonable inference from the skill file.

### WG-0879 · P1 · defend · effort S

**Stop committing runtime logs (lore_keeper.log, ingest.log, expand_retry.log) that carry Notion content**

- Failure surface: Six *.log files plus dozens of debug_log*.txt captures are tracked; lore_keeper.py appends page content and IDs to lore_keeper.log, so every push adds canon text and workspace IDs to history.
- First fork: if you observe any log contains page titles under PRIME lock -> route A: purge from history; else route B: git rm and ignore *.log
- Evidence: `lore_keeper.log`, `lore_keeper.py`, `debug_log.txt`
- Lens: privacy · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: lore_keeper.log, lore_keeper.py, and debug_log.txt all exist as tracked files; lore_keeper.py pushes page content to Notion and logs, consistent with committed logs carrying canon text.
- #550 families: 75

### WG-0889 · P1 · defend · effort M

**Make LoreDB sync runnable on Linux nodes, not only via sync_lore.bat and venv\Scripts\python.exe**

- Failure surface: sync_lore.bat hardcodes a Windows venv path and services/sync_engine.py needs the missing env_loader; the only sync trigger besides that is the unauthenticated /sync route, so phoebus/whoart cannot sync safely.
- First fork: if you observe env_loader exists on blade -> route A: commit it and add a python -m entrypoint; else route B: rewrite sync_engine to use python-dotenv
- Evidence: `sync_lore.bat`, `services/sync_engine.py`
- Lens: ci · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: sync_lore.bat and services/sync_engine.py exist; sync_engine.py does 'import env_loader' / 'env_loader.load_nexus_env()' and no env_loader.py module was found anywhere in the repo, confirming the missing-dependency claim.

### WG-0898 · P1 · defend · effort M

**Decide whether GEMINI_API_KEY_FALLBACK 429-pivoting crosses a provider billing boundary**

- Failure surface: Router and batch API rotate between primary/fallback keys and regional/global clients on 429 with 30s exponential backoff; if keys belong to different projects or a free tier, quota evasion and untracked spend land on the wrong account.
- First fork: if you observe the two keys map to different GCP projects -> route A: single project, remove pivot; else route B: keep pivot but tag usage by key in track_usage_cost
- Evidence: `rhea_noir/gemini3_router.py`
- Lens: cost · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: rhea_noir/gemini3_router.py reads GEMINI_API_KEY_FALLBACK (line 183) into a second client, rotates across [_client_global, _client_fallback, _client_regional] on 429/exhausted/quota errors with a 30s*2^attempt backoff (lines 266-300), and the batch path also pivots keys on 429 (lines 318-341).
- #550 families: 57, 58
