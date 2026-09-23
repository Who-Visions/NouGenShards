---
name: nougen-loop
description: Run one deterministic NouGen work loop on the current repo: recall related memory, run the tests, scan the change for secrets, commit only the named paths on a work branch, open or update a PR, capture a summary shard, run dream, record what changed since the last run, and write a handoff. Use when the user says "ship it", "commit and PR", "run the loop", "recurse / shard / dream / build / harden / evolve", or asks to finish a change end to end. Dry run by default; writes need --apply.
---

# nougen loop

One command runs the whole finish-a-change loop. The stage order and the gate rules are fixed code in `tools/nougen_loop.py`. The model picks the goal, the paths, and the message; it never decides which stages run or skips a gate.

## Stages (in order)

| Stage | What it does | Gate |
|---|---|---|
| recall | `nougen search "<goal>"` | skipped if no vault |
| build | runs the detected test command (pytest, npm test, or `NOUGEN_LOOP_TEST_CMD`) | stops the loop if red after `NOUGEN_LOOP_BUILD_ATTEMPTS` tries |
| harden | scans the named paths for secret-like strings and oversize files | stops the loop on any finding; prints file:line |
| commit | `git add -- <paths>` then commit on a work branch | never `git add -A`; creates `loop/<goal>-<date>` if you're on the default branch |
| pr | push + `gh pr create` (or updates the open PR) | refuses to push to the default branch; skipped without `gh` |
| shard | `nougen add --stdin --tags nougen-loop` with a run summary | skipped if no CLI |
| dream | `nougen dream wake` | skipped if no CLI |
| evolve | compares stage results to the last run in the ledger and appends this run | never edits code |
| handoff | `nougen handoff create -M <summary>` | skipped if no CLI |

Missing tools degrade to `skipped`, so the loop works in any git repo, not just NouGenShards.

## How to use it

1. Decide the exact files that belong in this change. Never pass a directory you haven't reviewed.
2. Dry run first and read the plan:
   ```bash
   python tools/nougen_loop.py --goal "fix flaky retry test" --paths src/pkg/retry.py tests/test_retry.py -m "fix(retry): bound backoff jitter"
   ```
3. If every stage shows OK or PLAN, apply:
   ```bash
   python tools/nougen_loop.py --goal "fix flaky retry test" --paths src/pkg/retry.py tests/test_retry.py -m "fix(retry): bound backoff jitter" --apply
   ```
4. Report the final stage table, the commit SHA, and the PR URL. If a stage failed, report its reason and evidence verbatim, fix the cause, and run the loop again. The evolve stage will show the stage flipping from failed to ok.

## Rules for the agent driving it

- A `FAIL` from build or harden is the answer. Fix the code or the finding. Don't add `--skip build` or `--skip harden` to get past it unless the user asks for that specific skip.
- `--keep-going` is for diagnosis only. Never combine it with `--apply` to force a commit past a failure.
- One loop per change. Don't batch unrelated fixes into one `--paths` list.
- Useful flags: `--no-pr` commits locally only, `--json` gives machine-readable results, and `--skip <stage>` is for stages the user opted out of.

## Configuration (all optional)

| Env var | Default | Purpose |
|---|---|---|
| `NOUGEN_LOOP_TEST_CMD` | auto-detect | explicit test command |
| `NOUGEN_LOOP_BUILD_ATTEMPTS` | 2 | retries before build fails |
| `NOUGEN_LOOP_STAGE_TIMEOUT` | 900 | seconds per stage |
| `NOUGEN_LOOP_MAX_FILE_KB` | 1024 | harden flags files larger than this |
| `NOUGEN_LOOP_EXTRA_SECRET_RE` | none | extra secret regexes, joined with `||` |
| `NOUGEN_LOOP_DEFAULT_BRANCH` | origin/HEAD, else main | protected branch |
| `NOUGEN_LOOP_LEDGER` | `~/.nougen/state/loop_ledger.jsonl` | evolve ledger |
| `NOUGEN_CLI` | `python -m nougen_shards.cli`, else `nougen` | NouGen CLI to call |
| `NOUGEN_AGENT` | nougen-loop | handoff author label |
