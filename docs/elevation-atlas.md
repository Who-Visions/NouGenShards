# NouGenShards Elevation Atlas — 1000 steps

This document is the repository-grounded, verified version of the fleet-wide Elevation Atlas (NouGenShards#551) and the War Game (NouGenShards#550), built for this repository alone. It started as a 10-zone draft plan. As of `main @ ae40d10` on 2026-09-24, every step in that draft was checked against the code, and the draft was corrected wherever the code disagreed with it. Every ✅ names the mechanism that makes it true (a file plus a function or line), not the intent behind it. Where the draft claimed something the tree does not contain, this atlas says so and marks the step 🟡 or ⬜.

## How to read this atlas

| Glyph | Meaning | What must be cited |
|---|---|---|
| ✅ | Done in `main` today | The mechanism: repo-relative file + function or line. Never a plan, doc, or PR description. |
| 🟡 | Partial | What exists **and** the gap, both specific. |
| ⬜ | Missing | Where it should land (file/module/test). `(unverified)` when it could not be checked. |

**No false green.** A step is ✅ only when the code does the thing. HARDENING.md learned this the hard way: one invariant was marked ✅ for two months while the code did not implement it. If the evidence is partial or unknown, the step stays 🟡 or ⬜.

**References**
- `[551:#N]`: step N of the fleet atlas NouGenShards#551 (Track 1 = 1-50 memory core, Track 2 = 51-100 federation, Track 16 = 751-800 security, Track 20 = 951-1000 evolution engine).
- `[550:#N]`: war-game scenario family N of NouGenShards#550 (families 1-100).
- `[PR #N]`: a pull request on Who-Visions/NouGenShards.
- `[branch name]`: a branch on origin, e.g. `[branch codex/fix-ollama-stdin]`.
- `id@dbN`: a fleet memory shard (shard id in grid DB N).

**Execution law (verbatim from #551):**

> Do not execute all 1000 blindly. Each step must become an evidence-backed candidate first, then a wargame, then a bounded implementation with receipts. Prefer small PRs, one subsystem at a time. Historical defects become permanent regression fixtures. Unknown or partial evidence must remain unknown, never false green.

## Ground truth as of 2026-09-24

| Claim in the draft plan | What the repository shows | Evidence |
|---|---|---|
| `app.py` is the monolith to split first | `app.py` is 140,972 B. It is the third-largest file. `src/nougen_shards/cli.py` (170,668 B) and `src/nougen_shards/core.py` (156,577 B) are bigger. Other large modules: `nougenmsg.py` 72,667 B, `handoff.py` 70,263 B, `persona.py` 61,518 B, `visual_evidence.py` 61,260 B, `models_client.py` 52,225 B, `architecture_gauntlet.py` 49,786 B; `tools/token_tracker.py` 97,906 B | `wc -c` at ae40d10 |
| The repo is a compact package | 133 top-level modules in `src/nougen_shards/` (192 `.py` files including subpackages); 224 `tests/test_*.py` files (239 `.py` under `tests/`), about 2,067 `def test` functions | `ls`/`find` at ae40d10 |
| Branch hygiene is a minor item | 241 branches on origin. Stale-branch triage is a real job ([551:#960]) | GitHub branch listing, 2026-09-24 |
| "Resolve the remaining security-shaped open issues" | There are only two open issues: #550 (War Game) and #551 (Elevation Atlas), both opened 2026-09-24. No security issue is open, so this advice points at nothing. Security work has to come from #551 Track 16 and #550 families 69-76, not from the issue tracker | GitHub issues |
| Open PRs are feature work | #555 War Games doctrine + first slice (draft), #554 1000-mission wargame catalog (draft), #552 docs START_HERE, #548 Ollama native lane (`feat/nougen-live-ollama-lane`), #537 dependabot grouping (draft), #535/#534/#533/#532 dependabot bumps | GitHub PRs |
| HARDENING.md war games exist | HARDENING.md has 9 invariants (§1-§9) and points to `wargames/fts-or-fallback.md`, `wargames/ingest-junk-gate.md`, `wargames/capture-secret-guard.md` and `wargames/embedding-inversion.md`. The tree has **no `wargames/` directory**, and only one src file (`coach_governor.py`) mentions "wargame" | HARDENING.md lines ~96, ~119, ~132, ~143; `ls wargames` fails |
| Replication/anti-entropy is in place and needs tuning | **No** src file mentions merkle or anti-entropy (0 hits). Nothing replicates across nodes or reconciles node state. `app.py` `/sync/push`, `/sync/pull` and `/sync/hashes` are point transfers, not reconciliation. #551 itself says replication "is currently not behaving as assumed across all three nodes" | `grep -rliE "merkle|anti.entropy" src` → 0 |
| Fleet recall is complete | A fleet `shards_search` fan-out returned `complete=false` on 2026-09-24: blade timed out while phoebus and whoart answered. `federation.FederatedResult` (line 61) carries `lane_failures` and `.complete` (line 81), so the gap is reported, not hidden. The architecture lock 12169@db6 requires per-machine multi-vault reads | `src/nougen_shards/federation.py` |
| Griot v2 coverage audit is done | `griot_v2.py` (398 lines) emits `NodeCoverageStatus` receipts, PARTIAL/DEGRADED states and compound `id@dbN`. `docs/griot-v2-coverage-audit.md` "Remaining scope" says it does not probe remote nodes itself and has no per-machine/per-vault matrix. It also lacks full amend/retract resolution, corpus identity validation, arbitrary date windows, cursor continuation, evidence hydration and per-arm query receipts. "The 28-class relay should not be reported fully resolved" | docs/griot-v2-coverage-audit.md |
| The shard schema is defined | `core.py` `init_db` line 418 creates `shards(id, timestamp, event_type, title, content, tags, utility_score, access_count, file_hash UNIQUE NOT NULL, domain_key)`. It then adds `embedding`, `density_score`, `consolidated`, `sensitivity`, `enc`, `machine`, `source_uri`, `learned_utc` and more through try/except `ALTER TABLE`. It also creates `semantic_knowledge`, `shards_fts` (FTS5 external-content, trigram) and `hashes`. `schema.py` targets v3 while core adds v4-style columns. There is no single written contract | `src/nougen_shards/core.py` ~418-600, `schema.py` |
| Capture is hardened | 9-DB grid with deterministic hash routing (`core.get_routing_index`, docs/architecture.md); content-hash dedupe; embed-at-ingest with an `EMBED_AT_CAPTURE_MISSES` counter (HARDENING §2); **no** blob gate: HARDENING §7 cites `_looks_like_blob`, which has zero hits in the tree (see step 101); redaction via `brain_scan.redaction.redact_content` before write (§8) | core.py, HARDENING.md |
| Test suite and CI are thin | `.github/workflows/ci.yml`: `ruff check src tests`; `ruff check tools --select F,E722`; `python -m pytest tests -q` on Python 3.10/3.11/3.12; requirements.txt dry-resolve for the Space; TypeScript build + `node --test`; desktop UI tsc. Also `security.yml`, `deploy-space.yml`, `keepalive.yml`, and dependabot config | .github/workflows/ |
| The Ollama remote-shell injection is open | Fixed on main: `nougenmsg.py` ~604-635 sends a constant `remote_cmd` with the payload on stdin. The same fix is on `[branch codex/fix-ollama-stdin]` commit f406825 | src/nougen_shards/nougenmsg.py |

## Where the memory actually lives

| Zone | Modules (lines) | What they prove today |
|---|---|---|
| 1 Memory Physics | `core.py` (156,577 B), `schema.py`, `history.py` 341, `consolidate.py` 195, `unlearning.py` 742 | Hash identity, 9-DB routing, dedupe, supersede tags. `unlearning.py` is not wired into the app |
| 2 Capture Intelligence | `core.capture`, `brain_scan/redaction`, `tools/handoff_guard.py` | Redaction and embed-at-ingest run at capture time; the §7 junk gate is absent (step 101) |
| 3 Retrieval Intelligence | `retrieval_v2.py` 549, `reconstructive_recall_v2.py` 330, `reconstruction.py` 710, `ann_index.py` 146 | Deterministic RRF fusion; YTD/MTD/today temporal intent; FTS AND->OR->LIKE fallback (HARDENING §5) |
| 4 Memory Graph | `graph.py` 205, `vector_graph.py` | Relations exist. `test_graph.py` has a known order-dependent flake |
| 5 Temporal Memory and Griot | `griot_v2.py` 398, `griot_sharder.py` 174, `kronos_temporal_engine.py` 120, `temporal_fabric.py` 665, `temporal_fabric_v2.py` 288 | Coverage receipts and PARTIAL/DEGRADED states. Remote probing is still the caller's job |
| 6 Federation and Multi-Vault Truth | `federation.py` 307, `app.py substrate_coverage` (line 420), `/sync/*` | Parallel lanes, `lane_failures`, `.complete`. No replication |
| 7 Truth, Contradiction and Canon | `canonical_facts.py` 523, `evidence_ledger.py` 368, `evidence_gate.py` 302, `status_semantics.py` 498 | v2 canonical index with epochs ([PR #434], 30698@db8); absence semantics |
| 8 Security, Privacy and Sovereignty | `private_vault.py` 426, `keymaker.py` 863, `fleet_keys.py`, `credential_patterns.py`, `tenants.py` | AES-256-GCM `ngenc1:`; credentials kept in Keymaker (§8) |
| 9 Performance and Scale | `ann_index.py`, the 9-DB grid, `tools/token_tracker.py` | No million-shard benchmark exists yet |
| 10 Autonomous Memory Organism | `control_loop.py`, `destiny.py`, `dream.py`, `evolution.py`, `architecture_gauntlet.py`, `hardcade_*.py` | Loops and scaffolding exist. No census-driven evolution ([551:#951-1000]) |

**Gravity wells.** `cli.py` (170,668 B), `core.py` (156,577 B) and `app.py` (140,972 B) hold about 468 KB between them. `core.py` holds the schema, capture, routing and retrieval together, so every other zone depends on it.

## The first five moves (verified)

### Move 1: Make NouGenShards#550 executable
- **What:** a CLI (`nougen wargame list|filter|run`) and 25 deterministic scenarios in `tests/wargames/`, each writing a JSON receipt (subsystem, severity, reproducibility, node, commit). Start with families [550:#1]-[550:#8], [550:#12], [550:#92], [550:#93], [550:#94] and [550:#100].
- **Why first:** every later step has to pass through a war game (the execution law). HARDENING.md already points to four war-game docs that do not exist, so today's ✅ claims have nothing to be replayed against.
- **Evidence:** `ls wargames` fails; the only src mention of "wargame" is in `coach_governor.py`; the harness requirements are in #550 (preconditions, mutation, observation, failure signal, countermove, cleanup, receipt).
- **Reconcile from:** HARDENING.md §4/§5/§7/§8 (write the missing `wargames/*.md` as executable tests); existing fixtures in `tests/`.
- **Patch:** `src/nougen_shards/wargame.py` (registry + runner + receipt writer), `tests/wargames/test_family_*.py`, a `cli.py` subcommand. Destructive cases run only on temp stores.
- **Done when:** `nougen wargame run --all` runs the 25 scenarios deterministically in CI on 3.10-3.12, writes a receipt for each, and fails closed on a missing receipt ([550:#100]).

### Move 2: Freeze Shard Protocol v1
- **What:** `docs/shard-protocol-v1.md` (fields, types, nullability, hash algorithm, `id@dbN` identity, enc/sensitivity semantics), a `shard_protocol.py` validator, and `tests/test_shard_protocol.py`.
- **Why:** other subsystems (griot_v2, canonical_facts, unlearning, sync) are defining shard semantics on their own. A frozen contract has to come before they drift further ([551:#49], [551:#36]).
- **Evidence:** `core.py` line 418 base columns plus about 10 try/except `ALTER TABLE` additions; `schema.py` targets v3 while core adds `source_uri`/`learned_utc`; `unlearning.py` writes tables init_db never creates.
- **Done when:** the validator runs on capture and on `/sync/push`, and every grid DB passes it in a read-only check.

### Move 3: Make multi-vault coverage and absence proof a first-class object
- **What:** one `CoverageProof` type, shared by `app.py substrate_coverage`, `federation.FederatedResult` and `griot_v2` `NodeCoverageStatus`. It should list the nodes and vaults required, attempted and answered, and distinguish unknown from empty ([551:#38], [551:#39]).
- **Evidence:** 12169@db6 (multi-vault reads required); 30683@db2 (a recall miss is not absence); the 2026-09-24 fan-out that returned `complete=false` with blade timed out; the "Remaining scope" section of the griot v2 audit.
- **Done when:** no recall surface can return an empty result without a proof object, and [550:#3]/[550:#92]/[550:#94] pass.

### Move 4: Replication canary and anti-entropy skeleton
- **What:** a canary shard captured on one node and proven to arrive on blade, whoart and phoebus ([551:#52]), plus per-vault summary hashes and a dry-run reconcile job ([551:#23], [551:#59], [551:#61]).
- **Evidence:** 0 src hits for merkle and anti-entropy; the `/sync/*` routes transfer data but never reconcile it; the note in #551.
- **Patch:** `src/nougen_shards/replication.py`, `tests/test_replication_canary.py` (runs against temp stores).
- **Done when:** the canary reports arrival per node with receipts, and the reconcile dry run lists the divergent hashes.

### Move 5: Split the gravity wells
- **What:** break `core.py` (156,577 B) into schema, capture, routing and retrieval modules first, then do the same for `cli.py` (170,668 B, one command group per module) and `app.py` (140,972 B, one router per tool family). Each extracted module gets contract tests.
- **Why after 1-4:** once the war games and the protocol tests exist, they can show that a refactor did not change behavior.
- **Done when:** no module is larger than about 40 KB, the imports are re-exported for compatibility, and the full suite and war games pass unchanged.

## Relationship to NouGenShards#551 and #550

| This atlas | #551 tracks | #550 families owned here |
|---|---|---|
| Zones 1-3 | Track 1 (1-50) | 1-11, 69, 84-90, 97-99 |
| Zones 4-5, 7 | Track 1 (19-20, 38-40), Track 20 (987) | 3, 9-15 |
| Zone 6 | Track 2 (51-100) | 12-15, 27-28, 91-96 |
| Zone 8 | Track 16 (751-800) | 69-76 |
| Zone 9 | Track 1 (13-15, 42-43), Track 2 (93-95) | 86-88, 93 |
| Zone 10 | Track 20 (951-1000) | 100 |

Bus families 16-20 and 39-50 belong to NouGenMsg (Track 4). Here they matter only where the bus is implemented, in `src/nougen_shards/nougenmsg.py`.

How a step becomes a PR: (1) the step here names its evidence; (2) it becomes a #550 scenario in `tests/wargames/` with a JSON receipt; (3) a bounded PR fixes one subsystem and turns the scenario from failing to passing; (4) the defect stays as a regression fixture, and the glyph changes only when the mechanism is merged.

## Zone index

| Zone | Title | Steps | Focus | ✅ | 🟡 | ⬜ |
|---|---|---|---|---|---|---|
| 1 | Memory Physics | 1-100 | Identity, schema, amend/retract/forget | 28 | 24 | 48 |
| 2 | Capture Intelligence | 101-200 | Ingest gates, redaction, embedding | 20 | 25 | 55 |
| 3 | Retrieval Intelligence | 201-300 | Fusion, fallback, recall proofs | 21 | 36 | 43 |
| 4 | Memory Graph | 301-400 | Relations, edges, lineage | 10 | 17 | 73 |
| 5 | Temporal Memory and Griot | 401-500 | Time, coverage receipts | 10 | 34 | 56 |
| 6 | Federation and Multi-Vault Truth | 501-600 | Fan-out, replication, reconciliation | 15 | 22 | 63 |
| 7 | Truth, Contradiction and Canon Engine | 601-700 | Canonical facts, evidence | 13 | 49 | 38 |
| 8 | Security, Privacy and Sovereignty | 701-800 | Vault, keys, public hygiene | 42 | 17 | 41 |
| 9 | Performance, Scale and Million-Shard Architecture | 801-900 | ANN, grid, benchmarks | 13 | 20 | 67 |
| 10 | Autonomous Memory Organism | 901-1000 | Census, evolution, self-regeneration | 7 | 26 | 67 |
| **Total** | | 1000 | | 179 | 270 | 551 |

## Zone 1: Memory Physics (steps 1-100)

1. **Pin the shard row contract** — 🟡 `src/nougen_shards/core.py` init_db (~418-500) defines `shards` columns; gap: no single documented field list, types or nullability outside the ALTER soup. [551:#49]
2. **Unify schema versioning** — 🟡 `schema.py` TARGET_SCHEMA_VERSION=3 (v1-v3 Migration list ~202); gap: core.py adds "schema v4" columns (valid_until, last_verified, learned_utc, source_uri) that schema.py never migrates or stamps. [551:#11]
3. **Route all DDL through schema.py** — ⬜ core.init_db still runs try/except ALTER TABLE on every open; land migrations only in `schema.py` and have init_db call the runner. [551:#11]
4. **Stamp user_version on every grid DB** — 🟡 `schema.py` `_user_version` reads/writes it in plan/apply; gap: normal init_db startup never stamps, so live DBs can report 0. [551:#36]
5. **Read-only migration verifier** — ✅ `schema.py` plan_vault is dry-run by default, `--execute` backs up to `<db>.bak` first (module docstring). [551:#12]
6. **Cross-version compatibility test** — ⬜ add `tests/test_schema_compat.py` opening v0-v3 fixture DBs through capture/retrieve. [551:#36]
7. **Content-addressed identity** — ✅ `core.capture` computes `fhash = md5(clean_content)` (~1081); `file_hash UNIQUE NOT NULL`. [550:#8]
8. **Global dedupe map** — ✅ `core` `hashes(file_hash PRIMARY KEY, db_index)` (~602) checked in capture (~1106) before insert. [551:#5] [550:#8]
9. **Hash algorithm versioning** — ⬜ fhash is bare MD5 hex with no algorithm prefix; add `hash_alg` column or `md5:` prefix in core.capture so a future digest cannot collide semantically. [551:#34]
10. **Canonical serialization before hashing** — 🟡 capture hashes redacted, recall-packet-stripped content only; gap: no Unicode/newline normalization, title/tags excluded, so trivially different bodies fork identities. [551:#9]
11. **Deterministic hash routing** — ✅ `core.get_routing_index` = int(fhash,16) % MAX_DB_COUNT + 1 (~206), with overflow walk (~216). [550:#98]
12. **Dedupe collision audit** — ⬜ add a job in `core` or `tools/` comparing content for equal fhash across the 9 DBs and hashes table. [551:#33]
13. **Duplicate-capture convergence test** — 🟡 capture returns reason "duplicate" (~975); gap: no concurrent same-content capture test across processes. [551:#5] [550:#8] [550:#84]
14. **Fix amend hash drift** — ⬜ DEFECT: `app.py shard_amend` (~597) UPDATEs content in place; file_hash no longer addresses the body, breaking get_shard_by_hash and sync hash reconciliation. Amend must append a child shard. [550:#9]
15. **Fix amend on encrypted shards** — ⬜ DEFECT: shard_amend/shard_retract concatenate plaintext onto `ngenc1:` ciphertext when enc=1, making the body undecryptable; decrypt-append-reencrypt or refuse in `app.py`. [550:#9] [550:#10]
16. **Redact amend/retract notes** — ⬜ DEFECT: app.py shard_amend/shard_retract bypass `brain_scan.redaction.redact_content`, which capture applies (~1043); a secret in a note lands unredacted. [550:#70]
17. **Log amend/retract/forget to history** — ⬜ capture logs CREATED via `history.log_event` (~1234); app.py amend/retract/forget log nothing. Add events. [551:#6]
18. **Revision lineage table** — ⬜ add `shard_revisions(file_hash, parent_hash, op, utc, agent)` in `history.py` so amendments form a graph, not a merged text blob. [551:#6]
19. **Retract as state, not text** — 🟡 app.py shard_retract prefixes `[RETRACTED]`, tags `retracted`, utility 0.0; gap: no status column, detection is by title prefix (idempotency check ~624). [551:#7] [550:#10]
20. **Retract visibility invariant test** — ⬜ add test that retracted shards never outrank live ones in `core.retrieve` and remain fetchable by hash. [551:#7] [550:#10]
21. **Forget tombstones** — ⬜ DEFECT: app.py shard_forget DELETEs with "no tombstone" and leaves the `hashes` map row; add `tombstones(file_hash, utc, reason)` in core. [551:#8] [550:#11]
22. **Resurrection protection on sync** — ⬜ `/sync/push` re-captures via core.capture (~app.py 1719); without tombstones a peer re-inserts forgotten content. Check tombstones before insert. [551:#8] [550:#11] [550:#15]
23. **Wire or delete LineageUnlearner** — 🟡 `unlearning.py` has dry-run impact reports and retract/forget/quarantine; gap: imported by nothing in src/app/tools, and writes `temporal_status`, `dedup_map`, `ctx_events` which init_db never creates.
24. **Unlearning dry-run default** — 🟡 `unlearning.py DryRunImpactReport` exists; gap: unreachable from app.py shard_forget, which executes immediately.
25. **Forget propagation test** — ⬜ add `tests/test_forget_propagation.py`: forget on one grid, sync_pull from peer, assert absent. [551:#8] [550:#11]
26. **Supersession edges** — 🟡 `consolidate.py` emits `supersedes:<id@dbN>` tags (~173), never deletes; gap: tag-only, feature flag `enabled()`, not a queryable edge. [550:#9]
27. **Canon never superseded by lower authority** — ✅ `consolidate.consolidate` guards locked/canon neighbours, returns CONFLICT (~11, ~127). [550:#9]
28. **Identical restatement is duplicate** — ✅ `consolidate.consolidate` guard `supersede_of_identical_fact` (~107). [550:#8]
29. **Stable cross-DB shard ID** — 🟡 compound `id@dbN` used in consolidate and griot_v2; gap: integer ids repeat per DB (app.py shard_forget docstring); make file_hash the canonical external ID everywhere.
30. **Confirm-title guard on mutations** — ✅ `app.py _resolve_shard(expect_title=)` used by amend/retract/forget (~591, ~623, ~662).
31. **Machine provenance** — 🟡 capture stamps `socket.gethostname()` into `machine` (~1229); gap: raw hostname, not normalized to blade/whoart/phoebus node names; leaks private hostnames into synced rows. [551:#96]
32. **Agent identity per shard** — 🟡 capture tags `via:<agent>` (core ~2530); gap: no column, not validated. Add `agent` column in schema.py. [550:#18]
33. **Ingestion source URI** — ✅ `source_uri` column (core ~487) redacted and written by capture (~1070).
34. **Bi-temporal timestamps** — ✅ `timestamp` event time + `learned_utc` store time (core ~490-496), written at capture (~1229). [550:#14]
35. **Future-dated shard guard** — ⬜ capture accepts any event timestamp; clamp or flag skew beyond tolerance in core.capture. [550:#14] [550:#13]
36. **Validity window** — ✅ `valid_until`, `last_verified` columns (core ~474-480); recall demotes expired via `_mark_expired`.
37. **Per-shard source confidence** — ⬜ no confidence column; add `confidence REAL` in schema.py + capture param. [551:#10]
38. **Source reliability class** — 🟡 `evidence_ledger.py Provenance` enum (~19) classifies sources; gap: ledger is separate, not linked to shards rows. [551:#10]
39. **Link shards to evidence ledger** — ⬜ add `claim_sources` references from shard file_hash in `evidence_ledger.py`.
40. **Corrections as ledger rows** — ✅ `evidence_ledger.py` `corrections` and `conflicts` tables (~140, ~150).
41. **Sensitivity classification** — ✅ `private_vault.normalize_sensitivity`/`should_encrypt` (~76-81) applied in core.capture (~1056, ~1203).
42. **Encryption at rest** — ✅ `private_vault.encrypt_text` AES-256-GCM `ngenc1:` (~300) sets enc=1 in capture.
43. **Decrypt failure is explicit** — ✅ core (~2766) returns `[encrypted shard -- unavailable: ...]`, never silent empty.
44. **Sync hashes plaintext, not ciphertext** — ✅ app.py sync push (~1716-1723) decrypts ngenc1 via `private_vault.decrypt_text` before capture so hashes represent plaintext.
45. **Secret redaction before write** — ✅ core.capture calls `redact_content` on title/content/tags/source_uri (~1038-1070). [550:#70]
46. **Domain namespace** — ✅ `domain_key` column default 'global' (core ~427) with index idx_shards_domain_utility. [550:#5]
47. **Project/repo/task namespaces** — ⬜ only domain_key and free tags exist; add structured `namespace` fields in schema.py rather than tag conventions.
48. **Episodic vs semantic split** — 🟡 `semantic_knowledge` table (core ~508) beside `shards`; gap: no promotion rule or link back to source shards.
49. **Memory kind taxonomy** — ⬜ `event_type` is free text; add an enum (decision, incident, preference, procedure, hypothesis, negative) validated in core.capture.
50. **Fact vs hypothesis flag** — ⬜ add `epistemic` field (fact/hypothesis/candidate) in schema.py; consolidate only supersedes facts.
51. **Canonical fact index** — ✅ `canonical_facts.CanonicalFactIndex` (~184) with `validate_snapshot` (~70) and `_canonical_json` (~154); 14 tests in tests/test_canonical_facts.py.
52. **Link canonical facts to shard hashes** — 🟡 canonical_facts keeps its own index; gap: no file_hash foreign reference, so canon cannot cite supporting shards.
53. **User-authored vs machine-inferred** — ⬜ add `origin_kind` column (human/agent/derived) in schema.py; stamp in capture.
54. **Negative knowledge shards** — ⬜ define event_type `absence` carrying coverage receipt in core.capture; ties to status_semantics.py. [550:#3]
55. **Utility and access counters** — ✅ `utility_score`, `access_count` columns (core ~425-426); utility blends into ranking.
56. **Recall reinforcement is deterministic** — ✅ tests/test_core_determinism.py `test_retrieve_order_is_invariant_to_clock_advance`. [550:#99]
57. **Explicit permanence / protected shards** — ⬜ add `protected` flag in schema.py that app.py shard_forget refuses without override.
58. **Retention policy per class** — ⬜ add retention rules in a new `src/nougen_shards/retention.py` keyed on sensitivity and kind.
59. **Relationship edges** — 🟡 `graph.py` holds relations (`shard_edges`); gap: edges keyed by id not file_hash in places, and test_graph.py has an order-dependent flake. [550:#83]
60. **Typed edge vocabulary** — ⬜ define supports/contradicts/supersedes/derived_from/summarizes in graph.py with validation.
61. **Contradiction state** — 🟡 `reconstructive_recall_v2.py` handles contradictions at read time; gap: no persisted contradiction edge.
62. **Derived/summary shards cite sources** — ⬜ require `derived_from` edges when dream/consolidation writes summary shards.
63. **Attachment references** — ⬜ add `artifact_refs` (hash + uri) column; bodies stay out of the DB.
64. **Maximum shard size** — ⬜ no per-shard size cap in core.capture; add `NOUGEN_MAX_SHARD_BYTES` refusal with skip contract. [551:#31]
65. **Shard size telemetry** — ⬜ add size histogram to status output in core. [551:#31]
66. **Junk-ingest gate** — 🟡 HARDENING §7 and tools/capture_doctrine.py describe `_looks_like_blob`; gap: that function does not exist anywhere in src. [551:#32]
67. **Junk-gate receipts** — ⬜ once the gate lands, return reason "junk" through `CaptureResult` in core (~975). [551:#32]
68. **Embed-at-ingest accounting** — ✅ `core.EMBED_AT_CAPTURE_MISSES` incremented on embed failure (~854-894).
69. **Malformed grid DB quarantine** — ✅ `core.quarantine_malformed_dbs` (~309) moves and recreates; test_quarantine_malformed_on_boot.py. [551:#21] [550:#6]
70. **Locked is not corrupt** — ✅ capture reroute path treats locked/busy as non-quarantine (~1248); test_write_quarantine.py. [550:#86]
71. **Write-quarantine reroute** — ✅ core `_next_write_target` skips quarantined indexes (~950) and raises when all are. [551:#21]
72. **Malformed shard row quarantine** — 🟡 app.py sync push counts `skipped_malformed` (~1712); gap: no quarantine table for bad rows, they are just dropped.
73. **Per-DB size limit** — ✅ `core.MAX_DB_SIZE` via NOUGEN_MAX_DB_SIZE (~47) checked at ~195. [550:#87]
74. **Content-hash lookup** — ✅ `core.get_shard_by_hash` exact and prefix with ambiguity refusal (~2785-2824); tests/test_content_addressing.py.
75. **Hash-map rebuild** — ✅ core rebuilds `hashes` from every DB (~618-630).
76. **Hash map purge on forget** — ⬜ DEFECT: shard_forget leaves a stale `hashes` row, so capture dedupe (~1106) may skip re-capturing legitimately. Delete it in app.py shard_forget.
77. **Per-vault integrity manifest** — ⬜ add manifest (count + sorted-hash digest) per grid DB in core. [551:#22] [551:#23]
78. **Crash-consistent capture test** — ⬜ kill between shards insert and hashes insert (~1226-1241); assert repair. [551:#25] [550:#90]
79. **Lock contention test** — 🟡 locked handling exists (~1248); gap: no multi-writer stress test. [551:#26] [550:#86]
80. **Disk-full and read-only FS tests** — ⬜ add temp-store tests in tests/ for capture under ENOSPC and EROFS. [551:#28] [551:#29] [550:#87] [550:#89]
81. **Partial-write recovery** — ⬜ add truncated-DB fixture test through quarantine_malformed_dbs. [551:#27] [550:#88]
82. **Backup restore drill** — 🟡 schema.py writes `.bak`; gap: no restore command or test. [551:#24]
83. **History DB writer lock** — ✅ `history._writer_lock` (~146) serializes `log_events`.
84. **History coverage test** — 🟡 tests/test_history_engine.py has 1 test; gap: tests/SHARD_HISTORY_PLAN.md scope largely unexecuted.
85. **Idempotent replay harness** — ⬜ replay a capture log into an empty grid, assert identical hashes map. [551:#35] [550:#15]
86. **Out-of-order replay test** — ⬜ amend-before-capture and forget-before-capture ordering in the replay harness. [551:#6] [550:#15]
87. **Near-duplicate relationship** — ⬜ no simhash/minhash in src; add near-dup edge in graph.py at capture.
88. **Conflict fingerprints** — ⬜ fingerprint (subject, predicate) in canonical_facts to detect conflicting facts.
89. **Invariant registry** — 🟡 HARDENING.md lists 9 invariants; gap: prose only, no machine-checked registry mapping each to a test. [551:#1]
90. **Restore the wargame receipts** — ⬜ HARDENING.md cites `wargames/*.md` that do not exist; add them or fix the references. [550:#100]
91. **Property tests for capture** — ⬜ hypothesis tests: redaction idempotent, hash stable, route in 1..9.
92. **Executable schema tests** — ⬜ assert init_db and schema.py migrations yield identical column sets.
93. **Origin signatures** — ⬜ sign (file_hash, machine, agent) with node key from fleet_keys.py. [551:#96]
94. **Replication fingerprint set** — 🟡 app.py `/sync/hashes` (~1891) lists hashes; gap: no tombstone set, no digest compare. [551:#61]
95. **Memory strength decay metadata** — ⬜ record decay params per shard instead of implicit ranking.
96. **Working-memory tier** — ⬜ ephemeral shards with TTL in a separate table, never synced.
97. **Multimodal references** — ⬜ link visual_evidence.py outputs as artifact_refs.
98. **Shard Protocol v1 spec** — ⬜ `docs/shard-protocol-v1.md` from the frozen schema and tests. [551:#49]
99. **Conformance suite** — ⬜ `tests/protocol_v1/` any node must pass before sync. [551:#92]
100. **Freeze Protocol v1** — ⬜ tag schema version and hash alg once steps 1-99 hold.

### Zone 1 verdict
- Exists: content-addressed capture (`core.capture` MD5 fhash, global `hashes` map, redaction, AES-GCM `ngenc1:` for private/secret, bi-temporal and validity columns), DB quarantine, and a dry-run `schema.py` runner.
- Load-bearing gap: mutation physics. `app.py shard_amend` rewrites content in place (hash drift, and it corrupts encrypted bodies); `shard_forget` hard-deletes with no tombstone and no history, so `/sync/push` can resurrect forgotten shards.
- First PR: "shards: append-only amend, tombstoned forget, history events" touching `app.py` (shard_amend/retract/forget), `src/nougen_shards/core.py` (tombstones table, capture tombstone check), `src/nougen_shards/history.py`, and new `tests/test_mutation_physics.py`.
- Contradictions: HARDENING §7 `_looks_like_blob` and §4 `core.lane_health()` are not in src; schema.py stops at v3 while core adds v4 columns; `unlearning.py` is dead code writing tables/columns that init_db never creates; shard_amend's docstring says "history is never rewritten", but the code rewrites it.

## Zone 2: Capture Intelligence (steps 101-200)

101. **Implement the missing junk gate** — ⬜ HARDENING.md §7 claims done `_looks_like_blob` in `core.capture()`; zero hits for it anywhere in the tree (removed in the core.py rewrite around commit 6f48135, #500). Land `_looks_like_blob` + `NOUGEN_JUNK_MAX_TOKEN`/`NOUGEN_JUNK_ALPHABET_RATIO` in `src/nougen_shards/core.py` [550:#8] [551:#32]
102. **Restore tests/test_ingest_junk_gate.py** — ⬜ cited by HARDENING §7 as "4 tests"; the file does not exist. Recreate: base64 run rejected, hex dump rejected, minified bundle rejected, prose and real code pass [551:#32]
103. **Correct HARDENING §7 status to match code** — 🟡 §7 text exists but claims done for absent code, repeating the §2 two-month failure; downgrade to missing until 101-102 merge, citing this step [551:#1]
104. **Wire NOUGEN_MIN_DENSITY floor** — ⬜ HARDENING §7 names an opt-in density floor; `NOUGEN_MIN_DENSITY` has zero hits in src/tools. `density_score` is computed (`core.calculate_contrastive_perplexity`) but never compared; add the floor in `core.capture()` [551:#32]
105. **Restore tests/test_capture_secret_guard.py** — 🟡 redaction runs in `core.capture()` (lines ~1043-1046, 1070) and `tests/test_audit_fixes.py` tests `redact_content` directly; the capture-level regression file HARDENING §8 cites does not exist. Add an end-to-end capture test [550:#70]
106. **Assert no plaintext secret reaches embedding or FTS** — ⬜ redaction precedes hashing/embedding in `core.capture()`; no test proves the stored row, `shards_fts` and embedding input are all redacted. Add to `tests/test_capture_secret_guard.py` [550:#70]
107. **Redact before snapshot forward** — ✅ `core.capture()` redacts title/content/tags before the `snapshot_mode.forward_capture` branch, so forwarded captures carry redacted text [550:#70]
108. **Redact source_uri** — ✅ `core.capture()` applies `redact_content` to `source_uri` before storage (`source_uri_value`)
109. **Route ingest_pending_shard through core.capture** — ⬜ `tools/ingest_pending_shard.py` INSERTs directly into a legacy vault DB (line ~93), bypassing redaction, dedupe, embed and grid routing; rewrite to call `core.capture()` [550:#70]
110. **Drop the stale default shard path** — 🟡 `tools/ingest_pending_shard.py` `DEFAULT_SHARD` points at a dated `pending_shards/` file; require an explicit path argument
111. **Unify redaction and credential_patterns** — 🟡 `brain_scan/redaction.py` `SECRET_PATTERNS` and `src/nougen_shards/credential_patterns.py` both define secret shapes; make one registry and test both callers against it
112. **Capture size ceiling** — ⬜ `core.capture()` has no maximum body length (only `cli.py` ~1010 truncates display at 2000 chars); add a `NOUGEN_CAPTURE_MAX_CHARS` refusal with reason `rejected` in `core.py` [551:#31] [550:#87]
113. **Dedup hit reports durable identity** — ✅ `core.capture()` returns `existing_db_index`/`existing_shard_id`/`durable=True` with `reason="duplicate"` and no claimed `shard_id` [550:#8]
114. **Stale-index IntegrityError self-repair** — ✅ `core.capture()` `except sqlite3.IntegrityError` inserts the missing `hashes` row and returns duplicate [550:#84]
115. **Duplicate capture convergence test across nodes** — ⬜ dedupe is per-node hash index only; add `tests/test_capture_convergence.py` proving the same payload captured on two grids converges to one hash [551:#5] [550:#8]
116. **Refuse empty bodies after stripping** — ⬜ `core.capture()` (~1074-1082) strips a recall-packet suffix, then hashes `clean_content` even when empty, so every packet-only capture collapses to one MD5 identity; refuse empty or whitespace-only bodies [550:#8] [551:#32]
117. **Event-type registry at capture** — ⬜ `core.capture()` stores any `event_type` string unchecked, yet recall filters on it (`NOUGEN_RECALL_EXCLUDE_EVENT_TYPES`, core.py ~1546); add an allowlist in `core.py` with a test [551:#1]
118. **Normalize tags at capture** — ⬜ `core.capture()` (~1045-1053, ~1172) stores tags as given via `json.dumps`, so case, whitespace and duplicate variants split scope filters; sort, dedupe and trim tags in `core.py` [551:#9]
119. **Race-safe concurrent capture** — 🟡 UNIQUE(file_hash) plus IntegrityError path covers same-DB races; no test for two processes racing the central index. Add to `tests/test_capture_convergence.py` [550:#84]
120. **Embed at capture** — ✅ `core._embed_for_capture` called from `core.capture()` when `embedding is None`; toggle `NOUGEN_EMBED_AT_CAPTURE`, timeout `NOUGEN_EMBED_TIMEOUT` [551:#16]
121. **Expose EMBED_AT_CAPTURE_MISSES** — 🟡 module global counter in `core.py` (~854), logged per miss; process-local and lost on restart. Surface it in `node_status` (app.py) and persist in history [551:#16]
122. **Record embed misses on the shard** — ⬜ a miss leaves `embedding` NULL with no reason; add an `embed_status` field or history event in `core.capture()`
123. **Backfill queue for missed embeds** — 🟡 `embedding_backfill` exists as a sweep; no targeted queue of rows missed at capture. Feed from 122
124. **Capture result contract** — ✅ `core.CaptureResult` carries `captured`, `reason` (written/duplicate/error), `shard_id`, `db_index`, `error`
125. **Add `rejected` reason for gate refusals** — ⬜ once 101 lands, junk refusal must be distinct from `duplicate` (callers like `tools/arxiv_backlog_ingest.py` conflate them as "skipped_dedupe_or_junk") [551:#32]
126. **Junk classifier receipts** — ⬜ refusals leave no trace; log a `REJECTED` history event with gate name and metric from `core.capture()` [551:#32]
127. **Corrupt-DB write reroute** — ✅ `core.capture()` quarantines a malformed DB in `_QUARANTINED_WRITE_DBS`, logs `DB_DEGRADED`, retries `_next_healthy_write_index` [551:#21]
128. **CREATED provenance event** — ✅ `history.log_event(..., "CREATED")` in `core.capture()` after commit
129. **Machine provenance on write** — 🟡 done: `machine` column set from `socket.gethostname()` in the INSERT; gap: map to blade/whoart/phoebus names before any public export (hygiene)
130. **Original-timestamp normalization** — ✅ `core.capture()` parses `original_timestamp` to UTC ISO, warns and falls back on parse failure
131. **Validity window at capture** — ✅ `valid_until` normalized by `_normalize_iso` and stored with `last_verified`
132. **Private sensitivity encryption** — ✅ `private_vault.should_encrypt` + `encrypt_text` just before INSERT in `core.capture()`
133. **Auto-classify sensitivity** — ⬜ `sensitivity` defaults to caller choice via `normalize_sensitivity`; add a personal-scope detector (finance/health/ID shapes) in `private_vault.py`
134. **Keep identifying detail out of titles for private shards** — 🟡 docstring warns titles stay plaintext; nothing enforces it. Add a title check in `core.capture()` when sensitivity is private/secret
135. **Utility prior validation** — ✅ `core.capture()` coerces `utility` to float with warning fallback 1.0
136. **Domain inference** — 🟡 `resolve_domain_from_path()` uses cwd when `domain_key` absent; content-based domain inference missing. Add in `core.py`
137. **Capture write-time consolidation** — 🟡 `consolidate.consolidation_tags` (Jaccard + ollama decider) tags supersede/conflict/duplicate, opt-in via `consolidate.enabled`; off by default and never blocks
138. **Semantic duplicate detection** — 🟡 `consolidate.py` `_jaccard`/decider flag duplicates only when enabled; add an embedding-cosine near-dup check using the capture vector
139. **Contradiction detection before capture** — 🟡 `consolidate` decider can emit conflict tags; no contradiction corpus or test. Add `tests/test_capture_contradiction.py`
140. **Supersession link, not tag** — ⬜ consolidation writes tags only; store `supersedes` relation via `graph.py` at capture
141. **Remove the hardcoded consolidate model** — 🟡 `consolidate.ollama_decider(model="gemma4:e2b-qat", host=<loopback>)` defaults; route through `ollama_host.discover_ollama_url` and env model
142. **Capture preview / dry run** — ⬜ `core.capture()` has no dry_run; `brain_scan.importer.run_import` has an estimation dry run only. Add `dry_run=True` returning the would-be CaptureResult
143. **Capture explanation** — ⬜ return which gates ran (redaction count, dedupe, junk, embed) in CaptureResult from `core.capture()`
144. **Redaction count in result** — ⬜ `redact_content` returns text only; add a count variant in `brain_scan/redaction.py` so capture can report redactions [551:#32]
145. **Brain-scan file classification** — ✅ `brain_scan/classifiers.classify_file` scores high/medium/low from `registry` term lists
146. **Brain-scan content classification** — ⬜ `classify_file` inspects path/name only; add content shape (blob, lockfile, vocab) checks reusing 101
147. **Safe scanning walk** — ✅ `brain_scan/scanner._safe_walk`, `_is_safe_dir`, `_within_size_budget`, `.memoryignore` via `_is_memoryignored`
148. **Import redacts by default** — ✅ `brain_scan/importer.run_import(redact=True)` applies `redact_content` and counts `secrets_redacted`
149. **Import requires confirm** — ✅ `run_import(confirm=False)` default estimates only
150. **Tool detection** — 🟡 done: `classifiers.detect_tool` names the source tool; gap: `unknown` fallback carries no provenance hint
151. **Atomize handoffs into claims** — ✅ `tools/atomize_handoffs.py` extracts single-claim DOCTRINE shards via `core.capture` (deduped)
152. **Atomize journal shards** — ✅ `tools/atomize_journal_shards.py` line ~112 captures each claim as DOCTRINE
153. **Move atomizers into the package** — 🟡 both tools default to `~/Watchtower` roots and manipulate `sys.path`; land `src/nougen_shards/atomize.py` with a CLI verb
154. **Atomicity scoring** — ⬜ atomizers trust LLM claim splits; add a claim-length/single-predicate score in the new `atomize.py`
155. **Session-end trace** — 🟡 `tools/handoff_guard.py --mode sessionend` writes an auto-stub handoff file + `rebuild-db`; it does NOT capture a vault shard as HARDENING §1 states. Add a `core.capture()` call
156. **handoff_guard interpreter path** — 🟡 `NOUGEN_PY` default is `.venv/Scripts/python.exe` (Windows-only); fall back to `sys.executable` in `tools/handoff_guard.py`
157. **Product-lane session capture** — ⬜ HARDENING §1 open item; app session close must call `core.capture()` (app.py)
158. **Capture doctrine seeding** — 🟡 done: `tools/capture_doctrine.py` captures DOCTRINE shards; gap: its §7 text asserts `_looks_like_blob` exists, so re-seeding writes a false fact until 101 lands
159. **MCP capture_experience uses core.capture** — ✅ `app.py capture_experience` (~236-248) and HTTP path (~1682) call `core.capture`
160. **Git hooks carry identity only** — 🟡 `hooks/pre-commit`, `hooks/prepare-commit-msg` locate the relay CLI; no secret scan of staged files. Add redaction-pattern scan in `hooks/pre-commit` [550:#76]
161. **Inbound message triage** — ✅ `taskflow_triage.py` `classify_payload` urgency P0-P3, `triage_directory`, `generate_report`
162. **Triage to capture candidates** — ⬜ triage items never become shards; add a candidate emit from `taskflow_triage.py` into the review queue (175)
163. **Relay triage eval** — 🟡 `tools/relay_triage.py` + `relay_triage_eval.py` exist; no precision numbers recorded in CI
164. **Prompt-injection flag at ingestion** — ⬜ capture stores instruction-shaped content verbatim; add a detector tagging `untrusted-instruction` in `core.capture()` [550:#69]
165. **Recall-time injection fence** — ⬜ recalled content is not fenced as data; wrap in recall packet builder in `core.py` [550:#69]
166. **Forged sender text in bodies** — ⬜ capture of messages keeps sender only as text; bind sender to origin envelope fields [550:#19]
167. **Machine-generated fact label** — ⬜ no field distinguishes agent inference from user statement; add `origin_kind` tag convention in `core.capture()`
168. **User vs assistant statement separation** — ⬜ conversation captures store merged text; split roles in the conversation adapter (new `src/nougen_shards/capture_adapters/`)
169. **Quote vs assertion separation** — ⬜ add quoted-span detection in the same adapter
170. **Uncertainty preservation** — ⬜ hedges ("maybe", "CANDIDATE") are not structured; map to a `confidence` field (HARDENING §9 uses CANDIDATE manually)
171. **Canon vs candidate declaration** — 🟡 `canonical_facts.py` v2 index holds canonical_current; capture does not route "CANON:" declarations there. Add dispatch in `core.capture()`
172. **Correction/amend detection** — 🟡 amend/retract/forget exist (`unlearning.py`, app `shard_amend/retract/forget`); capture does not detect correction intent. Add intent classifier
173. **Relative date normalization** — ⬜ "yesterday"/"last week" in content are not resolved; add to capture adapter using capture timestamp
174. **Future-dated capture guard** — ⬜ `original_timestamp` accepts future dates; reject or flag beyond skew in `core.capture()` [550:#14]
175. **Candidate/review queue** — ⬜ no queue between ingest and canonical; add `src/nougen_shards/capture_queue.py`
176. **Promotion receipts** — ⬜ promotion to canonical writes no receipt; log history event with evidence refs
177. **Entity resolution** — ⬜ no entity table; land in `graph.py` relations at capture
178. **Repository/PR/relay linking** — ⬜ GitHub, relay and message ids stay free text; parse into relations in `graph.py`
179. **Automatic tagging** — ⬜ tags come only from callers and consolidation; add keyword tagger in `core.py`
180. **Capture rate limit** — ⬜ nothing bounds writes per agent; add token bucket in `app.py` capture routes
181. **Capture budget for embeds** — 🟡 per-call timeout only (`DEFAULT_EMBED_CAPTURE_TIMEOUT_S`); no aggregate budget on bulk import
182. **Batch capture API** — 🟡 `/sync/push` batches exist in app.py; no local `capture_many` with per-item results in `core.py`
183. **Structured JSON capture** — ⬜ content is text; add schema-validated JSON payload mode
184. **Existing blob-shard audit** — ⬜ HARDENING §7 open item; read-only `tools/audit_blob_shards.py` before any purge (GM sign-off)
185. **Pre-guard secret backfill sweep** — ⬜ HARDENING §8 open item; read-only report first, `tools/redact_backfill.py` [550:#70]
186. **Recreate wargames/ docs** — ⬜ HARDENING cites `wargames/ingest-junk-gate.md` and `capture-secret-guard.md`; no wargames/ dir exists. Land them or remove the citations
187. **False-positive corpus** — ⬜ `tests/fixtures/capture/fp/` of prose and code that gates must pass
188. **False-negative corpus** — ⬜ `tests/fixtures/capture/fn/` of blobs and secrets that must be caught
189. **Duplicate corpus** — ⬜ paraphrase/whitespace variants for 118 and 138
190. **Contradiction corpus** — ⬜ fixture pairs for 139
191. **Adversarial capture tests** — ⬜ injection, zero-width chars, split secrets across tags; `tests/test_capture_adversarial.py` [550:#69]
192. **Capture benchmark** — ⬜ time per gate and embed; `tools/capture_bench.py`
193. **Multi-shard decomposition** — ⬜ generalize atomizers into capture-time splitting (opt-in)
194. **Timeline linking** — ⬜ connect captured events into temporal_fabric at write
195. **Plugin capture adapters** — ⬜ adapter interface in `capture_adapters/` for files, transcripts, repos
196. **Stream capture** — ⬜ incremental capture from message bus inbox
197. **Autonomous capture policy** — ⬜ declarative policy for what agents may self-capture
198. **Embedding-inversion defense** — ⬜ HARDENING §9 CANDIDATE; stored vectors of private shards remain plaintext
199. **Memory Precision Score** — ⬜ precision of captured shards against corpora 187-190, published per node
200. **Nightly capture war-game** — ⬜ run corpora + gates nightly with receipts [551:#50] [550:#100]

### Zone 2 verdict
- Exists: redaction in `core.capture()` before hash/embed/FTS/forward; O(1) hash dedupe with durable identity; embed-at-capture with `EMBED_AT_CAPTURE_MISSES`; corrupt-DB reroute; brain_scan importer that redacts and requires confirm; atomizers; opt-in consolidation.
- Load-bearing gap: the ingest junk gate does not exist. `_looks_like_blob`, `NOUGEN_JUNK_*`, `NOUGEN_MIN_DENSITY` and `tests/test_ingest_junk_gate.py` are absent while HARDENING §7 claims ✅.
- First PR: "fix(capture): restore ingest junk gate and capture secret-guard tests" — `src/nougen_shards/core.py`, `tests/test_ingest_junk_gate.py`, `tests/test_capture_secret_guard.py`, `HARDENING.md`, `CHANGELOG.md`.
- Contradictions: HARDENING §7 ✅ junk gate (no code); §8 cites a missing test file; §1 says handoff_guard writes a vault shard (it writes a handoff file); `tools/capture_doctrine.py` seeds a DOCTRINE shard asserting the gate exists; wargames/ docs cited but absent.
- Bypass: `tools/ingest_pending_shard.py` writes raw SQL, skipping every capture gate.

## Zone 3: Retrieval Intelligence (steps 201-300)

201. **Restore the lane-health sensor HARDENING §4 claims** — ⬜ HARDENING.md §4 marks done `core.lane_health()` and `tests/test_lane_health.py`; neither exists (zero grep hits in src, tests, app.py). Land it in `src/nougen_shards/core.py` with the named test. [551:#37] [550:#1] [550:#2]
202. **Make empty recall packets carry coverage, not a bare marker** — ⬜ `core.compile_recall_packet` and `compile_recall_packet_dual` both return `<!-- NO RELEVANT MEMORY RECALLED -->` with no counts or embedding coverage; emit lane health plus `NOUGEN_MIN_COVERAGE_PCT` verdict there. [551:#38] [550:#1] [550:#3]
203. **Correct HARDENING §4 status to the truth** — ⬜ `HARDENING.md` §4 is a false done (the exact failure its own preamble warns about); downgrade to missing until 201-202 land, and add a CI grep asserting every done-cited symbol resolves. [551:#1]
204. **Fix the no-op zero-hit angle sweep** — ⬜ `compile_recall_packet` calls `retrieval_angle_sweep("", [])` (empty query, zero sources) and discards the envelope; it can never recover anything. Pass the real query and sources, or delete the call, in `core.py`. [550:#1] [551:#44]
205. **Typed unknown vs empty result** — 🟡 `retrieval_v2.QueryCoverage`/`Completeness` literals (EMPTY, COVERAGE_UNKNOWN, INDETERMINATE) exist; gap: `core.retrieve` returns a bare `list`, so callers cannot distinguish empty from unread. Return a result object from `retrieve`. [551:#39] [550:#3]
206. **Keep FTS AND->OR->LIKE ladder** — ✅ `core._keyword_retrieve` (~1596-1700) builds implicit-AND, retries with `_build_fts_match_query(joiner=" OR ")`, tags `_or_retry`, then LIKE; covered by `tests/test_fts_or_fallback.py`. [550:#4] [551:#2]
207. **Tier OR-retry hits below full-coverage hits** — ✅ `core._keyword_retrieve` `_tier()` (~1872-1883) orders full-coverage AND/LIKE hits before `_or_retry` rows with `(_db_index, id)` tie-break. [550:#4]
208. **Quote every FTS token against operator injection** — ✅ `core._build_fts_match_query` doubles embedded quotes and wraps each token, so `AND`, `c++`, bare quotes cannot parse as FTS5 operators. [551:#41]
209. **Report dropped short tokens and boilerplate** — 🟡 `_build_fts_match_query` silently drops tokens <3 chars and a boilerplate stop-list (`fix`, `run`, `test`, `code`); (kept only if every token is boilerplate); gap: no receipt says which words were ignored. Emit them in the receipt. [551:#44]
210. **Coverage trust must fail closed on errored DBs** — ✅ `app._substrate_coverage` (~1039-1120) sets `recall_trustworthy=False` when `databases_errored` is non-empty; `tests/test_coverage_trust_when_db_errored.py`. [550:#6] [551:#38]
211. **Probe the upstream before calling an incomplete grid trustworthy** — 🟡 `app._substrate_coverage` returns trustworthy=True for "incomplete but read-through configured" without probing that upstream; gap: probe it or return UNKNOWN. [550:#3] [550:#46]
212. **Surface every lane failure, not only timeouts** — 🟡 `app.recall_memory` appends `_deadline_trailer` only for `lanes_timed_out`; `federation.FederatedResult.lane_failures`/`.complete` is dropped by the list comprehension. Emit a trailer for any `lane_failures`. [551:#37] [550:#92] [550:#94]
213. **Federated returns carry lane coverage** — ⬜ HARDENING §4 own missing: "surface the same metadata in federated_retrieve cross-node returns"; land per-lane coverage in `federation.federated_retrieve` result. [551:#85] [550:#12]
214. **Retraction-aware ranking** — ⬜ `app.shard_retract` sets title `[RETRACTED]`, utility 0; `core.retrieve` ranks on relevance*decay*density and never reads utility_score or the `retracted` tag, so retracted rows rank normally. Demote them in `retrieve`'s tier sort. [550:#10]
215. **Fix unlearning writes to a non-existent column** — ⬜ `unlearning._execute_retract_single`/`_execute_forget_single` UPDATE `temporal_status`, which no `init_db` DDL creates; the UPDATE raises. Add the column in `core.init_db`/`schema.py` or use `valid_until`, plus a test. [550:#10] [550:#11]
216. **Forget-aware vector cache** — 🟡 `_vector_cache_entry` prunes deleted ids on row-count shrink (`_prune_deleted`); gap: forget sets `embedding=NULL` in place, which only shrinks the embedded count if detected; add an explicit invalidation hook from `unlearning.py`. [550:#11] [550:#7] [551:#15]
217. **Vector cache invalidates on signature change** — ✅ `core._db_write_signature` compared in `_vector_cache_entry` (~1989-2010); refresh appends ids above cached max; `tests/test_vector_cache_delete.py`, `tests/test_vector_cache_herd.py`. [550:#7] [551:#13]
218. **Detect in-place embedding updates** — 🟡 `_vector_cache_entry` docstring accepts stale vectors after a backfill UPDATE until full reload; gap: add an embedding-version counter to the write signature. [550:#7] [551:#13]
219. **Loud semantic-lane-off state** — 🟡 `_vector_retrieve` warns once when `NOUGEN_VECTOR_CACHE=0`; gap: the warning is a log line, not a field in the recall result. Surface `vector_lane: off` per 201. [550:#2]
220. **Per-DB vector build locks** — ✅ `core._vector_cache_lock(i)` and `_vector_cache_wait_s` give one lock per grid DB and bail to keyword lane on timeout instead of queuing (phoebus burst note ~1920). [550:#93]
221. **Embed the query for every entry point** — ✅ `core.retrieve` calls `_embed_query` when `_query_embed_enabled()` with `NOUGEN_QUERY_EMBED_TIMEOUT` (default 6s). [551:#16]
222. **Record when the query embed failed** — ⬜ `_embed_query` returning None silently turns `_vector_retrieve` into `[]`; add `query_embedded: false` to the retrieval receipt in `core.retrieve`. [550:#2] [551:#44]
223. **Consolidate three RRF implementations** — 🟡 RRF lives in `core.reciprocal_rank_fusion` (~2272), `retrieval_v2.reciprocal_rank_fusion` (~480) and `reconstruction.reciprocal_rank_fusion` (~145); gap: one canonical function with shared tests. [551:#17]
224. **Consolidate two RetrievalIntent classes** — 🟡 `retrieval_v2.RetrievalIntent`/`compile_intent` and `reconstruction.RetrievalIntent`/`compile_retrieval_intent` overlap; neither is called by `core.retrieve`. Pick one.
225. **Wire temporal intent into core.retrieve** — 🟡 `retrieval_v2.compile_intent` parses YTD/MTD/today/latest; used only by `griot_v2.py`. Gap: `retrieve` takes `event_after/before` but never derives them from query text. [551:#19]
226. **Hash-keyed RRF collapses DB mirrors** — ✅ `core.reciprocal_rank_fusion.get_rrf_key` keys on `file_hash` before `(_db_index,id)`, so mirrored rows fuse once. [550:#8]
227. **Deterministic tie-breaks end to end** — ✅ `core.retrieve` sorts on `(title_exact, expired, -utility, _db_index, id)`, single `score_now` clock, no random epsilon (~2686-2720). [550:#99] [551:#47]
228. **Scoped-plus-global fusion for implicit domain** — ✅ `core.retrieve` runs scoped and `*` passes concurrently and applies `_domain_affinity_boost`; `tests/test_recall_domain_mask.py`. [550:#5]
229. **Known-item exact-title lane** — ✅ `core._title_retrieve` + `_title_hit` tier in `retrieve`; `tests/test_title_recall.py`. [551:#40]
230. **Validity-aware demotion** — ✅ `core._mark_expired` flags `valid_until` passed; `retrieve` sorts `_expired` below live rows in the same tier (`NOUGEN_VALIDITY_RANK`). [550:#14]
231. **Supersession-aware retrieval** — 🟡 `_mark_expired` covers `valid_until`; gap: `consolidate.py` supersede and `canonical_facts.canonical_current` are not consulted by `retrieve`. Add a canonical tier. [550:#9]
232. **Canonical-only retrieval mode** — ⬜ no `canonical_only` flag in `core.retrieve`; land it by joining `canonical_facts` v2 index (shard 30698@db8, PR #434).
233. **Bi-temporal filters over fused set** — ✅ `core._apply_filters` handles `scope`, `as_of` (learned time), `event_after/before`; `retrieve` over-fetches 5x when filtering. [551:#19]
234. **Report filtered counts** — ⬜ `_apply_filters` drops rows without a count; add pre/post filter counts to the receipt in `core.retrieve`. [551:#46]
235. **Report threshold-dropped counts** — ⬜ `retrieve` drops the bottom half and scores <0.05 silently; record `dropped_by_threshold` in the receipt. [551:#44]
236. **Rerank must not truncate candidate pool silently** — 🟡 `retrieve` calls `rerank(query, all_results[:RERANK_CANDIDATES], len(all_results))`; everything past 60 is discarded when `NOUGEN_RERANK=1`. Append the tail or record it.
237. **Rerank fallback visibility** — 🟡 `core.rerank` falls back to input order on any failure; gap: no `rerank_applied` flag, so a dead model looks like success. [551:#44]
238. **Lost-in-the-middle ordering is reader-only** — ✅ `core.lost_in_the_middle_reorder` applied last in `retrieve`; `tools/recall_eval.py` measures rank before it. Document that list order is not rank.
239. **Expose rank alongside interleaved order** — ⬜ callers of `retrieve` cannot recover true rank after reorder; add `_rank` field in `core.retrieve`.
240. **Token-budgeted packet** — ✅ `core.compile_recall_packet(token_budget, strategy="knapsack")` caps and truncates with a marker naming the budget; `tests/test_recall_token_budget_default.py`.
241. **Snippet-plus-handle recall** — ✅ `app.recall_memory` returns `_slim_shard` snippets with `get_shard(id, db)` marker; `tests/test_recall_snippets.py`.
242. **Retrieval receipt object** — 🟡 `retrieval_v2.QueryReceipt`/`create_query_receipt` (lanes_queried, failed_lanes, candidate_count, coverage_complete) exists; gap: not produced by `core.retrieve` or `app.recall_memory`. [551:#46] [550:#100]
243. **Retrieval trace ID** — ⬜ no trace id on recall; mint one in `core.retrieve` and propagate through `federation.federated_retrieve`. [551:#45]
244. **Per-lane latency in receipts** — 🟡 federation times each lane (`sweep_report["lanes"]`); gap: local keyword/vector/title/distill lanes in `retrieve` are untimed. [551:#42]
245. **Per-lane candidate counts** — ⬜ `run_parallel_retrieval` fuses lanes without counting each; record per-lane hit counts in `core.retrieve`. [551:#17] [551:#46]
246. **FTS vs semantic divergence report** — ⬜ nothing compares keyword and vector top-k overlap; add to `tools/recall_eval.py` report. [551:#17]
247. **Fallback reason codes** — 🟡 `_or_retry` tag marks OR fallback; gap: LIKE fallback, scoped->global fallback, and distill-skip carry no reason codes. Enumerate in `core.py`. [551:#44]
248. **Distill lanes fail soft and say so** — 🟡 `retrieve` catches distill exceptions with a warning; gap: skip reason absent from result.
249. **Wire ann_index or delete it** — ⬜ `src/nougen_shards/ann_index.py` (HNSW build/query) is imported only by `tests/test_sqlite_timeout.py`, nothing in src, app.py or tools; either route `_vector_retrieve` through it behind a flag or remove it.
250. **ANN recall parity test** — ⬜ before wiring 249, add `tests/test_ann_parity.py` asserting ANN top-k overlaps exact matmul top-k above a threshold.
251. **Golden-set recall eval** — ✅ `tools/recall_eval.py` build/run: Recall@k, MRR, nDCG, p50/p95, negatives false-positive rate; `tests/test_recall_eval.py`. [551:#40]
252. **Latency and accuracy gate** — 🟡 `tools/recall_bench.py` exits nonzero on `NOUGEN_BENCH_P95_S`/`MIN_ACC` miss; gap: not invoked by `.github/workflows/ci.yml`. [551:#42]
253. **Synthetic CI corpus for recall** — 🟡 `tests/fixtures/synthetic_reconstruction_vault.py` feeds `tools/bench_angle_sweep.py`; gap: no synthetic grid fixture for `core.retrieve` in CI.
254. **Known-answer tests** — 🟡 `recall_eval` golden set is built from the live vault into `analysis/recall_eval/`; gap: not committed, not reproducible on a clean clone. [551:#2]
255. **Empty-result tests** — ⬜ assert `compile_recall_packet([])` returns coverage + "absence unverified" wording (after 202). [551:#2] [550:#1]
256. **Starvation tests** — 🟡 `tests/test_fts_or_fallback.py` covers AND starvation; gap: filter starvation (5x over-fetch) and domain starvation untested together. [550:#4] [550:#5]
257. **Partial coverage tests** — 🟡 `tests/test_federation_coverage_honesty.py`, `test_recall_deadline_visibility.py` exist; gap: none assert a non-timeout lane error reaches `recall_memory` (see 212). [550:#92]
258. **Federated divergence tests** — ⬜ no test compares the same query across two stores returning different rows; land in `tests/test_federation_divergence.py`. [550:#12] [551:#4]
259. **Adversarial query corpus** — ⬜ injection, unicode, huge, all-stopword, and operator-only queries as a fixture in `tests/fixtures/`. [551:#41] [550:#69]
260. **Historical recall defects as fixtures** — 🟡 comments cite dated incidents (2026-08-29 corrupt DB, 2026-09-04 phoebus lock storm); gap: only some are tests. Catalogue in `tests/`. [551:#48]
261. **Absence proof object** — ⬜ define `AbsenceProof(stores_expected, stores_read, lanes_healthy, coverage_pct)` in `status_semantics.py`; empty is "absent" only when it holds. [551:#38] [550:#3]
262. **Reuse ContextReceipt for recall** — 🟡 `status_semantics.derive_context_state`/`ContextReceipt` classify required sources answered/missing; gap: not used by any recall path.
263. **Health generation stamps** — 🟡 `status_semantics.stamp_generation`/`is_stale_generation` exist; gap: recall coverage has no generation, so stale health can vouch for recall. [550:#95] [550:#96]
264. **Per-machine multi-vault completeness** — 🟡 federation fans out local/external/cloud/vault lanes; gap: shard 12169@db6 law (completeness needs per-machine vault reads) has no required-node set. [551:#83] [551:#84]
265. **Required-node timeout receipt** — ⬜ add `required_nodes` param and a per-node miss receipt to `federation.federated_retrieve`. [551:#84] [550:#43]
266. **Angle sweep as opt-in deep recall** — ✅ `reconstruction.retrieval_angle_sweep` with `SweepConfig` (`NOUGEN_RECON_ANGLES`), `should_sweep`; benchmarked by `tools/bench_angle_sweep.py` (shard 30683@db2).
267. **Expose deep recall as a tool** — ⬜ no MCP tool in `app.py` calls `retrieval_angle_sweep` with real sources; add `shards_deep_recall`.
268. **Alias map for entity expansion** — 🟡 `reconstruction.load_alias_map`/`_apply_aliases` expand aliases inside the sweep; gap: not applied in `core.retrieve`.
269. **Wispr-drift normalization** — ⬜ phonetic proper-noun normalization is absent from retrieval; add an alias fixture for `load_alias_map`.
270. **Typo tolerance** — 🟡 trigram FTS tokenizer gives substring tolerance; gap: no edit-distance correction for tokens that miss entirely. Land in `core._build_fts_match_query` retry.
271. **Kreyol-aware query handling** — 🟡 `persona.py` `_KREYOL` detects Haitian Creole; gap: retrieval neither detects nor expands it. Reuse in `core.retrieve`.
272. **Query decomposition** — ⬜ multi-clause conversational queries are one FTS expression; add decomposition in `retrieval_v2.compile_intent`. [551:#18]
273. **Scope filters by agent/machine/project** — ✅ `distill.scope_matches`/`scope_from_tags` via `_apply_filters(scope=)` (via:, machine:, domain_key).
274. **Provenance-weighted ranking** — ⬜ `machine`/`source_uri` columns exist but do not affect `retrieve` scoring; add a provenance tier. [551:#10]
275. **Contradiction-aware recall** — 🟡 `reconstructive_recall_v2.ReconstructiveRecallEngine` skips RETRACTED/QUARANTINED edges and tracks `ContradictionState`; gap: engine is fed hand-built events, not `core.retrieve` output.
276. **Evidence lock on reconstructed answers** — 🟡 `reconstructive_recall_v2.EvidenceLockError` refuses unsupported claims; gap: no production caller.
277. **Recovery-action planner** — 🟡 `retrieval_v2.next_recovery_action(QueryState)` exists; gap: nothing executes the action after an empty recall.
278. **Graph neighborhood lane** — 🟡 `distill.graph_lane` joins fusion when a sidecar exists; gap: no hop limit or neighborhood receipt.
279. **Redundancy suppression / MMR** — ⬜ no MMR or near-duplicate suppression beyond hash; add to `core.retrieve` after scoring.
280. **Diversity across DBs and event types** — ⬜ top-k can be one event_type; add optional diversity cap in `core.retrieve`.
281. **Research-corpus exclusion** — ✅ `core.bulk_ingest_event_types`/`_ingest_filter_sql` exclude IMPORT/INGEST unless `include_research`.
282. **Report excluded research hits** — ⬜ add "N research hits hidden" count when `include_research=False`, in `core.retrieve`.
283. **Answerability score** — ⬜ no score says whether top hits answer the query; add in `reconstruction.recognition_score` reuse.
284. **Confidence calibration** — ⬜ `utility_score_tripartite` is min-max normalized per query, so 1.0 is always top; add calibrated confidence in `tools/recall_eval.py`. [551:#40]
285. **Cold vs warm recall numbers** — 🟡 `tests/test_recall_warmup.py` covers warm-up; gap: no recorded cold/warm latency series. [551:#43] [551:#14]
286. **Query result cache with invalidation** — ⬜ no query cache; if added in `core.retrieve`, key on `_db_write_signature` of all DBs. [550:#66] [550:#67]
287. **Recall replay from receipt** — ⬜ receipts (242) must include query, flags, signatures so `tools/recall_eval.py replay` reproduces a ranking. [551:#47]
288. **Search modes** — ⬜ fast (`FAST_LOCAL` keyword-only exists in `retrieve`), precision, exhaustive, forensic modes; formalize as one `mode` enum in `core.retrieve`.
289. **Exhaustive mode reads every lane or fails** — ⬜ exhaustive must refuse to answer when any DB errored; lands with 288.
290. **FAST_LOCAL must label itself** — 🟡 `retrieve` short-circuits to `_keyword_retrieve` under `FAST_LOCAL`; gap: result does not say the vector lane was skipped.
291. **Recall docs match code** — 🟡 `docs/reconstructive-recall-research.md` "Implemented hardening and current limits"; gap: verify each claim against code as 203 does.
292. **arXiv donor fusion stays separate** — ✅ `arxiv_retrieval_donors.py` imports `retrieval_v2.reciprocal_rank_fusion`; `tests/test_arxiv_retrieval_donors.py`.
293. **Nightly recall war-game profile** — ⬜ schedule `recall_eval run` + `recall_bench` against isolated temp grid; JSON receipts. [551:#50] [550:#100]
294. **Clock-skew tolerant decay** — ⬜ `_temporal_decay` trusts shard timestamps; future-dated rows get decay >1 or clamp unknown. Test in `tests/`. [550:#14] [550:#13]
295. **Cross-node rank consistency** — ⬜ same query, same data, three nodes, same order; assert in `tests/test_federation_divergence.py`. [551:#4] [550:#12]
296. **Semantic compression with quote preservation** — ⬜ packets truncate bodies; add verbatim-quote retention in `compile_recall_packet`.
297. **Adaptive depth** — ⬜ escalate from fast to sweep only when `should_sweep` says low confidence, wired in `core.retrieve`.
298. **Personalization without overriding truth** — ⬜ any user boost must sit below canonical and retraction tiers in the sort key.
299. **Learned reranker from eval deltas** — ⬜ far horizon: train weights from `recall_eval` reports; gate by 251/252.
300. **Recall certification suite** — ⬜ one command runs 251-259, 293-295 and emits a signed pass/fail receipt. [551:#50] [550:#100]

### Zone 3 verdict
- Exists today: a deterministic hybrid stack in `core.retrieve` (keyword AND->OR->LIKE, cached vector matmul, title lane, distill lanes, RRF, validity tiering, filters, reorder), fail-closed `app._substrate_coverage`, and eval tooling (`tools/recall_eval.py`, `recall_bench.py`, `bench_angle_sweep.py`).
- Load-bearing gap: `retrieve` returns a bare list; no receipt, lane health, or absence proof reaches callers, and retracted shards rank normally.
- First PR: "recall: lane_health + coverage-bearing empty packets" touching `src/nougen_shards/core.py` (`lane_health`, `compile_recall_packet[_dual]`, fix `retrieval_angle_sweep("", [])`), `tests/test_lane_health.py`, `HARDENING.md` §4.
- Contradiction: HARDENING §4 claims ✅ `core.lane_health()` and `tests/test_lane_health.py`; neither exists and both empty paths return the bare marker.
- Contradiction: `unlearning.py` writes `temporal_status`, a column no DDL creates; `ann_index.py` (HNSW) is dead code.

## Zone 4: Memory Graph (steps 301-400)

301. **Repair the vector-graph live probe** — ⬜ defect: `tools/live_probe_vector_graph.py` calls `vector_graph.init_vector_graph_db`, `ingest_shard_triplets`, `retrieve_vector_graph`; `src/nougen_shards/vector_graph.py` (32 lines) defines none, so the probe raises AttributeError. Implement them or delete the probe [550:#32]
302. **Make autolink real or delete its probe** — ⬜ defect: `tools/autolink_probe.py` sets `NOUGEN_AUTOGRAPH_ENABLED=1`; zero hits in `src/` or `app.py`, so capture never auto-links. Land an opt-in edge writer in `core.capture()` or remove the probe [550:#32]
303. **Fix the test_graph order-dependent flake** — 🟡 HARDENING §4 notes `test_related_relation_filter` flakes; the fixture patches `core.GLOBAL_DIR` but `graph.get_graph_db_path()` reads `core.active_vault_dir()` (contextvar first). Reset `_ACTIVE_VAULT_DIR` in `tests/test_graph.py` fixture, then drop the note [550:#83]
304. **Rename check_kg_keys.py for what it does** — 🟡 `tools/check_kg_keys.py` is a Keymaker secret-presence check (decrypts values, prints lengths), not knowledge-graph code; hardcodes `~/.nougen/shards/shards_secrets.db`. Move into `keymaker.py` CLI and stop decrypting to count [551:#751]
305. **Keep the edge store** — ✅ `graph.init_graph_db()` creates `shard_edges(src_hash, dst_hash, relation, created_at)` with src/dst indexes in `graph.db` inside the active vault
306. **Keep file_hash as global node identity** — ✅ `graph._hash_for()` maps (id, db_index) to `file_hash`, avoiding per-DB id collisions across the 9-DB grid
307. **Keep idempotent edge writes** — ✅ `UNIQUE(src_hash, dst_hash, relation)` plus `INSERT OR IGNORE` in `graph.link_shards()`; self-loops refused (`src_hash == dst_hash`) [550:#8]
308. **Keep batch neighbour resolution** — ✅ `graph._shards_for_hashes()` resolves many hashes with one query per DB, lowest db_index wins
309. **Keep tenant/vault isolation of edges** — ✅ `get_graph_db_path()` uses `core.active_vault_dir()`, so request-local vaults get separate `graph.db` files
310. **Type the relation vocabulary** — 🟡 `relation` is free text in `link_shards`; the only typed list is `RELATION_WEIGHTS` in `unlearning.py:49`. Land a `RELATIONS` registry in `graph.py` and reject unknown labels
311. **Add edge provenance columns** — ⬜ `shard_edges` stores only `created_at`. Add `origin_machine`, `agent`, `source` (manual/auto/dream/canonical), `evidence_hash` in `graph.init_graph_db()` [551:#10]
312. **Add edge confidence** — ⬜ no confidence column; add `confidence REAL` to `shard_edges`, default 1.0 for manual links, below 1.0 for inferred [551:#10]
313. **Version the graph schema** — ⬜ `init_graph_db()` is `CREATE IF NOT EXISTS` only; add `PRAGMA user_version` plus additive migrations in `graph.py` [551:#11]
314. **Add an unlink API** — ⬜ `graph.py` has no delete; only `unlearning.py:611` issues raw `DELETE FROM shard_edges`. Add `graph.unlink_shards()` and route unlearning through it
315. **Add graph CLI commands** — ⬜ `cli.py` has no link/related subcommand (graph hits are destiny/algo only). Land `nougen graph link|related|stats` in `cli.py`
316. **Expose the graph on the Space** — ⬜ `app.py` has zero `link_shards`/`recall_related` hits; graph is reachable only via `mcp.py:199,222`. Add Space MCP tools with auth parity
317. **Keep the local MCP graph tools** — ✅ `mcp.py` `link_shards()` and `recall_related()` wrap `graph.link_shards` / `graph.related_shards`
318. **Make vector_graph.stats honest** — 🟡 `vector_graph.stats()` returns `"status": "active"` unconditionally, even with no `graph.db`. Report `absent`/`empty`/`active` from real state [550:#46]
319. **Add a graph HARDENING invariant** — ⬜ HARDENING.md has 9 sections, none for edges. Add §10 "edges never point at absent shards" with its regression test [551:#1]
320. **Add graph lane to lane_health** — ⬜ `core.lane_health()` reports shards and embedding coverage only; add edge count and orphan count [551:#37]
321. **Fix semantic_knowledge triple shape** — 🟡 `core.py:508` table has `subject, predicate` and `UNIQUE(subject, predicate)` but no object; a fact cannot hold two values. Add `object` and widen the unique key
322. **Clamp semantic_knowledge confidence** — ⬜ defect: `dream.py` upsert does `confidence_score = confidence_score + 0.1` with no cap, so scores exceed 1.0. Clamp with `MIN(1.0, ...)` in `dream.py` and `tools/dream_deep.py`
323. **Add provenance to semantic_knowledge** — ⬜ no source shard hash or machine column; rules cannot be traced to evidence. Add `source_hash` in `core.py` init_db [551:#9]
324. **Unify semantic_knowledge writers** — 🟡 two separate upserts: `dream.py` (~line 234) and `tools/dream_deep.py:139`. Move to one `core.upsert_semantic_rule()` with validation
325. **Guard semantic extraction against injected facts** — 🟡 `dream.py` skips non-string subject/predicate; nothing rejects instruction-shaped text from shard content. Add a filter before upsert in `dream.py` [550:#69]
326. **Keep degraded-safe semantic reads** — ✅ `core.py` ~3195-3225 loops DBs, catches `DatabaseError`/`OSError` per DB so one corrupt file does not zero the read [550:#6]
327. **Cascade retract to edges** — ⬜ (unverified) only `unlearning.py:611` (forget path) deletes edges; retracted shards keep live edges. Mark edges `retracted` in `unlearning.py` [550:#10] [551:#7]
328. **Keep forget purging edges** — ✅ `unlearning.py:611` `DELETE FROM shard_edges WHERE src_hash = ? OR dst_hash = ?`; `graph_mesh_edges` in the purge surface list (line 69) [550:#11] [551:#8]
329. **Re-point edges on amend** — ⬜ (unverified) if amend changes `file_hash`, edges orphan. Add `graph.rehash_node(old, new)` called from the amend path in `core.py` [550:#9] [551:#6]
330. **Write supersedes edges on consolidate** — ⬜ `consolidate.py` supersedes shards without touching `shard_edges`. Emit `supersedes` edges there
331. **Project canonical_facts supersession into the graph** — 🟡 `canonical_facts.validate_snapshot()` carries `supersedes` (line 150); nothing writes it to `shard_edges`. Add a projector in `canonical_facts.py` [PR #434 evidence]
332. **Persist contradiction edges** — 🟡 `reconstructive_recall_v2.py:42-43` tracks `supersedes`/`contradiction_group` in memory only. Persist `contradicts` edges via `graph.py`
333. **Keep lineage traversal** — ✅ `unlearning.trace_lineage_graph()` BFS over outbound edges with `RELATION_WEIGHTS` and depth attenuation `1/(1+0.3*depth)`
334. **Add inbound lineage to trace** — 🟡 `trace_lineage_graph` queries only `src_hash = ?` despite docstring "outbound and inbound". Add the inbound query in `unlearning.py`
335. **Keep degree centrality** — ✅ `graph.get_node_centrality()` counts edges where node is src or dst
336. **Rank related_shards results** — 🟡 `related_shards` concatenates out then in and truncates at `limit`, unranked, so in-edges starve. Rank by relation weight/confidence
337. **Add k-hop traversal** — 🟡 `related_shards` is 1-hop; `trace_lineage_graph` is unlearning-specific. Add generic `graph.walk(seed, hops, relations)` with cycle guard
338. **Add orphan-edge sweeper** — ⬜ nothing finds edges whose endpoint hash no longer resolves. Add `graph.find_orphans()` using `_shards_for_hashes` [551:#87]
339. **Add graph repair command** — ⬜ land `nougen graph repair --dry-run` deleting or quarantining orphans with a receipt [551:#11]
340. **Test concurrent link writes** — ⬜ no concurrency test for `link_shards`; add threaded test in `tests/test_graph.py` [550:#84] [551:#26]
341. **Test edges survive DB grid reroute** — ⬜ add test that a shard moving db_index keeps its edges via file_hash
342. **Add typed node kinds** — ⬜ every node is a shard. Land `graph_nodes(node_id, kind, label)` in a new `src/nougen_shards/memory_graph.py`
343. **Add entity nodes** — ⬜ people, machines, repos, agents, projects as nodes; land in `memory_graph.py`
344. **Add entity extraction at capture** — ⬜ deterministic extractor (repo names, PR numbers, node names blade/whoart/phoebus, file paths) in `memory_graph.py`, off by default
345. **Add mention edges shard→entity** — ⬜ `mentions` edges written by 344
346. **Add machine edges** — ⬜ link shards to origin machine using existing machine provenance column in `shards` [551:#97]
347. **Add agent/authorship edges** — ⬜ `authored_by` agent edges from capture metadata
348. **Add repository, commit, PR, issue edges** — ⬜ parse `#NNN`, commit SHAs, branch names into `references` edges
349. **Add file edges** — ⬜ `touches` edges to file-path entities; `tools/autolink_probe.py` intent, land in `memory_graph.py`
350. **Add relay/handoff edges** — ⬜ link handoff records (`handoff.py`) to the shards they cite
351. **Add message and receipt edges** — ⬜ link NouGenMsg `message_id`/receipts to shards they produced [551:#186]
352. **Add task/destiny edges** — ⬜ `destiny.py` goal graph is separate; bridge destinies to shards via `advances` edges
353. **Add evidence edges** — ⬜ link `evidence_ledger.py` entries to claims as `supports`/`refutes` edges
354. **Add derivation edges at write time** — 🟡 `RELATION_WEIGHTS` names `derived_from`, `summarizes`; no writer emits them. Emit from `dream.py`/`distill` summaries
355. **Add alias edges and reconciliation** — 🟡 `alias_of` weight exists in `unlearning.py`; no alias resolver. Land `memory_graph.resolve_alias()` (e.g. Wispr-drift names)
356. **Add identity confidence** — ⬜ score entity merges; store on alias edges
357. **Add duplicate entity merge** — ⬜ merge nodes with receipt and reversible log
358. **Add ambiguous entity split** — ⬜ split conflated entities; land beside 357
359. **Add temporal validity to edges** — ⬜ add `valid_from`/`valid_to` to `shard_edges` [550:#14]
360. **Add chronology edges** — ⬜ `precedes` edges from shard timestamps per entity, reusing `temporal_fabric.py`
361. **Add causal edges with causal class** — 🟡 `caused_by` weighted in `RELATION_WEIGHTS`; no class (engineering/incident/project). Add `causal_kind` column
362. **Add dependency edges** — ⬜ `depends_on` for decisions and code; land in `memory_graph.py`
363. **Add similarity edges from embeddings** — ⬜ kNN edges from shard `embedding` BLOB via `ann_index.py`, marked `source=auto`
364. **Add canonicality edges** — ⬜ link shards to `canonical_facts` keys they support
365. **Add adjacency index cache** — ⬜ in-memory adjacency built from `shard_edges` with invalidation on write
366. **Add entity index** — ⬜ indexed `graph_nodes(kind, label)` lookup
367. **Add timeline index** — ⬜ index `(entity, timestamp)` for timeline queries
368. **Make graph build incremental** — ⬜ backfill job over existing shards with a resume cursor [550:#97]
369. **Add "why do we believe this?"** — ⬜ evidence-path query over `supports`/`derived_from` in `memory_graph.py`
370. **Add "where did this come from?"** — 🟡 `trace_lineage_graph` walks descendants for unlearning; add ancestor provenance query
371. **Add "what changed this?"** — ⬜ query over `supersedes`/amend edges
372. **Add "what contradicts this?"** — ⬜ query over persisted `contradicts` edges (332)
373. **Add "what depends on this?"** — ⬜ reverse `depends_on` walk
374. **Add impact query** — ⬜ "what if this changes": transitive dependents with weights
375. **Add shortest evidence path** — ⬜ BFS path between two nodes
376. **Add strongest evidence path** — ⬜ max-product path using edge confidence × `RELATION_WEIGHTS`
377. **Add neighbourhood summaries** — ⬜ compact text summary of a node's 1-hop in recall packets
378. **Graph-expand retrieval** — ⬜ optional 1-hop expansion stage fused in `retrieval_v2.py` RRF
379. **Add entity cards** — ⬜ per-entity summary (facts, timeline, sources)
380. **Add JSON graph export** — ⬜ `nougen graph export --json` with hygiene scrub
381. **Add GraphML export** — ⬜ same exporter, GraphML writer
382. **Scrub exports for public hygiene** — ⬜ strip machine paths/IPs before export [550:#74]
383. **Add graph snapshots** — ⬜ content-hashed edge set per snapshot [551:#86]
384. **Add graph diffs** — ⬜ diff two snapshots (added/removed edges)
385. **Add graph receipts** — ⬜ every write/repair returns a receipt id
386. **Add cross-node graph reconciliation** — ⬜ `graph.db` is per-vault, never replicated; hash-compare edge sets across blade/whoart/phoebus [551:#59] [551:#61] [550:#12]
387. **Fan out graph reads across the fleet** — ⬜ `federation.py` has no graph lane; add one with `lane_failures` [551:#85] [550:#92]
388. **Detect stale edges** — ⬜ flag edges whose endpoints were superseded
389. **Add graph density and coverage metrics** — ⬜ shards with ≥1 edge / total, in `lane_health()`
390. **Add graph drift alarm** — ⬜ alert on sudden edge-count change between snapshots
391. **Add bridge detection** — ⬜ articulation points in `memory_graph.py`
392. **Add community detection** — ⬜ label propagation; no new dependency
393. **Add weighted centrality** — 🟡 degree only (`get_node_centrality`); add PageRank-style score
394. **Add graph war-game suite** — ⬜ `tests/test_graph_wargames.py`: orphan, retract, amend, cycle, poison edge [551:#50]
395. **Add visualization hook** — ⬜ Space route returning JSON subgraph for a node
396. **Add contradiction and causal views** — ⬜ render 372/361 paths in the desktop UI
397. **Add timeline visualization** — ⬜ entity timeline from 367
398. **Add memory constellation view** — ⬜ interactive topology over exported JSON
399. **Add shard self-position explanation** — ⬜ `explain_position(hash)`: neighbours, lineage, community, centrality
400. **Ship NouGen Memory Topology** — ⬜ fleet-reconciled, versioned, receipted graph that every recall can cite

### Zone 4 verdict
- Exists: a small shard-to-shard edge mesh (`graph.py`, 205 lines: `shard_edges`, idempotent `link_shards`, 1-hop `related_shards`, degree centrality), two MCP tools in `mcp.py`, lineage BFS in `unlearning.trace_lineage_graph`, edge purge on forget (`unlearning.py:611`), and a subject/predicate `semantic_knowledge` table (`core.py:508`).
- Real defects: `tools/live_probe_vector_graph.py` and `tools/autolink_probe.py` exercise functions/flags that do not exist; `dream.py` raises confidence above 1.0; `trace_lineage_graph` skips inbound edges despite its docstring; `vector_graph.stats()` always says "active".
- Load-bearing gap: edges carry no provenance, confidence, typed vocabulary, or schema version, and `graph.db` is per-vault and never reconciled across nodes; every query step (369-376) depends on 310-313.
- First PR: "graph: typed relations, edge provenance, schema version, flake fix" — `src/nougen_shards/graph.py`, `src/nougen_shards/vector_graph.py`, `tests/test_graph.py`, `tools/live_probe_vector_graph.py`, `tools/autolink_probe.py`, `HARDENING.md`, `CHANGELOG.md`.
- Contradictions: `vector_graph.py` is described as a vector graph but is a 32-line alias with no vector logic; `tools/check_kg_keys.py` is a Keymaker secret check, not knowledge-graph code; the autolink feature its probe assumes is absent.

## Zone 5: Temporal Memory and Griot (steps 401-500)

401. **Pick one temporal core, retire the duplicate** — 🟡 `temporal_fabric.py` and `temporal_fabric_v2.py` both define `TemporalEnvelope`, `HybridLogicalClock`, `extract_temporal_mentions`, `route_temporal_query` with different fields and return types; no src module imports v2. Fold v2's `HLCTracker` into v1, delete v2 [551:#19]
402. **Wire TemporalFabric into capture** — ⬜ `TemporalFabric.append_event` (`temporal_fabric.py`) is imported only by `canonical_facts.py` (`to_epoch_ms`) and `__init__.py`; `core.capture` never records a lifecycle event. Call `record_lifecycle(artifact_id, "capture")` from `core.py` capture path [551:#35]
403. **Log retraction time, not just state** — ⬜ defect: `unlearning.py:_execute_retract_single` does an in-place `UPDATE shards SET temporal_status='RETRACTED'`, discarding `reason` and when; append a `retraction` event to TemporalFabric and `history.log_event` [550:#10] [551:#7]
404. **Log forgetting time and tombstone** — ⬜ defect: `unlearning.py:_execute_forget_single` nulls embedding and sets `FORGOTTEN` with no timestamp or reason persisted; write a tombstone event (hash, reason, system time) to the append-only log [550:#11] [551:#8]
405. **Record amendment time in source** — ⬜ (unverified) no `amend` function exists in `src/nougen_shards/`; `shards_amend` is served by the gateway. Land an amend path that appends a `version` event via `TemporalFabric.record_version` with `known_from_ms` [550:#9] [551:#6]
406. **Emit history events for retract/forget/amend** — 🟡 `core.py` logs CREATED, ACCESSED, UTILITY_CHANGE, DB_DEGRADED, DB_QUARANTINED, SEARCH_FALLBACK via `history.log_event`; RETRACTED, FORGOTTEN, AMENDED, SUPERSEDED never reach `shard_events` [551:#7]
407. **Enforce append-only on history.db** — 🟡 `temporal_fabric.py` has `temporal_events_no_update/no_delete` triggers; `history.py:init_history_db` `shard_events` table has no such triggers. Add the same BEFORE UPDATE/DELETE triggers
408. **Stamp capture time with an HLC** — 🟡 `temporal_fabric.advance_hlc` and `temporal_fabric_v2.HLCTracker.now` exist; `history.log_event` stamps `datetime.now(timezone.utc)` only. Persist `physical_ms, logical_counter, node_id` on shard_events rows
409. **Stop defaulting HLC node to whoart** — ⬜ defect: `temporal_fabric_v2.HLCTracker.__init__(node_id="whoart")` and module-level `GLOBAL_HLC = HLCTracker()` stamp every event as whoart on blade and phoebus; resolve node via `get_current_node` or require the argument
410. **Reject past-skewed remote clocks too** — 🟡 `HLCTracker.receive_hlc` raises `ClockDriftError` only when remote is >60s ahead; a remote far behind is silently absorbed. Flag backward drift and record `clock_offset_ms` [550:#13]
411. **Persist drift flag per event** — 🟡 `TemporalEnvelope.from_timestamps` computes `drift_flag` from `clock_offset_ms` (>5s); nothing measures the offset between nodes. Add a peer-offset probe feeding `clock_offset_ms` into envelopes [550:#13]
412. **Detect future-dated shards at capture** — ⬜ no check in `core.py` capture rejects or flags `timestamp` beyond now plus tolerance; add flag `FUTURE_DATED` and test in `tests/test_temporal_fabric.py` [550:#14]
413. **Order replay by HLC, not arrival** — 🟡 `temporal_fabric.py` has index `idx_temporal_hlc_order`; no replay routine consumes it. Add `TemporalFabric.replay(since_hlc)` returning events in HLC order [550:#15] [551:#35]
414. **Test out-of-order replay convergence** — ⬜ no test feeds shuffled events and asserts identical `resolve_as_of` output; add to `tests/test_temporal_fabric.py` [550:#15] [551:#35]
415. **Keep bitemporal as-of resolution** — ✅ `temporal_fabric.py:TemporalFabric.resolve_as_of` selects the version with `valid_at_ms<=V`, `valid_to_ms>V`, recorded by transaction time T; `record_version` rejects `valid_to<=valid_from`
416. **Expose as-of recall through Griot** — ⬜ `griot_v2.gather_griot_archive` takes `now` but no `known_as_of`; add an `as_of` parameter that filters by capture/system time, answering "what did we know on September 1?"
417. **Canonical facts as-of** — ✅ `canonical_facts.py` stores `as_of_ms, event_at_ms, captured_at_ms` (`_backfill_v3`, `put`) and `resolve` compares `as_of` per key/scope [PR #434]
418. **Unify canonical epoch fields with envelope clocks** — 🟡 `canonical_facts` uses `as_of/event_at/captured_at`; `TemporalEnvelope` names `event_at/captured_at/valid_from/canonicalized_at`. Map `as_of` to `valid_from` explicitly and document it in `docs/griot-v2-coverage-audit.md`
419. **Temporal recall regression suite** — 🟡 `tests/test_griot_v2.py`, `test_temporal_fabric.py`, `test_temporal_fabric_v2.py`, `test_canonical_facts.py`, `test_original_timestamp.py` exist separately; no single marked suite. Add `pytest -m temporal` marker and CI job [551:#19]
420. **Make the temporal suite runnable without numpy** — ⬜ `tests/test_griot_v2.py` et al. fail at import because `nougen_shards/__init__.py` pulls `core.py` which imports numpy; lazy-import `core` in `__init__.py` so pure-temporal tests collect [550:#82]
421. **Griot coverage receipts per node** — ✅ `griot_v2.py:NodeCoverageStatus` plus the loop in `gather_griot_archive` marks unprobed nodes `attempted=False` with "no probe receipt supplied" and records failures
422. **Nine-DB coverage accounting** — ✅ `gather_griot_archive` iterates `expected_dbs = range(1,10)`, appends "expected database missing" and only adds completed DBs to `vault_dbs_scanned` [550:#3]
423. **PARTIAL/DEGRADED on missing coverage** — ✅ `griot_v2.py` sets `completeness="PARTIAL"` and `availability="DEGRADED"` when `is_fully_covered` is false; no-hit is `NO_HIT`, not absence [550:#2] [550:#3]
424. **Compound id@dbN and content hash** — ✅ `griot_v2.py:CompoundShardRef.compound_id/from_str` and artifacts carry SHA-256 of selected content, per `docs/griot-v2-coverage-audit.md` [551:#9]
425. **Probe nodes inside Griot** — ⬜ audit "Remaining scope": Griot never probes remote nodes; callers must supply receipts. Add an optional probe using the federation lane health in `federation.py` [551:#37]
426. **Per-machine per-vault coverage matrix** — ⬜ `GriotCoverageMatrix` reports nodes and local DBs as separate dimensions; add a (node, db) grid so blade DB 4 missing is distinguishable [551:#20]
427. **Fix FTS token cap silently dropping terms** — 🟡 `gather_griot_archive` builds `match_query` from only `words[:4]` joined by OR; words five onward are dropped with no receipt. Record dropped terms in the packet [550:#4]
428. **Arbitrary date-window parsing in Griot** — 🟡 temporal filter applies only when `intent.temporal.period != "ALL_TIME"` (YTD, MTD, today from `retrieval_v2`); "March 2025" or "between X and Y" is not bounded. Route through `temporal_fabric.extract_temporal_mentions` [551:#19]
429. **Use timestamp index instead of julianday()** — 🟡 Griot filters with `julianday(s.timestamp) >= julianday(?)`, which defeats any index on `timestamp`; compare normalized ISO strings or an epoch column
430. **Report unparsable timestamps as coverage** — 🟡 `tests/test_substrate_coverage_timestamps.py` proves `app.py:substrate_coverage` reports non-ISO rows instead of crashing; Griot's `julianday()` returns NULL and silently excludes them. Count them into `coverage.failures`
431. **Store normalized epoch column on shards** — ⬜ `shards.timestamp` is TEXT; add `event_at_ms`/`captured_at_ms` INTEGER columns backfilled via `temporal_fabric.to_epoch_ms` in a `core.py` migration [551:#11]
432. **Preserve raw timestamp and precision** — ✅ `TemporalEnvelope.from_timestamps` stores `raw_timestamps` and `original_precision` from `_precision(raw)` alongside normalized ms
433. **Source date versus inferred date** — ⬜ `kronos_temporal_engine.parse_payload_anchors` writes an inferred year into `valid_time_start` without marking it inferred; add `date_provenance: source|inferred|capture` to the envelope
434. **Stop year-only anchors pretending to be dates** — ⬜ defect: `kronos_temporal_engine.py` maps any 19xx/20xx in text to Jan 1 of that year; mark precision "year" and interval [Jan 1, Jan 1+1y) instead
435. **Decide Kronos' fate** — ⬜ `kronos_temporal_engine.py` (120 lines) is imported by nothing in `src/` or `tools/`; either wire `KronosEngine.calculate_cognitive_utility` into ranking or delete it
436. **Decide historical_fast_path's fate** — 🟡 `historical_fast_path.py:HistoricalFastPathStore` has `canonical_current`, `canonical_history`, postings; only `tests/test_historical_fast_path.py` uses it. Wire into `retrieval_v2` or remove
437. **Wire griot_sharder into a CLI** — 🟡 `griot_sharder.py:gather(tools, query, since, until)` dedupes by `_event_key`; no src or tools caller. Expose as `nougen griot shard --since --until` in `cli.py`
438. **Timezone normalization** — ✅ `temporal_fabric._aware_datetime` applies `timezone_name` (ZoneInfo) to naive values; `to_epoch_ms` normalizes to UTC
439. **Fix v2 mention extraction ignoring timezone** — ⬜ defect: `temporal_fabric_v2.extract_temporal_mentions` builds all dates with `tzinfo=timezone.utc`, so "yesterday" in Florida evening resolves to the wrong day; retire per step 401
440. **Relative date resolution against anchor** — ✅ `temporal_fabric.extract_temporal_mentions(text, anchor, timezone_name)` resolves relative forms against the anchor in zone and returns normalized start/end ms
441. **Interval semantics for uncertain times** — ✅ `temporal_fabric.causal_relation` returns `definitely_before/after` only when uncertainty intervals do not overlap, else `uncertain_or_concurrent`
442. **Allen interval relations** — ⬜ only before/after/concurrent exist; add during, overlaps, meets, contains in `temporal_fabric.py` for "during the outage" queries
443. **Impossible chronology detection** — 🟡 `TemporalEnvelope.__post_init__` rejects `valid_to<=valid_from`; nothing checks retracted before captured or event after ingest. Add envelope invariants
444. **Temporal contradiction detection** — 🟡 `reconstructive_recall_v2.py` skips edges with `temporal_valid=False` or `RETRACTED`; no detector for two canon facts valid over overlapping intervals. Add to `canonical_facts.resolve`
445. **Overlapping state detection** — ⬜ `canonical_current` holds one row per key/scope; overlapping `valid` windows from different machines are not reported. Emit a conflict receipt from `canonical_facts.py`
446. **Supersession chain** — 🟡 `canonical_facts.validate_snapshot` keeps `data["supersedes"]`; no traversal returns the chain. Add `supersession_chain(key)` for "what was believed before this correction?"
447. **Canon transition time** — ⬜ `TemporalEnvelope.canonicalized_at_ms` exists but no code sets it; record it when `canonical_facts.put` promotes a snapshot, answering "when did this become canon?"
448. **Candidate to canon state machine** — 🟡 `retrieval_v2.py:171` enumerates CANONICAL, CANDIDATE, HISTORICAL, SUPERSEDED, AMENDED, RETRACTED; transitions are not validated. Add allowed-transition table with timestamps
449. **Temporal diff: what changed since** — 🟡 `history.HistoryEngine.get_growth_rate/get_timeline(period)` count events; no diff of shard content between two times. Add `diff(since, until)` over TemporalFabric versions
450. **History period deltas are calendar-naive** — 🟡 `HistoryEngine.get_period_delta` maps periods to fixed `timedelta`; "month" is not a calendar month. Use `temporal_fabric._shift_months`
451. **Missing interval detection** — ⬜ no function finds days with zero captures per node; add `timeline_gaps(node, start, end)` in `history.py` [551:#20]
452. **Month coverage gap alarms** — ⬜ nothing alarms when a month has no shards on a lane that normally writes daily; land alongside step 451 [551:#20]
453. **No fabricated continuity** — 🟡 Griot marks PARTIAL when coverage is missing; the packet does not state which time spans have no evidence. Add `uncovered_intervals` to `GriotPacket.to_dict`
454. **Griot uncertainty reporting** — 🟡 `GriotPacket` carries completeness/availability; per-artifact date precision and inferred-date flags are absent. Attach envelope precision per artifact
455. **Recency weighting documented** — 🟡 `core.py` `_temporal_decay` uses one reference clock per scan; `KronosEngine` has a separate `half_life_days=30`. Pick one decay and document it
456. **Permanence weighting** — ⬜ canon and decisions decay like chatter in `_temporal_decay`; add a permanence class (from `griot_v2.EpistemicClass`) that exempts canon from decay
457. **Temporal reranking in RRF** — 🟡 `retrieval_v2` fuses lanes by deterministic RRF; no temporal arm. Add a temporal proximity arm to the fusion
458. **Temporal FTS** — 🟡 `temporal_fabric.py` creates `temporal_mentions` with range index; `shards_fts` has no date column. Join mentions into Griot's FTS query
459. **Temporal graph edges** — 🟡 `reconstructive_recall_v2` edges carry `temporal_valid`; `graph.py` relations have no valid_from/valid_to. Add columns
460. **Chronology confidence score** — ⬜ add a confidence derived from precision, provenance and drift to `TemporalEnvelope.to_dict`
461. **Duplicate event detection** — 🟡 `griot_sharder._event_key` dedupes hits; `history.log_events` has no idempotency key. Add unique (shard_id, db_index, event_type, hlc) [550:#8] [550:#16]
462. **Recurrence and periodicity detection** — ⬜ add `detect_recurrence(tag)` in `history.py` over event timestamps
463. **Change point detection** — ⬜ add a change-point pass over `shard_events` daily counts in `history.py`
464. **Trend detection** — 🟡 `HistoryEngine.get_growth_rate`, `get_utility_delta` compute deltas; no trend significance. Extend with slope over windows
465. **Utility trend per shard** — ⬜ `tests/SHARD_HISTORY_PLAN.md` task 202 `get_utility_trend(shard_id, window)` is not implemented in `history.py`
466. **Reconcile the history plan with code** — 🟡 `tests/SHARD_HISTORY_PLAN.md` lists 1000 tasks; tasks 1-5, 201, 203 exist in `history.py`/`core.py`. Mark done/remaining in the file
467. **Machine online/offline history** — 🟡 `core.py` logs `DB_DEGRADED`, `DB_QUARANTINED` events; no node up/down events. Log federation lane failures from `federation.py` into history [550:#27]
468. **Agent availability history** — ⬜ relay claims and nougenmsg presence are not recorded as intervals; land in `history.py`
469. **Deployment and PR history** — ⬜ no ingest of git merges into timeline; add a `tools/` importer writing `version` events
470. **Incident history** — ⬜ no incident record type; add `incident_open/close` events to TemporalFabric
471. **Decision history** — 🟡 `griot_v2.infer_epistemic_class` classifies titles/tags; decisions are not versioned. Record decisions via `record_version`
472. **Daily snapshots** — ⬜ add a daily snapshot table in `history.py` (counts, hashes per DB) for fast reconstruction
473. **Weekly and monthly rollups** — ⬜ derive from step 472 snapshots
474. **Snapshot acceleration for as-of** — ⬜ `resolve_as_of` scans events; add checkpoint rows in `temporal_fabric.py`
475. **State reconstruction at time T** — 🟡 `reconstruction.py` exists (710 lines) without an as-of parameter; add T and read TemporalFabric
476. **Historical replay API** — ⬜ add MCP tool `shards_timeline` in `mcp.py` over `TemporalFabric.events_for_range`
477. **Timeline export** — ⬜ add `nougen history export --jsonl` in `cli.py` (`cli.py:1234` only builds `HistoryEngine` stats)
478. **Griot forensic mode** — ⬜ mode returning raw events, hashes and HLCs for one artifact; land in `griot_v2.py`
479. **Griot historian mode** — ⬜ narrative over a period with cited compound ids only
480. **Griot diff mode** — ⬜ wraps step 449 diff with coverage receipts
481. **Griot reconstruction mode** — ⬜ wraps step 475
482. **Cursor continuation** — ⬜ audit lists cursor continuation as remaining; add `cursor` to `gather_griot_archive`
483. **Per-arm query receipts persisted** — ⬜ audit remaining scope; persist per-DB query and counts [551:#46]
484. **Evidence hydration from pointers** — ⬜ audit remaining scope; hydrate external pointer artifacts
485. **Corpus identity validation** — ⬜ audit remaining scope; verify DB identity before counting coverage [551:#22]
486. **Amend/retract resolution in Griot** — 🟡 `retrieval_v2.py:321` demotes SUPERSEDED/AMENDED/RETRACTED; Griot does not fold amendments into returned artifacts [550:#9]
487. **Named eras and bookmarks** — ⬜ add `eras` table (name, start, end) in `history.py`
488. **Project epochs** — ⬜ derive from eras plus PR history
489. **Fleet eras** — ⬜ derive from node online history (step 467)
490. **Timeline compression** — ⬜ summarize old events into rollups while keeping hashes
491. **Timeline summaries** — ⬜ Griot historian output per week
492. **Temporal vectors** — ⬜ time-aware embedding feature in `ann_index.py`
493. **Preference evolution** — ⬜ versioned preference facts via `canonical_facts`
494. **Character evolution** — ⬜ versioned lore facts, private vault only
495. **Repository evolution** — ⬜ depends on step 469
496. **Memory evolution report** — ⬜ monthly report from snapshots
497. **Lifecycle modeling of facts** — ⬜ birth, amend, supersede, retract, forget as one state chart
498. **Cross-node timeline merge** — ⬜ merge three nodes' TemporalFabric by HLC [550:#12]
499. **Temporal war-game profile** — ⬜ families 13-15 as nightly drill [550:#13] [550:#14] [550:#15]
500. **Griot answers only with temporal receipts** — ⬜ every Griot claim cites event time, capture time and coverage; far horizon

### Zone 5 verdict
- Exists: bitemporal append-only store with triggers and `resolve_as_of` (`temporal_fabric.py`), coverage-honest Griot with PARTIAL/DEGRADED, id@dbN and SHA-256 (`griot_v2.py`), canonical epoch fields (`canonical_facts.py`, PR #434), event log `history.py`.
- Load-bearing gap: the temporal fabric is not wired; capture, retract, forget and amend write no timestamped events (`unlearning.py` does in-place UPDATEs), so "what did we know on date X" cannot be answered.
- Duplicates and orphans: `temporal_fabric_v2.py`, `kronos_temporal_engine.py`, `historical_fast_path.py`, `griot_sharder.py` have no src caller.
- First PR: "Record retract/forget/capture as temporal events" — `src/nougen_shards/unlearning.py`, `src/nougen_shards/core.py`, `src/nougen_shards/history.py`, `tests/test_temporal_fabric.py`.
- Contradiction: the brief calls HLC "clock skew detection"; `receive_hlc` only rejects future drift, and `GLOBAL_HLC` stamps every node as whoart.

## Zone 6: Federation and Multi-Vault Truth (steps 501-600)
501. **Fix the phantom federation package imports** — ⬜ defect: `app.py` `fleet_health_endpoint` (/v1/health/fleet) and `recall_endpoint` (/v1/recall, fleet scope) import `nougen_shards.federation.config/client/service`; only the module `src/nougen_shards/federation.py` exists, so both raise ModuleNotFoundError. Land the package or delete the routes [551:#88] [550:#92]
502. **Test the /v1 federation routes** — ⬜ no file under `tests/` references `/v1/recall` or `/v1/health/fleet`, which is how step 501 shipped (added in #500). Add `tests/test_v1_federation_routes.py` hitting both through TestClient [551:#99]
503. **Keep FederatedResult as the one partial-result contract** — ✅ `src/nougen_shards/federation.py` `FederatedResult(list)` carries `lane_failures` and `.complete`; `_note_lane` mirrors each failure into `sweep_report["errored"]`; covered by `tests/test_federation_coverage_honesty.py` [551:#85] [550:#92]
504. **Shared long-lived lane pool** — ✅ `federation.py` `_lane_executor()` holds one `ThreadPoolExecutor` sized by `_lane_pool_size()`, never shut down per call, so stragglers cannot pile up pools; `tests/test_federation_lane_pool.py` [550:#94]
505. **Shared wall-clock recall deadline** — ✅ `federation.py` `_lane_result` bounds each lane by `NOUGEN_RECALL_DEADLINE_S` (default 20s), records `transport_timeout`, sets `deadline_exceeded` in the sweep report [550:#93] [550:#94]
506. **Per-lane latency accounting** — ✅ `federation.py` `_timed`/`_record_lane` record per-lane `elapsed_s`, status and row count, distinguishing never-scheduled (None) from still-running [550:#93]
507. **Parallelise the cloud lane per node** — ⬜ defect: `connectors/cloud.py` `query_cloud_shards` loops `for conf in cloud_configs` serially at 5s each; three slow peers exceed the 20s lane deadline and the whole lane, fast peers included, is dropped. Fan out per node [550:#93] [550:#94]
508. **Per-node failure entries inside the cloud lane** — 🟡 `query_cloud_shards` appends per-node `errored` entries with `_failure_class`, but the unsafe-URL rejection path only logs a warning; record it as `failure_class: rejected_url` [551:#85]
509. **Wire the tenant federation flag** — ⬜ defect: `tenants.tenant_allows_federation` has no caller; `federation.py` hardcodes `active_tenant_id() == "owner"`, so the registry's `allow_federation` field is dead. Route the gate through it [551:#83]
510. **Remove the hardcoded machine attribution fallback** — ⬜ `federation.py` stamps missing `machine_id` with a literal node name when `NOUGEN_MACHINE_ID` is unset, mislabelling rows on other nodes; use `locator.current_node()` [550:#12]
511. **Reinstate core.lane_health() or retract HARDENING §4** — ⬜ contradiction: HARDENING.md marks §4 done citing `core.lane_health()`, `NOUGEN_MIN_COVERAGE_PCT` and `tests/test_lane_health.py`; none exist in src, tests or git history (`git log -S`). Implement in `core.py` or downgrade [550:#2] [550:#3]
512. **Make sync_mesh_status measure parity** — ⬜ defect: `app.py` `sync_mesh_status` docstring promises hash parity across three stores but returns local node, vault dir, total and the constant `"3_VAULT_SYMMETRIC"`. Compare `/sync/hashes` digests per peer or rename it [551:#61] [550:#100]
513. **Substrate coverage reports unreadable DBs** — 🟡 `app.py` `substrate_coverage` counts per-month spans but silently `continue`s when a present DB fails to open or scan; add a `databases_skipped` list like `/sync/hashes` [550:#6] [550:#96]
514. **Federated coverage of local vaults** — ✅ `app.py` `_federated_coverage` opens each keymaker vault read-only, returns stores/names/rows_total and per-store `errored`, env-gated by `NOUGEN_COVERAGE_FEDERATED` [550:#3]
515. **Degraded-DB signal on bulk export** — ✅ `app.py` `sync_pull` skips unreadable grid DBs, sets `X-NGS-Degraded-DBs`, logs `DB_DEGRADED`; `tests/test_sync_pull_guard.py` [550:#6]
516. **Per-row sync_push outcomes** — ✅ `app.py` `sync_push` guards each row, returns `results[]` with reason/durable/shard_id, splits `skipped_duplicate` from `skipped_malformed`, counts write faults as `errored`; `tests/test_sync_push_guard.py`, `test_sync_push_write_fault.py` [551:#56]
517. **Hash manifest endpoint** — ✅ `app.py` `sync_hashes` returns every `file_hash` plus `databases_skipped`; consumed by `tools/relay_push.py` `fetch_remote_hashes` for missing-only planning [551:#61]
518. **Byte-level shard proof by id** — ✅ `app.py` `shard_by_id` returns `source_node` and SHA-256 `content_hash`, 409 on mismatch, because shard ids collide across nodes [551:#56]
519. **Define the replication contract document** — ⬜ no doc states which shards must exist on which nodes; briefing item 18 finds zero replication code. Write `docs/replication-contract.md` (scope classes, required nodes, receipt shape) [551:#51]
520. **Global shard identity = file_hash, never integer id** — 🟡 `tools/union_vaults.py` docstring declares `file_hash` the durable identity and regenerates ids; `/v1` and search results still key on integer id. Emit `id@dbN@node` plus hash everywhere [551:#61] [550:#12]
521. **Pin hash algorithm across nodes** — 🟡 `tools/relay_push.py` `relay_content_hash` mirrors capture's MD5 after stripping recall packets; any drift in capture normalisation breaks parity silently. Add a shared `core.content_identity()` and a cross-check test [551:#61]
522. **Stream or page /sync/hashes** — ⬜ `sync_hashes` materialises every hash in one JSON list; with 20k+ rows per node this is the whole inventory each call. Add `since`/cursor paging in `app.py` [551:#61]
523. **Page /sync/pull** — ⬜ `sync_pull` exports `SELECT *` from all DBs including embeddings as one bare list; add cursor and `since` parameters [551:#86]
524. **Per-DB digest for cheap divergence checks** — ⬜ add `/sync/digest` in `app.py` returning count plus rolling SHA-256 of sorted hashes per grid DB so peers compare nine digests before exchanging inventories [551:#60] [551:#61]
525. **Merkle or bucketed inventory** — ⬜ zero merkle code in src (briefing 18); add hash-prefix buckets in a new `src/nougen_shards/sync_inventory.py` so divergence narrows in O(log n) [551:#59]
526. **Cross-node count reconciliation report** — ⬜ nothing fetches counts from all three nodes and diffs them; add `tools/fleet_reconcile.py count` [551:#60] [550:#12]
527. **Cross-node hash reconciliation report** — 🟡 `relay_push.py --missing-only` diffs local hashes against one remote; no three-way diff naming which node lacks which hash. Extend into `tools/fleet_reconcile.py hashes` [551:#61]
528. **Anti-entropy job** — ⬜ no scheduled reconciliation exists; add `fleet_reconcile.py --apply` pushing missing hashes both ways, run by the existing keepalive or node lane [551:#59]
529. **Replication receipts per node** — ⬜ `sync_push` returns per-row outcomes but nothing persists them; write receipts (hash, node, db_index, ts) into a `replication_receipts` table in `history.py` [551:#56]
530. **Replication canary** — ⬜ capture a tagged canary shard, then prove arrival on every node via `/shards/{id}?content_hash=`; land in `tools/replication_canary.py` [551:#52] [550:#100]
531. **Replication lag metric** — ⬜ no timing between capture and remote arrival; derive from receipts (step 529) in `tools/fleet_reconcile.py` [551:#53]
532. **Retry queue for failed pushes** — 🟡 `relay_push.py --start` resumes by offset by hand; no durable queue of failed rows. Persist `errored` rows from `sync_push` responses to a retry file [551:#54] [550:#49]
533. **Dead-letter queue** — ⬜ rows failing repeatedly (e.g. cross-machine ngenc1 decrypt) are only logged by `sync_push`; add a dead-letter table with reason [551:#55]
534. **Era-preserving CLI pull** — ⬜ defect: `cli.py` node pull calls `capture()` without `original_timestamp`, `sensitivity` or `domain_key`, re-dating and declassifying rows that `sync_push` already preserves. Reuse `sync_push`'s row mapping [550:#15]
535. **CLI push must batch** — 🟡 `cli.py` node push sends the whole vault in one POST (`push_to_cloud`, 10s `SYNC_TIMEOUT_S`); `tools/relay_push.py` batches and resumes. Make the CLI call relay_push logic [550:#44]
536. **pull_from_cloud must not return [] on failure** — ⬜ `connectors/cloud.py` `pull_from_cloud` returns `[]` on any error, indistinguishable from an empty peer; raise or return a failure object [550:#46]
537. **Honor X-NGS-Degraded-DBs on the puller** — ⬜ `pull_from_cloud` ignores the header `sync_pull` sets, so a partial export ingests as complete; surface it [550:#92]
538. **Private shards stay local by default** — ✅ `tools/relay_push.py` `prepare_for_relay` skips private/secret rows unless `--include-private`, redacts via `redact_content`, drops stale hash and embedding when redaction changes text
539. **Scope classes on shards** — ⬜ no column marks local-only vs fleet vs public; add `scope` to `core.init_db` schema and honour it in relay_push and sync_pull
540. **Critical vs optional replication classes** — ⬜ nothing distinguishes decisions/canon from bulk imports; tie replication factor to event_type in the contract (step 519) [551:#51]
541. **Vault registry with identity** — 🟡 `keymaker.list_local_vaults()` / `list_cloud_nodes()` store path/url/table; no vault id, epoch, schema version or owner node. Extend the keymaker record [551:#97] [551:#98]
542. **Grid schema version stamp** — ⬜ `core.init_db` migrates by ALTER (schema v2 sensitivity, v3 machine) with no stored version; set `PRAGMA user_version` and expose it in `/health` [551:#76]
543. **Peer schema negotiation** — ⬜ `sync_push` accepts any dict shape; reject or adapt by peer schema version from step 542 [551:#76] [550:#32]
544. **Per-peer capability discovery** — ⬜ `query_cloud_shards` assumes `/search`; add a `/capabilities` route in `app.py` and cache it per peer [551:#77]
545. **Fleet topology manifest** — 🟡 fleet host map loads from local config (PR #528, `test_fleet_hosts_config.py`); no manifest of which vaults live on which node. Add `topology` output to `fleet_whoami` [551:#88]
546. **Topology drift detector** — ⬜ compare manifest (step 545) against live `/health` answers; land in `tools/fleet_reconcile.py topology` [551:#89] [550:#40]
547. **Node identity attestation** — 🟡 shards carry `machine` (core schema v3) and `shard_by_id` returns `source_node`; nothing proves the answering node is who it claims. Sign health responses with `fleet_keys.py` [551:#96]
548. **Mount completeness on every recall** — 🟡 `app.py` ~1070 computes `complete = len(mounted) == expected` and `recall_trustworthy`; the federated lanes' `lane_failures` are not folded into that verdict [550:#3]
549. **Timeout labels distinct from error labels** — ✅ `connectors/cloud.py` `_failure_class` returns `transport_timeout` for socket timeouts; `federation.py` uses the same class for deadline misses [550:#43]
550. **Stale labels on cached answers** — ⬜ no federated response carries data age; add `newest_timestamp` per lane from `substrate_coverage` span [550:#96]
551. **Hot/cold vault tiering** — ✅ `connectors/local_vault.py` `_partition_tiers` and `_tier2_enabled()` defer big unindexed stores, reported as deferred in `sweep_report`; `tests/test_federation_tiering.py` [550:#93]
552. **FTS indexes on registered vaults** — ✅ `tools/build_vault_fts.py` `build_for` adds external-content FTS5 `<table>_ngsfts` above `NOUGEN_FTS_MIN_ROWS`; connector falls back to LIKE [550:#4]
553. **Detect stale vault FTS** — ⬜ external-content FTS built once by `build_vault_fts.py` has no triggers on foreign vaults; add a row-count vs index-count probe [550:#97]
554. **Offline vault union** — ✅ `tools/union_vaults.py` `union_vaults` dedups by `file_hash`, preserves metadata/embeddings/encryption, `--apply` gated; `verify_vault` runs `PRAGMA integrity_check` per DB
555. **Union verification in CI** — ⬜ no `tests/test_union_vaults.py` exists; add a two-vault fixture proving dedup and integrity
556. **Handoff registry transport** — ✅ `src/nougen_shards/handoff_sync.py` `sync` runs git pull/push on a `handoffs` branch, aborts on `registry_conflict()`, replays arrival triggers via `_replay_arrivals`; `tests/test_handoff_sync.py`
557. **Handoff sync: report partial transport** — 🟡 `sync` returns `pulled`/`pushed`/`errors`; no receipt that the other two nodes have fetched. Add remote ref check per node
558. **Health cache with expiry** — ⬜ `tools/fleet.py` breakers cover LLM routes only; federation re-probes nothing and caches nothing. Add a TTL health cache in `federation.py` [551:#79] [550:#95]
559. **Circuit breaker per peer vault** — ⬜ a dead cloud peer costs its full timeout every recall; add open/half-open state per peer in `connectors/cloud.py` [550:#47] [550:#48]
560. **Health disagreement report** — ⬜ nothing compares what each node says about the others; add to `/v1/health/fleet` once step 501 lands [551:#80]
561. **Required-node set per request** — ⬜ callers cannot say "must include phoebus"; add `required_nodes` to the recall request and fail loudly when missing [551:#83]
562. **Required-node timeout receipt** — ⬜ follows 561: return which required node timed out, with elapsed, in `FederatedResult` [551:#84]
563. **Quorum semantics** — ⬜ define answer validity as k-of-n nodes in the replication contract; enforce in `federation.py` [551:#81]
564. **Degraded mode without quorum** — 🟡 today every partial is returned with `complete=false` (live fan-out: blade timed out, phoebus/whoart answered); no explicit degraded mode or caller policy [551:#82] [550:#92]
565. **Cross-vault dedupe in fusion** — 🟡 `core.reciprocal_rank_fusion` merges lanes; duplicates of one shard from two nodes are not collapsed by `file_hash`. Collapse and list all holders [550:#12]
566. **Record holders per fused hit** — ⬜ a fused hit keeps one `machine_id`; add `held_by: [nodes]` so divergence shows in results
567. **Lane weight evidence** — 🟡 `NOUGEN_FED_LANE_WEIGHT` (0.35) justified by a comment measurement; no eval fixture. Add a ranking test in `tests/test_federation.py`
568. **Request cancellation** — 🟡 `_lane_result` calls `future.cancel()`, which cannot stop a running thread; stragglers finish on the pool. Pass a cancel event into connectors
569. **Adaptive deadlines** — ⬜ deadline is a fixed env value; derive from `_record_lane` history per lane [550:#93]
570. **Local-first answer with remote enrichment** — ⬜ recall waits for all lanes up to the deadline; return local rows first and stream federated additions (MCP progress) [550:#93]
571. **Clock-skew detector** — ⬜ no node compares clocks; include server time in `/health` and flag skew in `fleet_reconcile.py` [551:#66] [550:#13]
572. **Future-dated shard guard on sync** — ⬜ `sync_push` accepts any `original_timestamp`; reject or flag beyond skew tolerance [550:#14]
573. **Monotonic sequence per origin** — ⬜ no per-node sequence column; add `origin_seq` to schema for ordering and gap detection [551:#68] [550:#15]
574. **Replay protection on sync_push** — 🟡 content-hash dedup makes replays idempotent, but amend/retract replays have no sequence guard [551:#69] [550:#17]
575. **Amendment routing** — ⬜ `shard_amend`/`shard_retract`/`shard_forget` act on the local grid only; nothing propagates them to peers [550:#9] [550:#10] [550:#11]
576. **Retraction tombstones replicate** — ⬜ a forgotten shard re-arrives on next relay_push from a peer; add tombstone hashes to `/sync/hashes` [550:#11]
577. **Conflict detector** — ⬜ same key, different content across nodes is never compared; use `canonical_facts.py` keys per node in `fleet_reconcile.py` [551:#57]
578. **Deterministic conflict policy** — ⬜ document and implement winner rules (canonical epoch, then timestamp, then node order) [551:#58]
579. **Canonicality divergence check** — ⬜ `canonical_facts.py` `canonical_current` is per node; compare across nodes [551:#57]
580. **Graph divergence check** — ⬜ `graph.py` relations never leave the node; add relation-hash digest to step 524
581. **Index divergence check** — ⬜ compare FTS/embedding coverage per node via `substrate_coverage` extension [550:#97]
582. **Embedding model parity** — ⬜ `sync_push` accepts embeddings from peers without model signature; reject mismatched dimensions/models [550:#7]
583. **Replication pause/resume switch** — ⬜ add a keymaker flag honoured by relay_push and anti-entropy [551:#62]
584. **Node join bootstrap** — 🟡 `union_vaults.py` offline union exists; no documented online bootstrap from peer `/sync/pull` [551:#63] [551:#94]
585. **Node leave drain** — ⬜ nothing proves a leaving node's unique hashes landed elsewhere first [551:#64]
586. **Sleep/restart recovery** — 🟡 handoff_sync replays arrivals after sleep; shard sync has no resume marker beyond `--start` [550:#28] [550:#91]
587. **Restart during sync safety** — 🟡 `sync_push` is per-row idempotent by hash; no test kills mid-batch and verifies [550:#91]
588. **Partition simulation tests** — ⬜ add fake-peer fixtures (timeout, 500, malformed JSON, slow) to `tests/test_federation.py` [551:#71] [550:#42] [550:#45]
589. **Slow-link and packet-loss tests** — ⬜ follow 588 with delayed and truncated responses [551:#73] [551:#74]
590. **Malformed peer response test** — 🟡 `_NET_ERRORS` in `connectors/cloud.py` catches JSON/Key/Value errors; no test asserts the resulting `errored` entry [551:#75] [550:#45]
591. **Split-brain detection** — ⬜ two nodes accepting conflicting canonical writes is never detected; derive from steps 577-579 [550:#12]
592. **Three-node deterministic comparison** — 🟡 `docs/cross-verification.md` codifies "publish the discriminator"; no tool runs one query on all three and diffs. Add `tools/fleet_reconcile.py query` [550:#12] [550:#99]
593. **Authoritative absence proof** — ⬜ an absence claim must cite all nodes complete plus hash digest match; compose in `federation.py` [550:#1] [550:#3]
594. **Replication dashboard** — ⬜ render receipts and lag (529, 531) in the existing desktop UI
595. **Fleet invariant checker** — ⬜ one command asserting counts, digests, schema, clocks agree [551:#87]
596. **Compatibility matrix across node versions** — ⬜ record git sha per node in `/health` and test sync across adjacent versions [551:#92]
597. **Rolling restart test** — ⬜ restart each node in turn under load; recall stays partial-honest [551:#93]
598. **Federation chaos suite** — ⬜ combine 588-591 into a scheduled war-game with receipts [551:#99] [550:#100]
599. **One-command federation certification** — ⬜ `tools/fleet_reconcile.py certify` running 526-598 checks, output signed receipt [551:#100]
600. **Provable fleet discoverability** — ⬜ a shard captured anywhere with fleet scope is proven present, by hash receipt, on every node its contract names

### Zone 6 verdict
- Exists today: honest partial fan-out in `federation.py` (`FederatedResult.lane_failures/.complete`, shared lane pool, 20s deadline, per-lane timing), guarded `/sync/push`, `/sync/pull`, `/sync/hashes`, hash-proof `/shards/{id}`, one-way missing-only `tools/relay_push.py`, offline `tools/union_vaults.py`, git-based `handoff_sync.py`.
- Load-bearing gap: no replication contract, receipts or reconciliation; nothing compares the three nodes, so divergence is invisible (zero merkle/anti-entropy code, briefing 18).
- Defects found: `/v1/recall` and `/v1/health/fleet` import a nonexistent `nougen_shards.federation` package; `sync_mesh_status` reports a constant instead of parity; serial cloud fan-out; dead `tenant_allows_federation`; CLI pull drops era/sensitivity.
- First PR: "fix(federation): repair /v1 routes and parallelise cloud peers" — `app.py`, `src/nougen_shards/connectors/cloud.py`, `src/nougen_shards/federation.py`, new `tests/test_v1_federation_routes.py`.
- Contradictions: HARDENING §4 ✅ cites `core.lane_health()`, `NOUGEN_MIN_COVERAGE_PCT`, `tests/test_lane_health.py`, none exist in git history; `sync_mesh_status` docstring claims hash-parity audit it does not do.

## Zone 7: Truth, Contradiction and Canon Engine (steps 601-700)

601. **Write the one rule into code: unknown beats manufactured certainty** — 🟡 `canonical_facts.py:resolve` returns `cannot_determine`; `status_semantics.py:ContextReceipt.absence_conclusions_permitted` requires FULL. Gap: no shared `TruthStatus` type; each module invents its own vocabulary. Land `src/nougen_shards/truth.py` [551:#39] [550:#100]
602. **Define one claim record** — ⬜ claims exist only as `evidence_ledger.py` `claims` table (business evidence) and `reconstructive_recall_v2.py:MemoryEvent`; no shared claim_id/subject/predicate/value schema. Add `Claim` dataclass in `truth.py` reused by both [551:#10]
603. **Content-address claim IDs** — 🟡 `canonical_facts.py:put` uses sha256 of canonical JSON as `snapshot_id`; `evidence_ledger.py:_id` uses random uuid for claims. Give claims a deterministic sha256 over normalized subject/predicate/value [551:#34]
604. **Claim normalization** — 🟡 `canonical_facts.py:validate_snapshot` normalizes ISO time, sorted machines/entities, Decimal totals. Gap: no normalizer for free-text shard claims; add `truth.normalize_claim` [551:#33]
605. **Claim equivalence** — 🟡 `consolidate.py:_jaccard >= 0.8` treats near-restatements as duplicates. Gap: lexical only, no entity/value equivalence; add equivalence classes keyed on normalized claim hash [551:#33]
606. **Unify provenance classes** — 🟡 `evidence_ledger.py:Provenance` (SOURCE_VERIFIED..CORRECTED) and `architecture_gauntlet.py:arbitrate_epistemic_authority` tiers (VERIFIED_TELEMETRY..MODEL_INFERENCE) are disjoint vocabularies. Map both into one enum in `truth.py` [551:#10]
607. **Observed versus inferred on every claim** — 🟡 `evidence_ledger.py:Provenance.INFERRED` and `add_event` refusing SOURCE_VERIFIED at creation. Gap: shards in `core.capture` carry no observed/inferred flag; add a column [551:#10]
608. **Separate model-generated hypotheses** — 🟡 `evidence_gate.py:evaluate` keeps candidates in OBSERVE/SHADOW until evidence. Gap: model-written shards are not tagged hypothesis at capture; tag in `core.py:capture` when source is a model lane
609. **Candidate status by default** — 🟡 `consolidate.py:consolidate(new_status="candidate")` and `_status_from_tags`. Gap: only reachable when `NOUGEN_CONSOLIDATE=1` (`consolidate.enabled`); default capture has no status. Make candidate the stored default
610. **Canon only by explicit flag** — ✅ `canonical_facts.py:validate_snapshot` raises unless `canonical is True` and `completeness.state == "complete"` with no missing machines
611. **Never infer missing as zero** — ✅ `canonical_facts.py:validate_snapshot` requires `per_machine` keys equal expected machines and `total` equal to their Decimal sum; tested in `tests/test_canonical_facts.py` [550:#3]
612. **Scope-safe canonical resolve** — ✅ `canonical_facts.py:resolve` rejects `scope_mismatch:*`, `future_as_of`, `incomplete_snapshot` with reasons in `rejected` and returns `cannot_determine` with `complete: False` [551:#38]
613. **Append-only canon history** — ✅ `canonical_facts.py:put` uses `INSERT OR IGNORE` into `fact_snapshots`; `canonical_current` only moves a pointer by `(as_of, version, event_at)` rank
614. **Ambiguity is a status, not a pick** — ✅ `canonical_facts.py:resolve_query` returns `status: "ambiguous"` with all tied candidates when two keys share the top score
615. **Read-only canon resolution** — ✅ `canonical_facts.py:CanonicalFactIndex(create=False)` opens `mode=ro` and refuses an unmigrated index; `put` raises PermissionError
616. **Explicit unknown versus empty type** — 🟡 `status_semantics.py:StatusLevel.UNKNOWN`, `ContextState.UNAVAILABLE`, `canonical_facts` `cannot_determine`. Gap: shard recall in `core.retrieve` still returns a bare empty list [551:#39] [550:#3]
617. **Wire ContextReceipt into recall** — ⬜ `status_semantics.py:derive_context_state` is imported only by `tests/test_context_state.py`; no recall or MCP path calls it. Attach it to `core.retrieve` and `app.py` recall_memory responses [551:#37] [551:#38]
618. **Global absence proof object** — 🟡 `ContextReceipt.absence_conclusions_permitted` gates on FULL. Gap: no receipt lists per-store searched ranges; add `AbsenceProof` in `status_semantics.py` [551:#38] [550:#3]
619. **Insufficient coverage label** — 🟡 `ContextState.DEGRADED`/`LOCAL_ONLY` exist. Gap: not surfaced to recall callers; add `coverage` to recall envelopes [550:#3]
620. **Unknowable versus unknown** — 🟡 `reasoning_governor.py:epistemic_check` handles `evidence_state == "UNKNOWABLE"`. Gap: no claim-level unknowable marker; add to `truth.TruthStatus`
621. **Fix: HUMAN_CONFIRMATION tier is dead** — ⬜ defect: `architecture_gauntlet.py:arbitrate_epistemic_authority` docstring ranks HUMAN_CONFIRMATION 5,000 bps but has no branch; human-only evidence returns `NO_EVIDENCE`. Add the branch and a test
622. **Fix: disagreeing documents silently pick first** — ⬜ defect: `arbitrate_epistemic_authority` returns `doc_items[0]` at 7,000 bps even when DOC_AUTHORITY items disagree. Apply the telemetry conflict rule to every tier
623. **Fix: inference tier ignores disagreement** — ⬜ defect: MODEL_INFERENCE branch returns `inference_items[0]` with up to 1,000 bps though items may contradict. Return quarantine on disagreement
624. **Fix: CANON_SUPERSEDED overridden_count** — ⬜ defect: `arbitrate_epistemic_authority` reports `len(evidence_list) - 1`, counting non-contradicting duplicates as overridden. Count only distinct losing values
625. **Move arbitration out of the gauntlet** — ⬜ `arbitrate_cross_domain_conflict` and `arbitrate_epistemic_authority` live in `architecture_gauntlet.py` with no production caller. Move to `src/nougen_shards/arbitration.py`
626. **Fix: canonical tie silently loses** — ⬜ defect: `canonical_facts.py:put` keeps the first of two snapshots with equal `(as_of, version, event_at)` and different values, recording no conflict. Return `contradiction` and add a conflicts table [550:#99]
627. **Fix: `today` hardcodes one timezone** — ⬜ defect: `canonical_facts.py:resolve_query` uses `ZoneInfo("America/New_York")` for "today", ignoring each snapshot's `temporal.timezone`. Resolve per-snapshot timezone
628. **Supersession consistency in canon** — 🟡 `validate_snapshot` keeps `supersedes` but never checks the target exists or shares `canonical_key`. Validate in `put`
629. **Fix: quarantine returns accepted=True** — ⬜ defect: `reconstructive_recall_v2.py:insert_event` returns `(True, QUARANTINED)` for invalid supersession and group conflict, but `(False, QUARANTINED)` for ID collision. Return False consistently
630. **Contradiction detection at capture** — 🟡 `consolidate.py:consolidation_tags` tags `consolidate:conflict`, called from `core.py:capture` (~line 1050). Gap: opt-in via `NOUGEN_CONSOLIDATE`, and exceptions return `[]` silently
631. **Recall must honour supersedes tags** — ⬜ `consolidate.py` writes `supersedes:<id@dbN>`, but no reader in `core.py` or `app.py` greps that tag; superseded shards still rank as current. Filter/annotate in `core.retrieve`
632. **Contradiction detection at retrieval** — 🟡 `reconstructive_recall_v2.py:execute_pulse_retrieval` sets QUARANTINED for duplicate contradiction groups. Gap: engine is in-memory, not called by `core.retrieve`; wire it
633. **Fix: retrieval VERSIONED on any supersedes** — ⬜ defect: `execute_pulse_retrieval` marks VERSIONED if any opened event has `supersedes`, even from an unrelated group. Check per group
634. **Surface consolidate conflicts** — 🟡 `consolidate-target:<id>` tag is written. Gap: no CLI or MCP lists open conflicts; add `nougen conflicts list` in `cli.py`
635. **Record decider failure** — 🟡 `consolidate.py:consolidate` tags `decider_failed`, but `consolidation_tags` swallows outer exceptions to `[]`. Emit a `consolidate:skipped` tag with reason
636. **Lock-tag vocabulary parity** — ⬜ defect: `consolidate.LOCKED_STATUSES` includes `corrected`, but `_LOCK_TAGS` lacks it, so a `corrected` shard is never seen as locked. Share one set
637. **Conflict quarantine store** — 🟡 in-memory `ReconstructiveRecallEngine.quarantined_events`; `evidence_ledger.py` `conflicts` table (status OPEN). Gap: no durable shard-side quarantine; add a `conflicts` table beside shards
638. **Conflict resolution API** — ⬜ `evidence_ledger.py` has `record_conflict` but no `resolve_conflict`; `resolved_at` is never set. Add resolve with reason and authority
639. **Review flag resolution** — ⬜ `evidence_ledger.py:flag_review` writes OPEN; nothing closes it. Add `close_review` in `evidence_ledger.py`
640. **Contradicting evidence links** — ⬜ `evidence_ledger.py:add_claim` inserts `claim_sources` with `supports=1` only; the schema allows 0 but no API writes it. Add `refuted_by`
641. **Fix: duplicate file counts as independent corroboration** — ⬜ defect: `evidence_ledger.py:add_source_file` mints a new root per call, so one file added twice passes `CORROBORATED`. Dedupe roots by `sha256` in `_validate_provenance`
642. **Evidence independence scoring** — 🟡 `_validate_provenance` requires two distinct `root_source_id` for CORROBORATED. Gap: roots are caller-asserted; add hash/origin independence score
643. **Derived-source tracking** — 🟡 `sources.root_source_id` links derivatives to a root. Gap: no multi-hop chain or depth; add `derived_from` edges
644. **Circular evidence detection** — ⬜ nothing rejects A-derived-from-B-derived-from-A in `evidence_ledger.py` or `reconstructive_recall_v2.find_provenance_path`. Add cycle check on insert
645. **Echo chamber detection** — ⬜ many shards citing one relay/message count as many; land a source-origin collapse in `truth.py` before counting support
646. **Claim promotion parity** — 🟡 `evidence_ledger.py:promote_event` validates and writes a correction. Gap: claims have no promote path; add `promote_claim`
647. **Correction chains** — 🟡 `evidence_ledger.py:correct` and `promote_event` append `corrections` rows with prior/corrected. Gap: no query walks a subject's chain; add `correction_chain(subject_id)`
648. **Correction provenance required** — 🟡 `correct` accepts `source_id=None`. Require a source or explicit authority for CORRECTED
649. **Transaction guards** — ✅ `evidence_ledger.py:add_transaction` refuses kinds other than EXPENSE/INCOME and tax treatment on OWN_ACCOUNT_TRANSFER; tested in `tests/test_evidence.py`
650. **Verified-at-birth refused** — ✅ `evidence_ledger.py:add_event` raises for SOURCE_VERIFIED/CORROBORATED; `_validate_provenance` requires a primary source
651. **Evidence bundle per answer** — 🟡 `evidence_ledger.py:evidence_for_transaction` returns sources, corrections, conflicts, flags. Gap: shard recall returns no bundle; add one to recall envelopes
652. **Evidence lock on answers** — 🟡 `reconstructive_recall_v2.py:verify_evidence_lock` and `EvidenceLockError`. Gap: only the in-memory engine uses it; enforce in `app.py` answer paths
653. **Truth receipt** — 🟡 `canonical_facts` receipts carry `lanes_queried`, `failed_lanes`, `rejected`, `coverage`. Gap: `failed_lanes` is always `[]`; populate on SQLite errors [551:#46] [550:#100]
654. **Why believed** — 🟡 `evidence_gate.py:Verdict.reason` explains status. Gap: shard recall has no why; add `why` to `truth.TruthReceipt`
655. **Why uncertain / rejected** — 🟡 `canonical_facts.resolve` lists `rejected[].reason`. Gap: shard recall does not; add reason codes [551:#44]
656. **Why superseded** — 🟡 `consolidate` returns `reason` and `guards`, but only tags survive capture. Persist the reason
657. **Confidence explanation** — 🟡 `MemoryEvent.confidence_bps`, `arbitrate_epistemic_authority` bps. Gap: no derivation text; add to receipt
658. **Uncertainty labels over raw numbers** — ⬜ no mapping from bps to labels (verified/likely/contested/unknown); add in `truth.py`
659. **Confidence calibration fixtures** — ⬜ no fixture checks bps against outcomes; land `tests/test_truth_calibration.py` [551:#40]
660. **Source reliability per source** — ⬜ no per-source reliability score in `evidence_ledger.sources`; add column
661. **Source freshness** — 🟡 `status_semantics.py:Observation.aged` and `DEFAULT_MAX_AGE_S=300` for status. Gap: no freshness on claims; reuse for claim `as_of`
662. **Stale truth detection** — 🟡 `status_semantics.is_stale_generation`. Gap: not applied to canonical snapshots; add max-age to `resolve`
663. **Authority hierarchy per domain** — 🟡 `arbitrate_epistemic_authority` fixed four tiers. Gap: one hierarchy for all domains; key tiers by domain in `arbitration.py`
664. **No universal precedence hack** — 🟡 `arbitrate_cross_domain_conflict` quarantines unbridged cross-domain conflicts. Keep; add test that no tier wins across domains without a bridge
665. **User authority for authored canon** — 🟡 `evidence_gate.py:Authority.OWNER` and invariant escalation in `evaluate`. Gap: not applied to shard canon; require OWNER to lock
666. **Repository authority for code truth** — ⬜ no rule that the checked-out tree beats a shard about code; add `repo` tier in `arbitration.py`
667. **Runtime authority for live state** — 🟡 `status_semantics.classify_node_dimensions` derives live state. Gap: not an arbitration tier; add it
668. **Telemetry authority and conflicting telemetry** — ✅ `arbitrate_epistemic_authority` returns TELEMETRY_CONFLICT_QUARANTINED at 0 bps on equal-time disagreement; tested in `tests/test_architecture_gauntlet.py` [550:#99]
669. **Conflicting nodes** — 🟡 `canonical_facts` per_machine requires every expected machine. Gap: no rule when two nodes report different values for one fact [550:#12]
670. **Conflicting agents** — ⬜ no arbitration when two agents' handoffs assert different outcomes; land in `arbitration.py` [550:#25]
671. **Relay completion needs evidence** — 🟡 `evidence_gate.py:evaluate` refuses without samples. Gap: relay close in `handoff.py` needs no receipt (unverified) [550:#23]
672. **Automatic safe arbitration** — 🟡 VERSIONED paths in `arbitrate_cross_domain_conflict` and `insert_event`. Gap: no policy of which classes auto-resolve
673. **Human-required arbitration** — 🟡 `consolidate` returns CONFLICT for locked targets. Gap: no queue to a human; route to `consolidate:conflict` list
674. **Arbitration workflow receipts** — 🟡 `EvolveGate.ledger` records check/promote/rollback. Gap: in-memory list; persist to SQLite
675. **Contradiction severity** — ⬜ `ContradictionState` has NONE/VERSIONED/QUARANTINED only; add severity in `reconstructive_recall_v2.py`
676. **Contradiction clustering** — 🟡 `MemoryEvent.contradiction_group`. Gap: caller-assigned; derive groups from normalized claim keys
677. **Contradiction timeline** — ⬜ no ordered view of a group's assertions; add `contradiction_timeline(group)`
678. **Contradiction explanation** — 🟡 `arbitrate_cross_domain_conflict` returns reason codes. Add human text in receipts
679. **Canon candidate promotion gate** — 🟡 `evidence_gate.EvolveGate.promote` needs ELIGIBLE plus authority. Gap: gates policies, not facts; reuse for shard canon
680. **Canon rollback** — 🟡 `EvolveGate.rollback` refuses without `rollback_to`. Gap: `canonical_current` has no rollback; add pointer revert with receipt
681. **Canon diffs** — ⬜ no diff between two `fact_snapshots` versions; add `nougen facts diff` in `cli.py`
682. **Canon snapshots and as-of reads** — ✅ `canonical_facts.py:resolve(as_of=...)` seeks `as_of_ms <= ?` per scope via `idx_fact_history_ms`
683. **Canon lock receipts** — ⬜ locks are just tags (`_LOCK_TAGS`); no receipt of who locked when. Add lock ledger
684. **Immutable historical canon** — 🟡 `fact_snapshots` is insert-only in code. Gap: no trigger forbids UPDATE/DELETE; add SQLite triggers
685. **Current canon projection** — ✅ `canonical_current` table maintained in `canonical_facts.py:put` and `_backfill_v2`
686. **Branch canon** — 🟡 `MemoryEvent.branch`; supersession requires same branch in `insert_event`. Gap: shards have no branch field
687. **Fictional namespaces and Route isolation** — ⬜ no universe/route/variant namespace in `core.py` shards; only `domain_key`. Add namespace so fiction never answers operational truth [550:#75]
688. **Production lock states** — ⬜ no draft/locked/production state machine for canon; land in `truth.py`
689. **Contradiction tests** — ✅ `tests/test_reconstructive_recall_v2.py`, `tests/test_consolidate.py` (13 tests) cover quarantine and supersede guards
690. **Hallucinated memory tests** — 🟡 `consolidate` guard `target_not_in_neighbours` tested. Gap: no end-to-end hallucinated-shard recall test [551:#41]
691. **Source spoofing tests** — ⬜ no test forges `root_source_id` to fake corroboration; add to `tests/test_evidence.py` [550:#19]
692. **Poisoned shard tests** — ⬜ no test that injected shard text cannot become canon; add under tests [550:#69]
693. **Stale evidence tests** — ⬜ add a test that aged claims downgrade in `resolve`
694. **Re-run determinism** — ✅ `evidence_gate.evaluate` is pure; `bundle_id` hashes the bundle; tested in `tests/test_evidence_gate.py` [550:#99]
695. **Absence war-game** — ⬜ harness that kills a lane and asserts no absence claim; `tests/` [550:#3]
696. **Truth benchmark** — ⬜ no scored corpus of contested facts; land `bench/truth/`
697. **Canon benchmark** — ⬜ scale test for `resolve` over deep history; `tests/`
698. **Provenance, evidence and claim graph** — 🟡 `reconstructive_recall_v2.find_provenance_path` (depth 3, in memory). Gap: no durable graph; join with `graph.py`
699. **Alternate timeline support** — ⬜ branch-aware as-of reads across timelines; extend `canonical_facts.resolve`
700. **Truth engine self-audit** — ⬜ nightly job re-deriving every canon pointer and conflict from raw evidence, failing closed on drift [551:#47] [550:#100]

### Zone 7 verdict
- Exists: a strict canonical fact index (`canonical_facts.py`: explicit canon, complete coverage, `cannot_determine`, `ambiguous`, as-of reads), a business evidence ledger with independence checks (`evidence_ledger.py`), a pure promotion gate (`evidence_gate.py`), and `ContextReceipt` absence rules (`status_semantics.py`).
- Load-bearing gap: none of it touches shard recall. `derive_context_state`, `ReconstructiveRecallEngine` and both arbitration functions have no production caller, and `supersedes:` tags from `consolidate.py` are written but never read.
- Real defects: human-confirmation tier unreachable and doc/inference disagreement ignored (`arbitrate_epistemic_authority`); duplicate file passes CORROBORATED (`add_source_file`); canonical ties silently lose (`put`); quarantine returns accepted=True (`insert_event`).
- First PR: "truth: honour supersedes and attach ContextReceipt to recall" — `src/nougen_shards/core.py` (retrieve), `src/nougen_shards/status_semantics.py`, `app.py` recall_memory, new `tests/test_recall_truth_receipt.py`.
- Draft-plan contradiction: the gauntlet text (`architecture_gauntlet.py` line ~71/151) claims ConflictAtWriteGate and EvidenceLockGate protect recall; in code they guard only an in-memory engine no recall path calls. Also the evidence ledger is business/tax evidence, not memory truth.

## Zone 8: Security, Privacy and Sovereignty (steps 701-800)

701. **Keep the full-history secret scan blocking** — ✅ `.github/workflows/security.yml` job `secrets-history` runs pinned gitleaks 8.30.1 `detect --log-opts="HEAD" --redact --exit-code 1` with `fetch-depth: 0` [551:#751] [551:#752] [550:#76]
702. **Verify the gitleaks binary checksum the workflow comment promises** — 🟡 comment in `security.yml` says "verify the sha256"; the `run:` step only curls and untars, no `sha256sum -c`. Add the pinned digest check [551:#788]
703. **Keep CodeQL gating Python and TypeScript** — ✅ `security.yml` job `codeql`, matrix `python, javascript-typescript`, `build-mode: none`, SHA-pinned actions [551:#751]
704. **Keep the blocking dependency CVE gate** — ✅ `security.yml` job `dependencies`: Trivy fs `scanners: vuln,secret,misconfig`, `severity: HIGH,CRITICAL`, `exit-code: "1"` [551:#784]
705. **Keep workflow-injection scanning and deny-all token scope** — ✅ `security.yml` top-level `permissions: {}`, per-job grants, zizmor job `workflows`, harden-runner egress audit on every job [551:#767]
706. **Restore or rewrite the missing wargame corpus** — ⬜ HARDENING.md §5/§7/§8/§9 and `security.yml` line 1 cite `wargames/*.md` (incl. `elevate-security.md`); no `wargames/` directory exists in the tree. Land `wargames/` or fix citations [551:#798] [550:#100]
707. **Make HARDENING.md statuses machine-checked** — ⬜ nine done/missing claims are prose only; add `tests/test_hardening_claims.py` asserting each cited symbol/test file exists (e.g. `_looks_like_blob`, `test_capture_secret_guard.py`) [551:#800]
708. **Pin redaction before every write path** — ✅ `src/nougen_shards/core.py:1038-1070` `capture()` runs `redact_content` over title, content, tags and source_uri before hash/embed/write [551:#762] [550:#70]
709. **Keep one canonical credential pattern set** — ✅ `brain_scan/redaction.py` `SECRET_PATTERNS`; `credential_patterns.py` `redact()` aliases it, `VERSION = "2.1.0"`, `self_test()` raises `StaleBackingSetError`; `tests/test_credential_patterns.py` [551:#762]
710. **Assemble fixture secrets at runtime, never as literals** — ✅ `credential_patterns.py` `_b64`, `_p`, `_pem` build shapes at import so gitleaks sees no literal; rationale documented inline [551:#759]
711. **Keep the published-surface guard running** — ✅ `tests/test_published_surface.py` checks credentials, `MACHINE` regex (Windows/mac/home user paths, personal mail domains), allowlist size, and `test_the_checks_actually_fire` [551:#758] [550:#74]
712. **Add LAN-IP and hostname rules to the surface guard** — 🟡 `test_published_surface.py` `MACHINE` has no RFC1918 or owner-hostname pattern; #542/#545 scrubs were manual. Add all three RFC1918 ranges and a config-sourced hostname list [551:#754] [551:#755] [PR #545]
713. **Set NOUGEN_SURFACE_NAMES in CI** — 🟡 `_identity_pattern()` returns None when unset and no workflow sets it, so `test_no_personal_names_are_published` is a no-op in CI; add a repo secret-backed env in `ci.yml` [551:#753] [550:#74]
714. **Guard against private canon in the public tree** — 🟡 #547 removed persona doc and neutralised lore names by hand; no test blocks re-entry. Add a canon-term list (env-sourced like surface names) to `test_published_surface.py` [551:#757] [550:#75] [PR #547]
715. **Guard owner domain in code** — 🟡 #549 moved owner domain to local config; no regression test forbids the literal. Add env-sourced domain terms to the surface guard [551:#756] [PR #549]
716. **Keep public defaults fleet-neutral** — ✅ `tests/test_public_fleet_neutral.py` proves `rich_hud._local_fleet_rows()` is empty without `~/.nougen/nodes.json` and uses RFC 5737 test-net fixtures [551:#760] [551:#761]
717. **Extend neutral-default tests to every roster consumer** — 🟡 only `rich_hud` is covered; `tools/cc_msg.py` `_known_nodes()` and nougenmsg `fleet_hosts_path` (PR #528) lack an empty-clone test [551:#760] [550:#35]
718. **Re-audit machine paths in CI** — 🟡 HARDENING §6 says "missing periodic re-audit in CI"; `test_published_surface.py` covers it only for paths matching `MACHINE`. Mark §6 done once that test is cited there [550:#74]
719. **Encrypt private/secret shard bodies at rest** — ✅ `core.py:1201-1205` `_pv.should_encrypt(sensitivity)` then `encrypt_text` (AES-256-GCM, `ngenc1:`) as the last step before INSERT; FTS never sees plaintext [551:#790]
720. **Stop storing plaintext-equivalent embeddings for encrypted shards** — ⬜ `core.py` embeds real text before encryption, so a `private` shard's raw vector sits beside its ciphertext (HARDENING §9). Skip or rotate embeddings when `enc=1` in `core.capture()` [551:#790]
721. **Validate sensitivity values at every entry** — ✅ `private_vault.normalize_sensitivity` raises `ValueError` outside normal/private/secret [551:#790]
722. **Protect the vault data key** — ✅ `private_vault.load_key`/`_generate_key` with DPAPI wrap and `_write_recovery_key` (RECOVERY_KEY.txt); `tests/test_private_vault.py` [551:#790]
723. **Fail closed on plaintext secret storage** — ✅ `keymaker._protect`: DPAPI on Windows, keyring elsewhere, `RuntimeError` unless `NOUGEN_ALLOW_PLAINTEXT_VAULT=1` [551:#762]
724. **Migrate legacy plaintext keymaker rows** — 🟡 `keymaker.migrate_to_encrypted()` exists but `_unprotect` still passes legacy plaintext through silently; add a doctor warning counting plaintext rows [551:#763]
725. **Harden secret-store file permissions** — ✅ `keymaker._harden_path` restricts the vault path; `tests/test_keymaker_security.py` [551:#765]
726. **Keep vault_put write-only and owner-only** — ✅ `app.py` `vault_put` raises `PermissionError` when `core.active_tenant_id() != "owner"`, returns a 12-hex fingerprint, never the value [551:#762]
727. **Keep credential objects non-printable** — ✅ `fleet_keys.FleetCredential.__repr__` hides the value ("never leak the value through a traceback") [551:#763]
728. **Fingerprint-only key health probes** — ✅ `auth_check.fingerprint` and `check_key` report LIVE/dead per key without echoing secrets; `tests/test_auth_check.py` [551:#763]
729. **Build a credential rotation ledger** — ⬜ keymaker stores values and fingerprints but no rotated_at/previous-fingerprint table; land in `keymaker.py` + `nougen auth rotate` [551:#764]
730. **Constant-time token comparison everywhere** — ✅ `tenants.resolve_token` uses `hmac.compare_digest` on sha256 hashes; also `mcp_oauth.py:125,298`, `dam/envelope.py:151` [551:#792]
731. **Refuse ambiguous tenant credentials** — ✅ `tenants.resolve_token` returns None when `len(matches) != 1`, so record order never picks a vault [551:#765]
732. **Isolate tenant vaults on disk** — ✅ `tenants.vault_dir_for`; `tests/test_local_vault_allowed_roots.py` blocks parent, sibling tenant, secrets store and traversal [551:#770] [550:#71]
733. **Fail closed when the tenant registry is unreadable** — ✅ `app.py:933-980` maps `RegistryUnreadableError`/`TenantRegistryError` to explicit errors, not open access [551:#765]
734. **Keep API docs and HUD off on exposed binds** — ✅ `app.py` import-time exposure decision; `tests/test_exposure_guard.py` reloads app under patched binds [551:#782]
735. **Gate the destructive /pop drain** — ✅ `tests/test_pop_requires_auth.py` [550:#17]
736. **Authenticate MCP over OAuth** — ✅ `src/nougen_shards/mcp_oauth.py` PKCE check (`compare_digest(expected, challenge)` line 125); `tests/test_mcp_oauth.py` [551:#766]
737. **Scope the fleet peer token** — 🟡 `app._resolve_tenant_credential` accepts `FLEET_PEER_TOKEN` as a second credential into the same tenant model; no read-only scope distinguishes it from owner writes. Add a scope field in `tenants.Tenant` [551:#765]
738. **Introduce read/write/amend/forget scopes** — ⬜ `tenants.TenantRecord` carries lane and `allow_federation` only; add per-token scopes checked in `app.tenant_vault_context` [551:#765]
739. **Admin scope for registry and mint** — ⬜ `tenants.mint_tenant` has no caller-scope check beyond local file access; land an admin scope in `tenants.py` [551:#765]
740. **Audit-log shard_forget** — ⬜ `app.py` `shard_forget` runs a raw `DELETE FROM shards` with no receipt, bypassing `unlearning.py`'s `audit_receipt_hash`; route through unlearning or write a receipt [551:#795] [550:#11]
741. **Audit-log amend and retract** — 🟡 `shard_amend`/`shard_retract` keep the row (retract prefixes `[RETRACTED]`), but record no actor/tenant/time receipt; add to `app.py` [551:#795] [550:#9] [550:#10]
742. **Keep confirm_title on forget** — ✅ `app.shard_forget` requires `confirm_title` via `_resolve_shard(..., expect_title=...)` because ids repeat across 9 DBs [550:#11]
743. **Refuse irreversible ops from queues** — ✅ `dam/envelope.py` `SPOOLABLE = {"shards_capture","shards_amend"}`; forget refused unconditionally [550:#17]
744. **Encrypt and authenticate spooled events** — ✅ `dam/envelope.py` AES-256-GCM with random 12-byte nonce, AAD hash, HMAC `sign`/verify with `compare_digest` [551:#789]
745. **Add freshness to envelopes** — 🟡 envelope has nonce but no max-age or seen-nonce store; a captured sealed event can be replayed. Add expiry + dedupe in `dam/envelope.py` [550:#15] [550:#17]
746. **Sign synchron receipts** — ✅ `synchron/receipt.py` `seal()`/`verify()` HMAC with `compare_digest` [551:#795]
747. **Sign amendments, retractions and forget requests** — ⬜ no signature on `shard_amend/retract/forget` payloads in `app.py`; reuse `synchron/receipt.seal` [551:#787]
748. **Hash-chain an append-only audit log** — ⬜ no tamper-evident log; land `src/nougen_shards/audit_log.py` chaining receipts from 740/741/747 [551:#795]
749. **Add auth-failure telemetry** — 🟡 `tests/test_auth_failure_taxonomy.py` and `test_auth_latch.py` classify failures; no counter/receipt of rejected `X-NGS-Token` attempts in `app.verify_token` [551:#793]
750. **Rate-limit auth and write endpoints** — ⬜ grep finds no rate limiter in `app.py` or src (only `coach_governor` spend throttle); add per-token/IP buckets around `verify_token` and `/sync/push` [551:#794] [550:#49]
751. **Throttle query fan-out** — ⬜ no per-tenant query budget on search/recall routes in `app.py` [551:#794]
752. **Keep the mutation gatekeeper honest about its limits** — ✅ `gatekeeper.check_mutation_gate` docstring states "NOT a security boundary"; `tests/test_gatekeeper.py` [551:#774]
753. **Bound dav1d exec to an allowlist** — ✅ `dav1d_executor.py:122-188` first-token and flag allowlist [551:#774] [551:#775]
754. **Sanitise evolved-skill paths** — ✅ `tests/test_evolution_security.py::test_skill_id_sanitization_blocks_traversal` pins `evolution.evolve_skill` inside `skills/` [551:#770] [550:#71]
755. **Refuse symlinks and credential files in the scanner** — ✅ `tests/test_scanner_security.py` `test_symlink_is_not_safe`, `test_credential_files_are_skipped`, `test_danger_dir_still_blocked` [551:#771] [550:#72]
756. **Redact local-vault read paths** — ✅ `tests/test_local_vault_redacts_read_path.py` [551:#762]
757. **Reject disguised uploads** — ✅ `tests/test_upload_security.py` rejects HEIF brand even when renamed [551:#770]
758. **Zip-slip defence for any archive import** — ⬜ (unverified) no zip-slip test in `tests/`; add one wherever brain_scan importers unpack archives [551:#772]
759. **Secure temp files** — ⬜ (unverified) no test pins `tempfile` mode/reuse; add `tests/test_temp_file_safety.py` [551:#773] [550:#73]
760. **Validate TLS on gateway probes** — ✅ `tests/test_gateway_probe_tls.py` [551:#791]
761. **Port shell-safe remote Ollama call everywhere** — ✅ `src/nougen_shards/nougenmsg.py` ~604-635 sends payload on stdin with constant `remote_cmd`; NouGenMsg copy still vulnerable (see briefing) [551:#774] [branch codex/fix-ollama-stdin]
762. **Label untrusted shard content at recall** — ⬜ recall returns shard text to agents with no untrusted-content marker; add a provenance/trust field in `core` recall payloads and MCP tools [551:#776] [551:#777] [550:#69]
763. **Prompt-injection corpus for shard and relay bodies** — ⬜ no injection fixtures in `tests/`; land `tests/fixtures/injection/` and a recall-path test [551:#777] [551:#778] [550:#69] [550:#19]
764. **Separate tool instructions from retrieved text** — ⬜ MCP tools in `app.py` concatenate content into responses; add a structured `source_content` field [551:#776]
765. **SSRF guard for linked nodes** — ⬜ `keymaker.register_cloud_node(url, name)` stores any URL; add scheme/host allowlist and private-range refusal [551:#780] [551:#783]
766. **Redirect policy on outbound calls** — ⬜ (unverified) no test pins redirect-following off for token-bearing requests [551:#781]
767. **Local-network egress policy** — ⬜ harden-runner is `egress-policy: audit` only in CI; no runtime egress allowlist in src [551:#782]
768. **Keep privacy mode refusing cloud routes structurally** — ✅ `tests/test_fleet_privacy_breaker.py` with `NOUGEN_PRIVACY` against `tools/fleet.py` [551:#782]
769. **Isolate plugins from private code** — ✅ `node_plugins.load_node_plugins` loads entry points in group `nougen_shards.node_plugins`; private packs live outside the repo [550:#31]
770. **Dedupe plugin registration** — ✅ `node_plugins.py` `seen` set on `(ep.name, ep.value)`; `tests/test_node_plugins.py` [550:#29]
771. **Contain plugin startup failures** — ✅ `load_node_plugins` catches `Exception`, logs, reports `failed:` [550:#30]
772. **Detect plugin tool/route collisions** — ⬜ `load_node_plugins` does not check existing routes or MCP tool names before `register`; add a pre/post diff in `node_plugins.py` [550:#33] [550:#34]
773. **Plugin manifests and capability declarations** — ⬜ `register(app, mcp, ctx)` gets full app access; add a manifest (tools, routes, scopes) validated in `node_plugins.py` [550:#32]
774. **Plugin signatures** — ⬜ entry points load unsigned; land signature/hash pinning in `node_plugins.py` [551:#786]
775. **Add a .dockerignore** — ⬜ `Dockerfile` does `COPY --chown=user:user . /app` and no `.dockerignore` exists, so a local build copies `.env`, `.vault`, `.git` into the image [551:#762]
776. **Keep the image non-root and slim** — ✅ `Dockerfile` `python:3.12-slim`, `useradd -u 1000`, `USER user` [551:#765]
777. **Install only the compiled lockfile** — ✅ `Dockerfile` `pip install -r requirements.txt` then `--no-deps .`; CI dry-resolves requirements.txt [551:#784]
778. **Add a container HEALTHCHECK and read-only data mounts** — ⬜ `Dockerfile` has no HEALTHCHECK; /data is chown'd writable by the app user [550:#89]
779. **Generate SBOM on the publish path** — ⬜ `security.yml` header says SBOM/provenance "live on the publish path (see deploy-space.yml)"; `deploy-space.yml` has no sbom/attest step. Add syft + attest there [551:#785]
780. **Provenance attestations for releases** — ⬜ no `actions/attest-build-provenance` in any workflow; land in `deploy-space.yml` [551:#786] [551:#787]
781. **Reproducible build check** — ⬜ no workflow rebuilds and compares digests; add to `ci.yml` [551:#788]
782. **Preserve deploy secrets across Space redeploys** — ⬜ (unverified) no test proves `deploy-space.yml` leaves Space secrets intact [551:#769]
783. **Backfill-redact pre-guard shards** — ⬜ HARDENING §8 "missing backfill sweep"; land a read-only audit then GM-approved sweep in `tools/` using `credential_patterns.contains_credential` [551:#762]
784. **Detect financial and personal identifiers** — ⬜ `SECRET_PATTERNS` covers credentials only; add card/account/phone shapes with `LOW_CONFIDENCE` tier in `credential_patterns.py` [551:#753]
785. **Auto-classify sensitivity at capture** — ⬜ `capture()` trusts caller `sensitivity`; route `contains_credential`/PII hits to `private` in `core.py` [551:#790]
786. **Configurable privacy rules file** — ⬜ patterns are code-only; load extra rules from `~/.nougen/privacy_rules.json` in `brain_scan/redaction.py` [551:#796]
787. **Encrypt backups and /sync/pull exports** — 🟡 `/sync/pull` ships encrypted-at-rest bodies as `ngenc1` (`app.py:1717`) but normal rows travel plaintext; add export-level encryption [551:#789]
788. **Verify database integrity on a schedule** — 🟡 corrupt DBs are routed around (`core._QUARANTINED_WRITE_DBS`, `app._start_boot_quarantine`); no periodic `PRAGMA integrity_check` receipt [550:#6] [550:#88]
789. **Privacy regression corpus** — 🟡 `test_credential_patterns.py` holds the credential corpus; no PII/host/canon corpus. Extend under `tests/fixtures/privacy/` [551:#796]
790. **Public-repo pre-push scanner** — ⬜ no `.githooks/` in this repo; add a pre-push hook running `test_published_surface.py` + gitleaks on the outgoing range [551:#797]
791. **Security event receipts** — ⬜ no unified receipt for auth failure, forget, vault_put, plugin failure; land in `audit_log.py` (748) [551:#795]
792. **Update SECURITY.md to match the code** — 🟡 `SECURITY.md` names `shards_secrets.db` and "filesystem permissions"; code uses `agent_secrets.db` with DPAPI/keyring (`keymaker._protect`). Correct and link HARDENING [551:#799]
793. **Update docs/privacy.md vault claims** — 🟡 `docs/privacy.md` says vault is "encrypted/protected by OS user permissions" and omits AES-GCM private shards and tenant isolation; rewrite from mechanism [551:#799]
794. **Incident response runbook** — ⬜ no runbook in `docs/`; add `docs/incident-response.md` (key leak, public leak, compromised node) [551:#799]
795. **Fleet key rotation drill** — ⬜ depends on 729; add a `nougen auth rotate --all` dry-run test [551:#764]
796. **Compromise mode and emergency vault lockdown** — ⬜ no switch refusing all non-owner tokens and writes; add an env/state flag checked in `app.verify_token` [551:#799]
797. **Selective namespace lockdown** — ⬜ depends on 738 scopes; per-tenant freeze in `tenants.py` [551:#765]
798. **Embedding-inversion wargame and rotation** — ⬜ HARDENING §9 CANDIDATE; `NOUGEN_EMBED_ROTATION` does not exist in src. War-game first, then symmetric rotation in `core.py` [551:#798]
799. **Fuzz redaction and auth parsers** — ⬜ no hypothesis/fuzz tests on `redact_content` or `tenants._validate_record`; add property tests [551:#800]
800. **Security certification suite** — ⬜ one CI job that runs 701-799 checks and emits a signed receipt proving zero owner secrets, canon, credentials or host identity in the public tree [551:#800] [550:#74] [550:#75] [550:#76]

### Zone 8 verdict
- Exists today: SHA-pinned security.yml (gitleaks history, CodeQL, Trivy, zizmor, deny-all perms), one canonical redactor enforced in `core.capture()`, AES-256-GCM private-shard bodies, fail-closed keymaker, constant-time tenant auth with ambiguity refusal, exposure guard, `tests/test_published_surface.py`.
- Load-bearing gap: nothing records or scopes mutation. Tokens are all-or-nothing per tenant, `shard_forget` is a raw DELETE with no receipt, there is no rate limit, and retrieved shard text reaches agents unlabeled (steps 738, 740, 750, 762).
- First PR: "security: forget/amend/retract receipts + surface guard LAN-IP rule". Files: `app.py` (shard_forget/amend/retract write receipts via `synchron/receipt.seal`), new `src/nougen_shards/audit_log.py`, `tests/test_published_surface.py` (RFC1918 pattern), `.github/workflows/ci.yml` (set NOUGEN_SURFACE_NAMES).
- Contradictions: `security.yml` says SBOM/provenance live in deploy-space.yml (they do not); `security.yml` claims gitleaks sha256 verification (not performed); HARDENING.md and security.yml cite `wargames/*.md` that are absent; SECURITY.md/docs/privacy.md describe a vault the code no longer uses; HARDENING §8/§9 imply redaction protects the substrate, but encrypted private shards still store plaintext-derived embeddings.

## Zone 9: Performance, Scale and Million-Shard Architecture (steps 801-900)

801. **Keep the 9-DB hash-routed grid as the scale unit** — ✅ `src/nougen_shards/core.py` `MAX_DB_COUNT = 9` (l.49), `get_routing_index` (md5 mod 9) and `get_write_index` skipping full DBs via `is_db_full`.
802. **Fix the stale 1GB claim in `is_db_full` and docs** — 🟡 `core.py` `MAX_DB_SIZE` is 2GB (l.33-48, raised 2026-09-06) but the `is_db_full`/`get_write_index` docstrings and docs/architecture.md still say 1GB; align text to the env-driven limit.
803. **Define what happens when all nine DBs are full** — 🟡 `get_write_index` returns the hash target anyway ("All databases full; fall back"), silently exceeding the cap; add a loud metric/refusal and a grid-growth path in `core.py`.
804. **Choose journal mode per mount, not per host** — ✅ `core.py` `get_vault_journal_mode` (l.58): env override, auto DELETE on Space/bucket mounts, else WAL; applied in `get_connection` (l.292, l.599).
805. **Set explicit write-path pragmas (synchronous, cache_size, temp_store)** — ⬜ `core.py` sets no `synchronous`, `cache_size`, `mmap_size` or `temp_store` pragma (only `historical_fast_path.py` and `wake/codex_bridge.py` set `synchronous`); land a `_apply_pragmas(conn)` helper in `core.py` next to journal mode.
806. **Give grid connections a busy_timeout pragma consistently** — 🟡 `history.py` sets `busy_timeout=10000`, `ann_index.py` l.57 sets it; grid DBs rely on `sqlite3.connect(timeout=)` (`DEFAULT_SQLITE_TIMEOUT_S`) only. Document or unify in `core.py`. [550:#86]
807. **Add a WAL checkpoint policy** — ⬜ no `wal_checkpoint` call anywhere in `src/`; WAL files grow until SQLite auto-checkpoints; add a periodic `PRAGMA wal_checkpoint(TRUNCATE)` in the maintenance path (`core.py` or a `maintenance.py`).
808. **Add a vacuum / incremental-vacuum policy** — ⬜ no `VACUUM`/`auto_vacuum` in `src/`; retract/forget in `unlearning.py` leave free pages; add a measured, off-hours vacuum command in `cli.py`.
809. **Run `ANALYZE`/`PRAGMA optimize` after bulk loads** — ⬜ no call in `src/`; planner has no stats on 1.2GB DBs; add after backfill (`embedding_backfill.py`) and in maintenance.
810. **Inventory every index with its justifying query** — 🟡 `core.py init_db` creates `shards_title_nocase` (l.502), `idx_semantic_domain_subject` (l.521), `idx_shards_domain_utility` (l.527); no doc maps index to query; add `docs/indexes.md`.
811. **Add query-plan regression tests** — ⬜ no test runs `EXPLAIN QUERY PLAN`; add `tests/test_query_plans.py` asserting the hot recall queries use an index, not `SCAN shards`.
812. **Parallelize per-DB scans** — ✅ `core.py` `_run_db_scans` (l.1574) ThreadPoolExecutor, workers from `NOUGEN_RETRIEVE_DB_WORKERS`, yields in DB order for bit-identical merge.
813. **Batch the recall access log** — ✅ `core.py` ~l.1748: one `history.log_events` batch per DB scan replacing ~360 per-row commits per recall.
814. **Keep the in-RAM vector matrix cache** — ✅ `core.py` `_VECTOR_CACHE`, `_vector_cache_entry` (l.1989): loads embeddings once per process, answers by matmul (27s scan to RAM, per comment l.1905). [551:#14] [550:#7]
815. **Per-DB build locks with bounded wait** — ✅ `core.py` `_vector_cache_lock(i)` per-DB locks, `_vector_cache_wait_s` (`NOUGEN_VECTOR_CACHE_WAIT_S`, default 5s); herd test `tests/test_vector_cache_herd.py`.
816. **Prune deleted rows without full reload** — ✅ `core.py` `_prune_deleted` id-only scan; covered by `tests/test_vector_cache_delete.py`. [551:#15]
817. **Harden the cache signature to sub-second resolution** — 🟡 `_db_write_signature` uses `(int(st.st_mtime), st_size)` of db and -wal; two same-second, same-size writes (in-place UPDATE, WAL reuse after checkpoint) look unchanged. Use `st_mtime_ns` plus `PRAGMA data_version`. [551:#13] [550:#7]
818. **Invalidate the cache on in-place embedding updates** — 🟡 `_vector_cache_entry` docstring accepts that a backfill UPDATE "stays stale until the next full reload"; `embedding_backfill._flush` UPDATEs in place. Add a per-DB generation counter bumped by `_flush`. [550:#97]
819. **Make vector-lane-off loud** — ✅ `core.py` `_vector_cache_enabled` + `_VECTOR_LANE_OFF_WARNED`: `NOUGEN_VECTOR_CACHE=0` disables semantic lane with a once-per-process warning.
820. **Raise the file-descriptor ceiling at boot** — ✅ `src/nougen_shards/fd_budget.py` `ensure_fd_headroom` raises soft `RLIMIT_NOFILE`; `open_fd_count`; `core.py` logs the count on "unable to open"; `tests/test_fd_budget.py`.
821. **Gate model loads on free VRAM** — ✅ `src/nougen_shards/vram_gate.py` `check_vram` reads `nvidia-smi`, refuses to guess on failure, `NOUGEN_VRAM_GATE`/`NOUGEN_VRAM_MANUAL` overrides.
822. **Keep the embed model resident during backfill** — ✅ `embedding_backfill.py` `_keep_alive()` passes `keep_alive` on `embed`/`embed_many`; `tests/test_embed_keep_alive.py`.
823. **Batch embedding backfill writes** — ✅ `embedding_backfill.py` `backfill_db(batch=64)` uses `embed_many` and `_flush` executemany in one transaction.
824. **Record embedding model and dimension per shard** — ⬜ `_flush` writes only `embedding` (+`schema_version=1`); no model/dim column in `core.py`; mixing models silently corrupts cosine. Add `embed_model`, `embed_dim` columns in `init_db`.
825. **Embedding migration and re-embed job** — ⬜ depends on 824; add `embedding_backfill.py --reembed --from-model X` with resumable cursor.
826. **Reconcile ann_index.py with the "HNSW" label** — 🟡 `src/nougen_shards/ann_index.py` header states it is a numpy matmul, not HNSW (hnswlib unavailable on Windows); zero importers in `src`/`app.py`/`tools`. Wire it in or delete it.
827. **Evaluate a real ANN index behind the ann_index interface** — ⬜ `ann_index.query(query_embedding, top_n)` is the seam; benchmark faiss/usearch at 1M x 768 vs matmul cache in a new `tools/ann_bench.py`.
828. **Quantize the cached matrix (float16/int8)** — ⬜ `core.py` stores float32 (l.938, 1468); ~800MB RSS at 260k (comment l.1905) implies ~3GB at 1M; add opt-in `NOUGEN_VECTOR_DTYPE`.
829. **Embedding dimensionality experiment** — ⬜ measure recall@k for 768 vs truncated 256/384 (Matryoshka) with `tools/recall_bench.py` golden set.
830. **Lazy embedding for bulk imports** — 🟡 `EMBED_AT_CAPTURE_MISSES` counter (HARDENING §2) plus manual `embedding_backfill`; no automatic background queue drains misses. Land in `embedding_backfill.py` as a scheduled mode.
831. **Recall latency percentiles** — 🟡 `tools/recall_bench.py` reports p50/p95 and gates on `NOUGEN_BENCH_P95_S`; no p90/p99/max. Extend `_pct` output. [551:#42]
832. **Run recall_bench in CI on a synthetic grid** — ⬜ `.github/workflows/ci.yml` has no bench step and recall_bench needs the live grid; add a fixture-grid mode.
833. **Cold vs warm recall measurement** — 🟡 comments in `core.py` cite cold ~38s vs warm ~2s (l.1983) and 15.7s cold build; not reproducible from a tool. Add `--cold` to `tools/recall_bench.py`. [551:#43] [551:#14]
834. **Angle-sweep bench stays CPU-only** — ✅ `tools/bench_angle_sweep.py` single-shot vs bounded sweep on synthetic fixture, no network.
835. **Synthetic grid generator** — ⬜ nothing builds N synthetic shards across 9 DBs; add `tools/synth_grid.py --shards N --dim 768` as prerequisite for 836-841.
836. **100K shard benchmark** — ⬜ uses 835; publish capture, FTS, vector, federated p50/p95/p99 in `bench/results/100k.json`.
837. **250K benchmark (current live scale ~260k)** — ⬜ baseline matching live grid size per `core.py` comment; same harness.
838. **500K benchmark** — ⬜ same harness; watch 2GB-per-DB cap (9 x 2GB = 18GB ceiling).
839. **1M benchmark** — ⬜ same harness; verify vector cache RSS and cold build within recall deadline.
840. **5M synthetic stress** — ⬜ expected to break the 9x2GB grid; its purpose is to find the failure mode and document it.
841. **Growth curves: storage, FTS, vector, graph** — ⬜ plot bytes per shard for `shards`, `shards_fts` (trigram, large), embedding BLOB and graph tables from 835 runs.
842. **Measure trigram FTS index amplification** — ⬜ `core.py` l.540 `tokenize='trigram'`; trigram FTS is ~3x content size; compare `unicode61`/porter for size and HARDENING §5 recall.
843. **Capture throughput benchmark** — ⬜ time `capture` with embed-at-ingest on vs off; target in the performance contract.
844. **Amend throughput benchmark** — ⬜ `shard_amend` path; include vector-cache refresh cost.
845. **Concurrent capture race test** — ⬜ N threads capturing same content must converge to one row via `file_hash UNIQUE`. [550:#84] [550:#8]
846. **Concurrent recall load test** — 🟡 herd behaviour covered by `tests/test_vector_cache_herd.py`; no throughput test of mixed recall at N clients. [550:#86]
847. **Mixed read/write workload bench** — ⬜ captures during recall to exercise WAL + signature refresh together.
848. **Memory, CPU, disk telemetry per recall** — ⬜ add RSS and open-fd (`fd_budget.open_fd_count`) to recall trace output.
849. **Federated latency per lane** — 🟡 `federation.py` records per-lane timing and `lane_failures`; not aggregated into percentiles. [550:#93]
850. **Deadline-bound slow lane cancellation** — 🟡 federation lanes time out and report `complete=false`; threads are not cancelled, only abandoned. Track in `federation.py`. [550:#94]
851. **Capture ack before secondary indexes** — ⬜ embed happens inline at capture (HARDENING §2); design an ack-then-index path with a durable pending-index table so §2 stays provable.
852. **Index repair command** — 🟡 `core.py` l.348 runs `PRAGMA quick_check(1)` for quarantine; no FTS `rebuild`/integrity command. Add `cli.py index repair`. [550:#6]
853. **Resumable index backfill** — 🟡 `embedding_backfill` processes `embedding IS NULL` rows so reruns resume implicitly; no checkpoint file or progress receipt. [550:#97]
854. **Deterministic rebuild check** — ⬜ rebuild the vector cache twice and assert identical ids/order hash. [551:#13] [550:#98]
855. **Hot-shard cache** — ⬜ `access_count`/`utility_score` columns exist in `shards`; no in-process cache uses them.
856. **Query result cache with signature invalidation** — ⬜ reuse `_db_write_signature` as key; negative results must carry coverage (HARDENING §4). [550:#66] [550:#67]
857. **Negative cache must never mask degraded lanes** — ⬜ any negative cache entry must store lane_health; test in `tests/`. [550:#2] [550:#95]
858. **Cache poisoning defence** — ⬜ cache keys must include vault/tenant and sensitivity. [550:#68]
859. **Entity and graph caches** — ⬜ `graph.py` recomputes relations per call; measure before caching.
860. **Access-frequency metrics** — 🟡 `access_count` + `history.log_events(... "ACCESSED")`; no popularity report.
861. **Working-set estimation** — ⬜ from `ACCESSED` events in `history.db`, report the set touched in 30 days.
862. **Hot/warm/cold tier definitions** — ⬜ write `docs/tiers.md`: hot (cache), warm (grid), cold (archive DB) with promotion rules.
863. **Cold archive store** — ⬜ move low-utility, unaccessed shards to an archive DB outside the 9-grid; still searchable on demand.
864. **Promotion and demotion policy** — ⬜ depends on 860-863; must preserve `id@dbN` compound ids used by `griot_v2.py`.
865. **Namespace/time partitioning study** — ⬜ hash routing gives no locality; evaluate time or domain partitions vs the O(1) dedupe `get_routing_index` provides.
866. **Grid expansion beyond nine DBs** — ⬜ changing `MAX_DB_COUNT` remaps every hash; design consistent hashing or a routing table before 1M.
867. **Adaptive retrieval budgets** — 🟡 `reconstruction.py` `SweepConfig` bounds angle sweeps; no budget tied to latency deadline.
868. **Early termination on confident hits** — ⬜ stop scanning remaining DBs once top-k is certain; must not break DB-order determinism in `_run_db_scans`.
869. **Streaming/progressive results** — ⬜ MCP/`app.py` returns full lists; add progressive lane results for federation.
870. **Compact result serialization** — ⬜ trim content in recall payloads; measure tokens per result in MCP tools.
871. **Token-efficient metadata** — ⬜ define a minimal shard header (id, title, ts, score) for list views.
872. **Read-path mmap experiment** — ⬜ `PRAGMA mmap_size` never set; benchmark on the 1.2GB DBs.
873. **Page-size experiment** — ⬜ default 4096 assumed; test 8192/16384 on the BLOB-heavy `shards` table.
874. **Split embedding BLOBs out of `shards`** — ⬜ `core.py` l.1905 notes vector reads pull full rows; a `shard_embeddings` side table cuts cold build IO.
875. **Covering/partial indexes for hot filters** — ⬜ e.g. partial index on `embedding IS NOT NULL` for `_prune_deleted`'s id scan.
876. **Redundant index detection** — ⬜ script using `sqlite_stat1` after 809.
877. **Write coalescing for captures** — ⬜ group bursts in one transaction; measure against WAL.
878. **Background graph updates** — ⬜ `graph.py` relation writes inline; move behind the pending-index queue from 851.
879. **Priority indexing** — ⬜ recent/high-utility shards embed first in backfill ordering.
880. **Database snapshots** — ⬜ use `sqlite3.Connection.backup` for consistent per-DB snapshots under WAL.
881. **Incremental backups** — ⬜ ship changed DBs by signature from 817; tie to `sync_push/pull/hashes` in `app.py`.
882. **Restore benchmark** — ⬜ time full 9-DB restore; the 2026-09-06 restore note in `core.py` l.33 is the only record.
883. **Corruption recovery drill** — 🟡 quarantine on `quick_check` failure exists (`core.py` l.348); no timed recovery drill. [550:#88] [550:#90]
884. **Disk-full behaviour** — ⬜ test capture under ENOSPC returns an error, not silent loss. [550:#87]
885. **FD exhaustion drill** — 🟡 `fd_budget` raises limits and logs; no test forces the ceiling and checks /health turns non-200. [550:#95]
886. **Replication benchmark** — ⬜ no replication exists in `src/` (briefing §18); measure after zone-level replication lands. [550:#12]
887. **Slow-gateway war game** — ⬜ inject latency into one node's lane and assert federated p95 stays within budget. [550:#44] [550:#93]
888. **Recall latency trace IDs** — ⬜ attach a trace id to each bench sample so outliers are explainable. [551:#45]
889. **Performance regression gate** — ⬜ fail CI when synthetic-grid p95 regresses >20% against stored baseline.
890. **Publish the bench fixture golden set** — 🟡 `recall_bench._golden` has a built-in set and `NOUGEN_BENCH_GOLDEN`; make a public, owner-free fixture in `tests/fixtures/`.
891. **Tenant-scaled benchmark** — ⬜ `tenants.py` exists; measure per-tenant isolation cost at scale.
892. **Semantic query cache** — ⬜ cache by query embedding similarity; only after 856 is proven safe.
893. **Automatic index recommendations** — ⬜ from query logs + `EXPLAIN` output.
894. **Query workload analysis** — ⬜ classify recall queries (FTS vs vector vs temporal) from history events.
895. **Billion-edge synthetic graph test** — ⬜ `graph.py`/`vector_graph.py` at scale; far horizon.
896. **Multi-node sharded grid** — ⬜ grids per node with routing; depends on replication.
897. **Million-shard war game** — ⬜ run [550] families 84-99 against the 1M synthetic grid.
898. **Disaster recovery targets (RPO/RTO)** — ⬜ define in `docs/performance-contract.md` from 880-883.
899. **Publish the NouGen Million Shard Performance Contract** — ⬜ `docs/performance-contract.md`: p50/p95/p99, RSS, capture rate, restore time, each backed by a bench receipt.
900. **Re-verify the contract every release** — ⬜ release checklist runs 836-839 and attaches receipts. [550:#100]

### Zone 9 verdict
- Exists today: 9-DB md5-routed grid with 2GB per-DB cap (`core.py` l.33-49, `get_write_index`), WAL/DELETE auto-selection (`get_vault_journal_mode`), parallel DB scans (`_run_db_scans`), per-DB vector matrix cache with delete pruning and herd protection (tests `test_vector_cache_delete.py`, `test_vector_cache_herd.py`), fd headroom (`fd_budget.py`), VRAM gate, keep-alive backfill, and a p50/p95 `tools/recall_bench.py`.
- Load-bearing gap: there is no synthetic-grid generator or scale benchmark, so every "million shard" claim is unmeasured; plus no pragma, checkpoint, vacuum or ANALYZE policy beyond journal mode.
- First PR: "perf: synthetic grid + scale bench (100K/250K) with p50/p95/p99" — new `tools/synth_grid.py`, extend `tools/recall_bench.py` (p90/p99, `--cold`, fixture mode), `tests/test_recall_bench_fixture.py`.
- Real defects: `_db_write_signature` uses whole-second mtime plus size (stale-cache window); in-place backfill UPDATEs are knowingly not invalidated; `get_write_index` silently overfills when all DBs are full.
- Contradictions: `ann_index.py` is a numpy matmul, not HNSW, and has no importers; `is_db_full` and docs say 1GB while `MAX_DB_SIZE` is 2GB; no embedding model/version is stored, so "embedding versioning" has no base to build on.

## Zone 10: Autonomous Memory Organism (steps 901-1000)

901. **Fix the app.py destiny MCP tools that cannot run** — ⬜ defect: `app.py` `create_destiny` passes `required=/forbidden=/variance=` and `update_destiny` passes `status=`; `destiny.create_destiny`/`update_status(destiny_id, to_status)` accept neither, so both raise TypeError. Add a test in `tests/test_app_destiny_tools.py` [550:#32]
902. **Collapse the two destiny MCP surfaces into one** — 🟡 `src/nougen_shards/mcp.py` destiny tools are tested (`tests/test_mcp_destiny_nougenmsg.py`); `app.py` re-implements them untested and its docstring lists nonexistent statuses "fumbled, abandoned". Make `app.py` delegate to `mcp.py` [550:#32] [551:#995]
903. **Refuse supersession of a missing or terminal destiny** — ⬜ defect: `destiny.create_destiny` ignores the error dict `_transition` returns, still inserts `supersedes=<id>` and runs `UPDATE ... superseded_by`. Check the result and roll back in `destiny.py` [550:#23]
904. **Make dream decay idempotent per cycle** — ⬜ `dream.wake` calls `core.decay_utility_scores()` (0.95x, `core.py:3002`) with no run key; every invocation compounds decay. Gate with `hardcade_cron_out.run_key` plus a ledger row [550:#8] [550:#99]
905. **Stop exporting sensitive shards into the SFT dataset** — ⬜ defect: `dream.fetch_high_utility_shards` selects title/content with no `sensitivity` filter and `parametric_burn_in` writes them to `dream_sft.jsonl`. Filter by `sensitivity` in `dream.py` and add a privacy test [550:#75] [551:#753]
906. **Report decay honestly in the wake receipt** — 🟡 `dream.wake` returns a hardcoded "Applied 0.95x utility decay to all shards" string even when `decay_utility_scores` skipped a DB on error. Return per-DB decay outcomes from `core.decay_utility_scores` [550:#100]
907. **Keep dream consolidation fail-closed** — ✅ `dream.consolidate_episodic_data` marks `consolidated = 1` only when `shard_rules` is non-empty, rolls back on `sqlite3.Error`, and returns `complete: not errors`; covered by `tests/test_dream_transactions.py` [550:#100]
908. **Make the orchestrator actually run the dream** — ⬜ contradiction: `tools/nougen_24_7_orchestrator.py` step "[4/6] Dream & Consolidation" only checks whether `dream_sft.jsonl` exists; it never calls `dream.wake`. Invoke it via a CronOut schedule or rename the step [550:#100]
909. **Make the orchestrator's evolution step real or delete it** — ⬜ step "[5/6] OpenSkill Evolution" checks one hardcoded `SKILL.md` path and logs "(v3.0.0)"; no evolution runs. Replace with `destiny.evolve_report` consumption in `tools/nougen_24_7_orchestrator.py` [550:#100]
910. **Remove unattended auto-claim from the 60s loop** — 🟡 orchestrator runs `nougen_relay.cli schedule --take` every `NOUGEN_CYCLE_INTERVAL_S` (default 60) with no lease or receipt; output is only logged. Require a governed CronOut lease before taking legs [550:#25] [550:#26]
911. **Make the orchestrator portable** — ⬜ `PYTHON_EXE` is hardcoded to `.venv/Scripts/python.exe` under `~/Outpost/NouGen`, and the watchdog spawns `cmd.exe`; it cannot run on a non-Windows node. Resolve via `sys.executable` and env in `tools/nougen_24_7_orchestrator.py` [550:#78]
912. **Give the orchestrator one numbered step list and an exit receipt** — 🟡 labels mix "[1/7]", "[3/7]", "[4/6]", two "4." sections and a duplicated warning log line; cycles emit logs only. Emit a JSON cycle receipt per run [550:#100]
913. **Wire CronOut to a real backend** — 🟡 `hardcade_cron_out.py` defines `CronOutSchedule`, `run_key`, `ScheduleState`, `LocalLoopAdapter`; nothing outside `tests/test_hardcade_cron_out.py` imports it. Drive dream/audit jobs through it [551:#979]
914. **Persist CronOut schedule state** — ⬜ `ScheduleState` holds runs in memory; the only JSON use (`run_key`, line ~277) is hashing. A restart forgets idempotency. Add a sqlite store in `hardcade_cron_out.py` [550:#91]
915. **Wire the CronOut lease requirement** — 🟡 `Governance` declares `lease_required`; the module docstring defers CoachGovernor/TokenFuse enforcement "to the lane that owns it". Implement the lease check in `ScheduleState._check_governance` [550:#61] [550:#62]
916. **Adopt the Hardcade verifier as the maintenance evidence gate** — 🟡 `hardcade_verifier.evaluate_hardcade_evidence` enforces evidence tuples, no self-attestation, credential dedupe; only tests import it. Require it before any maintenance job reports PERFECT [550:#100] [551:#986]
917. **Keep destiny transitions append-only** — ✅ `destiny._transition` enforces `TRANSITIONS`, refuses edits to terminal states and writes every move to `destiny_events`; `tests/test_destiny_wake.py::test_destiny_crud` [551:#6]
918. **Keep Evolve read-only by construction** — ✅ `destiny.evolve_report` only SELECTs terminal events and returns `note: "read-only: Evolve proposes, the GM decides"` [551:#982]
919. **Gate destiny activation on readiness** — 🟡 `control_loop.destiny_readiness` blocks destinies lacking verification or an observed environment; `update_status` never calls it. Call it on dormant->active in `destiny.py` [551:#982]
920. **Stop labelling evolution as done** — 🟡 `evolution.py` docstring and `cli.cmd_evolve` state acquisition and verification are "simulated stubs"; `grounding_source` says "(simulated)". Keep the flag until real retrieval lands; add a test asserting `experimental: True` [550:#23]
921. **Make the evolution verifier more than a length check** — 🟡 `EvolutionEngine.build_virtual_task` asserts grounding is non-empty, >40 chars and shares a token; the fallback grounding string can pass. Fail when only the fallback was used in `evolution.py` [550:#100]
922. **Keep skill deployment path-safe** — ✅ `EvolutionEngine.evolve_skill` slugs the instruction, appends a sha256 digest and refuses paths outside `skills/`; `tests/test_evolution_security.py::test_skill_id_sanitization_blocks_traversal` [550:#71]
923. **Stop evolution swallowing substrate errors** — ⬜ `EvolutionEngine.acquire_knowledge` wraps both substrate queries in bare `except Exception: pass`; a dead DB looks like "no grounding". Record per-DB errors in `evolution.py` [550:#6] [551:#44]
924. **Delete the duplicate invariant writer** — ⬜ `tools/dream_deep.py:upsert_invariants` duplicates the `semantic_knowledge` upsert from `dream.consolidate_episodic_data`, always into `db_index=1`, without the type guards. Call a shared `dream.upsert_invariant` [551:#995]
925. **Record which shard produced each invariant** — ⬜ `semantic_knowledge` upsert stores subject/predicate/domain/updated_at only; conflicts add +0.1 confidence with no source. Add a `source_shard` link table in `core.init_db` [551:#9] [551:#10]
926. **Bound invariant confidence** — ⬜ `ON CONFLICT ... confidence_score + 0.1` in `dream.py` and `tools/dream_deep.py` grows without ceiling; replays inflate it. Clamp and count distinct sources [550:#15] [551:#40]
927. **Keep skill promotion from dream sandboxed** — ✅ `dream.synthesize_skills_from_invariants` registers candidates and calls `verify_candidate_sandbox` to reach PILOT; errors stay CANDIDATE; `tests/test_dream_evolution_bridge.py` [551:#986]
928. **Make the wishlist verifier identity rule executable** — 🟡 `wishlist.WishlistState.mark` requires evidence for LANDED/VERIFIED but never checks that the VERIFIED owner differs from the implementer (item 87 in the enum comment). Enforce it in `mark` [550:#23]
929. **Keep drift detection read-only and exit-coded** — ✅ `tools/drift_check.py:check` compares running vs canonical sha256 and reports MATCH/DRIFT/UNTRACKED/MISSING; exit 0/1/2 [551:#969] [551:#997]
930. **Schedule drift_check as a maintenance job** — ⬜ `tools/drift_check.py` runs only by hand; no cron, orchestrator step or receipt ledger calls it. Add a CronOut schedule and inbox announce [551:#997]
931. **Define one maintenance receipt schema** — ⬜ dream, evolve, drift, harden each return ad-hoc dicts or logs. Add `src/nougen_shards/maintenance.py` with a `MaintenanceReceipt` (job, run_key, node, commit, inputs hash, outcome, evidence) [550:#100] [551:#47]
932. **Persist a maintenance ledger** — ⬜ no table records maintenance runs; `destiny_events` covers destinies only. Add a `maintenance_runs` table beside `destinies.db` [551:#998]
933. **Take a backup before any mutating maintenance** — ⬜ `dream.wake` decays and consolidates in place; `tools/publish_vault_snapshot.py:backup_db` exists but is not called. Call it first [551:#24]
934. **Roll back on invariant failure** — ⬜ nothing compares pre/post shard counts or hashes around a dream cycle. Add pre/post invariants and restore from the step 933 backup in `maintenance.py` [551:#1] [551:#12]
935. **Add a dry-run mode to every maintenance job** — ⬜ `dream.wake`, `cli.cmd_dream` have no `--dry-run`. Add a flag that returns the planned mutations [551:#11]
936. **Require human approval for destructive jobs** — 🟡 `hardcade_cron_out.GovernanceRefused` exists; nothing marks decay or consolidation as destructive. Add a `destructive` flag to `Governance` and refuse without an approval ref [550:#100]
937. **Make autonomous_harden more than pylint** — 🟡 `autonomous_harden.py` runs pytest and pylint on 8 files and exits honestly; it attacks no assumption. Add war-game family runs to it [550:#100] [551:#50]
938. **Emit a harden receipt** — ⬜ `autonomous_harden.main` prints to stdout only. Write a JSON receipt (commit, node, failures) via `maintenance.py` [551:#47]
939. **Duplicate audit job** — ⬜ dedupe is at capture (`file_hash UNIQUE`); no job scans for near-duplicates across the 9 DBs. Add `audits/duplicates.py` [551:#33] [550:#8]
940. **Orphan shard audit** — ⬜ nothing checks `destiny_links` refs or `semantic_knowledge` rows against existing shards. Add `audits/orphans.py` [551:#8]
941. **Database integrity audit** — 🟡 `PRAGMA integrity_check` runs only in `tools/union_vaults.py` and deep-sweep tools. Add a scheduled per-DB integrity audit with receipts [551:#21] [550:#6]
942. **Index integrity audit** — ⬜ no job compares `shards_fts` row count with `shards`. Add an FTS/content parity check in `audits/index.py` [551:#17] [550:#97]
943. **Embedding coverage audit** — 🟡 `EMBED_AT_CAPTURE_MISSES` counts misses at capture; no audit reports shards with NULL `embedding`. Add to `audits/embeddings.py` [551:#16]
944. **Missing provenance audit** — ⬜ no job counts shards lacking machine provenance columns. Add to `audits/provenance.py` [551:#9]
945. **Stale fact audit** — ⬜ `semantic_knowledge.updated_at` is never compared to an age budget. Add to `audits/staleness.py` [551:#19]
946. **Contradiction audit** — ⬜ no job looks for `semantic_knowledge` rows with the same subject and conflicting predicates. Add to `audits/contradictions.py`, reusing zone 7 truth types [551:#57]
947. **Temporal gap audit** — ⬜ no job reports months without shards. Add to `audits/temporal.py` [551:#20]
948. **Zero-result audit** — ⬜ recalls returning empty are not logged for replay. Log them and replay in `audits/zero_results.py` [550:#1] [550:#3]
949. **Federation divergence audit** — ⬜ no job compares per-node counts/hashes. Add in `audits/federation.py` [551:#60] [551:#61] [550:#12]
950. **Schema drift audit** — ⬜ nothing compares each DB's schema to `core.init_db`. Add to `audits/schema.py` [551:#36]
951. **Node drift audit across the fleet** — 🟡 `tools/drift_check.py` covers one node's bus files. Aggregate results for blade, whoart and phoebus [551:#89] [551:#969]
952. **One audit runner with a registry** — ⬜ no dispatcher. Add `nougen audit run <name>` in `cli.py` over an audit registry [551:#1]
953. **Memory quality metrics** — ⬜ duplicate, orphan, provenance-completeness and contradiction rates are not computed. Derive them from audit receipts in `maintenance.py` [551:#31]
954. **Known-answer benchmark** — ⬜ no fixed question/answer set scores recall. Add `tests/fixtures/known_answers.json` and a scorer [551:#40] [551:#41]
955. **Historical question replay** — ⬜ no harness replays past recall queries against a new build. Add in `tools/replay_recall.py` [551:#35] [551:#47]
956. **Self-generated test questions** — ⬜ dream extracts invariants but never generates questions to check recall. Add a question generator from `semantic_knowledge` in `dream.py` [551:#41]
957. **Incident-to-wargame generator** — ⬜ incidents in `docs/evolution/*.md` are prose. Parse them into #550-shaped cases (preconditions, mutation, observation, receipt) [551:#988] [550:#100]
958. **Regression-to-fixture generator** — ⬜ failures in `control_loop.post_run_learning` return `failure_class` items that nothing persists. Write them as fixtures [551:#991] [551:#48]
959. **Keep post-run learning write-free and capped** — ✅ `control_loop.post_run_learning` writes nothing, caps items via `learning_max_items`, reads only verified runs by default; `tests/test_control_loop.py` [551:#987]
960. **Persist accepted learnings as shards** — ⬜ `post_run_learning` proposes `mark_useful`/`recipe_candidate`; no path applies approved items. Add an approval-then-capture step [551:#987]
961. **Recurring failure clustering** — ⬜ nothing groups `failure_class` items over runs. Add clustering in `maintenance.py` [551:#973]
962. **Anomaly detection on receipts** — ⬜ no baseline over run durations or counts. Add a z-score check over the step 932 ledger [551:#42]
963. **Repair proposals as destinies** — ⬜ audits do not create work. Turn audit failures into dormant destinies via `destiny.create_destiny` with `verification` set [551:#982]
964. **Destinies to relay legs** — ⬜ no code turns an active destiny into a relay leg; links are recorded manually with `destiny.link(kind="relay")`. Add a bridge [551:#983]
965. **Relay legs to branches and PRs** — ⬜ no automation. Add a bridge that opens a branch per accepted leg and links the PR [551:#984] [551:#985]
966. **Require executable proof before merge** — 🟡 CI runs `pytest` on 3.10-3.12 (`.github/workflows/ci.yml`); no link from a destiny's `verification` to a test. Require a test ref on fulfil [551:#986]
967. **Close destinies only with evidence** — 🟡 `update_status` accepts any `evidence` string, including none, for `fulfilled`. Require evidence and verify it with `hardcade_verifier` [550:#23]
968. **Fleet availability awareness for jobs** — 🟡 orchestrator `ping_node` does a TCP connect only and writes ONLINE/STANDBY to logs. Feed node health into job placement [551:#80]
969. **Work leases for distributed jobs** — ⬜ no lease table; CronOut defers leasing. Add leases with expiry in `maintenance.py` [550:#26] [550:#27]
970. **Node specialization registry** — ⬜ nothing assigns job types to blade, whoart or phoebus. Add a role map from local config [551:#97] [551:#98]
971. **Idle-only maintenance** — ⬜ `wake_daemon` reports wake settings; no job checks idleness before running. Gate heavy jobs on an idle probe [551:#989]
972. **Shadow index builds** — ⬜ indexes are rebuilt in place. Build into a shadow table and swap atomically [551:#97]
973. **Shadow retrieval comparison** — ⬜ no A/B of old vs new ranking. Run both, log divergence [551:#17]
974. **Canary migrations** — ⬜ migrations in `tools/migrate_*.py` apply directly. Apply to one DB first with invariants [551:#11] [551:#12]
975. **Signed migration receipts** — ⬜ migrations emit no receipt. Add sha256 of before/after schema and data counts [551:#788]
976. **Adaptive retrieval depth** — ⬜ recall limits are static. Tune from the step 954 benchmark, recorded in the ledger [551:#989]
977. **Census jobs for the repo** — ⬜ no TODO/FIXME, untested-path or stale-branch census. Add `tools/census.py` [551:#951] [551:#957] [551:#960]
978. **Dedupe and rank elevation candidates** — ⬜ no ranking by evidence, blast radius, reversibility. Add in `tools/census.py` [551:#972] [551:#974]
979. **Weekly elevation delta** — ⬜ no report compares censuses week to week. Add to `tools/census.py` [551:#998]
980. **Fleet destiny progress report** — 🟡 `destiny.evolve_report` returns status counts and terminal events; no per-node or trend view. Extend it [551:#999]
981. **Self-generated architecture map** — ⬜ no dependency map is generated from imports. Extend `tools/audit_imports.py` to emit a graph [551:#970]
982. **Canonical Python memory API** — ⬜ callers import `core`, `shards` and `dream` internals directly. Publish one facade module with a version [551:#49]
983. **Canonical HTTP memory API** — 🟡 `app.py` exposes many endpoints and MCP tools with no version prefix. Add `/v1` and a contract test [551:#32]
984. **Canonical MCP memory API** — 🟡 two MCP tool sets (`mcp.py`, `app.py` `node_mcp`) drift (step 902). Generate one from a shared registry [550:#33]
985. **Cross-repo contract tests** — ⬜ NouGenMsg and Shards bus copies diverge (briefing). Add a contract suite run against both [551:#92] [551:#995]
986. **Integration tests for each organism organ** — 🟡 unit tests exist (`test_dream_*`, `test_destiny_wake.py`, `test_control_loop.py`, `test_hardcade_cron_out.py`); none chains audit to destiny to relay. Add an end-to-end test [551:#50]
987. **Delete duplicate TS dream/evolution ports or test them** — 🟡 `ts/src/nougen_shards/dream.ts` and `evolution.ts` mirror Python with no parity test. Add parity or remove [551:#995]
988. **Mutation and evolution ledgers** — ⬜ skill writes by `evolve_skill` capture a shard but record no before/after. Add ledger rows [551:#998]
989. **Autonomous documentation updates** — ⬜ `docs/evolution/*.md` are hand-written. Generate entries from the ledger [551:#992]
990. **Historical replay against new Shards versions** — ⬜ no harness. Add in `tools/replay_recall.py` with pinned fixtures [551:#47] [550:#99]
991. **Deterministic fleet simulation** — ⬜ no simulated three-node grid. Add a temp-dir fleet harness [551:#99] [550:#12]
992. **Digital twin of memory topology** — ⬜ no topology manifest. Build from audit receipts [551:#88]
993. **Canary fleet deployment** — ⬜ deploys are per-node by hand. Roll one node first with drift_check as gate [551:#91]
994. **Automatic regression rollback** — ⬜ no rollback on failed canary. Add to deploy tooling [551:#93]
995. **Detect repository splits and Voltron merges** — ⬜ no job. Add to census [551:#993] [551:#994]
996. **Detect stale deployments vs source** — 🟡 `tools/drift_check.py` covers bus files. Extend to the Space and all nodes [551:#997]
997. **Answer "which machines have this shard"** — ⬜ no per-shard possession query. Add from step 949 receipts [551:#56]
998. **Absence claims only after proven coverage** — 🟡 zone 7 notes `status_semantics.ContextReceipt.absence_conclusions_permitted`; maintenance jobs ignore it. Require it [551:#38] [550:#3]
999. **Trace how a memory changed later outcomes** — ⬜ `destiny_links` link shards to goals; nothing traces effects forward. Add a lineage query [551:#10]
1000. **Regenerate this atlas from live evidence** — ⬜ this atlas is hand-built. Generate it from census and audit receipts [551:#1000]

### Zone 10 verdict
- Exists today: an append-only destiny store (`destiny.py`), read-only `evolve_report`, fail-closed dream consolidation (`dream.consolidate_episodic_data`), a CronOut semantic layer (`hardcade_cron_out.py`), a Hardcade evidence verifier, read-only `tools/drift_check.py`, and write-free `control_loop.post_run_learning`, each with its own tests.
- Load-bearing gap: nothing connects these parts. CronOut, the Hardcade verifier and control_loop are imported only by tests, and no maintenance receipt, ledger, backup or rollback exists. Autonomy today is a 60-second Windows loop that mostly logs.
- Real defects: the `app.py` destiny MCP tools `create_destiny` and `update_destiny` raise TypeError because their kwargs do not match; `create_destiny(supersedes=)` ignores a failed transition; `dream.wake` decays scores on every call and exports sensitive shards to `dream_sft.jsonl`.
- First PR: "fix(destiny): app.py MCP tools match destiny.py; refuse bad supersedes". Files: `app.py`, `src/nougen_shards/destiny.py`, new `tests/test_app_destiny_tools.py`.
- Contradiction with the draft plan: the plan describes Dream, Evolve and Harden running as live autonomous organs. The code says otherwise. The orchestrator's Dream and Evolution steps only check that files exist, `evolution.py` calls itself "simulated stubs", and `autonomous_harden.py` only runs pytest and pylint.

## Regeneration

This document is regenerated, not hand-edited. Each run re-grounds every step against the current `main`. A ✅ must keep citing a mechanism (a repo-relative file plus a function or line); a step whose cited mechanism has disappeared reverts to ⬜. New defects found during a run become new steps rather than silent edits to old ones. The ✅/🟡/⬜ counts in the Zone index are recomputed from the step lines on every run.

## Provenance

Generated 2026-09-24 from Who-Visions/NouGenShards `main @ ae40d10`. Seeded from a ten-zone draft plan, then grounded zone by zone by one author and one adversarial verifier per zone, and assembled and critiqued afterwards. The coordinating session was a Claude Code cloud session.
