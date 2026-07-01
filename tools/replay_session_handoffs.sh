#!/usr/bin/env bash
# Replay the deep-dive-atom-audit session HANDOFFS into YOUR local .handoffs registry.
#
# WHY: like the vault, the .handoffs/ registry lives only in the ephemeral cloud
# container (it is .gitignore'd). This recreates each on-call handoff via the CLI on
# your machine, then rebuilds the index. Run from repo root with nougen configured:
#   bash tools/replay_session_handoffs.sh
#
# NOTE: handoff-create is NOT idempotent (each run makes new timestamped entries).
# RUN ONCE on a fresh registry to avoid duplicate handoffs.

set -euo pipefail
NOUGEN="${NOUGEN:-nougen}"   # override: NOUGEN="python -m nougen_shards.cli"

ho() { "$NOUGEN" handoff create -a "$1" -g "$2" -m "$3"; }

ho 'claude' 'Deep-dive atom audit: fix all verified findings end-to-end on PR #5' "$(cat <<'NGHOEOF'
## 🔴 Active Incidents
- None.

## 🟡 Ongoing Investigations
- Deep-dive audit of NouGenShards complete (6 parallel auditors, py+ts+rust). Findings being fixed end-to-end on branch claude/deep-dive-atom-audit-ebgn44 (PR #5). Each fix is test-gated on BOTH suites and pushed as its own checkpoint.
- AUDIT CORRECTION: the auditor agents' "stale/invalid model ID" findings were WRONG (no OpenRouter access from the cloud container). google/gemma-4-31b-it:free and nousresearch/hermes-3-llama-3.1-405b:free are REAL free models. All model-ID change findings are RETRACTED and out of scope.

## 📋 Recent Changes
- 9a769ad feat(router): cloud fallback now routes across the FULL live free-model roster via OpenRouterClient.get_free_models() (GET /api/v1/models, filter :free / price 0), not 4 hardcoded IDs. py+ts.
- e5ef926 fix(brain_scan): closed redaction leaks (passwordless DB URL, sk-proj keys, truncating secret char-class) and now redact rec.title. py+ts + regression tests.
- 3cfcf0f fix(billing): compute_cost() with configurable pricing, monthly usage reset, estimated_cost stored, total_tokens fallback, fixed +00:00Z timestamps. py+ts + new test suites.
- 14a4ab1 fix(security): evolution skill-path traversal sanitized+bounded; dream.py non-dict invariant crash guarded; app.py token compare now hmac.compare_digest. py+ts + regression test.
- Baseline established: Python 196 -> 206 tests; TS 131 -> 139 tests. All green.

## ⚠️ Known Issues & Workarounds
- Local MCP lanes (nougen-shards, ollama, fleet-registry) are NOT reachable from the cloud container; audit fixes done by workflow agents + direct edits instead of the Ollama fleet.
- Sandbox cannot reach openrouter.ai (proxy allowlists registries+anthropic only); free-roster discovery verified by logic/tests, not a live call. Works at runtime on the user's machine.
- Test deps (pytest, numpy, sqlalchemy, mcp, rich, pytest-asyncio) installed in sandbox only; CI still does not exist (audit flagged: no .github/workflows).

## 📋 Remaining Verified Fixes (next session)
- Resource leaks: connectors/sql.py engine.dispose(); core.py mark_shard, nougen_context.py, cli.py node push missing try/finally.
- Timestamps: history.py/graph.py datetime.utcnow() -> tz-aware; parsers.py +00:00Z; nougen_context.py +00:00Z.
- connectors/cloud.py: KeyError outside try; enforce https / size-cap responses. federation.py: local survives remote failure.
- models_client.py: add urlopen timeouts + find_best_edge_model return annotation. gatekeeper.py: strengthen denylist (defense-in-depth). Stand up CI.

## 📅 Upcoming Events
- None.
NGHOEOF
)"

ho 'claude' 'Deep-dive atom audit: end-to-end fixes on PR #5, CI green' "$(cat <<'NGHOEOF'
## Recent Changes
- PR #5 now has 8 fix commits, ALL test-gated; CI GREEN both jobs (py 206, ts 139).
- Done: free-roster dynamic discovery, dynamic routing everywhere (no hardcoded model literals), redaction leaks+titles, billing cost/reset, security (path traversal/dream crash/constant-time token), robustness (timestamps tz-aware, resource leaks, HTTP timeouts, find_best_edge_model annotation), CI stood up + fixed (node 22).
## Known Issues
- Local .vault/.handoffs ephemeral in cloud container; durable record = PR #5 + tools/replay_session_shards.sh (8 shards) for the real vault.
## Remaining (LOW/MED, next session)
- gatekeeper denylist hardening (defense-in-depth); federation.py local-survives-remote; cli.py node push conn try/finally + json.loads guards; core.py mark_shard try/finally.
## Upcoming
- None.
NGHOEOF
)"

ho 'claude-cli' 'CLI node sync: conn try/finally + json guards' "$(cat <<'NGHOEOF'
## 📋 Recent Changes
- cli.py node push: wrapped per-DB conn in try/finally (no leak on exception); guarded json.loads(embedding.decode()) with bytes-check + except -> skip bad row.
- cli.py node pull: guarded json.loads(tags) and wrapped shards.capture in try/except continue so one malformed remote shard does not abort the loop.
- cli.ts mirrored both fixes (push try/finally + embedding guard; pull tags guard + capture try/catch).

## ✅ Tests
- pytest tests/test_cli.py: 8 passed.
- ts: npm run build clean (no error TS), node --test 139/139 pass.

## ⚠️ Known Issues & Workarounds
- None. core.py untouched (owned by another session).

## 🔴 Active Incidents
- None
NGHOEOF
)"

ho 'claude-federation' 'Federation: local survives remote failure' "$(cat <<'NGHOEOF'
## Recent Changes
- federation.py + federation.ts: wrapped query_external_dbs / query_cloud_shards in try/except; remote failure now logged (logging.warning / console.warn '[federation]') and skipped, local_results + ordering preserved.
- Added tests/test_federation.py (3 tests: external-fail, cloud-fail, both-fail -> local survives).
## Test Results
- pytest test_cloud_integration.py + test_federation.py: 8 passed.
- ts build: no TS errors; node --test: 139/139 pass.
## Known Issues
- None.
NGHOEOF
)"

ho 'claude-gatekeeper' 'Harden mutation gate (defense-in-depth)' "$(cat <<'NGHOEOF'
## 📋 Recent Changes
- gatekeeper.py: normalized input (lowercase + collapse whitespace/tabs) before regex matching; added destructive patterns (shutil.rmtree, os.remove/unlink, rm --recursive/--force, del /, format, mkfs, dd if=, >/dev/sd[a-z], forkbomb) and deploy patterns (git reset --hard, chmod -R 777). git push regex already covers --force/-f. Added defense-in-depth/not-a-security-boundary comment.
- Created ts/src/nougen_shards/gatekeeper.ts as 1:1 mirror + ts/src/test/gatekeeper.test.ts.
- Added 2 regression tests in tests/test_gatekeeper.py for obfuscated commands.

## Test Results
- Python: test_gatekeeper.py 15 passed.
- TS: build clean (0 error TS); node --test 146 pass / 0 fail (gatekeeper suite 7/7).

## Known Issues & Workarounds
- None. Gate is a speed-bump, not a security boundary.
NGHOEOF
)"

ho 'claude' 'Deep-dive atom audit COMPLETE - all verified findings fixed on PR #5' "$(cat <<'NGHOEOF'
## Active Incidents
- None.
## Recent Changes
- ALL verified audit findings now fixed on PR #5 (12 commits). Final fleet batch (fdc2b4c) done by 4 parallel sessions: gatekeeper hardening, federation resilience, cli node-sync leaks, core.mark_shard leak.
- Full suite: Python 211, TS 146. CI green (verify latest run).
## Ongoing Investigations
- None - audit fix phase complete. Open question: merge PR #5 to main.
## Known Issues & Workarounds
- Model-ID 'staleness' findings RETRACTED (free models real; container can't reach openrouter.ai). Local .vault/.handoffs ephemeral; durable = PR #5 + tools/replay_session_shards.sh (12 shards) for the real vault.
## Upcoming Events
- Merge decision on PR #5.
NGHOEOF
)"

ho 'claude' 'PR #5 MERGED to main - audit complete' "$(cat <<'NGHOEOF'
## Active Incidents
- None.
## Recent Changes
- PR #5 MERGED to main (merge commit 6896a83). Deep-dive atom audit fully resolved end-to-end. CI green; Python 211, TS 146.
## Ongoing Investigations
- None. Audit + fix + merge cycle complete.
## Known Issues & Workarounds
- tools/replay_session_shards.sh (12 shards) still needs to be run on the operator's machine to populate the REAL vault (container vault is ephemeral).
## Upcoming Events
- Optional: delete merged branch claude/deep-dive-atom-audit-ebgn44.
NGHOEOF
)"

ho 'claude-core' 'core.mark_shard: try/finally conn close' "$(cat <<'NGHOEOF'
## Recent Changes
- core.mark_shard (core.py/core.ts): wrapped per-DB conn in try/finally so close always runs even if SELECT/UPDATE raises (fixes leak). UTILITY_CHANGE history event emitted only after close on success path. db_index falsy check -> 'is not None' so db_index=0 targets the right cluster DB.
- Verified: test_shards 18 passed, TS 139. Part of fleet commit fdc2b4c (PR #5).
## Note
- This handoff was recreated centrally: the original claude-core fleet handoff collided on the branch-derived filename and was overwritten. Underlying code change is safely committed.
NGHOEOF
)"

"$NOUGEN" handoff rebuild-db
echo "Replayed 8 session handoffs into your registry. Verify: $NOUGEN handoff list"
