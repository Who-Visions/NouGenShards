# Three-node cross-verification

*Codified 2026-09-05 from a five-hour phoebus/blade/whoart firefight. Every
example below is measured, and most of them are corrections to the lane that
wrote them down.*

The fleet's value is not that three nodes work in parallel. It is that they
**verify each other's claims against different OS and runtime surfaces**. A
claim that survives phoebus (macOS/Intel), blade (Windows) and whoart is
qualitatively stronger than the same claim measured three times on one box.

## The rule

**For any infrastructure claim, get independent-node verification before
promoting a local finding to fleet truth.** Preserve the chain:

> observation → contradiction check → measured provenance → corrected
> conclusion → reusable method

**Treat differences between nodes as information, not noise.** The asymmetry is
usually the finding. Blade's runtime provenance read from its Windows parent
process chain, next to phoebus's `lsof` cwd, exposed a real deployment
difference: blade runs from a dirty working tree, phoebus from an isolated
deployment clone. Neither node could have found that alone.

## What it caught in one afternoon

**Seven mechanisms proposed for one defect. Six died to a measurement**, each
from a different lane, several killed by their own author:

| hypothesis | killed by |
|---|---|
| memory pressure | memory freed; latency unchanged |
| dead embeddings | whoart has full coverage and fails identically |
| query cost | a one-word query failed like a heavy one |
| `9 × 5s` serial lock floor | the builds run concurrently — interleaved DB order |
| cold cache from continuous capture | a clean restart didn't help |
| thread contention | 4× the load added 8% latency |
| **writer inside the reader** | **survived** — the node that serves recall is the node that writes, so the vector cache is invalidated between every request |

The survivor was found by **reading the cache key**, not by measuring harder.

## The failure this exists to prevent

Nearly every wrong answer that day was a **true measurement of the wrong
subject**:

- "verified clean" on a tree `main` was never in
- CI red that measured a billing gate, not the code
- a sandboxed read returning a confident `0` for 108,415 rows
- a token proven valid — for a destination nobody knew it was being sent to
- `complete: true` sitting on top of an inner `INCOMPLETE`
- an `HTTP 200` returning one row of 335

**A single lane cannot catch these, because the measurement is correct.** Only a
second node asking "of what?" exposes them.

## Two failure modes, and they are separate

**Predicate** — *what* you match on. Scoping a leaked credential, four
predicates were tried and the first three each failed:

| predicate | what it actually finds |
|---|---|
| the secret value | writes the secret down again |
| the variable name | everyone who *responsibly reported* it — inflated 3× |
| the marker list used to search | whoever documented the method, one round later |
| **file size** | the artifact, and only the artifact ✅ |

**Scope** — *where* you look. After three lanes converged on the right
predicate, all three had scanned the same four directories. A wider recursive
sweep found the store nobody had modelled: every session transcript.

**Getting the predicate right does not fix a wrong scope.** Enumerate the stores
before choosing the test.

## Practices that earned their place

- **State the observation window, and the sha.** A check rollup read three
  different values in forty minutes; three lanes "disagreed" while all three
  were right. `main` moved five times during one test run.
- **n=1 is a sample, not a distribution.** One anomalous record became a
  headline twice; one wider query dissolved it both times. A "2.4× faster"
  result collapsed to ~1.2× when someone ran five samples per setting instead
  of one — the first number was measuring OS page-cache warmth.
- **Name the tree, the layer, and the config.** Two layers compared at different
  cache-wait settings produced a "17-second gap" that was partly configuration.
- **Read the success object, not just the error.** A `200` with one row is a
  failure wearing a success code.
- **Prefer evidence that doesn't depend on catching a good moment.** An error
  *changing class* (401 → 502) proved a fix landed; no green sample could.
- **Check the node that is not complaining.** It holds the constraint you are
  about to break.
- **Agreement is not validation.** A confirmation can reach the right answer
  from the wrong instrument, and it will never be questioned precisely because
  it agrees.

## Where the method breaks

Consensus is not verification. Two lanes agreed that unversioned code was
running on the always-on node and escalated it; a third ran one `lsof` and it
dissolved. **The measurement nobody ran is worth more than the one three lanes
repeated.**
