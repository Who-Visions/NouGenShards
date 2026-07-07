# WAR-GAME: open-engine-expansion

**Mission**: Fleet lanes auto-claim Open Engine queue tickets and post receipts without a human dispatcher, preserving claim-lock and block-on-ambiguity. Brief: `tasks/open-engine-expansion.md`. This is the force-multiplier war-game: it gives tool-less models (gemma family) hands.
**Authored by**: Claude Fable 5, 2026-07-06.
**Executor**: tool-bearing lane (claude-cli/codex) builds; gemma4:31b-cloud is the first auto-claiming worker.

## Move 1 — Recon: queue internals
- **Action**: read the queue implementation behind `nougen queue` (add/claim/block/answer/done, claim lock, status lanes) — find the storage (DB/files) and the atomic-claim mechanism.
- **Expect**: file paths + the exact claim-lock primitive (e.g. SQLite transaction or file lock) identified.
- **Failure signal**: claim is not actually atomic (check-then-write race).
- **Countermove**: fix atomicity FIRST (single UPDATE ... WHERE status='todo' guard); auto-claim on a racy lock is forbidden.

## Move 2 — Worker loop design (the runner)
- **Action**: design `fleet_runner`: claims oldest eligible ticket for its lane → builds a prompt from ticket fields (title/instructions/sources/stop/dod) → calls its model (ollama API) → posts `done` with receipt, or `block` with the exact question.
- **Expect**: design doc with the ticket→prompt mapping and receipt format (did/evidence/not-done).
- **Failure signal**: tickets require tool actions (file edits, tests) the model can't perform.
- **Fork**: IF ticket needs tools → runner posts `block` with "needs tool-bearing lane" tag and re-owners it; ELSE model-only tickets (drafting, review, analysis) proceed. Start with model-only tickets ONLY.

## Move 3 — Implement minimal runner
- **Action**: single Python file (e.g. `tools/fleet_runner.py`): one-shot mode first (`--once`): claim → execute → receipt → exit. No daemon yet.
- **Expect**: `nougen queue smoke`-style test passes end-to-end with gemma-31 as the worker.
- **Failure signal**: model output fails the ticket's DoD.
- **Countermove**: runner posts `done` with `--not-done` honesty field rather than fake success — receipts must be truthful; Coach reviews.

## Move 4 — Concurrency proof
- **Action**: two runner instances race for one ticket.
- **Expect**: exactly one winner claims; loser exits clean.
- **Failure signal**: double-claim or deadlock.
- **Countermove**: back to Move 1 countermove; do not ship.

## Move 5 — Ambiguity + escalation wiring
- **Action**: verify block-on-ambiguity path; add per-move escalation hook (low-confidence output → ticket re-queued for a stronger lane, per `(fable_credit_budget)`).
- **Expect**: ambiguous test ticket lands in `needs_input` with a precise question.

## Open variables → ledger.md
- `(runner_lanes_enabled)` (start: gemma-31 only?), `(daemon_vs_manual)` (one-shot per session vs background loop — background needs GM call), `(fable_credit_budget)` (shared with nougen-beats-fable).

## 2nd/3rd-order
- A daemonized runner writing receipts unattended is the first autonomous write-path in the mesh — it must respect the fail-closed write-auth doctrine (7.1) if it ever touches mesh endpoints.
- Bad receipts poison the handoff chain — truthful `--not-done` beats optimistic `done`.

## Abort conditions
- Claim-lock cannot be made atomic → stop, report design options to GM.
- Runner mutates anything outside the queue DB and its ticket artifacts.
