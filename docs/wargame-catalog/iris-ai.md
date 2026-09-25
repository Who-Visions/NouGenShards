# War-game candidates — Iris-Ai

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

12 candidates · P0 4 · P1 8 · P2 0 · P3 0 · defend 7 · elevate 5

| id | P | kind | title |
|---|---|---|---|
| WG-0012 | P0 | defend | Reconcile the three GCP identities and repoint every fleet caller at the live Iris URL |
| WG-0028 | P0 | defend | Re-apply generation rate limiting lost in df074bc before the next quota incident |
| WG-0043 | P0 | elevate | Decide Iris-Ai revival or retirement and fix the Iris-Vortex identity in README |
| WG-0057 | P0 | defend | Bring iris-agent-service /health back from 500/503 so the fleet roster reads ONLINE |
| WG-0374 | P1 | defend | Kill /personal-finances/stats before the next Cloud Run deploy of the tax hub path |
| WG-0390 | P1 | defend | Ship the Iris container without uploading the Watchtower working tree to Cloud Build |
| WG-0406 | P1 | elevate | Gate revived /web and /ingest behind the fleet ingest-junk-gate and capture-secret-guard rules |
| WG-0422 | P1 | elevate | Put auth on iris-agent-service without breaking Kaedra and Visions-ai fleet probes |
| WG-0438 | P1 | elevate | Restore the A2A agent card and OpenAI-compat endpoints the README and fleet still expect |
| WG-0454 | P1 | elevate | Normalize CRLF/LF with .gitattributes so future diffs are reviewable |
| WG-0469 | P1 | defend | Survive a scrape of unauthenticated /chat on gemini-3.1-pro with thinking=high |
| WG-0482 | P1 | defend | Verify git history carries no finance or tax records and document the finding for the fleet |

---

### WG-0012 · P0 · defend · effort M

**Reconcile the three GCP identities and repoint every fleet caller at the live Iris URL**

- Failure surface: Code and deploy.py use mineral-subject-487519-v6 / project number 885670388176 / engine 1834147023339651072; README advertises https://iris-agent-618147264860.us-central1.run.app and engine 7439808045950959616; bigquery_store uses iris-ai-481105. Visions-ai/tools/agent_connect.py:24 and neural_council.py:85 call the 618147264860 URL and Kaedra's probe uses a fabricated https://mineral-subject-487519-v6.us-central1.run.app, so at most one caller can be right.
- First fork: if you observe `gcloud run services describe iris-agent-service --project mineral-subject-487519-v6` returns a URL -> that is canonical; update README, the two Visions-ai tools and Kaedra's probe in one sweep; else -> the service does not exist and the deploy mission comes first
- Evidence: `README.md`, `deploy.py`, `db/bigquery_store.py`
- Lens: infra/config drift · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py/deploy.py/iris_adk_agent default to project mineral-subject-487519-v6, project number 885670388176, engine 1834147023339651072; README.md advertises https://iris-agent-618147264860.us-central1.run.app and reasoningEngines/7439808045950959616; db/bigquery_store.py defaults to project iris-ai-481105; Visions-ai/tools/agent_connect.py:24 and neural_council.py:85 hardcode the 618147264860 URL

### WG-0028 · P0 · defend · effort M

**Re-apply generation rate limiting lost in df074bc before the next quota incident**

- Failure surface: rate_limiter.py was 'created to comply with Google Cloud ToS after project reinstatement' and 65b0c1a applied GEMINI_LIMITER plus backoff around every generate; df074bc removed all of it from agent.py and iris_adk_agent never had it. Only embeddings are limited now, so the exact condition that got the project suspended is back.
- First fork: if you observe 429/RESOURCE_EXHAUSTED in Cloud Run logs since 09-16 -> wire with_retry_async + GEMINI_LIMITER into agent.chat and the ADK tools immediately; else -> wire it anyway and add a quota-usage alert on the project
- Evidence: `rate_limiter.py`, `agent.py`, `iris_adk_agent/agent.py`
- Lens: quota/compliance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: rate_limiter.py docstring: 'Created to comply with Google Cloud ToS after project reinstatement'; defines GEMINI_LIMITER (line 296) and EMBEDDING_LIMITER. grep for 'limiter'/'GEMINI_LIMITER'/'with_retry' in agent.py and iris_adk_agent/agent.py returns zero hits -- neither wires it in. Only embeddings.py imports rate_limiter constructs. git show df074bc --stat confirms agent.py and rate_limiter.py 
- #550 families: 57

### WG-0043 · P0 · elevate · effort M

**Decide Iris-Ai revival or retirement and fix the Iris-Vortex identity in README**

- Failure surface: Fifteen commits, all Dec 2025 except two on 2026-09-16 after a nine-month gap; README links github.com/Who-Visions/Iris-Vortex which does not exist (GitHub search shows only Iris-Ai), declares MIT with public socials on a private repo, and describes a project structure that no longer matches. No CLAUDE.md, no issues, no PRs; the next agent cannot tell what Iris is for.
- First fork: if you observe Dave confirms Iris is the tax hub + fleet Gemini lane -> write CLAUDE.md, fix README identity/links, and open the backlog as issues; else -> archive the repo with a retirement note and repoint fleet callers
- Evidence: `README.md`, `Kaedra/harvest_fleet.py`
- Lens: stale-repo governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: README.md line 67 links https://github.com/Who-Visions/Iris-Vortex (repo is actually Who-Visions/Iris-Ai per git remote/local checkout name); line 71 'MIT (c) 2026 Who Visions LLC'; lines 6-8 list public Instagram/YouTube socials; project structure section (lines 44-59) omits db/, rag.py, rate_limiter.py, embeddings.py, test_memory.py that exist in the repo. git log shows 13 commits Dec 2025 then 

### WG-0057 · P0 · defend · effort M

**Bring iris-agent-service /health back from 500/503 so the fleet roster reads ONLINE**

- Failure surface: Handoff 20260804_222419 records iris-agent-service answering fast but returning 500/503 on /health; the current health_check is a constant dict, so the deployed revision either predates df074bc or fails at import (google-adk, nest_asyncio, LABEL-before-FROM build). Kaedra and Visions-ai probes mark Iris OFFLINE and every fleet council that includes Iris degrades silently.
- First fork: if you observe the live revision's image digest predates 2026-09-16 -> the deploy never landed; run the build mission first; else -> pull Cloud Run logs for the import traceback and fix the module that fails at startup
- Evidence: `agent.py`, `nougen-handoffs/claude cli handoffs/handoff_20260804_222419_KushBoyGroups-Mac-mini_feat_auth-check.md`, `Dockerfile`
- Lens: runtime/observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py health_check (line 208) returns a constant dict unconditionally; nougen-handoffs/claude cli handoffs/handoff_20260804_222419_...md explicitly states iris-agent-service answers fast but returns 500/503 on /health, causing OFFLINE reads fleet-wide.
- #550 families: 42

### WG-0374 · P1 · defend · effort S

**Kill /personal-finances/stats before the next Cloud Run deploy of the tax hub path**

- Failure surface: agent.py exposes an unauthenticated GET that opens the SQLite at C:\Users\super\Watchtower\Iris-ai-repo\personal finances\personal_finances.db; handoff 20260725_011540 confirms that folder holds 243 bank/cashapp/paypal statements on Dave's box. Anyone who runs agent.py on that machine (or any future field added to the SELECT) makes Dave's transactions world-readable; on Cloud Run it 500s instead, so nobody notices the route exists.
- First fork: if you observe the route still returns 500 on the deployed revision and no client references it -> delete the route outright and redeploy; else (something calls it) -> move the path to IRIS_FINANCE_DB env, require auth, then delete the hardcoded string
- Evidence: `agent.py`, `nougen-handoffs/handoff_20260725_011540_chore_public-surface-untrack-internal.md`
- Lens: security/privacy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py:236-244 has GET /personal-finances/stats opening the exact hardcoded Windows sqlite path with no auth; handoff_20260725_011540 confirms 243 bank/cashapp/paypal statement docs in that folder.

### WG-0390 · P1 · defend · effort M

**Ship the Iris container without uploading the Watchtower working tree to Cloud Build**

- Failure surface: Dockerfile does COPY . . and .dockerignore only lists .env/.git/README; there is no .gcloudignore, so `gcloud builds submit` from Dave's Iris-ai-repo checkout tars personal finances/, tax_knowledge/, *.db into Cloud Storage and the image layer. The 2026-09-16 .gitignore fix protects git, not the build context; nobody sees it until an image is inspected.
- First fork: if you observe gcloud config `gcloudignore/enabled` true and git present (gcloud derives .gcloudignore from .gitignore) -> add an explicit .gcloudignore mirroring .gitignore and verify with `gcloud meta list-files-for-upload`; else -> block deploy.py until .dockerignore/.gcloudignore mirror the private-data rules and inspect the last pushed image in iris-repo for leaked layers
- Evidence: `Dockerfile`, `.dockerignore`, `.gitignore`
- Lens: secrets/deploy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Dockerfile:19 does COPY . . ; .dockerignore excludes only pycache/.git/.env/Dockerfile/deploy.py/README, nothing about personal finances/tax_knowledge/*.db; no .gcloudignore file exists in repo.

### WG-0406 · P1 · elevate · effort M

**Gate revived /web and /ingest behind the fleet ingest-junk-gate and capture-secret-guard rules**

- Failure surface: cli.py /web fetches any URL with urllib (SSRF incl. 169.254.169.254 if run on a cloud VM) and pushes raw page text toward RAG; /ingest walks directories, which on Dave's box include personal finances/ and tax_knowledge/. HARDENING already recorded lockfiles/base64 sharded as knowledge and secrets reaching shards; Iris has no gate at all.
- First fork: if you observe the RAG revival mission restores ingest_directory -> reuse the NouGenShards junk-gate and secret-pattern filters as a shared module; else -> restrict /web to http(s) public hosts and /ingest to an allowlisted root
- Evidence: `cli.py`, `rag.py`
- Lens: data integrity/security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cli.py's /web handler (lines 278-310) does `urllib.request.urlopen(url, timeout=10)` on any user-supplied URL with no host allowlist (SSRF-capable); /ingest (lines 411-421) calls os.path.isdir/isfile on any user-supplied path with no root restriction, so it can walk personal finances/ or tax_knowledge/ if ever pointed there.
- #550 families: 69, 70

### WG-0422 · P1 · elevate · effort M

**Put auth on iris-agent-service without breaking Kaedra and Visions-ai fleet probes**

- Failure surface: deploy.py passes --allow-unauthenticated and agent.py has no auth middleware; Kaedra/tools/kaedra_hi_probe.py and Visions-ai/tools/agent_connect.py poll the service. Turning on Cloud Run IAM or a bearer token flips those probes to OFFLINE and any fleet automation that trusts them.
- First fork: if you observe the probes only hit /health -> leave /health public, gate /chat,/generate,/vision/generate with a bearer from Secret Manager and update the two probes in the same sweep; else (probes call /chat) -> issue a fleet service token first, then gate
- Evidence: `deploy.py`, `agent.py`, `Kaedra/tools/kaedra_hi_probe.py`
- Lens: auth/public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: deploy.py:65 passes --allow-unauthenticated, agent.py has no auth middleware; Kaedra/tools/kaedra_hi_probe.py and Visions-ai/tools/agent_connect.py both poll /health on the deployed service URLs.

### WG-0438 · P1 · elevate · effort M

**Restore the A2A agent card and OpenAI-compat endpoints the README and fleet still expect**

- Failure surface: df074bc deleted /.well-known/agent.json, /rpc, /v1/chat/completions, /v1/embeddings, /v1/research, /search, /analyze-url, /execute-code; README still tells users to curl the agent card, python-a2a stays in requirements, and Visions-ai/tools/neural_council.py lists Iris as a council member. Fleet callers get 404s that look like Iris being down.
- First fork: if you observe any fleet script posts to /v1/chat/completions or reads the agent card -> restore those two from 65b0c1a on the new IrisAgent; else -> strip README/requirements of A2A claims and record the surface as retired
- Evidence: `README.md`, `agent.py`, `Visions-ai/tools/neural_council.py`
- Lens: public surface/fleet contract · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py's full route list (/,/health,/models,/chat,/generate,/vision/generate,/personal-finances/stats) has no /.well-known/agent.json, /rpc, /v1/*, /search, /analyze-url or /execute-code, while README.md still documents curling the agent card; requirements.txt still lists python-a2a (unused per grep); Visions-ai/tools/neural_council.py lines 84-86 lists 'iris' as a council member with a /chat UR
- #550 families: 32

### WG-0454 · P1 · elevate · effort S

**Normalize CRLF/LF with .gitattributes so future diffs are reviewable**

- Failure surface: df074bc shows 2784+/3400- across all 19 files because line endings flipped; README, cli, db/*, memory, rag, embeddings, rate_limiter, test_memory are CRLF while agent.py, deploy.py, Dockerfile are LF. Any secret or behaviour change hides inside a whole-file rewrite and reviewers (or a future secret scan of diffs) cannot see it.
- First fork: if you observe the Windows checkout has core.autocrlf true -> add .gitattributes `* text=auto eol=lf` and one renormalize commit; else -> fix editor settings on blade/whoart first, then renormalize
- Evidence: `cli.py`, `agent.py`, `.gitignore`
- Lens: toolchain/governance · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Direct byte-level check confirms cli.py, db/sqlite_store.py, memory.py, rag.py, embeddings.py, rate_limiter.py, test_memory.py, and README.md contain CRLF line endings, while agent.py, deploy.py, and Dockerfile are LF-only — exactly the split the claim describes; no .gitattributes file exists in the repo.

### WG-0469 · P1 · defend · effort M

**Survive a scrape of unauthenticated /chat on gemini-3.1-pro with thinking=high**

- Failure surface: Every /chat builds a fresh IrisAgent and calls generate_content with thinking_level=high and no HTTP rate limit; GEMINI_LIMITER exists in rate_limiter.py but agent.py never imports it (65b0c1a did). rate_limiter.py:9 records a prior Google Cloud project suspension; a bot loop burns the shared mineral-subject-487519-v6 quota that Kaedra also lives in.
- First fork: if you observe Cloud Run max-instances unset and no per-IP limiting -> set max-instances, concurrency, and re-wire GEMINI_LIMITER + a budget alert before anything else; else -> add per-session token caps and a daily spend kill switch
- Evidence: `agent.py`, `rate_limiter.py`, `deploy.py`
- Lens: cost/quota · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py has zero references to rate_limiter/GEMINI_LIMITER (grep confirms), while rate_limiter.py defines GEMINI_LIMITER and its module docstring/comment (line 9) references compliance 'after project reinstatement', i.e. a prior suspension; deploy.py sets no --max-instances or --concurrency.
- #550 families: 20

### WG-0482 · P1 · defend · effort S

**Verify git history carries no finance or tax records and document the finding for the fleet**

- Failure surface: The 2026-09-16 security commit implies exposure; a fresh check (git log --all --name-only lists only the 19 current paths, no .db/.json/finance files, no AIza/PRIVATE KEY hits) shows the private data never entered git and the only committed exposure is the hardcoded path in agent.py. Without a recorded verification, the next agent re-runs the audit or, worse, assumes a history rewrite is needed and force-pushes a private repo.
- First fork: if you observe origin/main has any commit not in this clone -> re-run the name-only and pattern scans against origin before concluding; else -> record the verification in CLAUDE.md/HARDENING-style note and close the question
- Evidence: `.gitignore`, `agent.py`
- Lens: secrets/history · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: .gitignore lines 27-31 exclude *.db/*.sqlite/'personal finances/'/tax_knowledge/ (added in the 101fb1d security commit); git log --all --name-only across all 15 commits shows only the repo's normal source files, no .db/finance paths ever committed, and a content grep for AIza/PRIVATE KEY across history returns nothing. agent.py:238 does contain a hardcoded local path 'C:\\Users\\super\\Watchtower\
- #550 families: 75
