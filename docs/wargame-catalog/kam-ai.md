# War-game candidates — Kam-ai

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

17 candidates · P0 2 · P1 15 · P2 0 · P3 0 · defend 9 · elevate 8

| id | P | kind | title |
|---|---|---|---|
| WG-0015 | P0 | defend | Prove rule 1 holds when phoebus rebases a whoart-stamped Kam-ai commit |
| WG-0031 | P0 | elevate | Arm the claim registry in every Kam-ai clone (core.hooksPath, nougen.machine, first record) |
| WG-0373 | P1 | defend | Survive an anonymous token-drain on public /v1/chat/completions |
| WG-0389 | P1 | defend | Remove the fleet Cloud Run enumeration from the public /.well-known/agent.json |
| WG-0405 | P1 | defend | Resolve the two KAM project numbers the fleet points at (587184277060 vs 885670388176) |
| WG-0421 | P1 | defend | Establish who owns kam-api before retiring it: all code commits are KRONOS-Agent |
| WG-0437 | P1 | defend | Make thought-signature history survive a JSON hop and OpenAI role names |
| WG-0453 | P1 | elevate | Decide revive / merge / retire for Kam-ai with evidence, not memory |
| WG-0468 | P1 | elevate | Retire the kam-api Cloud Run service cleanly: IAM, image, cards, callers |
| WG-0481 | P1 | elevate | Put auth on kam-api without breaking Visions agent_connect's optional Bearer flow |
| WG-0494 | P1 | elevate | Make /v1/chat/completions actually OpenAI-compatible without breaking prompt-style callers |
| WG-0506 | P1 | elevate | Migrate KAM's model routing for the frontier-lane cutover without a hard dependency on Gemini previews |
| WG-0518 | P1 | elevate | Publish a truthful A2A agent card and make check_a2a_cards validate it |
| WG-0530 | P1 | elevate | Return structured tone analysis (score, issues, alternatives) via response_schema |
| WG-0542 | P1 | defend | Reconcile three project ids before the 403 from commit 51f87a8 replays |
| WG-0554 | P1 | defend | Run setup_iam.sh without widening the shared default compute SA |
| WG-0566 | P1 | defend | Stop advertising /v1/embeddings in the agent card while it always 500s |

---

### WG-0015 · P0 · defend · effort S

**Prove rule 1 holds when phoebus rebases a whoart-stamped Kam-ai commit**

- Failure surface: The hook documents the 2026-07-31 incident where rebase on blade rewrote phoebus/claude-cli trailers to blade1tb/unknown-agent. Kam-ai's only trailer-stamped commit is 274b9bf (whoart/claude-cli); a rebase from another machine on this repo has never been exercised.
- First fork: if you observe `git interpret-trailers --parse` on a replayed 274b9bf still says Machine: whoart -> route A: record the pass in a handoff; else route B: the replay detection markers miss this git version, fix before the first multi-machine rebase.
- Evidence: `hooks/prepare-commit-msg`
- Lens: agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Hook header documents the 2026-07-31 blade rebase reattribution; git log shows 274b9bf is the only commit with Machine: whoart / Agent: claude-cli trailers, the other six are KRONOS-Agent with no trailers.
- #550 families: 9

### WG-0031 · P0 · elevate · effort S

**Arm the claim registry in every Kam-ai clone (core.hooksPath, nougen.machine, first record)**

- Failure surface: Hooks were pushed 2026-08-01 but core.hooksPath is unset in this checkout and .handoffs has no records, so the adoption is inert here: neither the foreign-claim guard nor the Machine/Agent trailers run, and the next duplication the commit message warns about can recur on this repo.
- First fork: if you observe `git config core.hooksPath` is empty on blade/phoebus/whoart clones -> route A: set it and write one record per machine in a coordinated pass; else route B: only the first record is missing, write it.
- Evidence: `hooks/pre-commit`, `hooks/prepare-commit-msg`, `.handoffs/.gitkeep`
- Lens: agent governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit and hooks/prepare-commit-msg both exist and implement the claim-guard/trailer logic described; `git config --get core.hooksPath` returns empty in this checkout, confirming the hooks are not wired up; .handoffs/ contains only .gitkeep (no machine records), confirming the adoption is inert here exactly as claimed. The registry-adoption commit (274b9bf, 2026-08-02) is present in git 
- #550 families: 25

### WG-0373 · P1 · defend · effort M

**Survive an anonymous token-drain on public /v1/chat/completions**

- Failure surface: kam-api is deployed --allow-unauthenticated with allUsers run.invoker; any caller gets Gemini 3 Pro with thinking_budget 32768, include_thoughts=True and Google Search grounding per request. Nobody notices until the metal-cable-478318-g8 bill lands (HARDENING history: ~$150/day unnoticed on one machine).
- First fork: if you observe the kam-api service still exists with non-zero request count in Cloud Run metrics -> route A: throttle/auth in place before any other work; else route B: confirm scaled-to-zero and move to retire/merge decision.
- Evidence: `cloudbuild.yaml`, `scripts/setup_iam.sh`, `agent.py`
- Lens: cost/auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudbuild.yaml deploys kam-api --allow-unauthenticated; setup_iam.sh grants allUsers run.invoker; agent.py sets thinking_budget 32768, include_thoughts=True, google_search default on. The $150/day HARDENING figure was not located in-repo but the exposure is directly supported.
- #550 families: 57

### WG-0389 · P1 · defend · effort S

**Remove the fleet Cloud Run enumeration from the public /.well-known/agent.json**

- Failure surface: FLEET hard-codes 9 sibling Cloud Run URLs with project numbers and AgentCard lists the fleet; the card is served unauthenticated. It also drifts: KAM lists iris-agent-618147264860 while the tester's fleet_ping uses iris-ai-481105, so a stale attack map is published.
- First fork: if you observe the FLEET dict is referenced by any outbound call in agent.py -> route A: move to env-configured peers with a private endpoint; else route B: delete FLEET and the fleet field from the card.
- Evidence: `agent.py`, `README.md`, `who-visions-tester/fleet_ping.py`
- Lens: security/public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: FLEET dict in agent.py hardcodes 9 run.app URLs with project numbers incl. iris-agent-618147264860; who-visions-tester/fleet_ping.py uses iris-ai-481105. Card served at unauthenticated /.well-known/agent.json (card lists fleet names, not URLs, but FLEET is in source shipped in the image).
- #550 families: 74

### WG-0405 · P1 · defend · effort S

**Resolve the two KAM project numbers the fleet points at (587184277060 vs 885670388176)**

- Failure surface: who-visions-tester (check_kam, fleet_ping, fleet_config_snippet) targets kam-api-587184277060; Visions-ai agent_connect/neural_council target kam-api-885670388176. At most one is live, so half the fleet's KAM calls fail silently in council flows.
- First fork: if you observe both URLs answer /health -> route A: two KAM deployments exist, pick one and delete the other; else route B: patch the dead URL in the caller repos and record it in a handoff.
- Evidence: `agent.py`, `scripts/setup_iam.sh`, `NouGenRelay .handoffs/20260802T164433Z__whoart__claude-cli.md`, `who-visions-tester/fleet_ping.py`, `Visions-ai/tools/agent_connect.py`
- Lens: fleet integration · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: who-visions-tester check_kam.py/fleet_ping.py/fleet_config_snippet.py use kam-api-587184277060; Visions-ai agent_connect.py/neural_council.py use kam-api-885670388176. setup_iam.sh PROJECT_NUMBER=587184277060. Handoff record mentions Kam-ai only as a repo name; added the caller files as evidence.

### WG-0421 · P1 · defend · effort S

**Establish who owns kam-api before retiring it: all code commits are KRONOS-Agent**

- Failure surface: Six of seven commits are authored by the bot identity KRONOS-Agent <ai-with-dav3@whovisions.com> with no Machine/Agent trailers; the Cloud Run service, IAM grants and gcr image live in metal-cable-478318-g8 under an unknown human owner. Retiring without an owner risks deleting something another agent still depends on.
- First fork: if you observe Cloud Run audit logs show the deployer principal for kam-api -> route A: that is the owner, confirm with Dave; else route B: treat as orphaned, label CANDIDATE, and park the delete behind a Dave lock.
- Evidence: `README.md`, `hooks/prepare-commit-msg`, `scripts/setup_iam.sh`
- Lens: governance/provenance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: git log: 6 of 7 commits by KRONOS-Agent <ai-with-dav3@whovisions.com> without trailers; only 274b9bf carries Machine/Agent. setup_iam.sh pins metal-cable-478318-g8; no owner named in README.

### WG-0437 · P1 · defend · effort M

**Make thought-signature history survive a JSON hop and OpenAI role names**

- Failure surface: History replay passes h.role straight to types.Content (an 'assistant' role from OpenAI-style callers is rejected by Gemini), sets thought_signature from a JSON string where the SDK expects bytes, and calls Part.from_bytes with base64 text. Multi-turn calls from Visions/tester 400 or lose reasoning continuity.
- First fork: if you observe a two-turn request with role=assistant returns 400 -> route A: map roles and base64-decode signatures/inline_data; else route B: add a regression test and move on.
- Evidence: `agent.py`
- Lens: correctness · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: History loop passes types.Content(role=h.role) verbatim, assigns thought_signature from the JSON string field, and calls Part.from_bytes(data=p['inline_data']['data']) with whatever JSON carried. No role mapping or base64 decode.

### WG-0453 · P1 · elevate · effort L

**Decide revive / merge / retire for Kam-ai with evidence, not memory**

- Failure surface: Runtime untouched since 2025-12-25; the only later commit is registry adoption. The fleet still lists KAM in REVIEW_BOARD and council configs, so retiring blindly breaks council flows while reviving blindly re-exposes a public Gemini 3 Pro endpoint.
- First fork: if you observe kam-api answers /health today and has traffic -> route A: merge path (keep endpoint, move code); else route B: retire path (delete service, redirect callers, archive repo).
- Evidence: `agent.py`, `docs/architecture.md`, `NouGenRelay/.handoffs/20260905T210800Z__phoebus__antigravity.md`, `Visions-ai/tools/neural_council.py`
- Lens: stale-repo · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: git log confirms all runtime commits dated 2025-12-25 with the sole later commit (274b9bf, 2026-08-02) being the relay registry adoption; Visions-ai/tools/neural_council.py and agent_connect.py, and who-visions-tester/src/council_cli.py + fleet_config_snippet.py list kam/KAM as a fleet member confirming council exposure.

### WG-0468 · P1 · elevate · effort M

**Retire the kam-api Cloud Run service cleanly: IAM, image, cards, callers**

- Failure surface: Retirement touches four places outside the repo: allUsers run.invoker binding, the gcr.io image, the fleet cards in who-visions-tester and Visions-ai, and the FLEET entry other agents copied. Missing one leaves a dangling public URL or a council member that always errors.
- First fork: if you observe the merge decision landed -> route A: retire after the new route is live and callers switched; else route B: retire straight away and mark KAM 'fallen' in fleet docs.
- Evidence: `scripts/setup_iam.sh`, `cloudbuild.yaml`, `agent.py`, `who-visions-tester/check_a2a_cards.py`, `Visions-ai/tools/agent_connect.py`
- Lens: stale-repo/deploy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: setup_iam.sh grants allUsers run.invoker on kam-api; cloudbuild.yaml pushes/deploys the gcr.io image; who-visions-tester/check_a2a_cards.py and Visions-ai/tools/agent_connect.py + neural_council.py hard-code KAM's Cloud Run URL as fleet cards/callers, confirming all four external touch points.

### WG-0481 · P1 · elevate · effort M

**Put auth on kam-api without breaking Visions agent_connect's optional Bearer flow**

- Failure surface: Switching to IAM-only ingress or a shared fleet token changes every caller at once; Visions-ai agent_connect already sends a Bearer token when available and the tester sends none, so a cutover can strand half the fleet.
- First fork: if you observe callers can obtain an identity token (Cloud Run to Cloud Run) -> route A: require IAM invoker and drop allUsers; else route B: shared fleet header checked in a FastAPI dependency, rotate via env.
- Evidence: `cloudbuild.yaml`, `scripts/setup_iam.sh`, `agent.py`, `Visions-ai/tools/agent_connect.py`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: setup_iam.sh binds allUsers as run.invoker (no IAM auth); Visions-ai/tools/agent_connect.py line ~92 sets headers['Authorization'] = f'Bearer {token}' conditionally for kam, directly matching the claimed optional Bearer flow.

### WG-0494 · P1 · elevate · effort M

**Make /v1/chat/completions actually OpenAI-compatible without breaking prompt-style callers**

- Failure surface: The route is named like OpenAI but takes {prompt, history[]} and returns choices[]; Visions had to special-case KAM ('Patched Kam schema', fleet_timeline 2025-12-25). Moving to messages[] breaks the tester and Visions unless both shapes are accepted during transition.
- First fork: if you observe live callers send 'prompt' -> route A: accept both shapes for one release and log which is used; else route B: switch to messages[] directly.
- Evidence: `agent.py`, `Visions-ai/tools/agent_connect.py`
- Lens: public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py's ChatCompletionRequest takes prompt/history and ChatCompletionResponse returns choices[]; Visions-ai/tools/agent_connect.py explicitly special-cases is_kam to send 'prompt' payload (comment: "KRONOS and KAM use 'prompt'"), confirming the caller-side special-casing claim (exact 'Patched Kam schema' string not located, but the mechanism is verified).
- #550 families: 32

### WG-0506 · P1 · elevate · effort M

**Migrate KAM's model routing for the frontier-lane cutover without a hard dependency on Gemini previews**

- Failure surface: KAM is Gemini-only with preview ids baked into three files; the fleet's July 2026 subscription-to-API cutover and free Gemini/OpenRouter/ollama fallback lanes are invisible to it. Any per-lane routing decision has to be re-implemented here.
- First fork: if you observe the merge target has a model router -> route A: KAM becomes a prompt profile in that router; else route B: add a model alias env with GA fallback (gemini-2.5-pro) and remove preview ids from the card.
- Evidence: `agent.py`, `cloudbuild.yaml`, `.env.template`
- Lens: model/cost · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py hard-codes DEFAULT_MODEL fallback 'gemini-3-pro-preview' and the AgentCard lists 'gemini-3-pro-preview','gemini-3-flash-preview','gemini-3-pro-image-preview'; cloudbuild.yaml sets --set-env-vars DEFAULT_MODEL=gemini-3-pro-preview; .env.template sets DEFAULT_MODEL=gemini-2.0-flash-lite-001 (yet another preview/non-GA id) -- three files with preview ids confirmed, no model-router abstractio
- #550 families: 53

### WG-0518 · P1 · elevate · effort S

**Publish a truthful A2A agent card and make check_a2a_cards validate it**

- Failure surface: AgentCard 2.0.0 lists 8 capabilities and 6 models; only chat works. Fleet discovery tools (check_a2a_cards, fleet_config_snippet) treat the card as truth, so councils route EQ, research and embedding tasks to endpoints that 500.
- First fork: if you observe the card is consumed programmatically by any fleet tool -> route A: derive the card from registered FastAPI routes and add a contract test; else route B: hand-edit to chat+health only.
- Evidence: `agent.py`, `README.md`, `who-visions-tester/check_a2a_cards.py`
- Lens: public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py's AgentCard lists 8 capabilities and 6 models (version 2.0.0) while only /v1/chat/completions is a working route (embeddings raises AttributeError per item 35, TTS/music are stubs per item 43); who-visions-tester/check_a2a_cards.py fetches KAM's /.well-known/agent.json and reports card_name/desc as ground truth, and Visions-ai/fleet_dashboard.py + who-visions-tester/src/fleet_config_snipp
- #550 families: 32

### WG-0530 · P1 · elevate · effort M

**Return structured tone analysis (score, issues, alternatives) via response_schema**

- Failure surface: SYSTEM_INSTRUCTION asks for an Impact score, Tone Issues and Alternatives but the API returns free text; the CLI and any fleet caller must regex the prose, and grounding citations get spliced into it. Switching to JSON output changes the contract for every caller.
- First fork: if you observe callers display raw text -> route A: add a /v1/analyze route with a pydantic response_schema alongside chat; else route B: switch chat to structured output behind a flag.
- Evidence: `agent.py`, `agents/kam.py`
- Lens: product/data integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: agent.py's SYSTEM_INSTRUCTION explicitly asks for Impact score / Tone Issues / Suggested Alternatives, but generate() returns response_text (or citation-spliced text via _add_citations) as a plain string with no response_schema/structured output config anywhere in GenerateContentConfig; agents/kam.py's analyze_message() only simulates the parsed fields locally rather than parsing a real structured

### WG-0542 · P1 · defend · effort S

**Reconcile three project ids before the 403 from commit 51f87a8 replays**

- Failure surface: agent.py defaults to metal-cable-478318-g8, config/kam.toml says kam-kindness-matrix, .env.template says kam-whovisions. Commit 51f87a8 records a prior 403 from Vertex when the wrong project was used; a deploy from a shell with a different active project or a copied .env recreates it.
- First fork: if you observe GOOGLE_CLOUD_PROJECT in the running service differs from metal-cable-478318-g8 -> route A: this is the live 403 path, fix env first; else route B: delete kam.toml/.env.template project ids and make agent.py refuse to start without an explicit project.
- Evidence: `agent.py`, `config/kam.toml`, `.env.template`
- Lens: deploy/infra · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: agent.py default metal-cable-478318-g8; config/kam.toml id=kam-kindness-matrix; .env.template GOOGLE_CLOUD_PROJECT=kam-whovisions. Commit 51f87a8 'Corrected default PROJECT_ID to metal-cable project to resolve 403 errors' documents the prior 403.

### WG-0554 · P1 · defend · effort M

**Run setup_iam.sh without widening the shared default compute SA**

- Failure surface: scripts/setup_iam.sh grants roles/aiplatform.user to 587184277060-compute@developer.gserviceaccount.com, the default SA shared by every Cloud Run/Function in metal-cable-478318-g8, and allUsers run.invoker on kam-api. Re-running it silently broadens access for services that are not KAM.
- First fork: if you observe other Cloud Run services in metal-cable-478318-g8 using the default compute SA -> route A: create a dedicated kam SA and migrate before touching IAM; else route B: the binding is KAM-only, scope it down and retire the allUsers grant.
- Evidence: `scripts/setup_iam.sh`
- Lens: security/iam · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: setup_iam.sh grants roles/aiplatform.user to 587184277060-compute@developer.gserviceaccount.com at project level and allUsers run.invoker on kam-api. Whether other services share the SA is unverifiable here but the default compute SA is shared by construction.

### WG-0566 · P1 · defend · effort S

**Stop advertising /v1/embeddings in the agent card while it always 500s**

- Failure surface: create_embeddings calls kam_agent.embed(), which does not exist on KAMAgent; every request returns 500 with 'KAMAgent object has no attribute embed', yet AgentCard.endpoints lists embed and claims gemini-embedding-001. Fleet callers doing capability discovery are misled.
- First fork: if you observe any fleet caller (tester, Visions, Kaedra) actually posting to KAM /v1/embeddings -> route A: implement embed with one chosen model; else route B: remove the route and the card entry.
- Evidence: `agent.py`
- Lens: product/public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: create_embeddings awaits kam_agent.embed(texts); KAMAgent defines no embed method; AgentCard.endpoints has embed=/v1/embeddings and response hardcodes model gemini-embedding-001.
- #550 families: 42
