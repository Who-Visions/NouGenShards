# War-Game Success Criteria (Rule 0.1 done-bar)

## A war-game file is complete when:
1. Every move states: the action, the expected observation if it worked, the failure signal if it didn't, and the countermove.
2. Every fork has an observable trigger ("if you observe X → route A, else B") — no linear blue-sky sequences.
3. The intended executor model/lane is named in the header, and the brief is written for that harness (not for the author).
4. Unresolved inputs appear as `(variable)` placeholders and are mirrored in `ledger.md` — never fabricated.
5. It ends with explicit abort conditions.
6. Second/third-order consequences of the mission are noted (what breaks two moves downstream).

## The NouGen system beats raw Fable when (system-level scoreboard):
- **Recall**: paraphrase queries (meaning, not keywords) return the right shard in top-5 at ≥ 80% on a 10-query probe set.
- **Execution**: a fleet-lane executor (gemma family) following a war-game completes the mission with fewer retries and no more escalations than a raw frontier run of the same mission.
- **Cost**: mission completes on free/local lanes; frontier credits spent only on single escalated moves, never whole missions.
- **Compounding**: every completed mission captures shards back to the vault (fixes, gotchas, countermoves that fired), so the next run starts smarter.
