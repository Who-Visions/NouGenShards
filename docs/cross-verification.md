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
> conclusion → reusable method → **publish the discriminator, not the total**

That last step is load-bearing. The leaked-file count only converged when
someone showed *how* they were splitting the set rather than what they counted;
the recall numbers were worthless until someone named the layer they measured
at. **A total invites agreement. A method invites refutation.**

**Treat differences between nodes as information, not noise — this is the
headline, not a footnote.** Every real finding on 2026-09-05 came from a
*contradiction*, not a concurrence: in-process 8.67s against HTTP 25s; one lane
green while another timed out on the identical query; 5-of-5 rows in process
against 1 row over HTTP. Each gap *was* the finding, and each was invisible
while lanes measured different layers on different boxes and compared the
results as though they were the same quantity. **The compounding comes from
contradiction.** Blade's runtime provenance read from its Windows parent
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

## Where the method breaks — read this before trusting a concurrence

**Agreement is evidence only when the methods are independent.** Two lanes
running the same command on different machines is *one measurement with two
witnesses*. Stated without this condition, "verify across nodes" gets read as
"if two lanes agree, it is true" — and on 2026-09-05 that produced three
confident wrong answers, each with two or more lanes agreeing.

| trap | what happened |
|---|---|
| **shared scope** | Three lanes each *improved* the leak-scoping predicate and converged — and all three scanned the same four directories. A fourth found the session transcripts; a fifth store turned up after that. Right predicate, wrong directory list, three-way agreement. |
| **shared premise** | "Phoebus has no embeddings" originated in one lane, was inherited by a second, and a third built a two-node comparison on it. The corpus had 3 nulls in 108,415 the whole time — and one of those lanes had measured that themselves hours earlier. The *conclusion* was right, which is exactly why nobody rechecked the premise. |
| **shared instrument** | Two lanes measured the sync workflow instead of CI and reached the correct per-repo conclusion by luck. **A measurement that agrees with the right answer is never questioned, because it agrees.** |

**The test, before treating concurrence as confirmation — different tools,
different scopes, different premises?** If any of the three is shared, you have
one measurement with two witnesses.

The whoart/blade case is the good example precisely because the *methods*
differed by OS: a Windows parent-process chain against a POSIX `lsof` cwd. That
agreement carried real information. Same-method agreement carries none.

And the corollary: **the measurement nobody ran is worth more than the one three
lanes repeated.** Two lanes agreed that unversioned code was running on the
always-on node and escalated it to the owner; a third ran one `lsof` and it
dissolved.
