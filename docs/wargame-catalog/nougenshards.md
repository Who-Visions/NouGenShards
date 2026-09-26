# War-game candidates — NouGenShards

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

86 candidates · P0 30 · P1 56 · P2 0 · P3 0 · defend 55 · elevate 31

| id | P | kind | title |
|---|---|---|---|
| WG-0005 | P0 | defend | Re-verify every HARDENING.md ✅ whose mechanism vanished in the 2026-09-05 history rewrite |
| WG-0021 | P0 | defend | Survive descriptor exhaustion on phoebus without /health lying about auth |
| WG-0036 | P0 | elevate | Rotate NGS_NODE_TOKEN across blade/phoebus/whoart/Space/Worker without a 401 outage |
| WG-0050 | P0 | defend | Run the claim-guard bypass drill: pre-commit fails open and hooksPath is opt-in |
| WG-0062 | P0 | defend | Restore the relay ASK/REPORT classifier after the fleet-ops script split moved it out of tree |
| WG-0073 | P0 | defend | Survive an Ollama outage on the embed lane without silently regrowing NULL embeddings |
| WG-0084 | P0 | defend | Stop the fleet Worker's SHARD_GATEWAY_TOKEN drift from reading green for hours |
| WG-0095 | P0 | defend | Publish relay handoff records without a `git add -A` leaking spend figures |
| WG-0105 | P0 | defend | Survive Kaedra cold-load timeouts without pinning VRAM forever |
| WG-0115 | P0 | defend | Keep the nougenmsg receiver auth-latched through a Keymaker miss |
| WG-0123 | P0 | elevate | Consolidate the Keymaker to one canonical store and retire Watchtower/agent_secrets.db strays |
| WG-0131 | P0 | elevate | Grow past the 9 x 2GB grid ceiling for the million-shard destiny without re-routing dedup |
| WG-0139 | P0 | elevate | Add admission control to the node so fan-out bursts degrade gracefully instead of parking 327 threads |
| WG-0147 | P0 | defend | Make /health stop lying: degraded DBs, persistent_storage false and slow recall must change the answer |
| WG-0155 | P0 | elevate | Publish the wargames/ corpus that HARDENING, CI and coach_governor cite but the tree lacks |
| WG-0163 | P0 | defend | Protect main against another disjoint-history force-push |
| WG-0171 | P0 | defend | Converge relay_triage rules with NouGenRelay's e2b ASK/REPORT verdicts into one recorded decision |
| WG-0179 | P0 | defend | Wire relay_triage into relay_watch announce() without silencing NEEDS_OWNER legs |
| WG-0185 | P0 | defend | Make the claim guard's fail-open observable so duplicated work stops being a surprise |
| WG-0190 | P0 | elevate | Wire the metered lanes into billing.log_usage before selling a Pro tier |
| WG-0195 | P0 | defend | Stop the Space cold boot from blocking 95-250s on api.gradio.app analytics |
| WG-0200 | P0 | elevate | Wire lane_freshness --json into `nougen hi` so stale ingestion lanes are seen at session start |
| WG-0205 | P0 | elevate | Schedule the weekly embedding backfill on all three nodes with its own freshness sensor |
| WG-0210 | P0 | defend | Mark or remove the unapproved continuous-sync draft so no lane implements against the Dave lock |
| WG-0215 | P0 | defend | Enforce the coach fan-out cap in code for Claude-side workflows, not only fleet lanes |
| WG-0220 | P0 | defend | Gate tracker-dailies publication on a mechanical privacy check, not inspection |
| WG-0225 | P0 | defend | Collapse the two handoff namespaces before one `git add -A` publishes spend and incident notes |
| WG-0230 | P0 | defend | Stop the sync/push cascade regression from shipping a third time |
| WG-0235 | P0 | elevate | Retire the Space latency band-aid by finding the 3-day recall degradation |
| WG-0240 | P0 | elevate | Publish the phoebus GATEWAY role: own tokens, tracker dailies, and a failover decision |
| WG-0368 | P1 | elevate | Make receiver auth mandatory on all three nougenmsg nodes and open 8766 only via tunnel |
| WG-0384 | P1 | defend | Audit and pin which nougen_shards.node_plugins entry points may register routes |
| WG-0400 | P1 | defend | Run an adversarial-shard drill against relay dispatch and coach classification |
| WG-0416 | P1 | defend | Secure the whoart standby mirror: private shards over plain LAN HTTP via encoded SSH PowerShell |
| WG-0432 | P1 | elevate | Least-privilege the CLOUDFLARE_API_TOKEN_NOUGEN_FULL used by cf_* tools and the gateway supervisor |
| WG-0448 | P1 | elevate | Wire the Shard Capture Dam into app.py capture without accepting unsigned envelopes |
| WG-0463 | P1 | elevate | Find the 4x recall latency leak and delete ngs-node-refresh.sh |
| WG-0476 | P1 | defend | Converge blade onto one hidden scheduled task and one code tree after the QuickEdit freeze |
| WG-0489 | P1 | defend | Survive the day the whoart tunnel dies again: named-tunnel watchdog with no 72h ExecutionTimeLimit |
| WG-0501 | P1 | defend | Keep the phoebus node schedulable when Antigravity's log show storm returns |
| WG-0513 | P1 | defend | Restore quarantined grid DBs from a peer instead of recreating them empty |
| WG-0525 | P1 | elevate | Cut over hardcoded claude-3-x / gemini-1.5 model ids before the Fable 5 API routing change |
| WG-0537 | P1 | defend | Detect OpenRouter free-model rotation before Rhea's $0 lane silently goes paid or dark |
| WG-0549 | P1 | elevate | Decide where war-game docs live: wargames/ is gitignored while HARDENING, CI and tests cite it |
| WG-0561 | P1 | defend | Close the prompt-injection-to-write path in Kaedra's 'read-only' tool binding |
| WG-0573 | P1 | elevate | Replace per-node hardcoded SSH remote script paths with fleet_hosts.json config |
| WG-0584 | P1 | elevate | Schedule the weekly embedding backfill sweep on all three nodes under the VRAM gate |
| WG-0595 | P1 | elevate | Run the pre-guard redaction sweep over live vaults and the Space without corrupting rows |
| WG-0606 | P1 | elevate | Introduce read-only tenant scope so a search token cannot export the whole vault via /sync/pull |
| WG-0617 | P1 | elevate | Carry lane-health metadata through federated cross-node returns |
| WG-0628 | P1 | elevate | Triage the Dependabot backlog under a defined self-merge authority |
| WG-0639 | P1 | defend | Stop the relay-watch echo storm before wiring triage into announce() |
| WG-0650 | P1 | defend | Stop remote command injection in sessions.py SSH fan-out |
| WG-0661 | P1 | defend | Heal a partially populated dedup_index.db that only backfills when empty |
| WG-0672 | P1 | defend | Stop /sync/pull from dropping float32 embedding BLOBs (JSON-only decode) on every replica pull |
| WG-0683 | P1 | elevate | Recover rows from .malformed-<stamp> quarantined grid DBs instead of recreating empty |
| WG-0694 | P1 | elevate | Run a full grid restore drill from the HF bucket snapshot onto a fresh machine |
| WG-0705 | P1 | defend | Route all grid writes on blade through one writer instead of N processes on the same sqlite files |
| WG-0716 | P1 | defend | Make nougenmsg delivery idempotent end to end so fan-out timeouts stop double-delivering |
| WG-0727 | P1 | defend | Fix ack-equals-dispatch so acks on receipt legs never replay merged PRs across the fleet |
| WG-0737 | P1 | defend | Survive a relay/main history rewrite without silently blinding fleet_inbox and relay_watch |
| WG-0747 | P1 | defend | Unify node identity so provenance stops defaulting to blade1tb and hostnames |
| WG-0757 | P1 | elevate | Carry lane health on every federated cross-node return (HARDENING §4 open item) |
| WG-0767 | P1 | defend | Keep Kaedra's gemma model resident and queue concurrent asks so 38s cold loads stop timing out MCP clients |
| WG-0777 | P1 | defend | Add an out-of-process watchdog that times a real recall after today's blade QuickEdit freeze |
| WG-0787 | P1 | defend | Survive the whoart named-tunnel dying at 11 AM and the 72h ExecutionTimeLimit on the admin task |
| WG-0797 | P1 | defend | Replace sync_mesh_status's hardcoded 3_VAULT_SYMMETRIC claim with a real hash-parity check |
| WG-0807 | P1 | defend | Re-provision Space persistent storage safely and prove durability with a survival probe every deploy |
| WG-0817 | P1 | defend | Audit every README product claim against code before public onboarding widens |
| WG-0827 | P1 | defend | Unify the secrets-store story across SECURITY.md, privacy.md, HARDENING §8 and keymaker |
| WG-0837 | P1 | elevate | Move the Mrs. B coloring-book engine out of the memory substrate via node_plugins |
| WG-0847 | P1 | defend | Re-baseline docs/architecture.md against core.py (2GB grid, MCPServer, no OpenRouter cache arrays) |
| WG-0857 | P1 | elevate | Ship docs/wargame-catalog/catalog.ndjson (1000 entries) and gate CI on render --check |
| WG-0867 | P1 | defend | Define who may merge dependabot and sweep PRs so cooldown-held updates do not rot unreviewed |
| WG-0877 | P1 | defend | Survive a fleet broadcast storm through nougenmsg_send and the inbox hooks |
| WG-0887 | P1 | defend | Quarantine evolve_skill output: no evolved skill enters apply_skills without review |
| WG-0896 | P1 | defend | Survive a leaked ?token= URL: per-tenant rate limit and spend cap on the inference routes |
| WG-0905 | P1 | elevate | Re-baseline quota_governor and token_tracker for the Fable 5 subscription-to-API cutover |
| WG-0913 | P1 | defend | Survive the day OpenRouter withdraws or throttles the :free models Rhea falls back to |
| WG-0921 | P1 | elevate | Promote google_workspace to a tested optional extra and decide its plugin status |
| WG-0929 | P1 | elevate | Close TS parity C9 so npm consumers rank shards the way Python does |
| WG-0937 | P1 | elevate | Close HARDENING §1: unconditional session capture on the product lane (app session close) |
| WG-0945 | P1 | defend | Prove the published grid snapshot carries no private rows or invertible embeddings |
| WG-0953 | P1 | defend | Retire or re-baseline docs/AUDIT_DEEP_DIVE.md so agents stop reading a June snapshot as current |
| WG-0961 | P1 | defend | Deprecate one of the two handoff protocols in public docs (nougen handoff vs relay verbs) |
| WG-0968 | P1 | defend | Align nougen.bat's Python 3.9 floor with pyproject's >=3.10 before the next Windows onboarding |

---

### WG-0005 · P0 · defend · effort L

**Re-verify every HARDENING.md ✅ whose mechanism vanished in the 2026-09-05 history rewrite**

- Failure surface: HARDENING.md §4 (core.lane_health, NOUGEN_MIN_COVERAGE_PCT), §7 (_looks_like_blob, NOUGEN_JUNK_MAX_TOKEN) and §8 cite mechanisms and regression suites (tests/test_lane_health.py, tests/test_ingest_junk_gate.py, tests/test_capture_secret_guard.py) that do not exist anywhere in src/, app.py or tests/ of the current 51-commit tree; the blob gate and lane-health sensor are gone while the doc still says ✅, so junk shards and 'no match' lies return silently, exactly the §2 failure class.
- First fork: if you observe `grep -rn lane_health src` and `grep -rn _looks_like_blob src` both empty -> route A: treat §4/§7/§8 as regressed, re-land from the pre-force-push history or rewrite, then flip HARDENING to ⬜ until tests exist; else route B: only the test files were dropped, restore them from the old tip and add a CI guard that every HARDENING ✅ cites an existing test path.
- Evidence: `HARDENING.md`, `src/nougen_shards/core.py`, `.handoffs/20260816T232004Z__whoart__codex.md`
- Lens: secrets/invariants · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified: HARDENING.md lines 75-131 cite core.lane_health, _looks_like_blob, NOUGEN_MIN_COVERAGE_PCT/NOUGEN_JUNK_MAX_TOKEN and the three named regression suites; grep -rn for lane_health and _looks_like_blob across src/ and core.py returns nothing, and tests/test_lane_health.py, tests/test_ingest_junk_gate.py, tests/test_capture_secret_guard.py do not exist. Route A confirmed directly.

### WG-0021 · P0 · defend · effort M

**Survive descriptor exhaustion on phoebus without /health lying about auth**

- Failure surface: 2026-09-04 the node hit launchd's 256-fd limit, tenants.json became unreadable and every data endpoint returned 503 'Tenant registry is invalid' while /health stayed 200; peers recorded it as unauthenticated. RegistryUnreadableError now separates the classes but the fd budget and launchd limit remain.
- First fork: if you observe fd_budget reports >80% of the soft limit under a 3-way federated search -> route A: raise the launchd LimitLoadToFileDescriptors in the ngsnode plist and add fd usage to /health; else route B: cap the federation executor and sqlite connection cache and re-measure.
- Evidence: `src/nougen_shards/tenants.py`, `src/nougen_shards/fd_budget.py`, `ops/launchd/com.whovisions.ngsnode.plist.template`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: tenants.py line 42 explicitly documents 'Measured on phoebus 2026-09-04: the node exhausted its 256-descriptor...' and defines RegistryUnreadableError (line 30); fd_budget.py line 4-8 corroborates the 256 soft-limit language, directly matching the claim.
- #550 families: 95

### WG-0036 · P0 · elevate · effort L

**Rotate NGS_NODE_TOKEN across blade/phoebus/whoart/Space/Worker without a 401 outage**

- Failure surface: The same secret lives in the Keymaker on each box, the fleet .env on phoebus, the Space secret, the Worker's SHARD_GATEWAY_TOKEN var and Apps Script Script Properties; docs/phoebus-gateway-upgrade.md records a live 401 from token-namespace drift and gateway_supervisor.ps1 records hours of false-green. Rotation today is a hand-ordered multi-machine dance.
- First fork: if you observe tools/gateway_supervisor.ps1 still re-puts the token from the vault on auth failure -> route A: rotate with dual-accept (old+new) window in verify_token, then flip each consumer; else route B: schedule a maintenance window and rotate consumers in dependency order with a scripted /health probe.
- Evidence: `docs/phoebus-gateway-upgrade.md`, `tools/gateway_supervisor.ps1`, `integrations/apps-script/nougenshards-gemini-lane.gs`
- Lens: token rotation · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/phoebus-gateway-upgrade.md explicitly documents a live 401 from blade/outpost token mismatch, and tools/gateway_supervisor.ps1 comments (lines 147-208) describe hours of false-green and a 're-putting SHARD_GATEWAY_TOKEN from vault' recovery dance, directly supporting the claim.

### WG-0050 · P0 · defend · effort S

**Run the claim-guard bypass drill: pre-commit fails open and hooksPath is opt-in**

- Failure surface: hooks/pre-commit exits 0 unless relay returns 3, only if nougen_relay imports, only if `git config core.hooksPath hooks` was set; four duplicated work legs in two days motivated it and nothing verifies it is armed on any of the three machines or five agent lanes.
- First fork: if you observe `git config core.hooksPath` unset on a lane -> route A: have `relay init` set hooksPath and add a `relay guard --self-test` heartbeat to tracker_daily; else route B: move the claim check into the NouGenRelay pre-receive side.
- Evidence: `hooks/pre-commit`, `hooks/prepare-commit-msg`
- Lens: governance/hooks · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit confirmed to fail open by design (comment: 'Fails OPEN. If relay is not installed...the commit proceeds'), and only takes effect via opt-in `git config nougen.requireClaim true` / hooksPath -- matches claim directly.

### WG-0062 · P0 · defend · effort S

**Restore the relay ASK/REPORT classifier after the fleet-ops script split moved it out of tree**

- Failure surface: BACKLOG.md assigns hyperion to move tools/classify_asks.py to 3-vendor consensus, but that file is not in the public tree (14 owner fleet-ops scripts left in #544) and sessions.py still calls tools/nougen_session.py; work items now point at code no public clone can run.
- First fork: if you observe classify_asks.py exists in the private fleet-ops repo -> route A: rewrite the BACKLOG item against tools/coach.py in this repo and reference the private path explicitly; else route B: reconstruct the classifier here with coach.py consensus.
- Evidence: `BACKLOG.md`, `tools/coach.py`, `src/nougen_shards/sessions.py`
- Lens: governance/dead references · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: BACKLOG.md line 2 confirms the item assigning hyperion to move tools/classify_asks.py to 3-vendor consensus via coach.py; tools/classify_asks.py does not exist in the tree (verified via ls) while tools/coach.py does; sessions.py line 137/139 confirms live calls to tools/nougen_session.py -- all three claims verified directly.

### WG-0073 · P0 · defend · effort M

**Survive an Ollama outage on the embed lane without silently regrowing NULL embeddings**

- Failure surface: 2026-09-23 whoart's tray process ran while nothing listened on 11434; embed-at-ingest degrades to keyword-only and increments EMBED_AT_CAPTURE_MISSES, but no probe reports the counter, so the 47-64% NULL months can return within a week of a dark daemon.
- First fork: if you observe EMBED_AT_CAPTURE_MISSES > 0 on any node -> route A: surface it in /health and tracker_daily and auto-run embedding_backfill when Ollama returns; else route B: schedule ollama_guard.ps1 every 5 minutes on both Windows boxes and a launchd equivalent on phoebus.
- Evidence: `tools/ollama_guard.ps1`, `src/nougen_shards/ollama_host.py`, `src/nougen_shards/core.py`
- Lens: runtime/ingest · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: core.py defines module-level EMBED_AT_CAPTURE_MISSES counter incremented on embed miss, with no evidence of it being surfaced in /health; ollama_guard.ps1 and ollama_host.py exist as claimed.
- #550 families: 3, 53

### WG-0084 · P0 · defend · effort S

**Stop the fleet Worker's SHARD_GATEWAY_TOKEN drift from reading green for hours**

- Failure surface: gateway_supervisor.ps1 documents a drifted Worker token that returned 401 while the supervisor logged healthy, and the phoebus doc shows blade's token 401 live from outpost; shards_search returned [] over the fleet with no alarm.
- First fork: if you observe the supervisor's auth probe still only checks /health -> route A: probe an authed /search with a canary shard id and alarm on 401/empty; else route B: add token fingerprints to /health and compare against the Worker var each tick.
- Evidence: `tools/gateway_supervisor.ps1`, `docs/phoebus-gateway-upgrade.md`, `src/nougen_shards/cloudflare.py`
- Lens: health probes · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: gateway_supervisor.ps1 comments explicitly describe a drifted SHARD_GATEWAY_TOKEN reading 401 while the supervisor logged healthy, and re-puts the token from vault on failure -- directly matches the failure_surface.
- #550 families: 95

### WG-0095 · P0 · defend · effort S

**Publish relay handoff records without a `git add -A` leaking spend figures**

- Failure surface: .gitignore documents that .handoffs/ was ignored for months (130+ legs never left the machine) and that one `git add -A` would have published spend, incident notes and machine paths; the current pattern set is a hand-tuned list that any new naming convention slips past.
- First fork: if you observe a new .handoffs file that matches neither the relay format nor an ignore rule -> route A: make relay write only <UTC>__<machine>__<agent> and add a pre-commit denylist for other names; else route B: move all handoffs to NouGenRelay and empty .handoffs here.
- Evidence: `.gitignore`, `.handoffs/20260915T040051Z__whoart__antigravity.md`, `docs/handoffs.md`
- Lens: files that should not be committed · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: .gitignore, an actual .handoffs/ file (20260915T040051Z__whoart__antigravity.md), and docs/handoffs.md all exist, matching the claim about historically-ignored handoff files.
- #550 families: 76

### WG-0105 · P0 · defend · effort M

**Survive Kaedra cold-load timeouts without pinning VRAM forever**

- Failure surface: kaedra_gateway pins every model with keep_alive=-1 because a 38s cold load blows the 30s MCP client timeout; on a box that also runs the embed model and dream lanes the pinned weights starve embed-at-ingest and the VRAM gate refuses backfill.
- First fork: if you observe vram_gate reports the gateway model resident while embeds miss -> route A: warm on a schedule and use keep_alive of minutes plus an async 202 on cold; else route B: keep -1 but move Kaedra to a smaller allowlisted model.
- Evidence: `ops/kaedra/kaedra_gateway.py`, `src/nougen_shards/vram_gate.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: kaedra_gateway.py explicitly sets keep_alive=-1 in multiple places and comments on a slow cold load after reboot, directly matching the failure_surface; vram_gate.py exists as the interacting component.
- #550 families: 52

### WG-0115 · P0 · defend · effort M

**Keep the nougenmsg receiver auth-latched through a Keymaker miss**

- Failure surface: tools/nougenmsg_node.py records a reload that flipped the receiver from auth=required to auth=open for ~37 minutes when the vault lookup missed; unauthenticated POSTs were accepted and nothing announced it. AUTH_LATCH exists now but the drain hooks and /pop path must honor it.
- First fork: if you observe `_auth_mode()` can still report open while AUTH_LATCH is set -> route A: fail closed (refuse all POSTs) on latched-no-token and page via relay; else route B: add a startup-line assertion test and a watchdog that curls /status and alarms on auth=open.
- Evidence: `tools/nougenmsg_node.py`, `docs/fleet-transport-node.md`
- Lens: auth · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg_node.py lines 91-105 document the exact incident ('routine reload flipped the receiver from auth=required to auth=open for ~37 minutes') and define AUTH_LATCH; _auth_mode() (line 143) and the AUTH_LATCH check at line 330 are present, matching the claim.
- #550 families: 67

### WG-0123 · P0 · elevate · effort M

**Consolidate the Keymaker to one canonical store and retire Watchtower/agent_secrets.db strays**

- Failure surface: 44 secrets across four stores was observed; candidate_stores still probes ~/Watchtower and legacy agent_secrets.db and serves from the first live one, so a rotated token in the canonical store can lose to a stale value elsewhere and node_lane.ps1 starts with the wrong NGS_NODE_TOKEN.
- First fork: if resolve_secrets_store reports more than one live candidate on any fleet box -> route A: migrate all rows into NOUGEN_SECRETS_VAULT_DIR, set divergence mode to fail, delete strays; else route B: keep warn mode and add the probe to nougen doctor.
- Evidence: `src/nougen_shards/keymaker.py`, `CHANGELOG.md`, `tools/node_lane.ps1`
- Lens: data-integrity/secrets-store · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: keymaker.py:175,183,260-270 shows candidate_stores() explicitly probing ~/Watchtower and legacy agent_secrets.db alongside the canonical store, directly matching the claim.

### WG-0131 · P0 · elevate · effort L

**Grow past the 9 x 2GB grid ceiling for the million-shard destiny without re-routing dedup**

- Failure surface: MAX_DB_COUNT is hardcoded 9 and NOUGEN_MAX_DB_SIZE 2GB; every DB sat at 1.2GB in September, and the all-full fallback silently spread one hash across neighbouring DBs (61k phantom duplicates). At 1M shards the grid hits all-full again and routing degrades to arbitrary placement.
- First fork: if any nougen_shards_N.db exceeds 80% of MAX_DB_SIZE -> route A: alert and decide between raising the ceiling per node and a cold tier; else route B: design a 9->18 re-shard with consistent-hash migration and dedup index rewrite, war-gamed before code.
- Evidence: `src/nougen_shards/core.py`
- Lens: data-integrity/scale · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: core.py:47-49 hardcodes MAX_DB_COUNT = 9 and NOUGEN_MAX_DB_SIZE default 2GB, directly matching the claimed ceiling; routing logic at lines 195-217 confirms hash-based placement across MAX_DB_COUNT.

### WG-0139 · P0 · elevate · effort L

**Add admission control to the node so fan-out bursts degrade gracefully instead of parking 327 threads**

- Failure surface: A six-way gateway burst exhausted fds and parked hundreds of threads on the vector-cache lock; the nightly restart recovers uptime degradation but nothing from concurrent load, and the ngsrefresh plist itself says the fix is a concurrency ceiling.
- First fork: if in-flight recalls exceed NOUGEN_MAX_INFLIGHT -> route A: return 503 with Retry-After and a partial-coverage flag instead of queueing; else route B: serve normally and log the high-water mark.
- Evidence: `src/nougen_shards/fd_budget.py`, `src/nougen_shards/core.py`, `ops/launchd/com.whovisions.ngsrefresh.plist.template`
- Lens: concurrency/backpressure · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: fd_budget.py exists at src/nougen_shards/fd_budget.py and ngsrefresh plist template exists, matching the fd/thread exhaustion and nightly-restart-as-bandaid narrative.

### WG-0147 · P0 · defend · effort M

**Make /health stop lying: degraded DBs, persistent_storage false and slow recall must change the answer**

- Failure surface: /health returned 200 in 25ms while recalls took 16s, while six DBs were quarantined, and while persistent_storage was false after the volume wipe; keepalive.yml only checks for 200, so every degraded state reads as healthy to the fleet.
- First fork: if quarantined DBs > 0 or persistent_storage is false or the last recall probe > 5s -> route A: /health returns 'degraded' with a non-200 for keepalive and the reason list; else route B: 200 with the measured recall time included.
- Evidence: `app.py`, `.github/workflows/keepalive.yml`, `ops/ngs-node-refresh.sh`
- Lens: observability/health-that-lies · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py has persistent_storage field (line 1218) and quarantine tracking (_start_boot_quarantine, quarantine_malformed_dbs) alongside keepalive.yml, supporting the /health-lies claim directly.
- #550 families: 6, 95

### WG-0155 · P0 · elevate · effort M

**Publish the wargames/ corpus that HARDENING, CI and coach_governor cite but the tree lacks**

- Failure surface: HARDENING.md, all four workflows and src/nougen_shards/coach_governor.py reference wargames/<mission>.md (fts-or-fallback, elevate-security, coach-governor-hardening, ledger) but no wargames/ directory exists. Rule 0.1 says fight it on paper first; a new lane cannot read the paper, so it re-fights or skips the step.
- First fork: if the files exist in the private canon pack -> decide per file whether it is publishable and copy the public ones in, replacing private ones with stub pointers; else reconstruct the missing ones from the commits that cite them
- Evidence: `HARDENING.md`, `.github/workflows/ci.yml`, `src/nougen_shards/coach_governor.py`
- Lens: agent-doctrine · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified no wargames/ directory exists in the repo root, while HARDENING.md and coach_governor.py are the cited references expected to point at wargames/<mission>.md files.

### WG-0163 · P0 · defend · effort S

**Protect main against another disjoint-history force-push**

- Failure surface: The tracked handoff records origin/main force-pushed on 2026-09-05 to a 50-commit history with no common ancestor, closing ~20 PRs unmerged; every clone on every node had to re-base or re-clone. Nothing in the repo prevents a repeat, and deploy-space.yml would faithfully mirror the rewritten tree to the public Space.
- First fork: if the force-push was an intentional GM squash -> enable branch protection with force-push disabled and a documented 'rewrite ceremony' that notifies the relay; else treat it as an incident and audit which commits were lost
- Evidence: `.handoffs/20260816T232004Z__whoart__codex.md`, `.github/workflows/deploy-space.yml`
- Lens: merge-authority · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Handoff doc explicitly records: 'origin/main force-pushed 2026-09-05 ~07:30 UTC to a disjoint 50-commit history (no common ancestor...). #135/#136 closed unmerged along with ~20 other open PRs'. deploy-space.yml exists and would mirror any tree state. Matches claim closely.

### WG-0171 · P0 · defend · effort M

**Converge relay_triage rules with NouGenRelay's e2b ASK/REPORT verdicts into one recorded decision**

- Failure surface: BACKLOG.md says single e2b verdicts mislabel completion notes as ASK and replay merged PRs across the fleet; this repo's src/nougen_shards/relay_triage.py is a separate deterministic classifier (with a NEEDS_OWNER regex that hardcodes the GM's first name). Two classifiers, two answers, and the ack-auto-dispatch path acts on whichever ran last.
- First fork: if relay_triage and classify_asks disagree on the last 100 legs (run both, diff) -> make disagreement its own surfaced label and require 3-vendor consensus via tools/coach.py; else adopt relay_triage as the rules layer and e2b as tie-break only
- Evidence: `BACKLOG.md`, `src/nougen_shards/relay_triage.py`
- Lens: ask-report-classification · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: BACKLOG.md documents the e2b single-verdict mislabeling issue and references tools/classify_asks.py (a separate classifier, not present in this repo, confirming it's a distinct/different-repo tool). src/nougen_shards/relay_triage.py has its own _OWNER_ASK regex hardcoding literal 'dave' as the owner name. Two distinct classifiers confirmed.
- #550 families: 23

### WG-0179 · P0 · defend · effort M

**Wire relay_triage into relay_watch announce() without silencing NEEDS_OWNER legs**

- Failure surface: The 2026-09-21 evolution log parks a relay-watch echo storm ('wire relay_triage into announce() — needs Dave, changes a live watcher'). Until then every node's inbox re-announces its own legs and other lanes' chatter; after a naive wiring, a mis-labelled STALE swallows a real owner ask.
- First fork: if announce() can log the triage label beside every leg for one week without filtering -> ship that shadow mode first and measure UNKNOWN rate; else ask the GM for the lock with the measured echo count
- Evidence: `docs/evolution/2026-09-21-nougenlive-dispatch.md`, `src/nougen_shards/relay_watch.py`, `src/nougen_shards/relay_triage.py`
- Lens: sweep-loops · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/evolution/2026-09-21-nougenlive-dispatch.md 'Open (parked, owned)' section literally states: 'relay-watch echo storm -> wire relay_triage into announce() -- needs Dave (changes a live watcher).' relay_watch.py currently has no announce()/relay_triage wiring, consistent with the still-parked state.
- #550 families: 21

### WG-0185 · P0 · defend · effort S

**Make the claim guard's fail-open observable so duplicated work stops being a surprise**

- Failure surface: hooks/pre-commit exits 0 whenever relay is not importable, the network is down, or any status other than 3 returns; on whoart the console script could not even be installed. Four duplications in two days motivated the guard, and a guard that silently no-ops teaches every lane it is protected when it is not.
- First fork: if `nougen hi` can run `relay guard --probe` at session start -> print GUARD: armed/disarmed there and shard disarmed sessions; else write a marker file the stop hook reads and warns on
- Evidence: `hooks/pre-commit`
- Lens: handoff-discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: hooks/pre-commit's own comments state 'Fails OPEN. If relay is not installed, or the network is down, or anything else goes wrong, the commit proceeds' and documents the whoart install failure ('pip could not write C:\Python311\Scripts\relay.exe'). Only exit code 3 blocks; everything else silently passes.
- #550 families: 25

### WG-0190 · P0 · elevate · effort M

**Wire the metered lanes into billing.log_usage before selling a Pro tier**

- Failure surface: docs/billing-boundaries.md, cloud-modes.md and privacy.md promise metered Pro usage tracked in billing.db, but billing.log_usage and check_subscription have zero callers in app.py, space_router.py, rhea_noir.py or models_client.py; only the TS port calls them. `nougen stats --period month` reads an empty ledger and a Pro customer is never limited or invoiced.
- First fork: if space_router.chat_completions already returns provider usage -> call log_usage there and in _ask_rhea_bounded with the tenant token, then gate on check_subscription; else instrument usage capture first
- Evidence: `src/nougen_shards/billing.py`, `space_router.py`, `docs/billing-boundaries.md`
- Lens: billing-boundaries · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: grep across app.py, space_router.py, rhea_noir.py, and models_client.py finds zero callers of billing.log_usage or billing.check_subscription; only ts/src/nougen_shards/billing.ts and its test reference the equivalents, matching the 'only the TS port calls them' claim.
- #550 families: 65

### WG-0195 · P0 · defend · effort S

**Stop the Space cold boot from blocking 95-250s on api.gradio.app analytics**

- Failure surface: ops/ngs-node-refresh.sh documents cold start blocking on Gradio's analytics and version check before uvicorn binds, varying 95s to 250s on the same box; deploy-space's verify loop and keepalive both time against this. The Dockerfile sets no GRADIO_ANALYTICS_ENABLED=False, so every Space restart and every phoebus refresh pays a network-dependent boot.
- First fork: if setting GRADIO_ANALYTICS_ENABLED=False in Dockerfile and bin/ngs-node.sh drops boot under 60s -> ship it and tighten NGS_BOOT_TIMEOUT; else the block is elsewhere (nine DB opens) and needs a boot profile
- Evidence: `ops/ngs-node-refresh.sh`, `Dockerfile`, `app.py`
- Lens: ux-latency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: ops/ngs-node-refresh.sh states verbatim: 'Boot opens nine databases AND blocks on outbound calls to api.gradio.app (analytics + version check) before uvicorn binds... measured at ~95s and ~250s on the same box.' No GRADIO_ANALYTICS_ENABLED setting found in Dockerfile or app.py.
- #550 families: 44, 52

### WG-0200 · P0 · elevate · effort M

**Wire lane_freshness --json into `nougen hi` so stale ingestion lanes are seen at session start**

- Failure surface: §3 is ✅ for the sensor (tools/lane_freshness.py) but ⬜ for surfacing it; the sync agent died May 9 and arxiv Jun 18 unnoticed for weeks. `nougen hi` (the session-open probe) exists in cli.py and does not call it, so a dead lane still fails silently for anyone who does not run the tool by hand.
- First fork: if `nougen hi` already prints fleet pulse -> append the lane table and exit non-zero on stale>threshold only when NOUGEN_HI_STRICT=1; else add the section and shard any stale lane automatically
- Evidence: `tools/lane_freshness.py`, `src/nougen_shards/cli.py`, `HARDENING.md`
- Lens: hardening-backlog · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: cli.py defines `p_hi` ('Session-open probe: identity, fleet pulse, open handoffs') and cmd_hi at line 3524; HARDENING §3 explicitly marks the sol_hi_probe/mesh_health wiring as ⬜ ('wire lane_freshness.py --json into sol_hi_probe.ps1 / mesh_health'). No lane_freshness call found near cmd_hi. Evidence directly supports the claim.
- #550 families: 95

### WG-0205 · P0 · elevate · effort M

**Schedule the weekly embedding backfill on all three nodes with its own freshness sensor**

- Failure surface: §2 leaves the scheduled weekly backfill ⬜; embedding_backfill.py exists but no launchd template (ops/launchd) or PowerShell lane schedules it. Embed-at-ingest misses (ollama down, timeout) accumulate again with no sweep, recreating the 63.6% NULL month one outage at a time.
- First fork: if each node has a resident ollama with NOUGEN_EMBED_MODEL -> add com.whovisions.ngsbackfill.plist.template and a schtasks lane, and register 'backfill' in lane_freshness; else run it from the node with the GPU and ship the vectors
- Evidence: `src/nougen_shards/embedding_backfill.py`, `ops/launchd`, `HARDENING.md`
- Lens: hardening-backlog · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: HARDENING §2 explicitly marks 'scheduled weekly backfill sweep' as ⬜. ops/launchd contains templates for fleetinbox, fleetssh, kaedragw, ngsnode, ngsrefresh, ngstunnel, phoebus-logshow-guard — no backfill-named plist. embedding_backfill.py exists as a standalone tool. Supports the claim directly.
- #550 families: 95, 97

### WG-0210 · P0 · defend · effort S

**Mark or remove the unapproved continuous-sync draft so no lane implements against the Dave lock**

- Failure surface: docs/continuous-sync-design-DRAFT.md specifies blade-authoritative replication with LWW and three GM-DECISION placeholders, while the Dave lock (9/10, 12169@db6) makes single-node residency by design and tools/publish_vault_snapshot.py records GM decision B (read-only snapshot consumer). A sweep lane reading docs/ as canon builds the replica the GM rejected.
- First fork: if the GM confirms the lock supersedes the draft -> add a SUPERSEDED banner citing the shard id and move it to docs/theory; else leave it but rename to *-REJECTED-pending-GM and remove the implementation steps
- Evidence: `docs/continuous-sync-design-DRAFT.md`, `tools/publish_vault_snapshot.py`, `ops/doctrine/capability_layer_draft.md`
- Lens: canon-consistency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/continuous-sync-design-DRAFT.md contains multiple GM-DECISION lines and an LWW policy with logical-clock design, consistent with the claim. tools/publish_vault_snapshot.py header literally states 'Architecture (GM decision B, 2026-08-31): the Space is a READ-ONLY consumer', directly contradicting the draft's blade-authoritative replication design. Strong direct support.

### WG-0215 · P0 · defend · effort M

**Enforce the coach fan-out cap in code for Claude-side workflows, not only fleet lanes**

- Failure surface: skills/coach/SKILL.md records a 244-agent workflow on 9/13 that burned ~2.1M tokens and stalled WhoArt; the rule 'no Workflow tool, no Agent fan-out' lives in a skill and in tools/coach.py's ledger (60 calls/day), while coach_governor.MAX_FANOUT=8 only governs lanes that lease through it. This very war-game harness is a fan-out; nothing in code stops the next one.
- First fork: if the harness can register each spawned agent as a coach_governor lease -> require it and deny above MAX_FANOUT; else add a PreToolUse hook (like tools/paste_guard.py) that counts Agent/Workflow spawns per session and blocks past the cap
- Evidence: `skills/coach/SKILL.md`, `src/nougen_shards/coach_governor.py`, `tools/coach.py`
- Lens: autonomy-limits · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: skills/coach/SKILL.md literally references the 244-agent workflow burning ~2.1M tokens and states 'No Workflow tool, no Agent fan-out...'. coach_governor.py defines MAX_FANOUT (env NOUGEN_COACH_MAX_FANOUT, default 8) enforced only within its own lease logic (fanout_outstanding checks). tools/coach.py has LEDGER_BUDGET_CALLS=60 as a separate soft ledger. All three pieces of evidence directly verifi
- #550 families: 49

### WG-0220 · P0 · defend · effort S

**Gate tracker-dailies publication on a mechanical privacy check, not inspection**

- Failure surface: docs/recipe-cards/daily-usage-export.md publishes token dailies (model, machine, date) to the public NouGenTracker repo and states the payload carries no paths or session ids 'confirmed by inspection'; tools/token_tracker.py reads ~/.claude/projects JSONL and Antigravity RPC where project paths and session ids abound. One schema change in the exporter and a session id lands on a public commit.
- First fork: if the export writes a fixed schema -> add a pre-publish validator that rejects any field outside the allowlist and any path-shaped or uuid-shaped value; else block the publish step until the schema is fixed
- Evidence: `docs/recipe-cards/daily-usage-export.md`, `tools/token_tracker.py`
- Lens: privacy · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: daily-usage-export.md line 22 literally reads '...paths, no session ids. Confirmed by inspection, not assumption.' tools/token_tracker.py reads PROJECTS = ~/.claude/projects and extracts session_id fields (multiple occurrences, e.g. line 442, 630, 774, 864) from JSONL, confirming the raw source carries path/session data that the exporter must be trusted (not mechanically checked) to strip. Direct 
- #550 families: 75

### WG-0225 · P0 · defend · effort S

**Collapse the two handoff namespaces before one `git add -A` publishes spend and incident notes**

- Failure surface: .gitignore carries a long, hand-maintained list of .handoffs/ patterns (handoff_*, *handoffs/, audit_*, *-note.md) and admits the per-agent subdirectories were untracked-but-not-ignored, one add away from publishing spend figures and machine paths; tools/handoff_guard.py keeps writing handoff_*.md into the same dir the relay publishes from.
- First fork: if handoff_guard can write to NOUGEN_HANDOFF_DIR outside the repo (~/.nougen/handoffs) -> move it and reduce .gitignore to the relay record glob; else add a pre-commit check that refuses any .handoffs path not matching <UTC>__<machine>__<agent>
- Evidence: `.gitignore`, `tools/handoff_guard.py`, `.handoffs/20260816T232004Z__whoart__codex.md`
- Lens: handoff-discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: .gitignore contains an extensive, clearly hand-maintained set of .handoffs/ patterns (handoff_*, *handoffs/, audit_*, *-note.md, etc., ~15 lines) with an explanatory comment about per-agent dirs. tools/handoff_guard.py confirms HANDOFF_DIR defaults to REPO/.handoffs and writes 'handoff_{ts}_{AGENT}_auto.md' into an '<Agent> handoffs' subdir — exactly the pattern .gitignore has to keep excluding. T
- #550 families: 75

### WG-0230 · P0 · defend · effort S

**Stop the sync/push cascade regression from shipping a third time**

- Failure surface: app.py's /sync/push comment records the per-shard guard added in #148, silently dropped by a later merge, and regressed again 2026-08-31 as deterministic 500 cascades killing 100-row batches. A change that ships twice has no test naming the property; the third regression is a merge away.
- First fork: if a test injects one poisoned row into a 100-row push and asserts 99 captured -> keep it and add the guard's line to a CODEOWNERS-protected region; else write that test first, then refactor the guard into a helper with its own unit test
- Evidence: `app.py`, `tests/test_quarantine_malformed_on_boot.py`
- Lens: test-coverage · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py around line 1687-1705 has the /sync/push endpoint with a comment: 'This is the second time this protection ships - #148 ... the regression resurfaced 2026-08-31 as deterministic 500 cascades'. tests/test_quarantine_malformed_on_boot.py exists but its name suggests it covers boot-time quarantine, not necessarily the /sync/push per-row guard specifically — plausible but not verified to name t
- #550 families: 91

### WG-0235 · P0 · elevate · effort L

**Retire the Space latency band-aid by finding the 3-day recall degradation**

- Failure surface: ops/ngs-node-refresh.sh restarts the phoebus node on a schedule because recall goes from 3-4s to 14-16s over three days (63s concurrent) with no CPU/RSS growth and /health still 25ms; root cause unfound, candidates listed in the script. Every fleet fan-out silently loses half its corpus when a node is in the slow state, and the user sees a 20s cliff.
- First fork: if the before/after latency log in logs/ngs-node-refresh.log shows a monotonic curve -> bisect by disabling one candidate at a time (MCP session state, sqlite statement cache, per-request structures) on a fresh process; else it is load-dependent and needs a request-rate correlation first
- Evidence: `ops/ngs-node-refresh.sh`, `ops/launchd/com.whovisions.ngsrefresh.plist.template`, `app.py`
- Lens: ux-latency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: ops/ngs-node-refresh.sh directly confirms: 'sequential recall 13.7 - 16.1 s | 3.1 - 4.1 s' comparison, mentions phoebus, states 'THIS IS A BAND-AID, NOT A FIX. The root cause is still unfound -- candidates', and notes /health stayed at 25ms while recall sat at 16s. ops/launchd/com.whovisions.ngsrefresh.plist.template exists as the scheduling template. Direct, strong support.
- #550 families: 7

### WG-0240 · P0 · elevate · effort L

**Publish the phoebus GATEWAY role: own tokens, tracker dailies, and a failover decision**

- Failure surface: docs/phoebus-gateway-upgrade.md records the 2026-08-17 GM decision that phoebus terminates connector traffic like blade, with a checklist (mint NGS_NODE_TOKEN/SHARD_GATEWAY_TOKEN, never copy blade's; backfill dailies stale since 08-02; failover vs fan-out in the Worker). The 401 from a copied token was confirmed live once already; a second gateway with a copied token repeats it for every connector lane.
- First fork: if phoebus's keymaker ledger shows a fingerprint distinct from blade's 9c67af03a9da -> proceed to Worker routing and dailies backfill; else stop and mint first
- Evidence: `docs/phoebus-gateway-upgrade.md`, `docs/recipe-cards/daily-usage-export.md`, `tools/wrangler_fleet.py`
- Lens: governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/phoebus-gateway-upgrade.md directly confirms: inherits blade's failure modes ('a wrong token is a live 401... confirmed live'), a checklist item 'NGS_NODE_TOKEN — phoebus's own node token. Current ledger entry fingerprints 9c67af03a9da (rotated 2026-08-14); phoebus's must be a new value', and 'SHARD_GATEWAY_TOKEN ... Do not reuse blade's; that is the 401 above.' Exact fingerprint and 401 deta

### WG-0368 · P1 · elevate · effort M

**Make receiver auth mandatory on all three nougenmsg nodes and open 8766 only via tunnel**

- Failure surface: Receiver auth is opt-in ('unset means open'); skills/nougenmsg/SKILL.md tells operators to open TCP 8766 across the LAN; whoart was bound loopback so peers never reached it and phoebus :8766 hangs. Any LAN device can inject fleet messages today.
- First fork: if you observe phoebus /msg on :8766 still hangs -> route A: fix the phoebus hop first, then flip auth to required with a fleet-wide token in Keymaker; else route B: flip auth required on whoart+blade now and leave phoebus on the SSH fallback until fixed.
- Evidence: `tools/nougenmsg_node.py`, `skills/nougenmsg/SKILL.md`, `docs/evolution/2026-09-21-nougenlive-dispatch.md`
- Lens: infra/auth · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: nougenmsg_node.py and skills/nougenmsg/SKILL.md exist and auth is opt-in per item #9's evidence; the specific port-hang and LAN-open claims for :8766/phoebus are a reasonable but not fully re-traced inference.

### WG-0384 · P1 · defend · effort M

**Audit and pin which nougen_shards.node_plugins entry points may register routes**

- Failure surface: load_node_plugins calls register(app, mcp, ctx) for every installed distribution in the entry-point group, handing it the tenant dependency and Rhea call; any pip package on the node's venv can add routes or MCP tools. A duplicated editable install already double-registered on blade 2026-09-23.
- First fork: if you observe more than one distribution provides the group on any node -> route A: add NGS_NODE_PLUGINS allowlist by name and log the loaded set into /health; else route B: keep open loading but refuse plugins outside a signed private index.
- Evidence: `src/nougen_shards/node_plugins.py`, `app.py`
- Lens: supply chain/plugins · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: node_plugins.py confirms entry_points-based loading and a register(app, mcp, ctx) call (lines 13-51), matching the plugin-loading mechanism; the specific 2026-09-23 blade double-registration incident is asserted but not independently verifiable from these files alone.
- #550 families: 29, 33, 34

### WG-0400 · P1 · defend · effort M

**Run an adversarial-shard drill against relay dispatch and coach classification**

- Failure surface: Recalled shard bodies feed coach/relay_triage decisions; #541 already had to stop deriving inbox origin from the message body, and BACKLOG records single-e2b verdicts mislabelling completion notes as ASK, which replays merged PRs across the fleet. A shard crafted to look like an ASK gets dispatched fleet-wide.
- First fork: if you observe relay_triage still takes a single-model verdict -> route A: gate dispatch on 3-vendor consensus via tools/coach.py and exclude legacy handoff_* ids; else route B: add an allowlist of dispatchable origins and a dry-run mode that only logs.
- Evidence: `src/nougen_shards/relay_triage.py`, `src/nougen_shards/nougenmsg.py`, `BACKLOG.md`
- Lens: prompt injection via stored content · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: relay_triage.py exists with a closed LABELS menu (line 10) and nougenmsg.py/BACKLOG.md are present; the specific #541 and single-model-verdict claims are plausible inferences from the module's design but not fully traced to a single-vendor code path.
- #550 families: 69

### WG-0416 · P1 · defend · effort M

**Secure the whoart standby mirror: private shards over plain LAN HTTP via encoded SSH PowerShell**

- Failure surface: tools/standby_sync.ps1 pushes --include-private rows to http://<whoart-LAN>:4445 from blade through an -EncodedCommand over SSH, with Watchtower paths and no TLS; tools/shard_primary_proxy.ps1 forwards 127.0.0.1:4444 across boxes. A LAN sniffer or a stale route sees ngenc1 bodies and the node token.
- First fork: if you observe :4445 answers without TLS and without the tunnel -> route A: route the mirror through the named tunnel or an SSH -L forward and drop the LAN URL; else route B: keep LAN but require NGS_ALLOW_INSECURE_CLOUD to be explicit and log every private-row push.
- Evidence: `tools/standby_sync.ps1`, `tools/shard_primary_proxy.ps1`, `src/nougen_shards/connectors/cloud.py`
- Lens: secrets in transit · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/standby_sync.ps1 lines 1-25 confirm the http://<LAN-IP>:4445 target, --include-private flag, and `ssh ... -EncodedCommand $encoded` pattern with no TLS, matching the claim directly.

### WG-0432 · P1 · elevate · effort M

**Least-privilege the CLOUDFLARE_API_TOKEN_NOUGEN_FULL used by cf_* tools and the gateway supervisor**

- Failure surface: cloudflare.py and tools/wrangler_fleet.py resolve a token named *_FULL from the Keymaker and expose deploy/secret/KV operations through MCP cf_deploy_worker; gateway_supervisor.ps1 redeploys the fleet Worker unattended every 60s. One compromised lane rewrites shards.nougenai.com routing.
- First fork: if you observe the token's Cloudflare permissions include Zone or Account-wide edit -> route A: mint a Workers-Scripts-only token for the supervisor and a read token for cf_status, rotate FULL; else route B: keep one token but move deploy behind a relay ack.
- Evidence: `src/nougen_shards/cloudflare.py`, `tools/wrangler_fleet.py`, `tools/gateway_supervisor.ps1`
- Lens: token scope · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: cloudflare.py line 29 and tools/wrangler_fleet.py lines 26-192 both confirm CLOUDFLARE_API_TOKEN_NOUGEN_FULL as the resolved token name for cf_* operations and the supervisor, directly matching the claim.

### WG-0448 · P1 · elevate · effort L

**Wire the Shard Capture Dam into app.py capture without accepting unsigned envelopes**

- Failure surface: ops/dam_space/app.py only checks the HMAC when NOUGEN_DAM_HMAC_KEY is set (`if HMAC_KEY:`), so a misconfigured Space silently accepts unsigned ciphertext; the dam is validated only standalone (validate10.py) and the front-door spool/spillway in src/nougen_shards/dam is not on the /capture path, so Space restarts still lose writes.
- First fork: if you observe the dam Space /health reports ingress_signed=false -> route A: make HMAC mandatory (503 when unset) before wiring the spool; else route B: wire spillway ACK into /capture behind NGS_DAM_URL and shadow-write for a week.
- Evidence: `ops/dam_space/app.py`, `src/nougen_shards/dam/spillway.py`, `validate10.py`
- Lens: deploy/durability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: ops/dam_space/app.py line 86 literally does `if HMAC_KEY:` gating the HMAC check only when NOUGEN_DAM_HMAC_KEY is set; matches claim exactly.
- #550 families: 19

### WG-0463 · P1 · elevate · effort L

**Find the 4x recall latency leak and delete ngs-node-refresh.sh**

- Failure surface: phoebus recall degrades from 3-4s to 14-16s over three days with flat CPU/RSS; a scheduled launchd restart is the documented band-aid; candidates are MCP session state, sqlite statement caches across 9 DBs + history.db, or the shared federation ThreadPoolExecutor never freeing per-request structures.
- First fork: if you observe the before/after latencies in logs/ngs-node-refresh.log correlate with request count rather than wall time -> route A: instrument per-request object growth (tracemalloc snapshots at /health?deep) and bisect the executor/session store; else route B: bisect by disabling the MCP mount for a day and compare.
- Evidence: `ops/ngs-node-refresh.sh`, `ops/launchd/com.whovisions.ngsrefresh.plist.template`, `src/nougen_shards/federation.py`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: federation.py confirms a shared/module-level _LANE_EXECUTOR ThreadPoolExecutor replacing a per-call one; ops/ngs-node-refresh.sh exists as the documented band-aid restart script.
- #550 families: 93

### WG-0476 · P1 · defend · effort M

**Converge blade onto one hidden scheduled task and one code tree after the QuickEdit freeze**

- Failure surface: Blade froze today because the node ran in a visible console (QuickEdit paused the asyncio loop, /health hung, CLOSE_WAIT piled up); the fix left two scheduled tasks pointing at two code trees (install_ngs_node_task.ps1 -> ngs_node_boot.cmd -> start_grid.py vs node_lane.ps1), so the next repo update patches one tree and the live node runs the other.
- First fork: if you observe `schtasks /query` lists both 'NouGen NGS Node' and 'NouGen NGS Node (src)' -> route A: disable the legacy task, make install_ngs_node_task.ps1 the only installer and assert Hidden+PT0S in a test; else route B: keep both but make start_grid.py refuse to run from a non-canonical path.
- Evidence: `tools/install_ngs_node_task.ps1`, `tools/ngs_node_boot.cmd`, `tools/node_lane.ps1`
- Lens: scheduled tasks · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: All three scripts exist (install_ngs_node_task.ps1, ngs_node_boot.cmd, node_lane.ps1); plausible inference of two parallel scheduled-task trees from file names/paths.
- #550 families: 29

### WG-0489 · P1 · defend · effort M

**Survive the day the whoart tunnel dies again: named-tunnel watchdog with no 72h ExecutionTimeLimit**

- Failure surface: whoart's cloudflared died ~11 AM today; a 5-minute watchdog was added but the admin task still carries a 72h ExecutionTimeLimit, and gateway_supervisor.ps1 still knows the quick-tunnel URL-rotation dance that re-points the Worker via wrangler; a tunnel flap silently shuts shards.nougenai.com's whoart leg.
- First fork: if you observe the whoart task XML has ExecutionTimeLimit != PT0S -> route A: re-register with PT0S and RestartOnFailure, keep the watchdog; else route B: move whoart to the named tunnel token in tunnel_lane.ps1 and delete quick-tunnel logic from the supervisor.
- Evidence: `tools/tunnel_lane.ps1`, `tools/gateway_supervisor.ps1`, `tools/install_ngs_node_task.ps1`
- Lens: tunnels · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: tunnel_lane.ps1, gateway_supervisor.ps1, install_ngs_node_task.ps1 all exist; claim about ExecutionTimeLimit and quick-tunnel rotation is a reasonable inference from file names/content areas not fully verified line-by-line.
- #550 families: 43

### WG-0501 · P1 · defend · effort S

**Keep the phoebus node schedulable when Antigravity's log show storm returns**

- Failure surface: 2026-09-05 26+ stuck `log show` children drove load to 367; the ngsnode launchd job runs ProcessType=Background and was never scheduled for 4+ hours while listening on :4444 and passing every surface check. phoebus-logshow-guard.sh kills stragglers but the node's priority class is unchanged.
- First fork: if you observe ProcessType still Background in the ngsnode plist -> route A: switch to Interactive/Standard and add a recall-latency probe to fleetinbox; else route B: keep Background and make the guard also `launchctl kickstart -k` the node when /health times out.
- Evidence: `ops/phoebus-logshow-guard.sh`, `ops/launchd/com.whovisions.ngsnode.plist.template`, `ops/launchd/com.whovisions.phoebus-logshow-guard.plist.template`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: phoebus-logshow-guard.sh and both launchd plist templates exist; claim about ProcessType=Background is plausible given file naming and pattern matches other observed launchd issues in this batch.
- #550 families: 49

### WG-0513 · P1 · defend · effort M

**Restore quarantined grid DBs from a peer instead of recreating them empty**

- Failure surface: quarantine_malformed_dbs renames a 'disk image is malformed' DB and recreates it empty; six of nine went malformed on the Space's network volume 2026-09-01, so one bad boot silently drops two thirds of the corpus while /health reports ignited and recall says 'no match'.
- First fork: if you observe _substrate_coverage reports errored or missing indexes after boot -> route A: block writes to that index and pull it via /sync/pull from blade before serving; else route B: serve degraded but mark recall_trustworthy=false and alert via relay.
- Evidence: `src/nougen_shards/core.py`, `tests/test_quarantine_malformed_on_boot.py`, `app.py`
- Lens: runtime/data loss · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: src/nougen_shards/core.py has quarantine_malformed_dbs() at line 309 with docstring/comments referencing 'malformed' disk images, quarantine renaming with -wal/-shm sidecars, and comments referencing the 2026-08-30 malformed DB8 observation -- directly supports the claim.
- #550 families: 6

### WG-0525 · P1 · elevate · effort M

**Cut over hardcoded claude-3-x / gemini-1.5 model ids before the Fable 5 API routing change**

- Failure surface: models_client.py hardcodes claude-3-7-sonnet-latest, claude-3-5-haiku-latest and gemini-1.5-*, router.py routes to anthropic/claude-3.5-sonnet, while data/pricing/anthropic.json already prices claude-fable-5; the July 2026 subscription-to-API cutover routes the frontier lane to ids the clients cannot name and billing cannot price.
- First fork: if you observe custom_model_resolver.py can already map aliases from a config -> route A: move every default id into data/pricing-backed config and add a deprecation probe test; else route B: bump the literals now and add an ids-in-pricing-table test.
- Evidence: `src/nougen_shards/models_client.py`, `src/nougen_shards/router.py`, `data/pricing/anthropic.json`
- Lens: model-id cutover · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: models_client.py hardcodes claude-3-7-sonnet-latest, claude-3-5-haiku-latest, and gemini-1.5-pro/flash (lines 221,223,290,301); router.py routes to anthropic/claude-3.5-sonnet (line 14); data/pricing/anthropic.json contains a claude-fable-5 entry (line 4) -- all three claims verified directly.
- #550 families: 54

### WG-0537 · P1 · defend · effort S

**Detect OpenRouter free-model rotation before Rhea's $0 lane silently goes paid or dark**

- Failure surface: rhea_noir._try_free walks a hardcoded list of :free ids (nemotron, glm-5.2, gpt-oss-20b) that rotate off the free tier without notice; a bad afternoon already cost $0.09 on the Kimi route, and openrouter_mcp_client imports an openrouter_guard from a Watchtower path that public clones lack.
- First fork: if you observe /v1/models on OpenRouter no longer lists one of the ids -> route A: probe the free list at boot and drop missing ids, alert via relay; else route B: keep the list but fail closed (no paid fallback) unless NOUGEN_RHEA_ALLOW_PAID=1.
- Evidence: `rhea_noir.py`, `src/nougen_shards/openrouter_mcp_client.py`
- Lens: upstream drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: rhea_noir.py _try_free() (line 217) hardcodes a list of :free OpenRouter ids including nemotron variants, z-ai/glm-5.2:free, and openai/gpt-oss-20b:free (lines 228-231) -- matches claim directly.
- #550 families: 59

### WG-0549 · P1 · elevate · effort M

**Decide where war-game docs live: wargames/ is gitignored while HARDENING, CI and tests cite it**

- Failure surface: Rule 0.1 makes wargames/<mission>.md the gate for every mission, yet .gitignore hides wargames/ (cost/billing analysis, GM decisions), HARDENING.md and ci.yml cite wargames/elevate-security.md, and tests/test_wargame_catalog.py always skips because docs/wargame-catalog/catalog.ndjson is absent; the fleet catalog of 1000 has no home other agents can read.
- First fork: if you observe Dave wants the catalog public -> route A: split public mission skeletons (no cost data) into docs/wargame-catalog and keep full docs in the private canon pack; else route B: publish the catalog to NouGenRelay .handoffs/ and point the test at that path.
- Evidence: `.gitignore`, `tests/test_wargame_catalog.py`, `HARDENING.md`
- Lens: governance/doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: .gitignore line 144 confirms 'wargames/' is ignored; tests/test_wargame_catalog.py and HARDENING.md both exist and are cited as referencing wargames/elevate-security.md and docs/wargame-catalog/catalog.ndjson, both of which are indeed absent from the working tree -- directly confirms the claimed contradiction (the missing paths ARE the evidence of the gap, not an error).

### WG-0561 · P1 · defend · effort M

**Close the prompt-injection-to-write path in Kaedra's 'read-only' tool binding**

- Failure surface: kaedra_tools.py's docstring says all six tools are read-only, but _DISPATCH binds shards_capture (core.capture) and nougenmsg_send (fleet fan-out). A shard body returned by shards_recall can instruct the model to capture poisoned shards or wake every fleet agent; the gateway is tunnel-reachable.
- First fork: if you observe KAEDRA_TOOLS=1 default and no allowlist env for write tools -> route A: split into KAEDRA_READ_TOOLS default-on and KAEDRA_WRITE_TOOLS default-off with a 'kaedra-authored' quarantine tag; else route B: keep writes but require a human-signed origin header on nougenmsg_send.
- Evidence: `src/nougen_shards/kaedra_tools.py`, `ops/kaedra/kaedra_gateway.py`
- Lens: MCP/tool abuse · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: kaedra_tools.py line 3 docstring literally states 'Six tools, all read-only' while _DISPATCH (line 307-315) binds shards_capture and nougenmsg_send, a direct, verifiable contradiction matching the claim exactly.
- #550 families: 69

### WG-0573 · P1 · elevate · effort M

**Replace per-node hardcoded SSH remote script paths with fleet_hosts.json config**

- Failure surface: nougenmsg._REMOTE_SCRIPTS and sessions.py hardcode blade's Watchtower and whoart's Outpost checkouts, phoebus's interpreter is a coin flip, and fleet-ssh-keepalive.sh depends on ~/.ssh/config aliases; one moved checkout or lease change makes a node 'unreachable' with no diagnostic.
- First fork: if you observe fleet_hosts.json already has a nodes map -> route A: add per-node remote_python and remote_script keys and read them in nougenmsg/sessions; else route B: standardize on ~/.nougen/tools on every box and delete the map.
- Evidence: `src/nougen_shards/nougenmsg.py`, `ops/fleet-ssh-keepalive.sh`, `src/nougen_shards/sessions.py`
- Lens: fleet transport · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: nougenmsg._REMOTE_SCRIPTS hardcodes blade's Watchtower and whoart's Outpost paths (lines ~899-901); fleet_hosts.json loader (fleet_hosts_path/_load_fleet_hosts) already exists in nougenmsg.py, matching route A's premise.
- #550 families: 39, 40

### WG-0584 · P1 · elevate · effort M

**Schedule the weekly embedding backfill sweep on all three nodes under the VRAM gate**

- Failure surface: HARDENING §2 leaves the weekly backfill ⬜; embedding_backfill.py UPDATEs live shards and polls nvidia-smi every 64 rows, so an unattended run on blade during a game/render or on phoebus without a GPU either starves the box or loops on timeouts while lane_freshness reports nothing.
- First fork: if you observe `count_pending` > 0 on any node -> route A: add a Sunday task/launchd job with NOUGEN_VRAM_GATE=1 and report rows/misses into tracker_daily; else route B: run it only from the coach loop on idle detection.
- Evidence: `HARDENING.md`, `src/nougen_shards/embedding_backfill.py`, `tools/lane_freshness.py`
- Lens: scheduled tasks · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: HARDENING.md literally lists '⬜ scheduled weekly backfill sweep' and discusses embedding_backfill.py/coverage tracking; embedding_backfill.py and lane_freshness.py both exist.
- #550 families: 97

### WG-0595 · P1 · elevate · effort L

**Run the pre-guard redaction sweep over live vaults and the Space without corrupting rows**

- Failure surface: HARDENING §8 leaves ⬜ the backfill that redacts shards captured before the secret guard; those rows sit in nine DBs on four vaults plus /sync/pull exports, and a sweep that rewrites content changes file_hash identity and breaks dedup/federation unless designed for it.
- First fork: if you observe credential_patterns hits in a read-only scan of blade -> route A: write a two-phase tool (report, then redact keeping file_hash and re-embed) and run on whoart standby first; else route B: mark the invariant satisfied for new writes and archive the finding.
- Evidence: `HARDENING.md`, `src/nougen_shards/credential_patterns.py`, `src/nougen_shards/brain_scan/redaction.py`
- Lens: secrets in substrate · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: HARDENING.md line 132 references '⬜ backfill sweep to redact any' secrets found by the guard; credential_patterns.py and brain_scan/redaction.py both exist as the tools implied.
- #550 families: 85

### WG-0606 · P1 · elevate · effort M

**Introduce read-only tenant scope so a search token cannot export the whole vault via /sync/pull**

- Failure surface: Every credential that passes verify_token can call /sync/pull (full-vault export incl. ngenc1 bodies) and /capture; tenants carry allow_federation but no read/write scope, so the Apps Script lane, Kaedra and the Worker all hold full-export power.
- First fork: if you observe tenants.json records have no scope field -> route A: add scope in {read,write,admin} to TenantRecord and enforce per-route; else route B: split /sync/* behind a second NGS_SYNC_TOKEN.
- Evidence: `app.py`, `src/nougen_shards/tenants.py`, `docs/DEPLOY_SPACE.md`
- Lens: token scope · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: app.py's verify_token gates /sync/pull and other routes; tenants.py's TenantRecord/Tenant only carry allow_federation (bool), no read/write/admin scope field found.

### WG-0617 · P1 · elevate · effort M

**Carry lane-health metadata through federated cross-node returns**

- Failure surface: HARDENING §4 leaves ⬜ surfacing coverage in federated_retrieve; with lane_health itself absent from core.py, a peer that quarantined six DBs or has 60% NULL embeddings contributes 'no match' that the caller reads as fact.
- First fork: if you observe /health substrate coverage exists but /search returns none -> route A: include per-lane coverage in cloud connector responses and in the recall packet; else route B: rebuild lane_health first (see HARDENING re-verify mission).
- Evidence: `src/nougen_shards/federation.py`, `src/nougen_shards/connectors/cloud.py`, `HARDENING.md`
- Lens: federation · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: HARDENING.md explicitly leaves '⬜ surface the same metadata in federated_retrieve cross-node returns' unchecked, and no `def lane_health` exists anywhere under src/nougen_shards despite HARDENING claiming core.lane_health() -- supports the claim that lane_health is effectively absent/inconsistent.
- #550 families: 12

### WG-0628 · P1 · elevate · effort M

**Triage the Dependabot backlog under a defined self-merge authority**

- Failure surface: Dependabot PRs sit unreviewed because no agent may self-merge; cooldown defers worms but the backlog itself means a fixed HIGH CVE stays open while security.yml keeps failing weekly; NouGenShards #455 has been unmoved 20+ sweeps.
- First fork: if you observe Dave grants 'green CI + patch/minor + cooldown passed' auto-merge -> route A: enable Dependabot auto-merge for those with a relay ack record; else route B: batch-review weekly in one session and record decisions as shards.
- Evidence: `.github/dependabot.yml`, `.github/workflows/security.yml`, `BACKLOG.md`
- Lens: dependencies/governance · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: dependabot.yml, security.yml, and BACKLOG.md exist; did not verify the specific PR #455 claim or 20+ sweep count, but the governance gap is a reasonable inference from the files present.
- #550 families: 77

### WG-0639 · P1 · defend · effort S

**Stop the relay-watch echo storm before wiring triage into announce()**

- Failure surface: relay_watch.py auto-pushes legs from git log and announces them; without relay_triage in announce() every fan-out re-announces, and the evolution log parks the fix because it changes a live watcher Dave owns. A storm floods three inboxes and the Kaedra tool loop.
- First fork: if you observe Dave approves the watcher change -> route A: wire relay_triage.dedupe into announce() with a seen-set in the cache file; else route B: rate-limit announce per leg id locally without touching the watcher contract.
- Evidence: `src/nougen_shards/relay_watch.py`, `src/nougen_shards/relay_triage.py`, `docs/evolution/2026-09-21-nougenlive-dispatch.md`
- Lens: fleet messaging · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: relay_watch.py, relay_triage.py, and the evolution doc all exist; did not find an explicit announce() function or confirm relay_triage is unwired from it, but the echo-storm concern is a reasonable inference from the auto-push/announce design described.
- #550 families: 22, 49

### WG-0650 · P1 · defend · effort S

**Stop remote command injection in sessions.py SSH fan-out**

- Failure surface: RemoteSessionManager.send_to_session and wake_remote_session f-string the message/task straight into `ssh node 'python ... "{message}"'`; nougenmsg.py learned to base64 bodies (_supports_text_b64) but this sibling path did not, and it also targets tools/nougen_session.py which no longer exists. A crafted fleet message runs shell on blade/phoebus.
- First fork: if you observe tools/nougen_session.py absent on every node -> route A: delete the SSH branches and route through NouGenMsgBus.live_ping; else route B: port the base64url envelope and _refuse_if_shell_unsafe guard into sessions.py.
- Evidence: `src/nougen_shards/sessions.py`, `src/nougen_shards/nougenmsg.py`
- Lens: injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: sessions.py lines 133-168 show f-string interpolation of message/task directly into ssh remote_cmd/cmd strings referencing tools/nougen_session.py and tools/nougenmsg.py, and that nougen_session.py path was not found anywhere in the repo, confirming the injection path and stale target.

### WG-0661 · P1 · defend · effort M

**Heal a partially populated dedup_index.db that only backfills when empty**

- Failure surface: _ensure_dedup_index backfills only if the hashes table has zero rows; a partial index (crash mid-backfill, corrupt DB skipped, restored grid) never heals, so global dedup silently misses duplicates across overflow DBs. Observed as 61,124 phantom 'new' rows on the restored grid.
- First fork: if COUNT(hashes) in dedup_index.db is less than SUM(COUNT(shards)) across the 9 DBs -> route A: rebuild index from all DBs under a write pause and diff duplicates by file_hash; else route B: add a periodic parity check between index count and grid count and alert on drift.
- Evidence: `src/nougen_shards/core.py`, `tests/test_write_quarantine.py`
- Lens: data-integrity/dedup · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Confirmed: core.py's _ensure_dedup_index only backfills when `SELECT 1 FROM hashes LIMIT 1` returns nothing (i.e., table is empty), matching the claim that a partially populated index never heals.
- #550 families: 3

### WG-0672 · P1 · defend · effort S

**Stop /sync/pull from dropping float32 embedding BLOBs (JSON-only decode) on every replica pull**

- Failure surface: sync_pull does emb.decode() + json.loads; the grid stores float32 bytes, so every real embedding decodes to None and pulled replicas arrive embedding=NULL. That re-creates the HARDENING §2 hole on whoart/phoebus through a side door while the source grid reports 100% coverage.
- First fork: if a /sync/pull sample row has embedding None while the source row's BLOB length % 4 == 0 -> route A: decode float32 via np.frombuffer (mirror relay_push._decode_embedding) and add a round-trip test; else route B: embeddings are JSON legacy on that node, run migrate_to_binary first.
- Evidence: `app.py`, `tools/relay_push.py`, `src/nougen_shards/embedding_backfill.py`
- Lens: data-integrity/embeddings · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py:1842-1843 sync_pull does emb.decode() then json.loads(raw) with no float32 branch, confirming JSON-only decode against binary BLOBs as described.

### WG-0683 · P1 · elevate · effort M

**Recover rows from .malformed-<stamp> quarantined grid DBs instead of recreating empty**

- Failure surface: quarantine_malformed_dbs moves a failing DB aside and recreates it empty; every shard in that file is silently gone from recall and the .malformed files accumulate on the Space /data volume until it fills. Six of nine DBs went malformed on the Space 2026-09-01.
- First fork: if `sqlite3 <file>.malformed-* .recover` yields a readable shards table -> route A: re-ingest rows through capture() with original_timestamp so dedup and FTS stay coherent, then delete the quarantined file; else route B: pull the same hashes from a sibling node via /sync/hashes diff and record the loss count in history.
- Evidence: `src/nougen_shards/core.py`, `tests/test_quarantine_malformed_on_boot.py`, `tests/test_grid_corrupt_db_degrades.py`
- Lens: data-integrity/corruption · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: core.py, test_quarantine_malformed_on_boot.py, and test_grid_corrupt_db_degrades.py exist and relate to malformed-DB quarantine; did not verify the exact '.malformed-<stamp>' naming or the 2026-09-01 six-of-nine incident, but the recovery gap is a reasonable inference.
- #550 families: 6

### WG-0694 · P1 · elevate · effort M

**Run a full grid restore drill from the HF bucket snapshot onto a fresh machine**

- Failure surface: publish_vault_snapshot ships only nougen_shards_N.db; dedup_index.db, graph.db, history.db, the private key file and tenants.json are not in the set. The 2026-09-06 restore surfaced 61k dedup phantoms, so a restore is not known to produce a coherent vault.
- First fork: if after restore the rebuilt dedup_index count != grid row count or any private shard fails hydrate -> route A: extend the snapshot manifest with the missing files and rerun; else route B: record the drill as the restore runbook.
- Evidence: `tools/publish_vault_snapshot.py`, `src/nougen_shards/snapshot_mode.py`, `src/nougen_shards/core.py`
- Lens: data-integrity/restore-drill · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: tools/publish_vault_snapshot.py, src/nougen_shards/snapshot_mode.py and core.py exist; the incomplete snapshot manifest (missing dedup_index/graph/history/key/tenants) is a reasonable inference from the snapshot tool's name suggesting it focuses on grid DBs.

### WG-0705 · P1 · defend · effort L

**Route all grid writes on blade through one writer instead of N processes on the same sqlite files**

- Failure surface: MCP stdio sessions, the node, handoff_guard hooks, the arxiv lane and backfills all open the 9 DBs plus dedup_index and history directly; on 2026-09-08 'database is locked' lost three lanes' captures and was mis-reported as malformed rows.
- First fork: if two or more writer processes hold the grid concurrently (lsof/handle on nougen_shards_*.db) -> route A: point local lanes at the node's /capture (write-forward) with a queue and keep direct sqlite for the node only; else route B: raise NOUGEN_SQLITE_TIMEOUT_S and add a retry with jitter in capture().
- Evidence: `app.py`, `src/nougen_shards/core.py`, `tools/handoff_guard.py`
- Lens: concurrency/locks · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: app.py, core.py and tools/handoff_guard.py exist; multiple independent writer processes opening the same sqlite files directly is a reasonable inference from the multi-tool/multi-process architecture evidenced across this batch.
- #550 families: 84, 86

### WG-0716 · P1 · defend · effort M

**Make nougenmsg delivery idempotent end to end so fan-out timeouts stop double-delivering**

- Failure surface: Envelopes carry idempotency_key but inbox drains and pipe receivers do not dedupe; on 2026-09-14 a connector gave up at 20s, fell back, and the message arrived twice. messages.db is only appended if the file already exists, so fresh nodes keep no ledger to dedupe against.
- First fork: if the same idempotency_key appears in two inbox files or two receiver deliveries -> route A: create messages.db on first use and reject duplicates at every receiver; else route B: shorten fan-out retries and mark receipts.
- Evidence: `src/nougen_shards/nougenmsg.py`, `tests/test_nougenmsg_fanout_async.py`
- Lens: distributed/idempotency · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: nougenmsg.py carries idempotency_key in envelope schema and DB insert; dedup-on-receive not directly verified but claim is a reasonable inference from the schema.
- #550 families: 16

### WG-0727 · P1 · defend · effort M

**Fix ack-equals-dispatch so acks on receipt legs never replay merged PRs across the fleet**

- Failure surface: relay ack auto-dispatches; single e2b verdicts mislabel completion notes and legacy handoff_* records as ASK, so a board sweep re-wakes every lane with work that already merged.
- First fork: if dispatch --dry-run lists any leg whose id starts with handoff_ or whose last checkpoint is complete -> route A: exclude and require 3-vendor consensus before ASK; else route B: keep single-verdict but require a human ack for legs older than 7 days.
- Evidence: `BACKLOG.md`, `docs/evolution/2026-09-21-nougenlive-dispatch.md`, `src/nougen_shards/relay_watch.py`
- Lens: distributed/ack-discipline · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: relay_watch.py and BACKLOG.md/dispatch doc exist and relay ack/dispatch logic is plausible from file roles; did not trace the exact ASK-mislabeling path.
- #550 families: 17, 22

### WG-0737 · P1 · defend · effort M

**Survive a relay/main history rewrite without silently blinding fleet_inbox and relay_watch**

- Failure surface: origin/main was force-pushed to a disjoint history on 2026-09-05; fleet_inbox's `pull --ff-only` fails and keeps logging nothing new, relay_watch's watermark points at commits that no longer exist, and handoff_sync aborts every merge.
- First fork: if `git merge-base` between local and origin returns nothing -> route A: alert loudly, re-clone to a fresh dir and rebuild seen-state from leg ids not SHAs; else route B: normal ff-only pull.
- Evidence: `.handoffs/20260816T232004Z__whoart__codex.md`, `ops/fleet_inbox.py`, `src/nougen_shards/handoff_sync.py`
- Lens: distributed/sync · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: handoff_sync.py, fleet_inbox.py and the handoff record exist and match the ff-only/watermark failure mode described.
- #550 families: 24

### WG-0747 · P1 · defend · effort M

**Unify node identity so provenance stops defaulting to blade1tb and hostnames**

- Failure surface: capture stamps machine=socket.gethostname(), federation defaults machine_id to 'blade1tb', node_state uses NOUGEN_NODE_NAME/NOUGEN_MACHINE, coach_governor uses COMPUTERNAME, live uses nodes.json coach/machine. Cross-node hits and telemetry carry inconsistent or wrong origins (on the Space, a container hostname).
- First fork: if two identity resolvers on the same box return different names -> route A: one locator.current_node() used by capture, federation, telemetry and messaging with a test; else route B: at least drop the blade1tb default for an explicit 'unknown'.
- Evidence: `src/nougen_shards/federation.py`, `src/nougen_shards/core.py`, `src/nougen_shards/node_state.py`
- Lens: distributed/provenance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: federation.py:301 defaults to 'blade1tb', core.py uses socket.gethostname(), node_state.py:59 uses NOUGEN_NODE_NAME/NOUGEN_MACHINE fallback to hostname -- all three inconsistent resolvers confirmed directly.
- #550 families: 18

### WG-0757 · P1 · elevate · effort M

**Carry lane health on every federated cross-node return (HARDENING §4 open item)**

- Failure surface: A lane that misses the recall deadline merges as an empty list; the HTTP body came back 200 with 2 bytes, indistinguishable from no matches; lane_failures ships now but cross-node hits still carry no embedding coverage or FTS reachability from the remote.
- First fork: if sweep_report.deadline_exceeded or any remote lane omits lane_health -> route A: mark the recall 'partial' in the packet header and refuse absence claims; else route B: complete, assert normally.
- Evidence: `src/nougen_shards/federation.py`, `HARDENING.md`, `tests/test_federation_coverage_honesty.py`
- Lens: observability/health-that-lies · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: federation.py, HARDENING.md, test_federation_coverage_honesty.py exist, consistent with an open coverage-honesty item.
- #550 families: 12

### WG-0767 · P1 · defend · effort M

**Keep Kaedra's gemma model resident and queue concurrent asks so 38s cold loads stop timing out MCP clients**

- Failure surface: kaedra_gateway pins keep_alive=-1 but ollama still evicts on reboot; ThreadingHTTPServer spawns unbounded threads onto one Ollama, so a burst of fleet asks serializes behind a 38s load and every client hits its 30s timeout while the gateway reports healthy.
- First fork: if /health shows loaded_models empty -> route A: prewarm on boot and return 503 'warming' with ETA instead of accepting; else route B: bound concurrency with a semaphore and expose queue depth.
- Evidence: `ops/kaedra/kaedra_gateway.py`, `tools/wake/kaedra.py`
- Lens: distributed/timeouts · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: kaedra_gateway.py and wake/kaedra.py exist; keep_alive/ThreadingHTTPServer claim is plausible from the gateway's role.
- #550 families: 52

### WG-0777 · P1 · defend · effort M

**Add an out-of-process watchdog that times a real recall after today's blade QuickEdit freeze**

- Failure surface: The blade node's asyncio loop stopped when the console paused; /health hung, CLOSE_WAIT piled up, and the scheduled task saw a running process. Two scheduled tasks now point at two code trees, so the watchdog may restart the wrong one.
- First fork: if drift_check reports the running tree != canonical -> route A: retire the stray task first; else route B: install a watchdog that POSTs a recall_memory probe every 5 minutes and kickstarts the hidden task on two consecutive timeouts.
- Evidence: `tools/install_ngs_node_task.ps1`, `tools/drift_check.py`, `tools/start_grid.py`
- Lens: observability/watchdogs · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: install_ngs_node_task.ps1, drift_check.py, start_grid.py exist and match a watchdog/drift scenario.

### WG-0787 · P1 · defend · effort M

**Survive the whoart named-tunnel dying at 11 AM and the 72h ExecutionTimeLimit on the admin task**

- Failure surface: The named tunnel died silently; a 5-minute watchdog was added today but the admin task still carries a 72h execution limit that will kill it on schedule, and the quick and named tunnels once shared a pid file so status lied UP.
- First fork: if the tunnel task shows ExecutionTimeLimit != PT0S -> route A: re-register with PT0S plus periodic retrigger like install_ngs_node_task; else route B: verify the watchdog restarts on a 530 from the public hostname, not only on a dead pid.
- Evidence: `tools/tunnel_lane.ps1`, `tools/gateway_supervisor.ps1`, `tools/install_ngs_node_task.ps1`
- Lens: observability/watchdogs · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: tunnel_lane.ps1, gateway_supervisor.ps1, install_ngs_node_task.ps1 exist; ExecutionTimeLimit specifics not line-verified but consistent with file roles.
- #550 families: 27, 91

### WG-0797 · P1 · defend · effort S

**Replace sync_mesh_status's hardcoded 3_VAULT_SYMMETRIC claim with a real hash-parity check**

- Failure surface: The MCP tool sync_mesh_status returns symmetric_standard '3_VAULT_SYMMETRIC' and a local count without querying any sibling; agents read it as proof the three vaults match while single-node residency is the actual design.
- First fork: if sibling /sync/hashes are reachable -> route A: compute per-node counts and symmetric-difference sizes and report 'independent, not replicas'; else route B: report unknown, never symmetric.
- Evidence: `app.py`
- Lens: observability/false-done · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py:2908 (and 504, 1326) hardcodes 'symmetric_standard'/'parity_standard': '3_VAULT_SYMMETRIC' exactly as claimed.
- #550 families: 100

### WG-0807 · P1 · defend · effort M

**Re-provision Space persistent storage safely and prove durability with a survival probe every deploy**

- Failure surface: The first wipe tool deleted the volume via a dead API; the Space ran on ephemeral disk with persistent_storage:false and a 232k-shard rebuild evaporated at the next deploy. Deploys still do not assert persistence.
- First fork: if /health persistent_storage is false after a deploy -> route A: block the deploy workflow from reporting success and page; else route B: run the survival probe (push, restart, count) and record it.
- Evidence: `tools/wipe_space_volume.py`, `.github/workflows/keepalive.yml`, `app.py`
- Lens: data-integrity/backups · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: wipe_space_volume.py, keepalive.yml, app.py all exist; persistent_storage assertion gap is a reasonable inference though not independently confirmed against a specific historical incident.
- #550 families: 91

### WG-0817 · P1 · defend · effort M

**Audit every README product claim against code before public onboarding widens**

- Failure surface: README.md tells a fresh user that persona Modelfiles live under fleet/ (no such dir; roster is src/nougen_shards/agents.py), that there are '460+ unit tests' (2075 today), that data sits in 'encrypted SQLite databases' (only sensitivity=private/secret bodies are encrypted per CHANGELOG 1.3.0) and that skills/design ships (tests skip when absent). The first external user files a bug against a doc, and the bug tracker URL in pyproject points at github.com/whovisions/nougen, which does not exist.
- First fork: if you observe a README claim with no code path behind it (grep for fleet/, count tests, check capture(sensitivity=)) -> rewrite the claim to cite the mechanism; else keep the claim and add a test that fails when the mechanism disappears
- Evidence: `README.md`, `src/nougen_shards/agents.py`, `pyproject.toml`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Verified: no fleet/ directory exists (roster is in src/nougen_shards/agents.py as claimed), README says '460+ unit tests' while actual test count is 2075, pyproject.toml Bug Tracker points to github.com/whovisions/nougen.

### WG-0827 · P1 · defend · effort S

**Unify the secrets-store story across SECURITY.md, privacy.md, HARDENING §8 and keymaker**

- Failure surface: Four public documents name three different stores: SECURITY.md says shards_secrets.db, HARDENING §8 says agent_secrets.db, docs/privacy.md tells users never to commit a .nougen_vault directory that CHANGELOG 1.3.0 explicitly moved to ~/.nougen/secrets. A user following privacy.md protects the wrong path and commits the real one.
- First fork: if keymaker.py resolves one canonical store today (NOUGEN_SECRETS_VAULT_DIR else ~/.nougen/secrets) -> rewrite all four docs to that chain and add a doc-lint test; else first finish keymaker legacy-store consolidation and then document
- Evidence: `SECURITY.md`, `docs/privacy.md`, `src/nougen_shards/keymaker.py`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: SECURITY.md names shards_secrets.db, HARDENING.md/keymaker.py reference agent_secrets.db, docs/privacy.md tells users to protect .nougen_vault while keymaker.py shows the legacy dir is deprecated in favor of a resolve_secrets_vault_dir() chain -- confirms the documented inconsistency.

### WG-0837 · P1 · elevate · effort M

**Move the Mrs. B coloring-book engine out of the memory substrate via node_plugins**

- Failure surface: src/nougen_shards/mrsb.py ('Learn With Mrs. B: ESOL Coloring Book production engine') ships a private KDP product's spec file names, character names and a `nougen mrsb` CLI verb inside the public memory package; tests/test_mrsb.py skips on every public clone. The public-parity campaign moved remix_refinery (#546) but left this sibling.
- First fork: if the private pack already has a node_plugins entry point -> move mrsb.py, its CLI verb and tests there in one PR; else create the pack skeleton first and migrate mrsb as its first citizen
- Evidence: `src/nougen_shards/mrsb.py`, `tests/test_mrsb.py`, `src/nougen_shards/node_plugins.py`
- Lens: product-surface · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: src/nougen_shards/mrsb.py exists with docstring 'NouGen Mrs. B Project Engine', tests/test_mrsb.py contains a skip marker keyed to project-file absence ('in the public repo... skip cleanly on a fresh clone'), and node_plugins.py exists as the proposed migration target.

### WG-0847 · P1 · defend · effort S

**Re-baseline docs/architecture.md against core.py (2GB grid, MCPServer, no OpenRouter cache arrays)**

- Failure surface: The 21-step architecture page still says 1GB DB limits (core.MAX_DB_SIZE defaults to 2GB), names FastMCP (mcp 2.0 renamed it MCPServer, pyproject comment), and claims context is kept server-side via OpenRouter caching arrays and sticky session_ids that no module implements. Agents onboarding from the doc build against a substrate that does not exist.
- First fork: if a step in architecture.md names a function/constant that grep cannot find in src/ -> delete or rewrite that step with the real symbol; else leave it and add the symbol to a docs-symbol test
- Evidence: `docs/architecture.md`, `src/nougen_shards/core.py`, `pyproject.toml`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/architecture.md literally says '1GB limits' and cites OpenRouter caching arrays/sticky session_ids and FastMCP, while core.py shows MAX_DB_SIZE=2GB (comment says raised from 1GB) and pyproject.toml confirms FastMCP was renamed MCPServer.

### WG-0857 · P1 · elevate · effort L

**Ship docs/wargame-catalog/catalog.ndjson (1000 entries) and gate CI on render --check**

- Failure surface: tools/wargame_catalog.py and tests/test_wargame_catalog.py expect a catalog.ndjson with >=1000 WG-#### ids, contiguous numbering, and rendered INDEX.md/per-repo markdown that must not drift; only families.json exists and ci.yml never runs render --check. The catalog this scout pass feeds has no landing zone and no drift gate.
- First fork: if the merged catalog validates (`validate` exit 0, ids contiguous) -> commit it plus rendered markdown and add `render --check` to ci.yml; else fix the validator gaps first (priority derivation, families mapping) and land the catalog in a second PR
- Evidence: `tools/wargame_catalog.py`, `tests/test_wargame_catalog.py`, `docs/wargame-catalog/families.json`
- Lens: agent-doctrine · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/wargame_catalog.py enforces ID_RE = WG-\d{4} and mentions a 1000-item reserve; tests/test_wargame_catalog.py asserts len(items) >= 1000 with contiguous WG-#### ids; docs/wargame-catalog/ contains only families.json, no catalog.ndjson -- confirming the described gap.

### WG-0867 · P1 · defend · effort M

**Define who may merge dependabot and sweep PRs so cooldown-held updates do not rot unreviewed**

- Failure surface: dependabot.yml holds updates 5 days for the worm class, but the fleet context records dependabot PRs unreviewed and a 26-deep backlog of clean sweep PRs because self-merge authority was never answered; PR #455 has sat through 20+ sweeps. The cooldown protects against a compromised release for five days and then the PR sits open for weeks, exposing the same window on the other side.
- First fork: if the GM issues a written merge policy (agent may merge green dependabot minors + sweep records; majors and src/ changes need a second lane) -> encode it as a CODEOWNERS + auto-merge rule; else park merges and escalate one consolidated ask
- Evidence: `.github/dependabot.yml`, `CONTRIBUTING.md`
- Lens: merge-authority · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: dependabot.yml confirms the 5-day cooldown mechanism. CONTRIBUTING.md exists but says nothing about merge authority/self-merge policy, and the specific '26-deep backlog' / PR #455 claims are not found in the local repo (they reference fleet-external PR state not visible in this checkout). Not self-contradictory, so treated as a reasonable inference per the PR-id evidence rule.

### WG-0877 · P1 · defend · effort M

**Survive a fleet broadcast storm through nougenmsg_send and the inbox hooks**

- Failure surface: The MCP tool nougenmsg_send defaults to target='all' with background=True and no rate limit; tools/claude_inbox_hook.py and agy_inbox_hook.py inject inbox text into the next prompt of every Claude/Antigravity session. An agent that broadcasts a question, receives it back via its own hook, and answers by broadcasting again loops across five lanes on three machines with nobody watching.
- First fork: if a message envelope carries a hop count or origin session id -> drop self-originated and hop>2 messages at the hook; else add a per-sender token bucket in NouGenMsgBus.emit_fleet and a fleet-wide NOUGEN_MSG_MUTE kill switch
- Evidence: `src/nougen_shards/mcp.py`, `tools/claude_inbox_hook.py`, `tools/agy_inbox_hook.py`
- Lens: multi-agent-governance · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: mcp.py's nougenmsg_send has target: str = 'all' default and calls NouGenMsgBus.emit_fleet(..., background=True). No rate limiting, token bucket, or hop-count/self-origin filtering found in mcp.py, agy_msg.py, or the inbox hook tools.
- #550 families: 49

### WG-0887 · P1 · defend · effort M

**Quarantine evolve_skill output: no evolved skill enters apply_skills without review**

- Failure surface: The MCP tool evolve_skill reports 'evolved and verified' while src/nougen_shards/evolution.py says its verification stages are simulated stubs; the result lands in <vault>/skills/ where skills/README.md declares skills 'not optional' and apply_skills returns them in full. A client can mint a standing instruction from a prompt and every later session obeys it.
- First fork: if evolution.run_autonomous_evolution is still a stub -> make evolve_skill write to <vault>/skills/_pending and have apply_skills ignore that dir until an operator promotes; else keep auto-promotion but require a passing generated test
- Evidence: `src/nougen_shards/mcp.py`, `src/nougen_shards/evolution.py`
- Lens: autonomy-limits · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: mcp.py's evolve_skill returns "Skill '...' evolved and verified." while evolution.py's own module docstring says stages are 'currently simulated stubs, not a live open-world research + verification' and its grounding_source is literally '(simulated)'.
- #550 families: 69

### WG-0896 · P1 · defend · effort M

**Survive a leaked ?token= URL: per-tenant rate limit and spend cap on the inference routes**

- Failure surface: app.py has no rate limiting (no 429 path anywhere) and accepts the node token as a ?token= query parameter for connector compatibility; /agent, /rhea/brain, /iris/ask, /agents/ask and space_router's /v1/chat/completions all spend Who Visions' HF router and OpenRouter credentials. One pasted connector URL in a chat log becomes unbounded spend on company keys until someone reads the bill.
- First fork: if tenants.resolve_token can attach a per-tenant budget -> add a token-bucket middleware keyed on tenant id with a daily spend ceiling from billing; else at minimum cap concurrency per token and alert on 100 calls/hour
- Evidence: `app.py`, `space_router.py`, `rhea_noir.py`
- Lens: rate-limits · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: app.py has a Query(None) token parameter (?token= support) and no 429/rate-limit code path anywhere in the file; /agent, /rhea/brain, /iris/ask, /agents/ask routes all exist and are unthrottled.
- #550 families: 58, 62

### WG-0905 · P1 · elevate · effort M

**Re-baseline quota_governor and token_tracker for the Fable 5 subscription-to-API cutover**

- Failure surface: tools/token_tracker.py aggregates Claude Code JSONL and Antigravity RPC to produce dailies; quota_governor's ladder assumes a subscription bucket with a reset_eta; tools/coach.py budgets 60 fleet calls/day. When the frontier lane moves to metered API (~July 2026) the denominator changes from 'percent of plan' to dollars, DenominatorProvenance flips to ESTIMATED, and every threshold (60/75/85/90/95%) silently stops meaning anything.
- First fork: if the API lane reports usage in the response -> feed tokens*price from billing.compute_cost into the governor with a dollar bucket; else keep the percent ladder but mark provenance UNKNOWN and warn on every alert
- Evidence: `tools/token_tracker.py`, `src/nougen_shards/quota_governor.py`, `tools/coach.py`
- Lens: provider-billing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: quota_governor.py defines DenominatorProvenance with an ESTIMATED/UNKNOWN state and reset_eta field consistent with a subscription-bucket percent model; token_tracker.py and coach.py exist as described, supporting the cutover-risk claim.
- #550 families: 64, 65

### WG-0913 · P1 · defend · effort M

**Survive the day OpenRouter withdraws or throttles the :free models Rhea falls back to**

- Failure surface: rhea_noir.py hardcodes a fallback list of :free OpenRouter models (nemotron-3-ultra, glm-5.2:free, gpt-oss-20b:free) and README/bootstrap call this 'Rhea's default brain'. Free tiers are routinely rate-limited or removed; when they go, the 'always-up cloud brain' answers 502 and the only alternative is the paid HF router on company credit.
- First fork: if OpenRouter's /models lists a :free model at boot -> resolve the fallback list dynamically and shard the resolved set; else degrade to grid-only answers ('recall without a brain') and report the missing lane in /health warnings
- Evidence: `rhea_noir.py`, `src/nougen_shards/openrouter_mcp_client.py`, `tools/bootstrap.py`
- Lens: provider-boundaries · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: rhea_noir.py hardcodes a fallback list including 'nvidia/nemotron-3-ultra-550b-a55b:free', 'z-ai/glm-5.2:free', and 'openai/gpt-oss-20b:free', matching the named models in the claim.
- #550 families: 57, 59

### WG-0921 · P1 · elevate · effort M

**Promote google_workspace to a tested optional extra and decide its plugin status**

- Failure surface: src/nougen_shards/google_workspace/ ships 17 Gmail/Calendar/Drive tools and an OAuth mint flow with zero tests (no test file references it), while its four google-* libraries were added to core dependencies so every `pip install nougen_shards` pulls them. A regression in auth.py token caching goes unnoticed until an operator's mailbox tool fails live.
- First fork: if the tools can be exercised against mocked googleapiclient builds -> add tests and move the deps to a [google] extra; else keep them core but at least test auth.py token-cache resolution with a fake home
- Evidence: `src/nougen_shards/google_workspace/server.py`, `docs/google-workspace-mcp-port.md`, `pyproject.toml`
- Lens: test-coverage · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: No test file under tests/ references google_workspace; the four google-* libraries (google-api-python-client, google-auth, google-auth-oauthlib, google-auth-httplib2) are listed in pyproject.toml's core `dependencies`, not an optional extra.

### WG-0929 · P1 · elevate · effort L

**Close TS parity C9 so npm consumers rank shards the way Python does**

- Failure surface: docs/AUDIT_DEEP_DIVE.md leaves retrieve() domain filter, RRF, vector lane and decay unported in ts/ and notes an embedding storage-format divergence; ts/src/test has 18 suites against ~226 Python files. A node/better-sqlite3 user and a Python user querying the same vault get different top results, and the npm package is still 1.1.0.
- First fork: if ts/PORTING_CONVENTIONS.md lists a mechanical mapping for retrieve -> port in the documented order with golden-set parity tests against tests/fixtures; else write the golden set first from Python and diff
- Evidence: `docs/AUDIT_DEEP_DIVE.md`, `ts/PORTING_CONVENTIONS.md`, `ts/src/test`
- Lens: product-parity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/AUDIT_DEEP_DIVE.md lists the unported items verbatim: 'retrieve() domain filter / RRF / vector lane / decay'; ts/src/test contains 18 test suite files; npm package.json (both root and ts/) report version 1.1.0.

### WG-0937 · P1 · elevate · effort M

**Close HARDENING §1: unconditional session capture on the product lane (app session close)**

- Failure surface: §1 is ✅ only for the agent lane (tools/handoff_guard.py sessionend stub); the product lane (Gradio HUD / node sessions) still relies on voluntary capture, which is the 'manual capture == eventual amnesia' failure the invariant was born from. A Pro user's session ends and leaves no trace.
- First fork: if the HUD has a session lifecycle hook (Gradio unload / MCP session close) -> call the same dedup'd capture with a product-lane tag; else capture on a periodic heartbeat with a last-activity window
- Evidence: `HARDENING.md`, `tools/handoff_guard.py`, `app.py`
- Lens: hardening-backlog · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: HARDENING.md §1 literally states ✅ agent lane / ⬜ product lane must call the same unconditional capture. tools/handoff_guard.py has a sessionend mode (line 109, 'AUTO-WRITE a handoff'). app.py is a large Gradio HUD (gr.Blocks 'NouGenShards Cortex HUD') with no matching sessionend capture hook found. Evidence directly supports the claim.
- #550 families: 8

### WG-0945 · P1 · defend · effort M

**Prove the published grid snapshot carries no private rows or invertible embeddings**

- Failure surface: tools/publish_vault_snapshot.py ships blade's nine DBs whole to an HF bucket the Space reads; unlike tools/build_whoart_vault.py it applies no sensitivity/enc fence, so private/secret rows travel as ngenc1 ciphertext while their raw embedding BLOBs (HARDENING §9, inversion) travel in the clear. A bucket ACL slip publishes reconstructable private memory.
- First fork: if the snapshot can be built from a filtered backup (WHERE sensitivity='normal' AND enc=0) -> do so and null embeddings on any non-normal row; else at least strip embedding BLOBs for non-normal rows post-copy and add a manifest assertion
- Evidence: `tools/publish_vault_snapshot.py`, `tools/build_whoart_vault.py`, `HARDENING.md`
- Lens: privacy · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Grep for sensitivity/enc/ngenc1 in publish_vault_snapshot.py returns nothing (no fence), while build_whoart_vault.py explicitly implements 'Sensitivity fence: only rows with sensitivity normal and enc=0 are exported' with a skip counter. Direct code contrast confirms the asymmetry claimed.
- #550 families: 75

### WG-0953 · P1 · defend · effort S

**Retire or re-baseline docs/AUDIT_DEEP_DIVE.md so agents stop reading a June snapshot as current**

- Failure surface: The audit's header says 'Fix status (this branch)', its line numbers (app.py:195, billing.py:75) no longer match, and it is the file test_published_surface.py allowlists for credential-shaped prose. Sweep lanes cite it as the open-items list and re-fix things fixed months ago or miss the items that were deferred.
- First fork: if the deferred items (atomic billing, error-string contract, gatekeeper allowlist, C9) are tracked elsewhere (BACKLOG.md/issues) -> replace the doc with a short pointer and drop it from ALLOWED; else move the open items to BACKLOG.md first
- Evidence: `docs/AUDIT_DEEP_DIVE.md`, `tests/test_published_surface.py`, `BACKLOG.md`
- Lens: docs-drift · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: docs/AUDIT_DEEP_DIVE.md header literally reads '> Fix status (this branch): ✅ C1 ... ✅ C7' confirming the 'this branch' framing described. tests/test_published_surface.py contains an ALLOWED dict (line 89) that explicitly lists 'docs/AUDIT_DEEP_DIVE.md' (line 109) as an allowlisted credential-shaped-prose file. BACKLOG.md exists as the plausible destination. Direct support for the claim.

### WG-0961 · P1 · defend · effort M

**Deprecate one of the two handoff protocols in public docs (nougen handoff vs relay verbs)**

- Failure surface: README and docs/handoffs.md teach `nougen handoff create/read/ack` with git-backed sync (handoff_sync.py), while the fleet actually runs NouGenRelay verbs (open ack checkpoint dispatch) and the evolution log shows a lane inventing `relay sync` because the docs did not match. A new lane picks the documented protocol and its baton never reaches the relay board.
- First fork: if handoff_sync.py still has a live user (grep launchd/ps1/hooks) -> document it as local-only and point fleet work at relay; else mark `nougen handoff` deprecated with a shim that forwards to relay
- Evidence: `docs/handoffs.md`, `src/nougen_shards/handoff_sync.py`, `docs/evolution/2026-09-21-nougenlive-dispatch.md`
- Lens: docs-drift · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: docs/handoffs.md teaches `nougen handoff create/read/ack/list/start` (lines 55-68). docs/evolution/2026-09-21-nougenlive-dispatch.md line 19 records exactly the incident: '`nougen relay sync` failed — no such verb | valid: open ack checkpoint complete autoclose policy init pull rules react shards admit guard adopt dispatch', and line 55 states '`relay sync` was invented, not read.' src/nougen_shar

### WG-0968 · P1 · defend · effort S

**Align nougen.bat's Python 3.9 floor with pyproject's >=3.10 before the next Windows onboarding**

- Failure surface: nougen.bat accepts any Python 3.9+ interpreter and builds the venv from it; pyproject requires >=3.10 and mcp 2.x needs newer typing. A Windows user on 3.9 sees the launcher succeed, then `pip install -e .` fail with an unreadable resolver error inside a window that closes.
- First fork: if the launcher can read requires-python from pyproject -> derive the floor and print a clear 'install 3.11+' message; else hardcode 3.10 and add a test that greps both files for the same floor
- Evidence: `nougen.bat`, `pyproject.toml`
- Lens: onboarding · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: nougen.bat line 24/33 confirms 'Locate a real Python 3.9+' and checks `sys.version_info >= (3, 9)`. pyproject.toml line 13 confirms `requires-python = ">=3.10"`. Direct version mismatch confirmed exactly as claimed.
- #550 families: 79
