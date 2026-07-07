# NouGen Drill Library — 100 Practice Reps

Drills are the practice squad's reps: small, repeatable, **scored** tasks that keep fleet agents sharp, expose their failure modes early, and feed the raw-vs-NouGen scoreboard (war-game `nougen-beats-fable`, Move 5). War-games are for missions; drills are for muscle.

## Drill schema (every drill)
```
### <CAT>-<##>: <name>
- **Trains**: <agent role from wargames/fleet-roster.md>
- **Input**: <what to feed the agent — always concrete/derivable from the repo or vault>
- **Task**: <one-sentence order>
- **Expect**: <output shape + the property that makes it a pass>
- **Fail signals**: <the known failure mode this drill is designed to catch>
```

## Categories (10 × 10)
| File | Category | Trains against |
|---|---|---|
| recall.md | RECALL — paraphrase vault probes | semantic recall misses |
| compress.md | COMPRESS — compression with evidence handles | blob-dumping, lost row/shard IDs |
| fact.md | FACT — verify a claim against a source | hallucinated stats & citations (iris, gemma-31 modes) |
| triage.md | TRIAGE — route a task to the right lane | wrong-lane dispatch, cloud waste |
| diag.md | DIAG — read failing test output, name the suspect | shallow diagnosis |
| patch.md | PATCH — draft a minimal diff | blast-radius creep |
| review.md | REVIEW — find the planted defect | rubber-stamping |
| fork.md | FORK — add missing fork/countermove to a plan | linear blue-sky planning |
| receipt.md | RECEIPT — write honest done/not-done receipts | fake-success receipts, roleplay output (dav1d mode) |
| adversary.md | ADVERSARY — attack a given artifact | agreement bias |

## Scoring
- Each drill is pass/fail against its **Expect** line; the **Judge** agent (HF lane) or Coach scores.
- Log runs as `drill-runs/<date>-<agent>.md`: drill ID, agent, pass/fail, one-line evidence.
- Reliability log in `wargames/fleet-roster.md` is updated from drill results — routing follows the numbers.
- A drill that every agent always passes is dead weight: replace it (keep the library at ~100 live drills).

## Provenance
Schema + seeds: Coach (Fable tier). Volume: `[fleet] gemma4:31b-cloud`, Coach spot-checked ≥10%. Regenerate any category by re-running the batch prompt with this README as context.
