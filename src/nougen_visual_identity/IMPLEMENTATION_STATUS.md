# Persistent Generative Identity: implementation status

The supplied sections 28–70 are the target design. This directory is a local
prototype, not evidence of fleet deployment or successful visual resurrection.
The included fixture uses synthetic data and does not alter or describe canon.

## Verified transaction boundary

The compiler resolves a root, optional variant, amendments, and scene inputs.
It rejects a variant whose parent differs from the selected root. Its output
recursively freezes mappings and sequences and detaches them from caller inputs.
`to_dict()` returns a separate JSON-compatible copy.

The SHA-256 hash covers every exported field except `transaction_id` and
`contract_hash`. That includes tenant/project/entity/variant, causal labels,
revision, resolved state, policy, resolution inputs, references, constraints,
fidelity and schema version. Transaction UUIDs remain distinct across identical
resolutions. `compute_hash()` allows verification from the snapshot. JSON uses
sorted keys, compact separators and rejects nonfinite numbers. This is a Python
serialization contract; cross-language numeric canonicalization still needs an
agreed format and golden vectors.

No visual asset availability, adapter validation, or closed-loop evaluation is
established by this compiler. It therefore reports F0. Embedding fields alone
do not justify F3–F5. Tenant/project values distinguish hashes; this function is
not an authorization or tenant-scoped storage boundary.

## Coverage against the proposal

| Sections | Current coverage | Remaining work |
| --- | --- | --- |
| 28–32 | Root/variant deltas, phenotype/presentation split, policy fields | Deeply immutable stored roots; calibrated per-property displacement checks; explicit rejection diagnostics; policy enforcement across every layer |
| 33–39 | Sample covariance, caller-selected shrinkage, diagonal distance helper | Full covariance estimator or explicit diagonal evaluation policy; evidence confidence; regional consensus; append-only outlier flags |
| 40–42 | View-based reference ranking retaining an anchor | Reference graph, configurable ranking weights, dynamic softmax temperature |
| 43–47 | Basic scene override and ordered merges | Field-scoped override authority; amendment approval/provenance validation; temporal validity intervals; causal branch resolution; conflict detection |
| 48–54 | Detached immutable snapshot, revision, transaction ID, scoped content hash | Store-backed resolver; generator adapter integration; canonical cross-language serialization; fleet hash comparison |
| 55–58 | Synthetic unit tests only | Cold-start B0/B1/BN image benchmark; repeat seeds, worst case and variance; adapter portability evaluation; empirical routing |
| 59–63 | Negative constraint field | Candidate/approved/rejected evidence lifecycle; reference promotion authority; contrastive memory; cross-identity collision tests |
| 64–69 | Scoped contract fields; capsule prototype nearby | Exact tenant/project store keys; digest-verified portable asset resolver; offline fetch/fallback reporting; evidence-based F1–F5; typed append-only events |
| 70 | Provider-independent identity contract concept | Generalize character-specific fields after validating the underlying contracts |

The current compiler accepts caller-supplied amendment/variant data as trusted
resolved input. It does not establish canon authority. Nonzero mutation budgets
are recorded, not measured against generated images. The manifold helper uses
only diagonal variances; it does not implement the full inverse covariance
formula in the proposal. None of these should be described as production-complete.

## Next integration boundary

Add an exact scoped store resolver with approved amendment records and explicit
event ordering. Resolve temporal and branch validity before calling the pure
compiler. Then connect verified content-addressed references and calibrated
evaluation policies to a generator adapter. Keep the render and validator tied
to the same exported snapshot. Promote fidelity only when the required evidence
exists, and retain approvals/rejections as append-only events.

## Verification

From the NouGenShards repository root `NouGen` directory:

```sh
python3 -m pytest -q src/nougen_visual_identity/tests
```

28 tests passed on 2026-09-29. Coverage includes nested immutability, input
isolation, reproducible hashes, namespace/causal separation, invalid policy
rejection, honest F0 reporting, tenant-scoped exact retrieval, local asset hash
checks, unsafe-input rejection, and malformed-vector rejection. These tests do
not measure generated-image identity fidelity.
