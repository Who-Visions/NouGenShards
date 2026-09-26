# War-game candidates — who-visions-tester

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

7 candidates · P0 1 · P1 6 · P2 0 · P3 0 · defend 5 · elevate 2

| id | P | kind | title |
|---|---|---|---|
| WG-0016 | P0 | defend | Resolve the DAV1D project migration in dav1d_brain or retire the BigQuery path |
| WG-0376 | P1 | elevate | Rebuild the KRONOS image against today's google-genai/google-adk without repeating the startup NameError |
| WG-0392 | P1 | defend | Close the Bandit 'Permission Denied (Ghost)' project or drop BANDIT from every registry |
| WG-0408 | P1 | elevate | Ship one truthful agent card: served AgentCard, committed agent.json and the A2A schema disagree |
| WG-0424 | P1 | defend | Label the lore docs as narrative before they are ingested into shards as evidence |
| WG-0440 | P1 | defend | Cap council fan-out cost and latency: 18 calls, 9 projects, 60s timeouts, no history bound |
| WG-0456 | P1 | defend | Reconcile README, README.md.bak, launcher banner and card on how many agents exist and who leads |

---

### WG-0016 · P0 · defend · effort M

**Resolve the DAV1D project migration in dav1d_brain or retire the BigQuery path**

- Failure surface: src/dav1d_brain.py defaults to gen-lang-client-0285887798 and a hardcoded Reasoning Engine ID; dav1d_history.md says migration to dav1d-kbg1019 was in progress and handoff_notes.md left 'confirm gen-lang-client is drained/deleted' open. Council Stage 0 queries a dataset that may no longer exist, using whatever ADC the operator has, and swallows the failure into an empty context.
- First fork: if `bq ls gen-lang-client-0285887798:dav1d_memory` fails -> repoint to dav1d-kbg1019 or delete search_memory; else -> both projects live, pick one and write the Dave lock
- Evidence: `src/dav1d_brain.py`, `dav1d_history.md`, `handoff_notes.md`
- Lens: infra · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/dav1d_brain.py:13 hardcodes DAV1D_PROJECT_ID default 'gen-lang-client-0285887798' plus a hardcoded DAV1D_REASONING_ENGINE_ID and DAV1D_DATASET='dav1d_memory'. All three evidence files exist; the project-ID mismatch is directly observable in code even though the migration-status text in the .md files was not independently cross-checked line-by-line.

### WG-0376 · P1 · elevate · effort M

**Rebuild the KRONOS image against today's google-genai/google-adk without repeating the startup NameError**

- Failure surface: Dockerfile pip-installs unpinned requirements.txt while uv.lock pins google-genai 1.55.0, google-adk 1.18.0, fastapi 0.124.4; a rebuild today pulls 9 months of SDK drift (Part.from_text signature, ThinkingConfig fields, media_resolution) into a service that already broke prod once on startup (commit 2a3095c). The first push after revival is the failure.
- First fork: if `uv lock --check` passes but `pip install -r requirements.txt` resolves different majors -> make Dockerfile install from uv.lock; else -> pin requirements.txt to the lock and add an import-smoke step in the build
- Evidence: `Dockerfile`, `requirements.txt`, `uv.lock`
- Lens: dependencies · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Dockerfile line `RUN pip install --no-cache-dir -r requirements.txt` installs from unpinned requirements.txt; uv.lock pins exact versions google-genai 1.55.0, google-adk 1.18.0, fastapi 0.124.4. Commit 2a3095c ('fix: Remove erroneous comment causing NameError on Cloud Run startup', 2025-12-25) confirms the prior prod break. All evidence paths exist and directly corroborate the claim.
- #550 families: 77

### WG-0392 · P1 · defend · effort S

**Close the Bandit 'Permission Denied (Ghost)' project or drop BANDIT from every registry**

- Failure surface: handoff_notes.md flagged Bandit's project as Permission Denied on 2025-12-14 and no later commit touches it; bandit-849984150802 stays in all FLEET dicts and REVIEW_BOARD, so every council run spends a 60s timeout and a Stage 2 slot on a possibly dead service, and the origin lore still counts it as active.
- First fork: if bandit-849984150802/health answers 200 -> the IAM issue was the GCP console, not the service, note it and close; else -> remove from REVIEW_BOARD and mark fallen in agent.json roster
- Evidence: `handoff_notes.md`, `src/council_cli.py`, `agent.json`
- Lens: infra · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: handoff_notes.md:23 states "Bandit's Project: Currently 'Permission Denied' (Ghost). Keep on radar." src/council_cli.py still lists BANDIT in the FLEET dict (url bandit-849984150802...) and in REVIEW_BOARD. agent.json still lists BANDIT as name at line 131. Directly supports claim.

### WG-0408 · P1 · elevate · effort S

**Ship one truthful agent card: served AgentCard, committed agent.json and the A2A schema disagree**

- Failure surface: src/agent.py serves capabilities as a flat list with fleet 'K.A.M', version 2.0.0 and no skills/url/provider; agent.json commits capabilities as a dict, four skills, a 10-agent roster and 'KAM'. check_a2a_cards only asserts a 'name' key so both pass. Any real A2A consumer picks one and gets a different contract than the other tells it.
- First fork: if a strict A2A validator rejects the served card -> serve agent.json from disk (single source) and validate in CI; else -> delete agent.json and generate it from the model at build
- Evidence: `agent.json`, `src/agent.py`, `check_a2a_cards.py`
- Lens: public surface · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/agent.py:47-48,55 shows capabilities as a List[str] and fleet including 'K.A.M', version='2.0.0'. agent.json has capabilities as a dict (line 7), a 'skills' array (line 14), and a fleet member named 'KAM' (line 126). check_a2a_cards.py's check_card only does `data.get("name", "Unknown")` with no schema validation. All three files exist and directly support the claim.
- #550 families: 32

### WG-0424 · P1 · defend · effort S

**Label the lore docs as narrative before they are ingested into shards as evidence**

- Failure surface: hive_mind_origins.md, dav1d_history.md and README claim precise birth dates that disagree internally (Yuki 'Dec 9*' vs 'immediately after Kaedra/Dav1d'), and the last commit a61b3fc edited the KRONOS creation date to 'align with lore' rather than with git. Ingesting these as knowledge breaks Destiny #2's evidence-density >=90% and strict contradiction resolution the moment two dates collide.
- First fork: if shards_search already returns these dates as facts -> shards_mark them CANDIDATE/narrative; else -> add a front-matter provenance header (source: lore, not evidence) before ingest-junk-gate sees them
- Evidence: `hive_mind_origins.md`, `dav1d_history.md`, `audit_repo_ages.py`
- Lens: evidence density · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: hive_mind_origins.md:41 says Yuki was 'Created immediately after the core tech (Kaedra/Dav1d) was settled' while the timeline table at line 103 lists Yuki's date as 'Dec 9*' (asterisked/uncertain) -- an internal inconsistency. git log confirms commit a61b3fc is titled 'docs: Align KRONOS creation date with lore and add fleet_ping.py to architecture' (2026-01-05), matching the claim about editing d
- #550 families: 69

### WG-0440 · P1 · defend · effort M

**Cap council fan-out cost and latency: 18 calls, 9 projects, 60s timeouts, no history bound**

- Failure surface: Each council question issues 1 briefing + 8 opinions + 8 reviews + 1 synthesis, each with a 60s timeout, plus DAV1D BigQuery and Vertex embedding; history is re-sent to all peers on every turn. A single interactive session can run 10 minutes and bill nine GCP projects, and the TUI swallows exceptions with print_exception and keeps going.
- First fork: if any peer times out in Stage 1 -> the run already costs 60s+ per stage, add per-stage deadline and peer-drop; else -> add a per-session call budget before opening it to agent lanes
- Evidence: `src/council_cli.py`, `src/roundtable_cli.py`
- Lens: cost · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/council_cli.py:103 uses `httpx.AsyncClient(timeout=60.0)`; stage1_opinions and a review stage (lines 175-237) fan out to all fleet members in parallel with asyncio.gather; line 378 calls `console.print_exception()` inside what is effectively a catch-and-continue handler. The exact call-count/9-project figures are a reasonable derivation from the FLEET dict size (9 members incl. leader) rather 
- #550 families: 65, 93

### WG-0456 · P1 · defend · effort S

**Reconcile README, README.md.bak, launcher banner and card on how many agents exist and who leads**

- Failure surface: README.md.bak says 9/9 Active and the leader is Who-Tester; README.md says 10 agents led by KRONOS; launcher prints 'Fleet: 10 Agents Active' unconditionally; council_cli has 9 members, roundtable 10, fleet_ping 10 with a different IRIS. Handoff notes say 9 Active, 1 Fallen. Any of these read by a lane becomes a false fleet-status claim.
- First fork: if the registry collapse lands first -> generate these counts from config/fleet.json and delete README.md.bak; else -> hand-fix now and mark every number CANDIDATE
- Evidence: `README.md.bak`, `README.md`, `launcher.py`
- Lens: docs claiming done · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: README.md.bak:7 badge says '9/9_Active'; README.md.bak:33 names Who-Tester as 'Leader / Chairman'. README.md:34 header is '## The Fleet (10 Agents)' with KRONOS as Chairman (line 84). launcher.py:118 unconditionally prints 'Fleet: 10 Agents Active'. Directly supports claim; the council_cli(9)/roundtable(10)/fleet_ping(10) member-count cross-check was independently verified in items 35-38's file re
