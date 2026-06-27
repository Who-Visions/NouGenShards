# NouGenShards — Deep-Dive Atom-Level Audit

> **Fix status (this branch):** ✅ C1 (HUD loopback-default + optional auth),
> ✅ C2 (constant-time token compare), ✅ C5 (redaction patterns),
> ✅ C6 (importer title), ✅ C7 (context-db `+00:00Z` timestamp),
> ✅ C8 (non-destructive `init_context_db` default), ✅ scanner HIGHs,
> ✅ C4 (network timeouts on all model HTTP calls),
> ✅ Gemini key-in-URL HIGH (moved to x-goog-api-key header),
> ✅ C3 (billing cost computation + over_limit flip + cached-token pricing),
> ✅ SSRF scheme allowlists in cloud/sql connectors,
> ✅ nougen_context leak/FTS-fallback MEDs — fixed & unit-verified.
> Remaining: C9 (TS parity — large, mirror module) + assorted MED/LOW open for
> the parallel fix thread. Note: full atomic billing reservation and the
> "error-string-as-content" return-contract change are deferred (architectural).


_Static audit (no pytest in this env). 6 parallel lanes across Python core, brain_scan, model/routing, security, orchestration, and TS/Rust/packaging._

## Remaining work (not fixed on this branch — by design)

- **C9 (TS parity)** — clear-cut correctness bugs FIXED & TS-test-verified:
  ✅ BM25 `abs()`→logistic (was inverting ranking), ✅ dedup hash now strips the
  recall packet like Python (was duplicating shards), ✅ `detect_current_agent`
  claude-cli lane + `AGENT_FOLDERS` entry. (117/117 runnable TS tests pass; 2
  unrunnable here on missing `@modelcontextprotocol/sdk`.) STILL PENDING — the
  larger structural port: `retrieve()` domain filter / RRF / vector lane / decay,
  and the embedding storage-format divergence. That's a dedicated effort.
- **core.py:** ✅ random-jitter ranking removed (recall now deterministic),
  ✅ `density_score` now SELECTed in both FTS + LIKE paths so the feature is live
  (regression tests in `tests/test_core_determinism.py`). Remaining core/handoff
  items (`mark_shard` leak, live-status desync) left to the parallel thread.
- **Architectural, deferred:** full *atomic* billing reservation (only the
  over_limit flip was added); gatekeeper denylist → allowlist redesign; the
  "error-string-as-content" return-contract change across `models_client.py`.
- **Already fixed by the parallel thread (audit was stale):** sandbox/MCP exec now
  gates by default + requires `NOUGEN_ENABLE_SANDBOX`; connector timeouts &
  stable hashing.

Regression tests for the fixes below live in `tests/test_audit_fixes.py`.
**Verification:** the full runnable suite passes (209 tests, incl. the 28 new
ones and all pre-existing suites for touched modules); the whole branch diff was
adversarially reviewed by two independent agents and the one regression they
found (durable billing lockout) was fixed. Only the two MCP-SDK-dependent test
files are unrunnable in this environment (missing `mcp` package).

## 🔴 CRITICAL — fix first

| # | Where | Problem |
|---|-------|---------|
| C1 | `app.py:195` | Gradio/FastAPI HUD binds `0.0.0.0:4444` with **no auth on read/recon/transcript endpoints** — only the write API checks a token. Whole vault browsable on the LAN. |
| C2 | `app.py:38` | `verify_token` uses `!=` (non-constant-time) → timing side-channel on the only write/sync gate. Use `hmac.compare_digest`. |
| C3 | `billing.py:75` | `log_usage` **never computes `estimated_cost`** — always 0.0. No price table exists. Billing meters tokens at zero cost; spend tracking is broken. |
| C4 | `models_client.py` (all clients) | **No timeout on any `urlopen`** for OpenAI/Anthropic/Gemini/OpenRouter/HF/Ollama. One hung TCP = thread blocked forever, no retry/breaker. |
| C5 | `redaction.py:7` | `sk-[A-Za-z0-9]{20,}` stops at `-`/`_` → modern `sk-proj-…`/`sk-svcacct-…` keys leak their tail. Also misses `ASIA` (STS temp creds) and DB URLs without a path. |
| C6 | `importer.py:50` | Redaction runs on `content` only — **`rec.title` (from JSON name/filename) is stored unredacted**. Secrets in titles leak into shards. |
| C7 | `nougen_context.py:84,120` | `datetime.now(utc).isoformat() + "Z"` → `…+00:00Z` (invalid ISO). Downstream `fromisoformat` fails. |
| C8 | `nougen_context.py:19` | `init_context_db(clean_slate=True)` **default wipes session.db** (+wal/shm) on every call while connections may be open → corruption. |
| C9 | `ts/core.ts:255,313 / handoff.ts:379` | TS mirror diverges: md5 over raw content (dedup breaks), BM25 uses `abs()` not logistic (inverts ranking), `detect_current_agent` drops claude-cli lane. |

## 🟠 HIGH

**Security / sandbox**
- `nougen_sandbox.py:15` — `bypass_gatekeeper=True`/`trusted=True` skip all checks; sandbox is only env-stripping (no seccomp/ns). Single flag flip = RCE path.
- `gatekeeper.py:18` — mutation gate is a **regex denylist** on `command.lower()` (`Rm`, obfuscation, encoding all bypass).
- `mcp.py:201` — `execute_sandboxed_code` MCP tool **bypasses the mutation gate** entirely (CLI path gates it; MCP doesn't). Constitution violation.
- `autonomous_harden.py:27` — `subprocess.run(cmd, shell=True)` with f-string-built path → command injection.
- SSRF via user-controlled URLs: `connectors/cloud.py:20`, `connectors/sql.py:46`, `models_client.py:567` (`WhoVisionsCloudClient`). Tokens forwarded to arbitrary hosts; cloud allows `http://` (cleartext token).
- `models_client.py:243,286,300` — Gemini API key in URL query string → leaks to logs/tracebacks.
- `keymaker.py:67` / `213` — `NOUGEN_ALLOW_PLAINTEXT_VAULT=1` stores keys cleartext; external DB URIs (with user:pass) always stored plaintext.

**Correctness / leaks**
- `models_client.py` (10+ sites) — bare `except` returns `f"Error: {exc}"` as model **content**; billing/parse treat error string as a real completion.
- `core.py:843,873` — `random.uniform` jitter injected into ranking → nondeterministic recall.
- `core.py:875` — `density_score` never SELECTed → entire density-weighting feature silently dead (defaults 1.0).
- `core.py:924` / `nougen_context.py:86` — DB connections opened without try/finally → leak on exception.
- `scanner.py:20,36` — `rglob` follows symlinks; danger-zone check inspects link path not resolved target → a symlink can pull `.ssh` into the scan. `p.stat()` unguarded → one unreadable file aborts whole scan.
- `parsers.py:8` — `.sqlite/.db/.zst` read as UTF-8 text; binary secret stores ingested as garbled text that defeats redaction.
- `dream.py:152` — `consolidate_episodic_data` runs per-shard LLM with no timeout/budget → `dream wake` can hang forever. `dream.py:117` — AttributeError when `find_best_edge_model()` returns None.
- `billing.py:92` — monthly-limit check non-atomic; concurrent requests all pass the gate before any increment.
- `Dockerfile:15` — `COPY . /app` with **no `.dockerignore`** → gitignored `.env`/`*.db`/secrets baked into image.
- `pyproject.toml:19` — all 11 deps unpinned → non-reproducible/​supply-chain risk.

## 🟡 MED (selected)
- `structured.py:67,69` — `bool` passes `integer`/`number` validation (bool ⊂ int).
- `history.py` / `graph.py` — naive `datetime.utcnow()`; `print()` to stdout can corrupt MCP stdio JSON-RPC.
- `context_client.py:88` — every method calls `asyncio.run` → unusable inside an event loop (e.g. MCP handler).
- `evolution.py:90` — `skill_id` from raw instruction into file path → path traversal on write.
- `redaction.py:24` — generic catch-all stops at non-alnum (partial redaction); missing labels `bearer`/`client_secret`/`pwd`; truncated PEM keys not caught.
- `graph.py:147` — `related_shards` opens up to 9 DBs per neighbour (O(n×9)).
- `classifiers.py` / `registry.py` — `.env`/`secrets.json`/`.netrc`/`.git-credentials`/`.pgpass` not danger-zoned; in-scope for ingestion.

## ⚫ Orphaned / dead code
- `kronos_temporal_engine.py` — imported nowhere; agent persona refs `core` functions, not this module.
- `agents.py` — no `nougen agent` CLI command; roster unreachable. Model tags (`dav1d:e2b`, `gemma4:12b`) likely nonexistent → every run escalates.
- `auto_research.py` — no CLI wiring; `python -m` only.

## ✅ Clean
- No live secrets committed (only test fixtures + redaction patterns). `.env`/`*.db`/vault tools gitignored.
- Tauri CSP set (`default-src 'self'`), no broad allowlist, no shell-open. Dockerfile drops to non-root. `package-lock.json` + `Cargo.lock` present.

## Recommended order
1. **C1/C2** (network-exposed unauthenticated HUD) — highest blast radius.
2. **C4** (timeouts) — one shared helper across `models_client.py`.
3. **C5/C6 + importer title + scanner symlink** (redaction layer) — secret-leak cluster.
4. **C3** (billing cost) — feature is non-functional.
5. **C7/C8** (context-db timestamp + destructive default).
6. SSRF allowlist + Gemini key-in-URL + sandbox/gatekeeper rethink.
