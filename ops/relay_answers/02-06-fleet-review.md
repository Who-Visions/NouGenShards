# Legs 2–6 — fleet drafts, coach-reviewed

Player drafts, coach reviews (Rule 0.7). Raw returns preserved in `raw/`. Below is what survives
review, plus every correction — including the corrections themselves as evidence, since a model
that invents a filename while being told "do not invent files that are not listed above" is a
data point the docs compiler must plan around.

---

# Leg 2 — Recursive learning through failure

*Draft: `arliai-gemma4-31b-opus`. Accepted with one correction.*

## Doctrine (endorsed as written)

> NouGen treats operational failure as primary training data. Every system fault, handoff error,
> or rejected claim triggers a capture event that updates behavioral shards. Recovery is
> incomplete without adapting the underlying skill or routing logic to prevent recurrence.
> Failure is not an exception; it is the mechanism of recursive optimization.

The load-bearing sentence is the third. "Recovery is incomplete without adapting" is what turns
the principle from a slogan into a testable claim: a fix that changes nothing about future
routing has not completed the loop.

## Falsifiable invariants

1. Every `CONTRADICTED` verdict from `assurance.py` triggers a `capture_experience` call.
2. No `handoff_triggers.py` failure repeats with identical parameters more than twice.
3. Every `run_brain_scan` error generates a corresponding `evolve_skill` invocation.
4. Every failure-derived shard carries a `verification_test` that failed before the fix.
5. Every retry storm (≥3 identical 4xx/5xx/52x) produces a relay leg, not just a log line.

**Correction applied:** the draft's invariant 1 said *"every VERIFIED claim contradiction"*, which
is incoherent — a contradiction is not a VERIFIED state. `assurance.py` emits exactly
`VERIFIED / CONTRADICTED / UNCERTAIN / UNVERIFIED`; the invariant belongs on `CONTRADICTED`.

**Correction applied:** the draft's invariant 5 mapped enforcement to `src/nougen_shards/vault.py`.
**That file does not exist.** Replaced with the retry-storm invariant, which is enforceable and
maps to capability (6) of the Dav1d leg — the two legs meet here, which is the point.

**Correction applied:** invariant 4 in the draft was *"the ratio of recall to capture calls
increases after a fault"*. That is a metric, not an invariant — it cannot fail in a way that
identifies a defect. Replaced with the `verification_test` requirement, which can.

## Failure-shard capture convention

Required fields, endorsed from the draft:

- `failure_signature` — hash of the error state / stack trace, so recurrence is detectable
- `recovery_path` — the sequence of actions that actually resolved it
- `adaptation_delta` — **the specific change made so it cannot recur**; empty means the loop
  did not close, and the shard should be labelled incomplete rather than filed as a lesson
- `severity_score`
- `related_shards`
- `verification_test` — a probe that fails before the fix and passes after

`adaptation_delta` and `verification_test` are the two that make the doctrine enforceable. The
other four are bookkeeping.

## The `Learned` CHANGELOG category — rejected

The leg proposed it. The fleet rejected it. **I'm endorsing the rejection**, and flagging clearly
that this contradicts the original ask so the director can overrule.

The argument: a CHANGELOG entry is a *public, user-visible transition*. A category called
`Learned` invites entries that describe internal realisations with no observable change — which
is exactly the prose a documentation compiler should never be allowed to generate. If a lesson
changed behaviour, it belongs under `Fixed` or `Changed` with the behaviour named. If it changed
nothing observable, it belongs in a shard, not a public changelog.

Adding `Learned` would create a sanctioned lane for unfalsifiable public prose, in the same
system that is simultaneously trying to make stale docs a detectable failure. Those two goals
are in direct tension.

## Product lines

> "We recursively learn through failure."
> "A mistake should make the next decision better."

Draft's longer line ("NouGen doesn't just recover from errors—it digests them…") is usable but
overclaims *automatically*; the capture is not automatic today. Do not ship that word until
invariant 1 is enforced.

---

# Leg 3 — Docs compiler (`tools/nougen_docs/`)

*Draft: `ollama-cloud-contact-whovisions`. Accepted with corrections.*

## Module layout (endorsed)

```
tools/nougen_docs/
├─ compiler.py      # mode orchestration
├─ manifest.py      # loads/validates the repo manifest
├─ sanitizer.py     # wraps brain_scan/redaction.redact_content()
├─ dedup.py         # clusters relay records into one incident
├─ changelog.py     # --changelog
└─ provenance.py    # sidecar state
```

Flow: repo source → manifest → relay registry → dedup → verification → provenance → mode
(`--check` / `--dry-run` / `--write` / `--changelog` / `--explain`) → sanitizer → markdown.

Note the ordering: **sanitizer runs last, on the rendered output**, not on the inputs. The draft
had it last too, and that is correct — sanitizing inputs leaves you trusting that every
downstream transform preserved the redaction.

## Modules to reuse (corrected)

- `src/nougen_shards/assurance.py` — verdict labelling. **Do not reimplement.**
- `src/nougen_shards/brain_scan/redaction.py` — `redact_content()`.
  **Correction:** the draft wrote `src/nougen_shards/redaction.py`. Wrong path; it lives under
  `brain_scan/`.
- `NouGenRelay/src/nougen_relay/core.py` — relay registry reads.
  **Correction:** the draft named `tools/fleet.py` as the way to "query the relay registry".
  `fleet.py` is a 48-route *inference* dispatcher. It has nothing to do with the relay registry.
- `src/nougen_shards/core.py` — `retrieve` / `compile_recall_packet` for shard reads.
- `tools/fleet.py` — only for the optional narrative-compression layer, never for facts.

## Repo manifest schema (corrected — draft's was unusable)

The draft's manifest described a *Python package* (entry_points, schemas, tests). It omitted
every field the compiler actually needs. Minimum viable:

```yaml
repos:
  nougenshards:
    public: true
    path: ../NouGenShards
    readme: README.md
    changelog: CHANGELOG.md
    generated_sections: [status, architecture, tools, install]
    source_of_truth:
      tools: src/nougen_shards/mcp.py   # counted, not remembered
    relay_tags: [shards, mcp, gateway]
    shard_tags: [shards, gateway, connector]
```

`source_of_truth` is the field that makes verification possible: it names *the file that settles
the question*, so "19 tools" is counted from `mcp.py` rather than recalled.

## Source-verification rules (endorsed)

1. Repo source outranks any relay or shard claim, always.
2. Claim matches repo fact → `VERIFIED`, evidence = file paths.
3. Claim disagrees → `CONTRADICTED`, **emit the conflict, change nothing**.
4. Disagreement is written to the provenance sidecar and surfaced in `--explain`; it never
   silently merges and it never mutates a shard.

Rule 3 mirrors `assurance.py`'s existing docstring policy — *never mutate from an automated
verdict*. Consistency here is deliberate.

## Relay dedup key (corrected)

Draft proposed `(incident_type, timestamp_window, shard_id, content_hash)`. **`shard_id` is
wrong** — relays do not carry one, and `content_hash` after redaction defeats clustering, since
two lanes describing one incident in different words hash differently.

Use: `(repo, 15-min window, normalized_scope_overlap, error_signature)`. Scope overlap and error
signature are what actually make two relays *the same incident*; wording is what makes them look
different. This is the same normalization the Dav1d ladder needs, so build it once.

## Must not be automated on day one (endorsed, verbatim intent)

No auto-write to shards or the relay registry. No auto-promotion of context to shard. No
auto-application of assurance verdicts. No auto-generated relay entries. No skill evolution.
Start at `--check`, graduate to `--write` only after `--explain` has been read by a human enough
times to be boring.

---

# Leg 5 — Connector tools: 20 proposed, 5 survive

*Draft: `ollama-cloud-davemeralus`. **Largely rejected** — the draft hit the token ceiling
mid-table and invented three connector endpoints (`read`, `search`, `status`) that do not exist.
Mapping below is coach-authored against verified inventory.*

| Tool | Already exists as | Verdict | Why |
|---|---|---|---|
| `repo_scan` | none | **BUILD** | `run_brain_scan` scans memory, not repos. Real gap. |
| `repo_read` / `repo_grep` | none on the connector | **BUILD (one tool)** | Merge. Two tools for "look at a file" is surface for its own sake. |
| `shards_related` | `recall_related` (MCP) | **DROP** | Already exists. Expose the existing one. |
| `shard_from_diff` | `promote_context_to_shard` | **THIN-WRAP** | Feed the diff as context. |
| `repo_diff` / `repo_status` | `git` | **DROP** | Wrapping `git status` in an MCP tool buys nothing. |
| `fleet_activity` | `tracker_daily` + `relay_*` | **THIN-WRAP** | Derivable today. |
| `fleet_compare` | none | **BUILD — later** | Genuinely novel, but useless until `repo_scan` exists. |
| `tests_run` | none | **BUILD** | Real gap, and the evidence source the Dav1d gate needs. |
| `command_run` | `execute_sandboxed_code` | **DROP** | Draft aliased these. They are not the same — one runs code in a sandbox, one runs shell on a host. The second is the highest-risk tool in the list for the least marginal gain. |
| `relay_from_failure` | `relay_create` | **THIN-WRAP** | Template, not a subsystem. |
| `readme_sync` / `docs_drift` / `changelog_build` / `public_surface_audit` | none | **BUILD as ONE** | All four are modes of `nougen_docs.py`, not four tools. |
| `service_health` | `gateway_probe.py`, `fleet.py probe`, `shards_status` | **THIN-WRAP** | Three probes exist; unify, don't invent. |
| `logs_query` | `search_context` (partial) | **DEFER** | Cross-machine log access is an infra problem, not a tool problem. |
| `incident_trace` | none | **DEFER** | Depends on `logs_query`. |
| `verify_relay` | `assurance.py` | **THIN-WRAP** | **The single highest-value item.** Substrate is built. |
| `release_snapshot` | none | **DEFER** | Wants a release cadence that does not exist yet. |

## First wave — five, ranked

1. **`verify_relay`** — `assurance.py` already returns the verdicts. Without this, "fixed" means
   "claimed", and every other tool inherits that lie. Cheapest, highest leverage.
2. **`repo_scan`** — nothing else lets memory look at reality. Every verification tool below
   depends on it existing.
3. **`tests_run`** — turns "done" into an exit code. The evidence source for rung 6 of the
   Dav1d ladder.
4. **`nougen_docs`** (one tool, four modes) — collapses four proposed tools into one and answers
   legs 3, 4 and half of 5 simultaneously.
5. **`repo_read`** (grep folded in) — the last mile from "there is a file" to "here is the line".

Dropped outright: `shards_related`, `repo_diff`, `repo_status`, `command_run`. Four proposals
that either already exist or are `git` with extra steps.

**20 → 5.** Fewer tools is the correct answer; the connector already exposes 25 and the local MCP
another 19, and nobody is short of surface area.

---

# Leg 6 — Adversarial review

*Draft: `ollama-cloud-mrsb-tutoring`. Strongest return of the batch. Findings 1, 2, 4 and 8
survive unchanged; 3 and 7 were rejected as invented.*

## 1. `VERIFIED` decays silently into a lie — most severe

**Trigger:** `assurance.py` labels a claim `VERIFIED` against shard #N. Someone calls
`shards_amend` on #N. The verdict is not re-evaluated. A stale `VERIFIED` now gates a "done"
transition, and the docs compiler renders it as current public truth.

**Mitigation:** verdicts store `evidence_used` already — bind each to the source shard's
content hash, and reset to `UNVERIFIED` on any amend or retract of a cited shard. A verdict must
name what it was verified *against* or it means nothing.

## 2. Retracted shards become confident public prose

**Trigger:** the compiler pulls shards for a README section without filtering retraction status.
`shards_retract` and `shards_forget` both exist, so retracted content is reachable. A belief the
fleet explicitly withdrew gets published as current architecture.

**Mitigation:** hard `status == ACTIVE` filter at the shard-fetch boundary, plus a regression test
that retracts a shard and asserts it cannot reach rendered output. This is a *test*, not a
convention — conventions are what fail at 3am.

## 3. `redact_content()` is not a public-safety guarantee

**Trigger:** redaction is string-oriented. Relay bodies and shard payloads carry nested
structures, tracebacks and JSON. A secret inside a nested value, or a machine name in a path
inside a code fence, survives a pass written for prose.

**Mitigation:** recursive, type-aware sanitization; allowlist rather than denylist for anything
crossing into a public repo; and never publish a raw relay body — only a verified summary. There
is precedent: dream-lane runs have leaked live credentials into on-disk digests more than once,
and the pre-disk redaction fix has been proposed and left unapplied across multiple nights. The
same class of defect will hit public docs harder, because the output is *public*.

## 4. Audit-by-model hallucinates its own evidence

**Trigger:** a README audit that asks a model to check facts gets priors instead of facts.
**Observed in this very batch:** given an explicit file inventory and the instruction not to
invent files, three separate fleet returns named `src/nougen_shards/vault.py`,
`tools/generate_docs.py` and `tools/drift_audit.py`. None exist.

**Mitigation:** every factual detector must be deterministic — `grep`, a parse, a count, an exit
code. Models may compress wording. Models may never establish a fact. That is not a style
preference; it is demonstrated three times in `raw/`.

## 5. Circular dependency: compiler ↔ connector tools

**Trigger:** the connector tools leg proposes `readme_sync`/`docs_drift` as tools; the compiler
leg proposes them as modes. Build both and each waits on the other's interface.

**Mitigation:** the compiler is a **script first**, exposed as a tool later. Resolved above by
collapsing four proposed tools into one tool with four modes.

## 6. Enforcement blocks legitimate parallel work

**Trigger:** two lanes legitimately touch adjacent paths under one prefix. Path-containment
rejects the second. Someone hits the friction once and sets `nougen.requireClaim=false`
permanently — and the guard is disabled everywhere, including where it mattered.

**Mitigation:** the existing warn-by-default posture is correct and should not be "upgraded" to
block-by-default. Block only on **exact** scope-set equality (the dedup case, which is never
legitimate) and leave prefix overlap as a warning.

## 7. Most likely to be abandoned half-built: the 20-tool connector expansion

**Trigger:** 20 tools is a surface nobody maintains. Partial completion is worse than none — a
connector advertising `verify_relay` that returns optimistic stubs actively launders unverified
claims into trusted ones.

**Mitigation:** the five-tool first wave above, and a rule that a verification tool ships with
its negative test — it must be shown *failing* on a known-bad input before it ships.

## Rejected from the draft

- *"Dav1d blocks `capture_experience` until assurance returns a verdict"* — invented. Nothing
  proposes gating memory ingestion on claim verification.
- *"Recursive failure doctrine triggers `log_context_event` which triggers a failure, recursing"* —
  a real class of bug, but no proposed component wires that loop. Keep the *idea* (failure
  handlers must be non-recursive) as a design note, not a finding.
