# WAR-GAME: migration-pipeline

**Mission**: Graduate validated prototype features from the live vault stack (push-main) to the public NouGenShards app, tested through NouGenShards-pull-clone. Brief: `tasks/migration-pipeline.md`.
**Authored by**: Claude Fable 5, 2026-07-06.
**Executor**: gemma4:31b-cloud (decisions/reports) + a tool-bearing lane (claude-cli or codex) for file/git moves — gemma has no tool harness yet (see open-engine war-game). Executor contract per fleet-roster.md.

## Move 1 — Recon: feature delta
- **Action**: tool-lane diffs `src/nougen_shards/` between push-main and pull-clone; list features (with file:line handles) present in prototype but not public.
- **Expect**: a concrete delta list — e.g. recall-packet truncation, MMR stage-3, auto-embed, Open Engine queue — each with commit or file evidence.
- **Failure signal**: pull-clone stale/missing or on a diverged history that won't diff cleanly.
- **Countermove**: `git -C NouGenShards-pull-clone pull` first; if still diverged, diff by file content not history.
- **Fork**: IF delta is empty → mission complete, report and stop; ELSE continue.

## Move 2 — Pick the graduation candidate
- **Action**: gemma-31 ranks the delta by (smallest blast radius × already-tested × user value); picks ONE.
- **Expect**: one feature named, with its existing tests cited. Sensible first pick: recall-packet truncation (small, tested, user-facing).
- **Failure signal**: candidate has no tests.
- **Countermove**: write tests in push-main FIRST; a feature without tests cannot graduate.

## Move 3 — Stage in pull-clone
- **Action**: apply the patch to pull-clone; run `PYTHONPATH=src python -m pytest tests` there.
- **Expect**: all tests pass in the clone environment.
- **Failure signal**: import errors or schema mismatch (public schema may lag prototype).
- **Countermove**: add a schema-compat shim or mark the feature blocked-on-schema in `ledger.md`; do NOT force-migrate schema as a side effect.

## Move 4 — Integrity gate against the live vault
- **Action**: READ-ONLY checks: shard count (expect 9,972+), dedup index in sync, FTS5 query returns.
- **Expect**: counts match pre-move values; zero writes to `C:\Users\super\Watchtower\vault` from clone tests.
- **Failure signal**: any count drift or write to the live vault.
- **Countermove**: ABORT (see below) — this is the one non-negotiable.

## Move 5 — Graduate
- **Action**: commit to a feature branch in the public repo, push, open PR with the test evidence.
- **Fork**: IF the public repo requires GM review for release → stop at PR (outward-facing gate); ELSE merge per standing authority.

## Open variables → ledger.md
- `(migration_cadence)`, `(next_features_after_first)`, `(public_schema_version)`.

## 2nd/3rd-order
- Each graduation widens the public attack surface — security-adjacent features need the Adversary agent's cross-review before PR.
- Clone drifts stale between runs; Move 1 must re-pull every time.

## Abort conditions
- Any write touches the live vault during clone testing.
- Shard/dedup counts drift at Move 4.
- Public/prototype schema conflict that requires destructive migration — stop, report to GM.
