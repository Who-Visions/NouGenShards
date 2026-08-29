# Answer — Dav1d enforcement hooks for Relay claims

**Leg:** `20260828T233017Z__chatgpt-app__g-whoentertains` (mirror `20260828T235220Z__ccr__claude-cli`)
**Lane:** whoart / claude-cli · **Date:** 2026-08-28
**Verdict:** Spec only from this lane. Blade implements — blade holds the live `relay_daemon` claim
and *is* the collision fixture.

---

## The correction this leg needs

The leg says "the missing piece is not another persona, it is enforcement capability." Half right.
**The enforcement capability is already written and shipped. It is switched off.**

`NouGenRelay/src/nougen_relay/guard.py` already implements, today:

| Asked-for capability | Existing implementation | State |
|---|---|---|
| (1) reject on path-containment collision | `own_cover()` → `gh._scopes_overlap()`, `foreign_claims()` | **built, advisory by default** |
| (3) revoke/expire stale claims | `claim_is_active()`, `_claim_ttl_hours()`, `_claim_age_hours()` | **built** |
| hard block | returns `gh.EXIT_DIVERGED` | **built, gated** |
| "don't be a bottleneck" | `_require_claim_default()` — per-repo opt-in via `git config nougen.requireClaim`, env `NOUGEN_REQUIRE_CLAIM`, **off by default**; warns ⚠️ yellow, blocks ✋ red | **built** |

The safety principle the leg asks for — *govern coordination, do not become a universal bottleneck* —
is not a thing to design. It is the existing default. Someone already made this call and made it
correctly: warn everywhere, block only where a repo opts in.

So the honest answer is **not** "build Dav1d enforcement". It is: **three specific gaps**, below.

## Gap 1 — enforcement fires at COMMIT time, not at CLAIM time

`guard` is a pre-commit hook. It checks *files you are about to commit* against *other machines'
claims*. Nothing checks a **new claim against existing claims at the moment it is created**.

That is precisely why the live fixture happened. Two `blade1tb/antigravity` claims, same session,
same goal, identical scope `relay_daemon,hud,ui,keymaker`, 21s apart, SHAs `7374548` and `c921bc0`.
No commit was involved, so no guard ran. The claim path has no gate at all.

**Fix:** move the existing overlap predicate to claim-creation. `cmd_claim` (core.py:772) calls
`foreign_claims()` before writing the record and applies the ladder below.

## Gap 2 — no dedup, so self-collision is invisible

`foreign_claims()` is by definition *foreign* — it excludes your own machine. Two claims from the
**same** machine and **same** session cannot collide by construction. The live fixture is a
self-collision, which is the one case the current code is structurally blind to.

**The dedup rule, concretely:** two claim records collapse into one when
`(machine, agent, session, normalized_scope_set)` are identical and `created_utc` differ by less
than the TTL. Newest `sha` wins; older record is marked `superseded_by` rather than deleted.
Applied to the fixture: `blade1tb` + `antigravity` + session `ac1f9b4e…` + scope set
`{relay_daemon, hud, ui, keymaker}` match exactly → the `7374548` record is superseded by
`c921bc0`, one active claim remains, nothing is lost, no human is asked anything.

Note this is a **pure equality check on normalized fields**. No model judgment. No embedding.

## Gap 3 — nothing verifies "done"

Capability (5), evidence before completion, has a substrate nobody has wired up:
`NouGen/src/nougen_shards/assurance.py` already returns
`VERIFIED / CONTRADICTED / UNCERTAIN / UNVERIFIED` with `confidence`, `rationale`, `evidence_used`,
`caveats` — and its docstring already states the correct policy: *"It never promotes, deletes, or
otherwise mutates shards from an automated verdict."* That is the right posture for claims too:
**label, do not auto-close.**

---

## (a) The deterministic predicate ladder, in evaluation order

Every rung is an exact comparison. Evaluation stops at the first rung that fires.

```
0. WELL-FORMED       schema check on the claim record        → reject if malformed
1. SELF-DEDUP        (machine, agent, session, scope_set)    → supersede older, exit OK
                     equal AND age < ttl_hours
2. STALE-SWEEP       now - created_utc > ttl_hours           → mark expired, do not count as active
3. PATH-CONTAINMENT  normalized prefix overlap of scope      → collision candidate
                     against ACTIVE claims of OTHER machines
4. LANE-FREEZE       machine in frozen_lanes set             → reject, cite freeze record
5. POLICY            repo opted in via nougen.requireClaim   → block (EXIT_DIVERGED) else warn
6. EVIDENCE-GATE     only on transition to status=done       → assurance verdict required
```

Rungs 0–5 are pure functions of the claim registry. Nothing calls a model. Rung 3 already exists
as `_scopes_overlap`; rungs 1, 4, 6 are new; rung 2 exists as `claim_is_active`.

## (b) Which of the 8 capabilities need model judgment

**Six need none.** (1) path containment, (2) dedup, (3) TTL expiry, (4) lane freeze, (6) failure-rate
escalation, and (8) the audit trail are all deterministic — normalized paths, prefix containment,
tuple equality, timestamp arithmetic, a counter with a threshold, and an append-only log.

**Two are partly judgment-bound:**

- **(5) evidence before completion.** Deterministic where the done-when is machine-checkable (test
  exit code, endpoint status, SHA present on a branch). Judgment-bound where the done-when is prose
  — which is most of them. Route those through `assurance.py`, and per its own rule, let it **label
  `UNVERIFIED` rather than block**. A gate that cannot be satisfied is a gate that gets disabled.
- **(7) reconciling contradictory relay assertions.** Deterministic *first*: if the repo can settle
  it, the repo settles it and no model is consulted. Only genuinely ambiguous residue reaches
  judgment, and the output is a labelled conflict for a human, never a silent merge.

## (c) Claim record fields to add

Current record: `machine, agent, goal, scope, status, session, branch, sha, created_utc, ttl_hours`.

Add exactly five:

- `claim_id` — content hash of `(machine, agent, session, scope_set)`; makes dedup a dict lookup
- `scope_set` — normalized, sorted, deduplicated path list; the *normalization* is what makes
  containment reliable, and it must be stored, not recomputed at read time
- `superseded_by` — `claim_id` of the winner, or null; preserves the loser instead of deleting it
- `evidence` — list of `{kind, ref, verdict}`; empty until a done-transition is attempted
- `decisions` — append-only list of `{at, rung, action, reason}`; this **is** capability (8)

## (d) The smallest first commit that proves the loop

Not the ladder. Not Dav1d. **Rung 1 only, on the existing fixture.**

Add `scope_set` normalization + `claim_id` + the self-dedup predicate to `cmd_claim`, and a single
regression test whose fixture is the two real blade claims (`7374548`, `c921bc0`, 21s apart,
identical scope). Assert: two claims in, one active claim out, loser carries
`superseded_by`, one entry appended to `decisions`, and **an unrelated third claim on a different
scope is untouched** — that last assertion is what proves Dav1d governs without becoming a
bottleneck.

One file, one test, one real incident it demonstrably prevents. Everything else in this document
is the plan *after* that lands.

---

## Architectural note for the director

The rule stands: **agents drive, Dav1d governs the road, Dave governs Dav1d.** But the road already
has speed limits painted on it. The work is not building an authority — it is moving an existing
check from the wrong moment (commit) to the right one (claim), teaching it to see self-collision,
and refusing to let "done" mean "claimed".
