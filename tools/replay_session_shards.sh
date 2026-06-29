#!/usr/bin/env bash
# Replay the deep-dive-atom-audit session experiences into YOUR local NouGen vault.
#
# WHY: this session ran in a remote cloud container whose .vault is ephemeral and
# is NOT your real vault (~/Watchtower/vault). The MCP could not boot
# here because .mcp.json pins it to Windows paths. Run this on your machine to
# capture the session's high-utility experiences into your real brain.
#
# Usage (from repo root, with your real vault configured):
#   bash tools/replay_session_shards.sh
# It just shells out to `nougen add`, so NOUGEN_VAULT_DIR / your normal config apply.

set -euo pipefail
NOUGEN="${NOUGEN:-nougen}"   # override with NOUGEN="python -m nougen_shards.cli" if needed

add() { "$NOUGEN" add "$1" --tags "$2"; }

add "LESSON (high utility): Do NOT relay subagent claims about model catalogs as verified fact. During the deep-dive audit, auditor agents flagged 'google/gemma-4-31b-it:free' and 'nousresearch/hermes-3-llama-3.1-405b:free' as invalid/stale model IDs. They are REAL free OpenRouter models with function calling. A cloud container cannot reach openrouter.ai, so model-catalog facts are unverifiable there and must never be asserted. All model-ID 'staleness' findings were RETRACTED." \
    "lesson,audit,models,retraction,openrouter,verification"

add "DECISION: OpenRouter cloud fallback routes across the FULL live free-model roster via OpenRouterClient.get_free_models() (GET /api/v1/models, keep :free or price==0), not a hardcoded handful. Wired into list_models(), chat_with_fallback default, and agents.py. Offline seed = hermes-3-llama-3.1-405b:free, gemma-4-31b-it:free, gemma-3-27b-it:free. Mirrored py+ts. Commit 9a769ad on PR #5." \
    "decision,router,openrouter,free-models,agents"

add "CHANGE: Closed verified redaction leaks (brain_scan/redaction): passwordless DB URLs, sk-proj-/sk-svcacct- keys, and a secret value char-class that truncated base64/JWT secrets. importer now redacts rec.title too. py+ts + regression tests. Commit e5ef926." \
    "change,security,redaction,brain_scan,leak"

add "CHANGE: billing.py was non-functional (estimated_cost never stored, monthly usage never reset). Added compute_cost() with NOUGEN_PRICING_JSON-configurable pricing (free models=0), monthly period reset, total_tokens fallback, fail-closed subscription upsert, fixed +00:00Z timestamps. py+ts + new test suites. Commit 3cfcf0f." \
    "change,billing,cost,bugfix"

add "CHANGE: security batch - evolution.evolve_skill skill-path traversal sanitized and bounded to skills/; dream.py guards non-dict LLM invariants (was crashing wake()); app.py verify_token uses hmac.compare_digest. py+ts + regression test. Commit 14a4ab1." \
    "change,security,evolution,dream,auth"

add "DECISION/PRINCIPLE: Prefer dynamic routes over hardcoded everywhere. Added OpenRouterClient.preferred_free_model() resolving a single model from the live free roster (get_free_models). Replaced ALL hardcoded free-model literals at call sites: agents.py cloud fallback, core.py density scorer, openrouter_mcp_client run_query (py+ts). get_free_models short-circuits to seed when no API key (fast + offline-safe). No call site hardcodes a model string anymore." \
    "decision,principle,dynamic-routing,openrouter,refactor"

add "CHANGE: robustness batch - timestamps tz-aware single-Z (history/graph utcnow()->now(timezone.utc); nougen_context +00:00Z fixed). Resource leaks fixed: sql.py engine.dispose() finally; nougen_context try/finally; cloud.py reads conf inside try (KeyError no longer aborts sweep). models_client _HTTP_TIMEOUT=120 on all cloud urlopen; find_best_edge_model annotation Optional[ModelBudgetConfig]. Commit fa61727." \
    "change,robustness,leaks,timestamps,timeouts"

add "CHANGE: Stood up CI (.github/workflows/ci.yml), the audit's biggest gap. Python + TypeScript jobs. First run failed (TS job: node 20 lacks ** glob support); fixed by pinning node 22 + shell-expanded glob. CI now GREEN on both jobs (run 0ef7344). Commits 770b59c, 0ef7344." \
    "change,ci,devops,testing,lesson"

add "FLEET FIX (gatekeeper): hardened check_mutation_gate (py + new ts mirror) vs obfuscation - lowercase + whitespace-collapse before matching; expanded denylist (shutil.rmtree, os.remove/unlink, rm --recursive/--force, del /, format, mkfs, dd if=, raw >/dev/sd* writes, forkbomb, git reset --hard, chmod -R 777). Defense-in-depth speed-bump, NOT a security boundary. Commit fdc2b4c." \
    "gatekeeper,security,defense-in-depth,fleet"

add "FLEET FIX (federation): federated_retrieve wraps each remote lane in try/except so a failing external DB/cloud node degrades to empty (logged), local results+ordering preserved. py+ts + test_federation. Commit fdc2b4c." \
    "federation,resilience,fleet"

add "FLEET FIX (cli + core): node push/pull conn try/finally + json.loads guards; core.mark_shard try/finally + db_index 'is not None'. py+ts. Commit fdc2b4c." \
    "cli,core,resource-leak,fleet"

echo "Replayed 12 session shards into your vault. Verify: $NOUGEN search \"free models retraction\""
