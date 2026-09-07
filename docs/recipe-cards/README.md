# Recipe cards

A recipe card is the artifact between a prompt and a spec. It names a real job,
sketches its sub-jobs, and states what the agent must **ask** for, what it
**handles alone**, when it must **come back**, and which actions need
**approval**.

`../hardcade-lexicon.md` is the *grammar* — the verbs, the stop conditions, the
evidence gates. These are the *cards*: the grammar applied to one job each.

## The rule that is ours

A card that says what to DO and when to COME BACK is half a card. **It must also
say how a claim is scored.** On 2026-09-07 this fleet spent a day where every
single incident had one shape — *a summary outranked the artifact it
summarized*: `complete:true` over timed-out lanes, `captured:false` over durable
writes, a merge command exiting `0` without merging, an "unread" count that was
a lifetime total, eight absent credential names returned by a working probe with
a valid positive control and still the wrong answer.

A long autonomous run does not fail loudly. It accumulates confident wrong state
and reports success. So every card ends with a **scoring clause**:

> a target is not scored until the claim has been checked against the substrate
> it describes, on the node the response named.

## Writing one

Write a card only for a job you have **actually run**. The value is in the
failure modes you hit, not the happy path you imagine. If you have not run it,
you are writing a spec, and specs are what recipe cards exist to replace.

## Cards

- [Daily usage export + publish](daily-usage-export.md)
