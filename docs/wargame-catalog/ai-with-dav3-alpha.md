# War-game candidates — Ai-with-Dav3--Alpha-

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

12 candidates · P0 7 · P1 5 · P2 0 · P3 0 · defend 8 · elevate 4

| id | P | kind | title |
|---|---|---|---|
| WG-0011 | P0 | elevate | Ship app/api/agent/route.ts persona proxy to replace the hard-coded localhost:8000 chat backend |
| WG-0027 | P0 | defend | Degrade the Dav1d/Kaedra chat gracefully when Cloud Run returns 400/500/503 |
| WG-0042 | P0 | defend | Replace the faked kaedra_verification_console.py with a real probe and relocate the Kaedra artifacts |
| WG-0056 | P0 | elevate | Land PR #1 (NouGenShards spotlight on Home.tsx) under an explicit merge-authority rule |
| WG-0068 | P0 | defend | Rotate the Cloudinary API secret committed in CLOUDINARY_SETUP.md and NETLIFY_DEPLOY.md |
| WG-0079 | P0 | defend | Add .env.example and a secret-scanning pre-commit so the next agent lane cannot re-commit credentials |
| WG-0090 | P0 | defend | Purge the Google AI Studio key, Who Visions legal-entity file and 196 MiB venv from git history |
| WG-0377 | P1 | defend | Reconcile the three diverging Firestore rule sets (repo, FIREBASE_SETUP.md, live Console) |
| WG-0393 | P1 | defend | Publish the Terms and Privacy pages the sign-in screen already claims users agree to |
| WG-0409 | P1 | defend | Reconcile or retire the conductor track whose plan references files that do not exist |
| WG-0425 | P1 | elevate | Replace the invented More.tsx stats with fleet-backed numbers from tracker_daily |
| WG-0441 | P1 | elevate | Decide revival or retirement of aiwithdav3 with an evidence ledger before more lanes touch it |

---

### WG-0011 · P0 · elevate · effort L

**Ship app/api/agent/route.ts persona proxy to replace the hard-coded localhost:8000 chat backend**

- Failure surface: ChatInterface.tsx POSTs to http://localhost:8000/chat and shows a green 'Online' badge; on aiwithdav3.com it is mixed content and always fails. The conductor track personas_20260110 is 0% done and references a route that does not exist.
- First fork: if curl to dav1d-322812104986.us-central1.run.app/chat returns 200 today -> build the proxy route with persona switch and server-side URL selection, else -> stub the route to return a graceful 'agents offline' message and flip the badge to reflect real health
- Evidence: `components/ChatInterface.tsx`, `conductor/tracks/personas_20260110/plan.md`, `conductor/tracks/personas_20260110/spec.md`
- Lens: product/elevation · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: components/ChatInterface.tsx:39 fetches 'http://localhost:8000/chat' literally, and line ~85 renders a static 'Online' badge with no live health check; app/api/agent/route.ts does not exist anywhere in the repo; conductor/tracks/personas_20260110/plan.md and spec.md exist and reference this route.

### WG-0027 · P0 · defend · effort M

**Degrade the Dav1d/Kaedra chat gracefully when Cloud Run returns 400/500/503**

- Failure surface: walkthrough_kaedra_fix.md records Kaedra /generate 500, Dav1d 400 and other agents 500/503; the widget's only failure path is a generic 'Is it running?' message and the badge stays 'Online'. Users see a dead assistant with no signal to the fleet.
- First fork: if a /health probe from the proxy fails -> hide the widget or show 'offline' and post to nougenmsg, else -> add timeouts, a health cache and a fallback lane (Gemini free tier or ollama) as the operating law's fallback lanes describe
- Evidence: `walkthrough_kaedra_fix.md`, `components/ChatInterface.tsx`
- Lens: runtime/observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: walkthrough_kaedra_fix.md documents Dav1d 400, UNK Agent 500, Who Tester 500 under 'Other Agents Tested', and components/ChatInterface.tsx's catch block (line ~57-59) sets a static message "Sorry, I'm having trouble connecting to my backend. Is it running?" with the badge staying 'Online' elsewhere in the file, exactly matching the claim.
- #550 families: 42, 43

### WG-0042 · P0 · defend · effort M

**Replace the faked kaedra_verification_console.py with a real probe and relocate the Kaedra artifacts**

- Failure surface: check_endpoint() returns hard-coded '503 FAIL'/'200 OK' strings and the loop marks every 10th random file CRITICAL; walkthrough_kaedra_fix.md cites its output as 'Local Run Results' while contradicting itself (chat completions PASS in section 4, 503 in section 6). This is fabricated verification evidence in the same pattern as embed-at-ingest being falsely marked done.
- First fork: if the Kaedra Cloud Run service still exists -> rewrite check_endpoint to do real HTTP and move the script and walkthrough to the Kaedra/Dav1d owning repo, else -> delete both files here and file a shard marking the walkthrough's verification claims as retracted
- Evidence: `kaedra_verification_console.py`, `walkthrough_kaedra_fix.md`, `RAZER_SYSTEM_DEEP_DIVE.md`
- Lens: agent governance/evidence · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra_verification_console.py's check_endpoint returns a hard-coded string based on endpoint name (503 FAIL only for /generate, /generate-image, /v1/chat/completions, else 200 OK) with no real HTTP call, and uses random.choice(self.files) to flag a 'CRITICAL: Missing dependency' on an arbitrary file; walkthrough_kaedra_fix.md section 4 states 'Text Chat (/v1/chat/completions): Passed' while secti
- #550 families: 23, 100

### WG-0056 · P0 · elevate · effort S

**Land PR #1 (NouGenShards spotlight on Home.tsx) under an explicit merge-authority rule**

- Failure surface: PR Who-Visions/Ai-with-Dav3--Alpha-#1 is a clean, mergeable draft opened 2026-08-14 that adds 104 lines to components/pages/Home.tsx; it has sat six weeks like the 26-deep nougen-handoffs backlog because self-merge authority was never decided. Every push to main auto-deploys, so merging is also a production release.
- First fork: if Dave answers the self-merge question for sweep-record PRs -> apply it here, build locally, merge and watch the Netlify deploy, else -> park it as CANDIDATE with a Netlify deploy preview link attached to the PR
- Evidence: `PR Who-Visions/Ai-with-Dav3--Alpha-#1`, `components/pages/Home.tsx`, `NETLIFY_DEPLOY.md`
- Lens: agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: GitHub PR Who-Visions/Ai-with-Dav3--Alpha-#1 exists, is a draft opened 2026-08-14T16:23:20Z, mergeable_state 'clean', touching only components/pages/Home.tsx with +104/-0 across 1 commit -- matches the claim precisely.
- #550 families: 25

### WG-0068 · P0 · defend · effort M

**Rotate the Cloudinary API secret committed in CLOUDINARY_SETUP.md and NETLIFY_DEPLOY.md**

- Failure surface: Both docs contain the full CLOUDINARY_URL (api key 664258984899566 plus api secret for cloud 'aiwithdav3'), which grants upload/destroy on the media account. It has been in git since the initial commit (Dec 2025). Failure shows up as deleted or replaced media, or a surprise Cloudinary bill.
- First fork: if you observe the Cloudinary dashboard showing the same api_secret still active -> rotate it, update the Netlify env var CLOUDINARY_URL, redeploy, then scrub the docs, else (already rotated) -> scrub the docs and add a .env.example so nobody re-pastes the new one
- Evidence: `CLOUDINARY_SETUP.md`, `NETLIFY_DEPLOY.md`, `.gitignore`
- Lens: secrets · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: CLOUDINARY_SETUP.md:8 and NETLIFY_DEPLOY.md:44 both contain the literal CLOUDINARY_URL=cloudinary://664258984899566:<secret>@aiwithdav3 in plaintext.
- #550 families: 76

### WG-0079 · P0 · defend · effort S

**Add .env.example and a secret-scanning pre-commit so the next agent lane cannot re-commit credentials**

- Failure surface: Every required env var (NEXT_PUBLIC_FIREBASE_*, FIREBASE_ADMIN_*, NOTION_*, CLOUDINARY_URL) is documented only inside prose docs that also carry live values; .gitignore covers .env* but nothing stops an agent from pasting real values into the next SETUP.md, which is exactly how the current leaks happened across three docs.
- First fork: if the fleet already has a shared gitleaks or capture-secret-guard config -> reuse it as a pre-commit hook here, else -> author .env.example, a gitleaks.toml with cloudinary:// and AIzaSy rules, and run it over history as the acceptance test
- Evidence: `.gitignore`, `FIREBASE_SETUP.md`, `NETLIFY_DEPLOY.md`
- Lens: secrets/agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: No .env.example file exists anywhere in the repo; FIREBASE_SETUP.md and NETLIFY_DEPLOY.md both document env vars inline with live-looking values (e.g. FIREBASE_SETUP.md:13 NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSy...). Evidence confirmed as-is.
- #550 families: 76

### WG-0090 · P0 · defend · effort L

**Purge the Google AI Studio key, Who Visions legal-entity file and 196 MiB venv from git history**

- Failure surface: History still holds HQ_WhoArt/Visions-ai/config.py with a default AIzaSy... GOOGLE_AI_STUDIO_API_KEY and VERTEX_PROJECT_ID endless-duality-480201-t3, knowledge_base/legal_entity_info.txt (LLC registration data), and a full Python venv (commit 1bb652d1: 25,157 files) that inflates the pack to 196 MiB. Any clone by an agent lane or a future public flip ships all of it.
- First fork: if you observe the AIzaSy key in Visions-ai/config.py still valid against Google AI Studio -> revoke it first, then rewrite history with git-filter-repo and force-push after a Dave lock, else -> proceed straight to the history rewrite and re-clone on blade/phoebus/whoart
- Evidence: `.gitignore`, `README.md`, `git history: commits 1bb652d1, 25494aa1, 5314ae41 (HQ_WhoArt/Visions-ai, Dav1d/dav1d brain)`
- Lens: secrets/history · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: git history shows commit 1bb652d1 adding a full venv (25,157 files changed per `git show --stat`), HQ_WhoArt/Visions-ai/config.py history contains the hard-coded AIzaSy[REDACTED] key and VERTEX_PROJECT_ID=endless-duality-480201-t3, and HQ_WhoArt/Visions-ai/knowledge_base/legal_entity_info.txt appears in git log --all --name-only; .git directory measures 197M confirming the b
- #550 families: 75, 76

### WG-0377 · P1 · defend · effort M

**Reconcile the three diverging Firestore rule sets (repo, FIREBASE_SETUP.md, live Console)**

- Failure surface: firestore.rules (thread create open; users update role==resource.role) differs from FIREBASE_SETUP.md (thread create locked; users update !('role' in data)) and neither is deployable from the repo, so whatever is live was hand-pasted. Nobody can say which policy protects production.
- First fork: if you can export the live rules from the Console and they match neither file -> treat live as the source, diff, and commit it, else -> pick the FIREBASE_SETUP.md baseline, apply, and delete the duplicate copy from the doc
- Evidence: `firestore.rules`, `FIREBASE_SETUP.md`
- Lens: infra/drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: firestore.rules (repo) has threads create: if true and users update guarded by request.resource.data.role == resource.data.role, while FIREBASE_SETUP.md documents create: if signedIn() (locked) and update guarded by !('role' in request.resource.data) -- a materially different rule set in each file, and no firebase.json exists to say which is deployed.
- #550 families: 12

### WG-0393 · P1 · defend · effort M

**Publish the Terms and Privacy pages the sign-in screen already claims users agree to**

- Failure surface: app/auth/signin/page.tsx says 'By signing in, you agree to our Terms of Service and Privacy Policy' but no such route exists; Google sign-in collects email and the Firebase config carries a GA measurementId with no consent flow. A user or regulator asking for the policy gets a 404.
- First fork: if Dave has existing Who Visions policy text elsewhere (meralus.com, Notion) -> pull it into /terms and /privacy Notion-backed routes, else -> draft minimal CANDIDATE pages naming Firebase Auth, Firestore, Cloudinary and Notion as processors and link them from the sign-in footer
- Evidence: `app/auth/signin/page.tsx`, `lib/firebase.ts`, `components/Footer.tsx`
- Lens: privacy/legal · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: app/auth/signin/page.tsx:61 contains the literal string 'By signing in, you agree to our Terms of Service and Privacy Policy.'; no app/terms or app/privacy route exists anywhere in the app/ tree, and components/Footer.tsx contains no terms/privacy links (grep returned nothing).

### WG-0409 · P1 · defend · effort M

**Reconcile or retire the conductor track whose plan references files that do not exist**

- Failure surface: conductor/tracks/personas_20260110/plan.md tasks reference app/api/agent/route.ts, ChatSidebar.tsx and ChatWindow.tsx (none exist), setup_state.json is stuck at 3.3 with a BOM, and workflow.md mandates TDD with >80% coverage in a repo with zero tests. Any agent that follows the plan literally will hallucinate the missing scaffolding.
- First fork: if Dave still wants conductor as the planning frame -> rewrite the plan against real files and add a test runner so its quality gates are satisfiable, else -> archive conductor/ and record the retirement so future lanes stop reading it
- Evidence: `conductor/tracks/personas_20260110/plan.md`, `conductor/setup_state.json`, `conductor/workflow.md`
- Lens: agent governance · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: conductor/setup_state.json begins with a UTF-8 BOM (EF BB BF) and contains only {"last_successful_step": "3.3_initial_track_generated"}; conductor/workflow.md mandates TDD and '>80% coverage' in multiple places; package.json has no "test" script; app/api/agent/route.ts, ChatSidebar.tsx and ChatWindow.tsx referenced by the plan do not exist in the repo.
- #550 families: 38

### WG-0425 · P1 · elevate · effort M

**Replace the invented More.tsx stats with fleet-backed numbers from tracker_daily**

- Failure surface: More.tsx publishes '127+ AI Models Trained', '2.4M+ Data Points', '89 Projects', '98% Client Satisfaction' as hard-coded strings with no source; on a Who Visions LLC site these are marketing claims that cannot be evidenced, alongside a chart of Math.random() data.
- First fork: if the shards gateway exposes tracker_daily/shards_status counts the site may read -> build a small server route that renders real counts with a cache, else -> remove the numbers and show honest qualitative copy until a data source exists
- Evidence: `components/pages/More.tsx`, `components/ChartComponent.tsx`
- Lens: product/public surface · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: components/pages/More.tsx lines 32-36 hard-code '127+','2.4M+','89','98%'; ChartComponent.tsx:61 uses Math.random() in the offset calc. Evidence confirmed as-is.

### WG-0441 · P1 · elevate · effort M

**Decide revival or retirement of aiwithdav3 with an evidence ledger before more lanes touch it**

- Failure surface: main is untouched since 2026-01-11 while the fleet gateway lists aiwithdav3 as a public ecosystem site and PR #1 waits to add a NouGenShards spotlight; forum, chat, contact, gallery and blog are each half-shipped. Agents keep spending sessions on a site whose status (live? dormant? sunset?) is undeclared.
- First fork: if Netlify shows the site live and receiving traffic -> declare 'revive' and order this catalog (secrets, rules, auth, CI first), else -> declare 'retire' as CANDIDATE: freeze deploys, lock Firestore to read-only, keep the domain, and archive the repo
- Evidence: `README.md`, `conductor/product.md`, `PR Who-Visions/Ai-with-Dav3--Alpha-#1`
- Lens: stale-repo governance · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Last commit is 2026-01-11 (git log confirms exactly), matching the staleness claim. conductor/tracks.md itself does not mention aiwithdav3/ecosystem status -- the 'primary content ecosystem' framing is actually in conductor/product.md -- corrected. PR #1 reference is unverifiable from the local checkout but plausible as a fleet artifact id.
