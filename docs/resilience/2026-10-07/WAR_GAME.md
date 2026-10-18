# NouGenShards resilience war game and implementation pack

Prepared 2026-10-07. Scope: the supplied Live NouGen Status transcript, the prior Google compiler synthesis, and the locally built EquivalenceCompiler slice.

## 1. Executive engineering decision

Build an evidence-driven transformation service around NouGenShards, with a durable control plane and replaceable execution adapters. Treat each model suggestion, provider substitution, refactor, embedding change, compiler projection, and promotion as a proposal that must preserve a declared contract.

The first production milestone is reliable ownership, durable effects, bounded execution, and reproducible receipts. More agent lanes amplify failure unless those controls are already present. A second milestone adds independent verification and sealed evaluation. Automatic promotion is the last milestone.

This package contains an attack plan and executable reference primitives. Passing its local tests does not certify the existing fleet, a distributed database, a cloud provider, a sandbox, or a production deployment. Every claim below is labeled as observed, implemented locally, proposed, or still requiring live evidence.

Deliverables:

- `resilience_core.py`: durable effect intent journal, ownership fencing, shared budget accounting, provider filtering, and a promotion decision function.
- `test_resilience_core.py`: repeatable attacks against those primitives, including concurrency and an abrupt child-process exit.
- `WAR_GAME.md`: threat model, all 28 verification requirements, operational scenarios, code integrations, deployment stages, and incident runbooks.
- Existing repo fix: independent frozen inputs for the two sides of differential execution, with a regression test.

## 2. Verified starting state and a real counterexample

Observed local implementation: `NouGen/src/nougen_shards/equivalence_compiler.py` runs reference and candidate callables over a finite JSON workload. It creates hashed receipts, tracks declared observations, and refuses automatic promotion. Prior checkpoint: shard 30205 in database 8. Prior master design: shard 30200 in database 6.

Observed defect during this war game: reference and candidate received the same mutable object. A reference that changed `input['value']` before candidate execution could manufacture agreement. The attack returned coverage 1.0 and zero counterexamples, even though the candidate was wrong on the original input.

Implemented fix: deserialize the original frozen JSON separately for candidate execution. The new test uses nested mutation, verifies the caller's input remains unchanged, and requires a counterexample with verdict REGRESSED.

```python
# Before: candidate sees reference-mutated state.
reference_result = _run_one(reference, case)
candidate_result = _run_one(candidate, case)

# Now: each side receives the same original value in a distinct object.
reference_result = _run_one(reference, json.loads(case_json))
candidate_result = _run_one(candidate, json.loads(case_json))
```

This patch fixes input contamination only. In-process callables still share interpreter globals, import state, files, network access, and process lifetime. The current harness is therefore a developer tool for trusted callables. It is not a production sandbox.

Other observed limits, requiring further implementation:

1. Callable fingerprints use bytecode and `repr` of constants/defaults/closures. Nested code representations can vary across processes; callable objects can hide configuration behind a shared class identity. Replace these fingerprints with source/build artifacts and dependency manifests for promotion.
2. Exception-type equality does not establish failure parity. The current harness correctly gives matching exceptions zero observation coverage, but needs explicit failure contracts and protected diagnostic artifacts.
3. Finite workload agreement is INDETERMINATE, as intended. A bounded model theorem also does not prove production implementation refinement.
4. There is no runtime sandbox, per-case termination, shadow executor, signed evaluator service, or fleet promotion integration in that slice.
5. The prior scope claim failed to publish. Local claim files cannot establish cross-machine ownership. Inspect and repair the registry publication path before concurrent repository work.

## 3. Source grounding and corrections

The supplied research provides mechanisms, not a production certification for NouGen.

- Google's [OLMo MaxText case study](https://developers.googleblog.com/reproducing-olmo-3-7b-pre-training-in-maxtext-case-study-of-large-scale-training-on-tpus/) motivates independent evaluation, data identity checks, checkpoint state continuity, and hardware-scoped performance validation. A better training metric can be caused by repeated examples.
- Google's [Antigravity local-model support](https://developers.googleblog.com/introducing-support-for-local-ai-models-in-the-antigravity-sdk/) provides an adapter route for local and compatible servers. API compatibility does not establish equivalent tools, privacy, or behavior.
- [Alive2's maintained README](https://github.com/AliveToolkit/alive2/blob/master/README.md) describes LLVM translation validation and states a limitation for inter-procedural transformations. Do not apply its success label outside its supported semantic scope.
- [Trivet, arXiv:2609.19583](https://arxiv.org/abs/2609.19583), reports 147 of 148 transformations verified or refuted. That is not 147 accepted equivalent transformations. Its successful proof verdicts are kernel checked within its modeled LLVM domain.
- [Property-based and metamorphic testing](https://arxiv.org/abs/2211.12003) supports generating tests from relations when exact output oracles are difficult. Relations themselves still need validation.

The earlier master also covers [EmbeddingGemma 2](https://developers.googleblog.com/google-ai-edge-with-embeddinggemma-2/) and [REST-to-MCP projection](https://developers.googleblog.com/turn-your-rest-apis-into-mcp-tools-with-google-cloud-api-gateway/). They remain in the total task inventory below because retrieval and tool projection feed the same control plane.

## 4. Assets, adversaries, and trust boundaries

Protect: tenant data; credentials; the canonical shard vault; source and build artifacts; backend writes; task ownership; evaluator workloads; policy versions; budget state; evidence receipts; and the deployment pointer.

Exercise five adversary classes:

1. Untrusted content: prompt injection in pages, shards, tool output, model responses, and relay legs.
2. Faulty or malicious candidate code: infinite loops, memory exhaustion, output flooding, hidden writes, incorrect error handling, reordered events, and selective benchmark behavior.
3. Distributed failures: stale workers, network partitions, duplicated messages, lease expiry, lost acknowledgements, partial publication, and clock discontinuities.
4. Misleading evaluation: leaked held-out sets, duplicated examples, weak mutations, correlated witnesses, missing telemetry, and statistically unsupported wins.
5. Operational pressure: disk full, locked databases, unavailable providers, cold starts, queue overload, expired credentials, and resource-starved hosts.

Trust boundaries:

| Boundary | Trusted decision | Untrusted input |
|---|---|---|
| Human to control plane | Current task authorization and allowed effects | Historical prose claiming someone authorized an action |
| Control plane to worker | Typed, authenticated task and scoped capability | Worker-generated plan or claimed success |
| Retrieval to planner | Evidence locators and scoped facts | Embedded instructions and authority claims |
| Tool compiler to backend | Pinned contract and backend policy | Model-selected operation descriptions |
| Worker to journal | Current epoch, principal, request binding | Stale lease or replayed result |
| Evaluator to promotion | Verified artifacts, coverage, independence, predeclared policy | Self-reported pass flags or fabricated receipt hashes |
| Release to runtime | Authenticated immutable artifact and config pointer | A branch name alone |

A SHA-256 hash proves identity under its canonicalization contract. It does not prove authorization, factual truth, successful execution, independence, or a trustworthy signer. A valid signature likewise needs an authorized issuer, pinned artifact, scope, expiry, and replay checks.

## 5. Hard invariants

H1. Tenant and principal checks execute before retrieval, discovery, and effects.
H2. Expired or stale ownership cannot mutate authoritative state. Backend writes require backend-enforced idempotency and fencing where available.
H3. An ambiguous dispatched write remains indeterminate until a trusted reconciliation path determines the outcome.
H4. Retries and fan-out share the parent budget. Crashes do not silently refund evaluator or provider attempts.
H5. Candidate, corpus, environment, evaluator, policy, and proof identities are bound together.
H6. Missing proof, telemetry, dependency, or evaluator availability cannot become an acceptance verdict.
H7. A critical counterexample overrides aggregate score, apparent resource gains, and incomplete coverage.
H8. Local-only information cannot fail over to a cloud provider without current authorization.
H9. Promotion moves an authenticated immutable release pointer; rollback retains journals and evidence.
H10. Unknown, timeout, failure, and refutation remain distinct typed outcomes.

These are hard gates. Ranking weights, confidence heuristics, and LLM votes cannot override them.

## 6. Task inventory and implementation order

| Task family | Smallest production contribution | Exit evidence |
|---|---|---|
| Durable control plane | One authoritative task store, effect journal, outbox, shared budget | Restart, race, stale-owner, and split-publication tests |
| QueryCompiler | Typed intent with exact identity/scope/time constraints | Cross-tenant and exact-entity negative cases |
| RetrievalCompiler | Versioned shadow index with frozen preprocessing and model identity | Paired retrieval suite, leakage checks, rollback |
| ToolCompiler | Contract intermediate representation and deterministic REST/MCP mapping | Auth, quota, schema, response, and effect parity |
| PermissionCompiler | One policy decision bound to operation/input/policy version | Revocation and stale-decision rejection |
| ContextCompiler | Evidence-preserving selection with source locators | Contradiction retention and omission tests |
| ProviderCompiler | Capability/privacy/budget filters before routing | Offline, malformed output, and fallback tests |
| Runtime | Isolated workers with resource limits and durable checkpoints | Abrupt death, resume, output cap, termination |
| EquivalenceCompiler | Typed observations and independent witness adapters | Counterexamples, mutation adequacy, bounded claims |
| AuditCompiler | Authenticated receipts and independent replay | Forgery, key rotation, mismatch, and replay rejection |
| NouGenCode loop | Candidate generation separated from evaluation and promotion | Sealed query budget, explicit human/policy release gate |
| Fleet delivery | Outbox publication and consumer dedupe | Duplicate delivery and partial publication recovery |

Order: durable control plane -> isolation and evidence -> adapters -> independent evaluation -> shadow rollout -> promotion. Do not put an autonomous promotion switch in front of unfinished evidence controls.

## 7. All 28 verification requirements mapped to work

| # | Requirement | Attack | Implementation and exit condition |
|---|---|---|---|
| 1 | Refinement | Candidate accepts an input forbidden by the reference contract | Declare preconditions, nondeterministic output sets, safety properties, and permitted deltas. Check refinement, not byte equality. |
| 2 | Proof ladder | Unit tests passed, theorem unavailable | Record evidence class and scope. Timeout/missing solver becomes UNKNOWN; no upgrade of evidence strength. |
| 3 | Differential execution | Reference contaminates candidate input | Separate frozen inputs and isolated state; compare typed outputs, state deltas, errors, and effects. |
| 4 | Trace bisimulation | Candidate reorders two externally visible events | Define allowed internal events and observable transitions. Match traces under that explicit relation; preserve visible ordering. |
| 5 | Property testing | Boundary input omitted from hand-written corpus | Use seeded generators, bounded domains, minimal counterexample shrinking, and replayable seeds. |
| 6 | Metamorphic testing | An invalid relation makes a broken transform appear sound | Validate relation preconditions; use domain-specific examples and contradictory negative controls. |
| 7 | Counterexample first | Aggregate quality masks one authorization failure | Stop acceptance on any critical counterexample, retain reproducer, continue only safe diagnostic work. |
| 8 | Mutation adequacy | Verifier never checks a critical observation | Inject meaningful mutants and require critical mutants to be killed. Report survivors and equivalent/excluded mutants separately. |
| 9 | Negative-space verification | Correct output accompanies an unauthorized write | Capture forbidden effects, secret exposure, extra network calls, and deleted state; assert their absence. |
| 10 | State machines | Duplicate message jumps directly from open to complete | Version transition tables; transact updates with expected state and epoch; reject illegal transitions. |
| 11 | Temporal logic | Eventually-success claim ignores infinite retry | Encode bounded liveness separately from safety; test stalls, starvation, cancellation, and deadline exhaustion. |
| 12 | Translation validation | LLVM proof accepted for unsupported optimization scope | Pin toolchain and lowering; bind source/target IR and assumptions; unsupported scope is unknown. |
| 13 | Kernel checks | LLM proof includes unsupported assumptions | Check proof with the pinned kernel and trusted environment; restrict axioms and imports, not just text tokens. |
| 14 | Orthogonal witness | Same implementation generates and judges its own answer | Use independent evaluator artifacts and data; record who produced each witness and what it covers. |
| 15 | Causal metric guards | Training loss improves through data repetition | Check unique example identities, data exposure, held-out behavior, and controlled paired workloads. |
| 16 | Reproducibility | Corpus changed after evaluation began | Freeze code, dependency lock, data, config, policy, evaluator, and environment manifests. Verify before resume. |
| 17 | Replay equivalence | Cursor restored without RNG or pending writes | Restore cursor, RNG, ordering, optimizer/worker state where relevant, journal, and policy versions. Compare interrupted and uninterrupted traces. |
| 18 | Sequential verification | Repeated peeking eventually produces a lucky winner | Use one immutable evaluator epoch and declared query/alpha budgets; no hidden resets or reused held-out feedback. |
| 19 | Pareto optimization | Latency falls while memory exceeds capacity | Require predeclared nonregression bounds for every critical resource and an established gain in at least one objective. |
| 20 | Hardware awareness | Different hardware makes a code change look faster | Match substrate or declare stratified comparisons. A hardware-specific win remains scoped to that hardware. |
| 21 | Semantic delta budget | Many small tolerable changes accumulate into drift | Store deltas against the original baseline as well as the parent; enforce per-invariant cumulative bounds. |
| 22 | Equivalence coverage | High line coverage ignores auth or concurrency | Weight semantic obligations and demand required critical witnesses. Missing obligations cannot be hidden by arithmetic. |
| 23 | Proof diversity | Five model votes count as five independent proofs | Model votes are not proofs. Independence groups derive from verified lineage and methods, not caller labels. |
| 24 | Shadow execution | Candidate writes during supposedly passive comparison | Shadow receives read-only credentials and simulated effects. Verify zero external writes and isolate secrets. |
| 25 | Certificates | Receipt hash changed with its verdict | Verify signature, content hash, artifact availability, bindings, issuer authority, and freshness before consumption. |
| 26 | Compiler orchestration | Early success skips required checks | Explicit required-stage graph with fail-closed incomplete state. Early rejection is allowed; early acceptance is not. |
| 27 | Transformation loop | Candidate learns from sealed evaluator feedback | Separate generation/tuning/held-out stores and principals; share immutable per-epoch evaluation accounting. |
| 28 | Promotion law | Evidence passes but rollback cannot restore state | Stage a reversible artifact pointer, validate rollback and state compatibility, then require current release authorization. |

## 8. Operational attack matrix

Every scenario needs a pinned starting snapshot, injected failure, expected observation, abort rule, and retained receipt. Run in disposable local databases or an authorized staging environment. The local reference tests cover a subset identified in section 17.

| ID | Injection | Required outcome | Evidence |
|---|---|---|---|
| C01 | Kill worker before intent commit | No backend request occurred | Journal and backend audit agree |
| C02 | Kill after PREPARED, before dispatch | Lease can transfer with epoch increment | Old worker rejected; one dispatch |
| C03 | Kill after durable DISPATCHED, before network send | Indeterminate; reconcile before retry | No timer-driven redispatch |
| C04 | Backend commits, response is lost | Backend idempotency returns committed receipt | One externally visible effect |
| C05 | Kill after backend receipt, before local complete | Reconciliation seals the prior effect | No duplicate write |
| C06 | Old worker resumes after takeover | Epoch rejected at journal and backend | Stale update audit event |
| C07 | Ten workers race on one effect | One prepared owner and one dispatch | Transaction/race trace |
| C08 | Reuse key with different payload or tenant | Conflict before backend call | Canonical request binding |
| C09 | Clock moves backward or forward | No duplicate effect; time anomaly surfaced | Server clock and epochs |
| C10 | Disk fills during journal/outbox write | No effect without committed intent | I/O failure and backend absence |
| C11 | SQLite busy/locked beyond deadline | Typed retryable storage error; no write attempt | Bounded timeout |
| C12 | Corrupt/restore stale database | Quarantine; validated restore and reconciliation | Backup manifest and restore drill |
| C13 | Shard succeeds, relay fails | Retain shard receipt; retry only outbox leg | Independent publication receipts |
| C14 | Outbox publisher dies after remote commit | Remote dedupe discovers existing publication | Same logical event ID |
| C15 | Replay message after acknowledgement | Consumer dedupe prevents repeated effect | Inbox identity and journal |
| C16 | Lease expires during effect | Do not reassign ambiguous operation automatically | Indeterminate backlog |
| P01 | Local runner down, cloud healthy | Local-only request remains blocked | Route rejection; zero cloud payload |
| P02 | Provider says tools supported but ignores schema | Capability probe fails; route quarantined | Real completion/tool fixture |
| P03 | 401, 429, 503, timeout bursts | Bounded eligible fallback; shared budget | Attempt log and circuit state |
| P04 | Malformed/truncated/oversized output | Typed failure, output cap, no partial acceptance | Output artifact digest |
| P05 | Model identity changes under a stable name | Probe/version drift blocks evaluation | Build/model hash mismatch |
| P06 | Parent spawns 100 children | Shared atomic attempt limit holds | Reservation ledger |
| R01 | Cross-tenant nearest neighbor is strongest | Hard scope filter removes it | Exact scope test |
| R02 | Stale and contradictory shard outranks source | Preserve conflict; abstain or escalate | Source/time/conflict locators |
| R03 | Shadow vector index uses wrong dimension/model | Reject incompatible index, keep baseline | Index manifest |
| R04 | Corpus swap during benchmark/restart | Fingerprint mismatch halts run | Frozen dataset manifest |
| T01 | REST rejects, MCP accepts same principal | Critical regression; disable tool projection | Paired auth results |
| T02 | Discovery lists sensitive operation | Critical descriptor leak | Tenant discovery fixture |
| T03 | REST and MCP each spend full quota | Shared quota blocks combined overuse | Backend quota ledger |
| T04 | Contract changes parameter semantics silently | Drift blocks adapter startup or exposure | Contract/compiler hash |
| E01 | Reference mutates candidate input | Independent input copies reveal mismatch | Added regression test |
| E02 | Both sides share faulty helper/global | Independent process/oracle exposes correlation | Separate build/dependency identities |
| E03 | Candidate loops or allocates without bound | Sandbox terminates within limits | Kernel job/container telemetry |
| E04 | Candidate produces correct output plus a write | Negative effect witness refutes | Filesystem/network/backend trace |
| E05 | Verifier receives swapped candidate hash | Indeterminate/reject; never promote | Receipt binding validation |
| E06 | Fake signature, untrusted issuer, expired key | No acceptance | Signature/key-authority checks |
| E07 | Critical mutant survives | Evaluator is inadequate; block promotion | Mutation report |
| E08 | Attractive aggregate conceals critical failure | REGRESSED overrides quality score | Critical invariant receipt |
| E09 | One witness repeated as multiple families | Independence requirement fails | Verified lineage graph |
| E10 | Missing solver, timeout, unsupported axiom | UNKNOWN/INDETERMINATE | Tool status and assumptions |
| E11 | Better point estimate but CI crosses zero | Resource improvement unestablished | Paired interval report |
| E12 | Evidence valid but from different hardware | Block or apply declared stratified policy | Environment binding |
| D01 | Canary fails halfway through rollout | Stop pointer advancement, rollback canary | Release/controller receipts |
| D02 | Rollback hits incompatible schema/state | Restore validated compatibility path or halt | Migration rehearsal |
| D03 | Metrics backend disappears | Treat required evidence as missing | Telemetry freshness gate |
| D04 | Signing key compromised | Revoke issuer, quarantine affected receipts | Trust-store version and audit |

## 9. Implementation: durable effects and fencing

The included Journal implements PREPARED -> DISPATCHED -> COMMITTED. DISPATCHED means the effect may have happened. It is written before the external request. That deliberately creates an indeterminate window if the worker dies before sending; conservatism is preferable to a duplicate financial, data, or infrastructure write.

```python
from resilience_core import Journal, digest, Indeterminate

journal = Journal("private-state/effects.db")
request = {"principal": principal_id, "tenant": tenant_id,
           "operation": operation_id, "contract": contract_hash,
           "policy": policy_hash, "input": canonical_input}
payload_hash = digest(request)
# retry_scope is a caller-generated stable business operation identity.
key = digest({"scope": retry_scope, "tenant": tenant_id, "request": payload_hash})
ticket = journal.prepare(key, payload_hash, authenticated_worker_id)

if ticket.replay_receipt is not None:
    return load_authorized_receipt(ticket.replay_receipt)

journal.dispatch(ticket)  # durable ambiguity BEFORE contacting backend
try:
    backend_reply = backend.apply(
        request, idempotency_key=key, fencing_epoch=ticket.epoch,
    )
except (TimeoutError, ConnectionError):
    raise Indeterminate("backend outcome requires reconciliation")

verified = validate_backend_receipt(backend_reply, request, key)
journal.complete(ticket, digest(verified))
return verified
```

`backend`, `load_authorized_receipt`, and `validate_backend_receipt` are application adapters, not provided functions. They must enforce the current policy and verify a canonical, authenticated backend result. Do not replace them with `return True` or trust a worker's success flag.

Backend obligations:

- Idempotency and business mutation must commit atomically in the backend's authoritative transaction where possible.
- A repeated key with a different request must fail. Tenant and principal belong in the binding.
- Fence obsolete epochs at the mutation point where supported. Client-side lease checks alone cannot stop a partitioned old worker from writing.
- Keep idempotency retention longer than the maximum supported retry/recovery window.
- If the backend cannot provide idempotency, status lookup, or a compensating operation, classify that operation as non-retryable and require manual reconciliation after ambiguity.
- Do not claim exactly-once effects across an arbitrary external service. The achievable guarantee depends on that service's transaction and idempotency contract.

Single-host SQLite reference: local disk, WAL, FULL synchronous mode, short BEGIN IMMEDIATE transactions, and bounded busy timeout. Do not share its file across machines over NFS/SMB. For a distributed control plane, use one service with authoritative transactions or a transactional database such as PostgreSQL; retain the same CAS predicates and expected epoch.

The reference does not implement a FAILED transition API or negative-outcome reconciliation. Add those only when the backend can positively prove no effect, or after a reviewed compensation. An absence in a weak or eventually consistent query is not that proof.

## 10. Implementation: outbox and partial publication

Persist publication intent in the same transaction that records the local milestone. Sending is a separate worker. Shard and relay are separate destinations with separate receipts; success in one must not suppress the other.

```sql
CREATE TABLE outbox (
  event_id TEXT NOT NULL,
  destination TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_locator TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PENDING','IN_FLIGHT','DELIVERED','INDETERMINATE')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  owner TEXT,
  epoch BIGINT NOT NULL DEFAULT 0,
  lease_until TEXT,
  remote_receipt TEXT,
  PRIMARY KEY(event_id,destination)
);
```

Publisher procedure:

1. Claim an eligible row with transactional expected-state/epoch conditions.
2. Reserve one parent-budget attempt. Do not hold a database transaction while making a network call.
3. Send a stable event ID and payload hash. Remote APIs must deduplicate or expose a lookup by that identity.
4. Validate the remote artifact and receipt. Then mark DELIVERED using the current epoch.
5. If the response is lost after a possible remote commit, query by event identity before resending.
6. Backoff with bounded jitter and an absolute deadline; terminal failures go to an actionable queue.

A Git relay leg exists for the fleet only after its commit is reachable from the canonical remote branch. Verify the remote blob and record identity. A local file or local claim is not a delivery receipt.

Never stage the entire working directory in a publication helper. Use exact paths in an isolated checkout and preserve unrelated changes. The current package does not invoke a fleet broadcast or create task ownership for other lanes.

## 11. Implementation: budgets, retries, and load shedding

```python
from resilience_core import BudgetExceeded

journal.budget(parent_request_id, limit_units=20)  # immutable within an epoch
reserved_now = journal.reserve_budget(parent_request_id, attempt_id, units=1)
if not reserved_now:
    # The same attempt already exists. Inspect its execution journal; this is
    # not permission to make another provider call.
    return replay_or_reconcile_attempt(attempt_id)
```

Unique attempt IDs represent actual attempts; duplicate transports reuse the same attempt. All descendants refer to the same authoritative parent budget. Count search, generation, evaluator queries, and retries according to a declared cost model. Keep evaluator query budget separate from statistical alpha spending; one is not a substitute for the other.

Retry only declared safe operations or the backend's idempotent retry contract. Use an absolute deadline as well as attempt count. Respect retry-after and provider limits. Circuit breakers use observed health and bounded probe traffic; a manifest listing is not a successful inference probe.

Admission controls: queue age, free RAM, disk reserve, active GPU jobs, provider capacity, and pending indeterminate effects. Load shedding returns a typed rejection before work starts. Do not launch additional lanes to compensate for an overloaded host.

## 12. Implementation: provider and privacy policy

```python
from resilience_core import Provider, choose_provider

routes = [
    Provider("private-local", True, frozenset({"json", "tools"}), 0, healthy=local_probe_ok),
    Provider("authorized-cloud", False, frozenset({"json", "tools"}), 1, healthy=cloud_probe_ok),
]
route = choose_provider(routes, local_only=task.private,
                        capabilities={"json", "tools"}, max_cost_units=task.budget)
```

The reference treats provider descriptors as trusted configuration. Production registration must verify model/version, region, data-retention policy, maximum context/output, actual tool support, and current health. Keep probe artifacts and expiry. Never accept a provider's own unverified claim of compatibility.

For hybrid planning, compile a minimal approved payload schema. Filenames, paths, task summaries, and metadata can themselves be sensitive. Redaction requires policy, not the assumption that only source code is private.

```python
def approved_planner_payload(task, policy):
    fields = policy.allowed_planner_fields(task.principal, task.tenant)
    payload = task.project(fields)
    policy.assert_no_local_only_fields(payload)
    return payload
```

Keep authorization at both request compilation and effect execution. An initially allowed plan can become invalid after revocation, changed operation scope, or policy drift. A route change cannot alter task permissions.

## 13. Implementation: isolation and observability

Production candidate execution requires an external isolation adapter. A Python subprocess alone is not a security boundary. On Windows use a restricted identity plus a Job Object to bound descendants and kill the entire tree; for stronger isolation use a suitable VM/container boundary. On Linux use a restricted container/VM with cgroup limits, filesystem policy, and explicit egress controls.

Worker contract:

```python
class IsolatedExecutor:
    def run(self, *, image_digest, artifact_digest, input_digest,
            wall_deadline, cpu_limit, memory_limit, output_limit,
            network_policy, filesystem_policy, effect_policy):
        """Return a typed result and immutable trace artifact locator.

        Required result states: SUCCESS, APPLICATION_ERROR, TIMEOUT,
        RESOURCE_LIMIT, SANDBOX_VIOLATION, INFRASTRUCTURE_ERROR.
        No state is silently converted to a successful empty output.
        """
        raise NotImplementedError("supply a platform-specific isolation adapter")
```

Use independently reset sandboxes for reference and candidate. Inputs come from immutable artifact storage. Capture output, exception contract, exit status, state diff, filesystem changes, external-call attempts, policy decisions, and trace order. Observation hooks must operate below candidate control where possible. If a required channel is absent, coverage is incomplete.

Bound JSON framing, stdout, stderr, trace size, artifact count, and decompression. Store hashes and approved locators in receipts. Raw secrets, private code, and user media do not belong in public logs or relay bodies.

Cancellation must terminate descendants and prevent new effects. A cancelled task with an already dispatched effect still needs reconciliation; cancellation is not proof that no effect occurred.

## 14. Implementation: evidence and promotion

Freeze one binding manifest before evaluation:

```python
bindings = {
    "reference": reference_build_hash,
    "candidate": candidate_build_hash,
    "workload": sealed_workload_hash,
    "environment": runtime_manifest_hash,
    "policy": promotion_policy_hash,
    "evaluator": evaluator_build_hash,
}
```

Each witness binds to this manifest and a retrievable artifact. Authenticate the producer and validate the artifact before the gate receives it. Independence group names in the reference code are placeholders for verified lineage; renaming the same evaluator does not make it independent.

```python
from resilience_core import promotion_gate

verdict = promotion_gate(
    bindings=bindings,
    witnesses=authenticated_witnesses,
    required_families={"formal", "heldout", "mutation", "effects", "replay"},
    min_groups=3,
    critical_violation=critical_counterexample_found,
    verifier=trust_store.verify_and_bind_witness,
    resource_bounds={"latency": (-0.14, -0.06), "memory": (-0.03, 0.0)},
    min_gain=0.01,
)
```

Resource bounds represent simultaneous, predeclared confidence intervals for relative candidate-minus-reference costs. The numeric example is illustrative, not measured NouGen performance. The reference gate consumes these intervals; it does not calculate statistical significance, correct repeated peeking, or prove the intervals were produced honestly.

Verdict precedence: verified critical failure/refutation -> REGRESSED; missing or invalid evidence -> INDETERMINATE; established behavioral envelope plus resource gain -> IMPROVED; established envelope without that gain -> EQUIVALENT. EQUIVALENT and IMPROVED are scoped to the accepted evidence domain. They are not deployment authorization.

Production gate additions:

- Authenticate the full gate request, including critical-violation status. A candidate must not supply `False` for itself.
- Derive required families from risk and transformation class; do not let the candidate omit inconvenient witnesses.
- Validate mutation adequacy, critical-obligation coverage, independence, confidence construction, sample size, epoch budget, freshness, and proof assumptions.
- Bind certificates to immutable code/build artifacts and dependency locks. Reject unavailable artifacts and mismatched hashes.
- Use a trusted time source, issuer revocation list, trust-store version, anti-replay nonce, and audience restrictions.
- Keep proof search and evaluation separate. Restrict Lean imports/axioms and compiler toolchain scope; textual rejection of `sorry` is only an additional check.
- Require a validated rollback artifact and schema/state compatibility before a release controller can act.

## 15. Implementation: retrieval, tool projection, and context controls

Retrieval shadow index manifest:

```python
index_manifest = {
    "corpus_hash": frozen_corpus_hash,
    "model_hash": embedding_model_hash,
    "preprocessor_hash": preprocessor_hash,
    "dimensions": validated_dimensions,
    "normalization": normalization_version,
    "distance_metric": distance_metric,
    "tenant_partition_policy": partition_policy_hash,
}
```

Filter principal/tenant/exact entity/time constraints before similarity ranking. Do not compare raw scores from incompatible models or dimensions. Calibrate by query class and modality. Contradictions remain explicit; staleness does not silently erase historical facts. Do not change the authoritative index while measuring the shadow candidate.

For REST-to-MCP, generate descriptors and adapters from a pinned contract intermediate representation. Runtime calls go to the existing backend authorization and quota path. Reject unsupported schemas explicitly. Authenticate sensitive discovery. A compiler must preserve error/status semantics and effect classification as well as parameter names.

Context compression must retain decisive sources, adverse evidence, conflict markers, exact IDs, and uncertainty. Run paired full-context versus compressed-context workloads; report omitted-evidence failures and scope leakage. Compression gains alone do not establish behavioral equivalence.

## 16. Incident runbooks

### Ambiguous external write

Freeze redispatch for that operation identity. Record DISPATCHED/indeterminate state. Query the authoritative backend using the stable key. Validate tenant, payload binding, and backend receipt. Reconcile COMMITTED only on positive evidence. If outcome remains unknown, keep it unresolved and notify the responsible operator; do not invent a successful or failed result to clear the queue.

### Stale or split-brain worker

Stop new dispatch from the stale epoch. Check the authoritative store and backend fencing. Preserve traces from both workers. Resolve pending effects by backend identity. Rotate the epoch and worker credentials where required. Never repair ownership by deleting the journal.

### Evaluator contamination

Invalidate the affected evaluator epoch and its dependent promotion decisions. Freeze automatic promotion. Preserve the exposed workload identities and query ledger. Rebuild a sealed set under a new epoch and re-evaluate candidates; do not silently reset counters under the old identity.

### Resource exhaustion

Reject new work before dispatch. Drain or cancel only safe prepared tasks. Preserve dispatched effects for reconciliation. Free resources through explicit retention/cleanup policies, not uncontrolled deletion of evidence or vaults. Reopen admission after a real health probe and reserve check.

### Receipt trust failure

Quarantine affected issuers/artifacts. Preserve original receipts. Verify trust-store scope and revocation time. Rebuild decisions from independently authenticated evidence. A newly signed copy of the same unsupported claim is not a repair.

### Rollback

Stop canary expansion, atomically restore the previous pinned release pointer, and verify operational SLOs. Reconcile in-flight effects across the old and new artifact versions. If schema/state compatibility is unproven, halt the rollout and use the rehearsed migration/restore procedure. Record the rollback as a new event rather than rewriting history.

## 17. How to run and what is actually tested

Verified local result on 2026-10-07: 21 reference attack tests passed; 23 NouGen differential/formal-prover tests passed; repository whitespace check passed. The matrix contains 46 operational scenarios; passing 44 local tests does not mean all 46 staging scenarios have been executed. Reference gate tests additionally ensure a verified refutation cannot be hidden by an earlier invalid witness, and an established resource regression cannot be hidden by an earlier uncertain metric.

From this package directory:

```powershell
C:\Python311\python.exe -m unittest -v test_resilience_core.py
```

From the NouGen repository:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_equivalence_compiler.py tests/test_formal_prover.py
```

Reference suite coverage: committed replay; payload identity conflict; live-owner contention; prepared-lease expiry and epoch fencing; ambiguous dispatch; abrupt process exit after dispatch; reconciler fencing; concurrent shared-budget exhaustion; duplicate reservations; immutable budget configuration; privacy-preserving provider rejection; capability filters; signed-adapter failure; wrong-candidate bindings; correlated witnesses; resource tradeoffs; uncertain intervals; and malformed evidence.

The process-exit test uses one bounded child process and a disposable local SQLite file. It invokes no real backend. Concurrent tests use at most eight local threads. They do not start model lanes.

The existing repo regression checks nested input mutation and the prior receipt behavior. Still untested here: actual network partitions, full disk, corrupted storage, distributed clocks, real backend idempotency, cloud rate limits, platform isolation, production signing keys, live canaries, and operational rollback. Those require the authorized staging adapters and scenario plan in section 8.

## 18. Release stages and acceptance gates

Stage A: freeze manifests and run local adversarial tests. Every observed critical bug gets a minimal reproducer and a regression test. Exit: deterministic receipts, no known counterexample in declared local scope, clear unknowns.

Stage B: deploy one authenticated control-plane service in staging with disposable effects and real isolation. Execute C01-C16 and E01-E12. Exit: no repeated effect, no stale-owner write, no scope leak, and successful restore/reconciliation drills.

Stage C: add version-pinned provider and retrieval adapters in shadow mode. Execute P/R/T matrices with read-only or synthetic effects. Exit: baseline stays available, capability probes are real, privacy filters hold, and evidence collection is complete.

Stage D: evaluate independent candidates on frozen held-out workloads under query and alpha budgets. Exit: required critical witnesses, mutation adequacy, authenticated artifact binding, and predeclared nonregression/resource constraints.

Stage E: authorized canary with rehearsed rollback and schema compatibility. Freeze promotion on missing required telemetry. Exit: declared exposure achieved, no critical invariant violations, measured SLOs and resource bounds satisfied.

Stage F: release controller advances the immutable pointer under current human/policy authorization. Keep previous artifacts, journals, outbox, evaluator epochs, and receipts according to retention policy. Continue drift detection and periodic mutation/restore drills.

Suggested initial operational targets are hypotheses to ratify against baseline: zero observed unauthorized writes or tenant leaks; zero blind redispatch of indeterminate effects; zero accepted stale epochs; complete evidence for critical obligations; and bounded cancellation/queue deadlines appropriate to each workload. Numerical latency, availability, recovery-time, and recovery-point targets must come from measured service needs rather than an invented universal percentile.

## 19. Implementation backlog with concrete boundaries

P0: isolate callable execution; replace weak callable fingerprints with artifact manifests; repair published ownership; add effect journal and outbox adapters; authenticate all task/evidence messages; require backend idempotency; freeze evaluator budgets.

P1: observed state/trace comparison; property and metamorphic generators; state-machine and crash/replay tests; mutation campaigns against the verifier; production trust-store verification; dataset fingerprint guard; structured failure taxonomy.

P2: bounded SMT/LLVM/Lean adapters tied to exact artifacts and assumptions; sealed evaluation service; resource interval estimator with sequential policy; privacy-preserving provider probes; shadow retrieval/tool/context evaluation.

P3: release controller and rollback rehearsals; lineage and cumulative semantic-delta accounting; canary exposure rules; periodic trust-key/backup/partition drills; workload-specific SLOs.

Each work item needs an owner, scope claim, reproducer, typed interface, negative controls, rollout switch, rollback path, and verified artifact receipt. This document does not assign ownership to another lane or authorize production deployment merely by naming the work.
