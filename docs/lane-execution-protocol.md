# Autonomous NouGen Lane Execution Protocol

Binding for every agent lane (Claude, Codex, Gemini, Antigravity, local models) that takes an
objective on the NouGenShards fleet. Referenced from `AGENTS.md` Rule 0.10. Operator-issued
2026-10-27; bound here to the tools and flags that actually exist in this repo and on the fleet
connector so that no stage names a primitive that does not.

## 1. Core directive

You own your objective end to end. You run a continuous, self-correcting loop until every
completion gate passes and the work is committed, verified, sharded and handed off. The loop
ends at Stage 7 and nowhere else.

## 2. Anti-bailout contract

- Do not end a turn on incomplete work while a path to resolution exists in your toolset.
- Do not stop at a diagnosis when you can implement the fix.
- Do not ask the operator for permission to fix a failing test, a lint or harden finding, or
  to retry a transient failure. Rule 0.0 already grants it.
- Do not leave untracked state, unverified code or unrecorded decisions. When an approach
  fails, pivot inside the same loop, record the failure vector, execute the alternative.
- Do not write "next steps for you", "what I didn't do" or "you will need to". The only
  admissible deferral is a gate that is genuinely outside the toolset (missing credential,
  branch protection, an operator-only action). Report it in the receipt as
  `BLOCKED: <exact blocker>` with everything else landed. Honesty is not a bailout; hiding a
  blocker is.

## 3. The deterministic loop

Stages run in order. Skipping a failed stage is not allowed; `--skip` and `--keep-going` on
`tools/nougen_loop.py` are for stages that do not apply to a change (for example `pr` with
`--no-pr` on a local-only experiment), never for a stage that failed.

### Stage 1: intake, claim, recall

1. Identity and field: `fleet_whoami`, `relay_claim_list`, `relay_open` / `relay_latest`.
2. Picking up fleet work: `relay_ack(id, note)` on the target leg.
3. Claim the files before editing (Rule 0.9): `python ~/.nougen/bin/lane_claim.py check <paths>`
   then `claim <paths> -g "<goal>"`. Claude Code sessions are claimed automatically by the
   edit hook; CLI claims under another holder name block it, so release a manual claim before
   editing from a Claude session.
4. Recall before reasoning: `shards_recall(query)` / `shards_search(query)` for invariants,
   prior decisions and known failure modes of the goal. Trained-data answers about fleet
   state are a defect (Rule 0.0.1).

### Stage 2: scoped implementation

1. Name the exact paths the change owns. Never stage a directory you did not review.
2. Implement the whole solution. No `TODO`, `FIXME`, `pass`-bodied functions or stubs.
3. Every env-, path-, port-, threshold- or model-shaped value resolves env -> config -> probe,
   with a logged fallback (Rule 0.2 #6).

### Stage 3: build and verification (self-healing)

1. Run the suite that covers the change (`PYTHONPATH=src pytest tests/<module>...`, then the
   full suite before the PR; `npm test` for the worker). On Blade run one full suite at a time
   and write output to a file: two concurrent runs collide on temp files and a `grep | head`
   pipe kills pytest early.
2. On any failure: read the exact traceback, fix the root cause, re-run. Repeat until green.
   Failures that reproduce on `main` unchanged are recorded in the PR body as pre-existing,
   with the test ids, and are not a reason to skip the stage.
3. `python tools/nougen_loop.py --goal "<goal>" --paths <paths> -m "<msg>"` is the dry run of
   the whole pipeline (recall -> build -> harden -> commit -> pr -> shard -> dream -> evolve
   -> handoff). Its build stage runs `NOUGEN_LOOP_TEST_CMD` and must be green on the executing
   machine before `--apply`.

### Stage 4: hardening gate

Scan every modified path for secrets, hardcoded credentials, personal data and oversized
files (the loop's `harden` stage; the repo-guard pre-push hook reports the same classes).
Remediate in code and re-run until clean. Secrets go through the Keymaker (Rule 0.3);
fingerprints only in output.

### Stage 5: branch, commit, PR

1. `python tools/nougen_loop.py --goal "<goal>" --paths <explicit paths> -m "<conventional
   commit>" --apply`, or the equivalent by hand: branch `loop/<goal>-<date>` (or
   `fix/`, `feat/`, `docs/` + slug), `git add <explicit paths>`, conventional commit with the
   session attribution lines, `git push -u origin <branch>`, `gh pr create`.
2. Never push to the default branch. Never `git add -A` or `git add .` (the lane guard
   blocks it). Review threads from Codex or the connector are fixed and resolved only after
   the fix has been pushed; a resolved thread ahead of the code is a false receipt.
3. Merge only when CI is green except known repo-wide jobs named in the PR body, and only
   with the merge rights the lane holds. A lane without merge rights ends the loop at the PR
   with a relay leg asking for the merge.

### Stage 6: durable memory and relay handoff

1. `shards_capture(title, content)`: the architectural finding, root cause, verification
   proof (commands and counts) and why the decision holds. Compress the message, never the
   sources: keep ids, paths, line ranges, error codes.
2. `relay_create(goal, message)`: final commit SHA, PR URL, verification status, and what is
   `BLOCKED` if anything. Do not route to `whoart` unless directed. On this repo's CLI the
   same record is `./tools/nougen handoff create -a <agent> -g "<goal>" -M <note file>` then
   `handoff rebuild-db`.

### Stage 7: terminal receipt

Only when Stages 1 through 6 have succeeded (or a gate is `BLOCKED` by something outside
the toolset) does control return to the operator.

## 4. Required terminal output

The final message is the receipt and nothing else:

```
Lane & Objective: [lane_id] - [goal]
Recall: OK | Build: OK (N/N tests, <command>) | Harden: OK | Commit: <sha> | PR: <url>
Shard: <id@db> | Relay: <leg_id> | Blocked: none | <exact blocker>
Changes landed: <exact paths> - <architectural delta in one line each>
Verification: <exact command> -> <pass count>; <live proof if delivery was claimed>
```

A receipt without a commit SHA, PR URL, test count and shard id is not a receipt; keep
working.

## 5. Tool and flag reference (verified 2026-10-27)

| Primitive | Where | Signature |
|---|---|---|
| `fleet_whoami`, `relay_claim_list`, `relay_open(limit)`, `relay_latest` | fleet connector `shards.nougenai.com/mcp` | no required args |
| `relay_ack` | fleet connector | `id` (required), `note` |
| `relay_create` | fleet connector | `goal`, `message` (both required) |
| `shards_recall` | fleet connector | `query` (required), `limit`, `summary` |
| `shards_capture` | fleet connector | `title`, `content` |
| `tools/nougen_loop.py` | this repo | `--goal --paths -m --body --repo --apply --skip {recall,build,harden,commit,pr,shard,dream,evolve,handoff} --no-pr --on-current-branch --keep-going --json` |
| `~/.nougen/bin/lane_claim.py` | fleet bin | `check <paths>`, `claim <paths> -g "<goal>"`, `release`, `status` |
| `./tools/nougen handoff` | this repo | `create -a <agent> -g "<goal>" -M <file>`, `rebuild-db` |
