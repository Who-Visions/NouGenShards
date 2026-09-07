# Recipe card — Daily usage export + publish

**Status:** written from a run actually performed (phoebus, 2026-09-07). Every
failure mode below was hit, not imagined.

**Job:** keep this machine's usage dailies current and published, so fleet
totals and the public tracker node reflect reality.

---

## Sub-jobs

1. Bring the tracker clone level with `origin/main`.
2. Export dailies for yesterday..today.
3. Commit, then publish.
4. Verify the published state is what you think it is.

## Ask the operator first

- Is publishing to the **public** repo authorised? (`WhoVisions/NouGenTracker`
  is public. The dailies carry token counts, model names, machine, date — no
  paths, no session ids. Confirmed by inspection, not assumption.)
- Should a gap be backfilled, or left as an honest absence?

## The agent handles alone

Fetch, rebase, export, commit, verify, and the local half of everything below.

## Come back to the operator when

- publishing to the public remote (**approval boundary, every time**);
- a rebase conflicts on a file another lane wrote;
- the export reports days you cannot corroborate from source;
- a push is rejected twice.

## Access needed

The tracker clone, `token_tracker.py`, git push rights to `origin`. No secrets.

---

## Order matters — and this is the part that bites

**Rebase BEFORE exporting.** Exporting first and merging after produced a real
conflict on 2026-09-07: upstream held a *midday partial* for the same date
(`partial=True`, 1,096 invocations) while the local export held the *finished
day* (`partial=False`, 2,376). Both sides had legitimately written the same
file. Rebasing first means the export lands on current state and there is
nothing to conflict with.

If you do conflict, the finished day wins over a partial — but **assert it**,
do not eyeball it:

```
partial=False  invocations=2376   <- correct side kept
```

## Failure modes actually encountered

**A stale checkout invents gaps.** The clone was 8 commits behind. Listing
`dailies/<machine>/` locally showed `2026-09-06` "missing"; `origin/main`
already had it. **Fetch before you diagnose**, or you will report — and "fix" —
an absence that exists only in your working copy.

**"Days absent" does not mean "unexported".** The validator says so itself:
`calendar days absent: 113 (idle or unexported — not a defect)`. It cannot tell
them apart. Ten of twelve apparent gaps in one window were genuinely idle days.
The discriminator is **source data**, and the check that makes it evidence
rather than a guess is that transcripts survive *on both sides* of the gap — so
retention is not the explanation.

**Today's file is `partial=True` by design.** The day is still running. It needs
re-export tomorrow; that is the whole reason this job is scheduled rather than
run once.

**Committing can blind the relay watcher.** Any workflow that commits to `main`
and fails to push leaves the clone `ahead=1`, which kills `merge --ff-only`
forever after. Resolve with `git rebase origin/main && git push`, **never**
`reset --hard` — on 2026-09-07 the local commit carried a file upstream lacked.

## Scoring clause

> **The job is not done until the published state has been read back from the
> substrate.**

Not the exit code, not the tool's success line, not the PR field. On 2026-09-07
a merge command exited `0` without having merged, and a `grep` reported a phrase
absent that was present but line-wrapped. Verify by reading `origin/main`'s tree
and the file's own contents:

```bash
git fetch -q origin main
git ls-tree --name-only origin/main dailies/<machine>/ | sort | tail -3
```

If a step reports "clean", "0", or "already exists", ask what a *positive*
result would have looked like through the same instrument — and confirm the
instrument can still produce one.

## Automation on this node

`~/.nougen/bin/tracker_daily_publish.sh`, driven by `com.nougen.trackerdaily`
every 4h. It refuses to run over another lane's uncommitted work, rebases before
exporting, retries a rejected push once, and never force-pushes. `ProcessType:
Adaptive` — `Background` pins to PRI 4 here and a starved `git push` is
indistinguishable from a network failure.
