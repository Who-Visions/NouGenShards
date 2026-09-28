# NouGen war-game catalog — 1000 missions that deserve a war game first

Built 2026-09-24/25 for the NouGen elevation push. Rule 0.1 of the fleet
doctrine says: before any mission with 3+ steps or a real failure surface,
fight it on paper first — `wargames/<mission>.md`, move by move, each move
with its expected observation, its failure signal and its countermove, every
fork with a trigger. Plans are banned for meaty missions; war games replace
them.

This catalog answers the question that rule leaves open: **which missions?**
It is 1000 grounded candidates across 15 Who Visions repos, NouGenMsg, and
the fleet as a whole, each one a mission (not a nit), each one tied to
evidence in the code or the handoff record, each one with its first fork
already named so the war game can start on line one. A further 1642 verified
candidates that ranked below the cut sit in `reserve.ndjson`.

Files here:

| file | what it is |
|---|---|
| `catalog.ndjson` | source of truth: one JSON object per candidate, `WG-0001`..`WG-1000` |
| `reserve.ndjson` | 1642 more candidates that passed verification but ranked below the cut |
| `INDEX.md` | generated: counts, per-repo table, the full P0 list, #550 family coverage |
| `<repo>.md` | generated: every candidate for that repo, P0 first |
| `families.json` | the 100 scenario families from the war-room umbrella issue NouGenShards#550, as data |
| `../../tools/wargame_catalog.py` | validate, render, stats; `render --check` is the CI gate |

Never hand-edit the markdown. Edit `catalog.ndjson`, then run
`python tools/wargame_catalog.py render`.

## How to use it

1. Pick an entry. P0 first; within a priority, whatever is closest to the work
   you are already in. `INDEX.md` lists every P0 (361 of them).
2. Take a relay claim on the repo area (`relay claim take -s <scope> -g "WG-NNNN"`).
3. Write `wargames/<slug>.md` in the owning repo (that directory is
   gitignored on purpose: war games are working documents). Start from the
   entry's `first_fork`; every move needs an expected observation, a failure
   signal and a countermove.
4. Flip the entry's `status` in `catalog.ndjson` from `open` to `gamed`, set
   `wargame` to the file path, re-render, and ship that in the same PR as the
   work. `done` and `wontfix` close it out. A `wontfix` needs a one-line
   reason in `verdict_note`.
5. If you need more than 1000, `reserve.ndjson` is the same shape and already
   verified — pull the next-ranked entries for your repo straight from it.

The operating law of 2026-09-24 applies: reversible and evidence-supported work
is yours to take; label uncertain-but-reversible choices CANDIDATE with
provenance; park what is blocked; a Dave lock wins; only irreversible or
external actions go to Dave.

## What every entry carries

| field | meaning |
|---|---|
| `title` | the mission, imperative, under 120 characters |
| `repo` | owning repo, or `fleet` for cross-cutting missions |
| `kind` | `defend` (a failure that could or did happen) or `elevate` (an upgrade, migration, launch or scale-up that carries risk) |
| `priority` | derived, never typed: `P0`..`P3` from blast radius + likelihood + verdict (see below) |
| `blast_radius` | `fleet` (other repos, machines or people), `repo`, or `module` |
| `likelihood` | `observed` (it already happened; the evidence says so) or `likely` |
| `effort` | `S` under an hour, `M` a session, `L` multi-session |
| `failure_surface` | what breaks, who notices, how |
| `first_fork` | the war game's opening trigger: "if you observe X -> route A, else route B" |
| `evidence` | repo-relative paths, or relay / shard / PR ids, that a verifier opened and checked |
| `verdict` | `CONFIRMED` (evidence directly supports it) or `PLAUSIBLE` (evidence exists; the claim is a reasonable inference) |
| `lens` / `lens_group` | which scouting lens surfaced it |
| `families` | the #550 scenario family numbers this mission exercises, into `families.json`; omitted when it maps to none |
| `status` | `open`, `gamed`, `done`, `wontfix` |

Priority formula (`tools/wargame_catalog.py:derive_priority`):
blast fleet 3 / repo 2 / module 1, plus likelihood observed 3 / likely 2 /
speculative 0, plus CONFIRMED 1. Score 7+ is P0, 5-6 is P1, 3-4 is P2, below
is P3. Every entry in this cut is P0 or P1 — the verified pool was deep
enough that the top 1000 never needed to reach into P2 or P3.

## Counts

1000 candidates. 361 P0 · 639 P1 · 0 P2 · 0 P3.

kind: 687 defend · 313 elevate (31% elevate)
likelihood: 690 observed · 310 likely
verdict: 894 CONFIRMED · 106 PLAUSIBLE
family-mapped: 663 of 1000 carry at least one NouGenShards#550 family number

| repo | catalog | reserve | total verified |
|---|---|---|---|
| nougen-handoffs | 169 | 69 | 238 |
| fleet | 122 | 180 | 302 |
| NouGenRelay | 106 | 96 | 202 |
| NouGenMsg | 95 | 127 | 222 |
| NouGenShards | 86 | 143 | 229 |
| Visions-ai | 76 | 131 | 207 |
| Kaedra | 71 | 131 | 202 |
| Dav1d | 68 | 152 | 220 |
| Rhea-Noir | 64 | 164 | 228 |
| unk-app-ai | 48 | 128 | 176 |
| Yuki-Ai | 38 | 156 | 194 |
| Kam-ai | 17 | 33 | 50 |
| Ai-with-Dav3--Alpha- | 12 | 42 | 54 |
| Iris-Ai | 12 | 35 | 47 |
| nougenai-mcp-gateway | 9 | 40 | 49 |
| who-visions-tester | 7 | 15 | 22 |

`INDEX.md` carries the live per-family coverage table generated from
`families.json`; this file is a snapshot from the build.

## How this fits the war room (NouGenShards#550)

Issue #550 is the umbrella for an executable adversarial harness: 100 scenario
families, and a rule that every scenario carries preconditions, mutation,
expected observation, failure signal, countermove, cleanup and a
machine-readable receipt. This catalog is the mission layer underneath it:
the harness needs scenarios, and scenarios need missions that are real. The
two link both ways:

- Every entry carries `families`, the #550 family numbers it exercises. The
  generated `INDEX.md` shows, per family, how many missions feed it, and which
  families nothing in the catalog reaches yet. Those gaps are the next thing
  to scout.
- A catalog entry turns into a #550 scenario spec field by field:
  `failure_surface` is the expected observation and the failure signal;
  `first_fork` is the first mutation and its two countermoves; `evidence` is
  where the preconditions come from; the receipt is what the war game writes
  when the scenario is run. `status: gamed` plus a `wargame` path is the
  catalog-side receipt that the paper game exists; the executable receipt
  belongs to the harness.
- #550 targets NouGenShards internals, which is only 8.6% of this catalog
  (86 of 1000). The rest is other repos and the fleet as a whole, so the
  family taxonomy will need fleet-level families (messaging bus, relay
  registry, public surfaces, provider cutovers, GM bandwidth) as the harness
  grows. The `lens_group` field is the seed for those.

Two sibling documents opened the same day: issue #550 above (the executable
harness umbrella) and PR #555, `docs/wargames-doctrine.md` (the war-games
architecture doctrine: actor roles, the action/reaction/counteraction loop,
game modes, starter injects, scoring, campaigns). Read them as the rules of
the game and this catalog as the list of games worth playing.

## How it was built (provenance)

**Scout.** Eight scout groups ran in parallel, one per repo cluster
(NouGenShards+gateway, NouGenRelay+handoffs, Kaedra+Kam-ai+Iris-Ai,
Dav1d+Visions-ai, Rhea-Noir+who-visions-tester, Yuki-Ai+unk-app-ai+aiwithdav3,
the fleet as a whole, and NouGenMsg on its own). Each ran map (a subsystem
survey: services, deploy targets, data stores, secrets handling, known
failures from docs and handoffs, stale areas, elevation opportunities, risk
hotspots) then find (one finder per lens group — `attack-operate`,
`data-distributed`, `product-governance` for big repos; one combined pass for
small repos; `federation-dr`/`relay-governance`/`providers-cost-scale`/
`surface-brand-privacy` for the fleet). Every finder had to cite evidence it
had opened, name a first fork, and stay specific to the codebase; near-
duplicate titles were dropped in code before verification. NouGenMsg's finders
were also seeded with an outside ten-block "1000 elevation steps" brainstorm
Dave brought in (protocol core, queue engine, routing brain, receipts and
truth, security, agent parity, observability, testing and chaos, operator
experience, fleet-grade evolution) — treated as candidates, not facts: only
steps the live code made real survived, tagged with the block number in
`lens` (`B4-...`). This pass found 2371 raw candidates.

**Verify, in three rounds.** A shared usage limit reset mid-run twice, cutting
most of the first verify pass short after only 109 items cleared. Rather than
lose the find-stage work, every raw candidate and partial result was recovered
from the workflow run journals (map/find output persists there independent of
downstream failures) and re-verified once the limit cleared: round 2 covered
what survived, round 3 targeted every repo, lens pass or backfill the first
two rounds hadn't reached — including three repos (unk-app-ai, and one lens
group each for Kaedra and Visions-ai and NouGenRelay) that had to be
rescouted from scratch because their find-stage output never made it to disk.
By the end, all 16 repo areas had full or near-full verification. The
verifier's job in every round was the same: for each candidate, check that
its evidence paths exist, read them, and mark CONFIRMED (evidence directly
supports the claim), PLAUSIBLE (evidence exists, claim is a reasonable
inference), REFUTED, GENERIC (could be pasted into any repo), or DUPLICATE
(restates another item in the same batch); wrong paths were corrected where
the verifier found the right one. Ground truth was always what a verifier
batch actually wrote to disk, never a workflow's self-reported count — one
verify batch (who-visions-tester, round 3) claimed success and a written
count in its own return value while never writing its file, which is
`NouGenShards#550` family 100 ("war-game claims success without a receipt")
observed live during this build rather than merely catalogued. 2645 of 2655
disk-verified candidates came back CONFIRMED or PLAUSIBLE.

**Family mapping.** Every kept candidate was checked against the 100
scenario families from NouGenShards#550: 0-3 family numbers per entry where
the failure mechanism genuinely matched, none forced. 663 of the 1000
catalog entries carry at least one family.

**Assemble.** A global near-duplicate pass by title (Jaccard similarity on
meaningful words, same-repo threshold 0.72, cross-repo 0.82) removed 3
remaining duplicates the per-batch verify hadn't caught, in place of a
separate LLM judge stage (dropped after the usage-limit disruption, to spend
the remaining budget on coverage instead). Survivors were scored (blast
radius + likelihood + verdict) and ranked, round-robin across repos within
each score tier so no single repo — nougen-handoffs and the fleet pass both
ran deep — crowded out the smaller ones. The top 1000 are the catalog; the
next 1642 are `reserve.ndjson`.

Known limits: verifiers could open repo paths but not GitHub, so PR / relay /
shard ids were accepted as PLAUSIBLE evidence rather than CONFIRMED. The
`wargames/` directories on the fleet machines were not visible from this
build, so entries may overlap war games already written locally; the
existing-war-games list the scouts were given covers only the ones named in
HARDENING.md, the handoffs and the code. Family mapping is a best-effort
LLM pass over titles and is not itself adversarially verified.
