---
name: nougen-root-cause
description: Use before proposing any fix for a bug, failed build, failed deploy, red CI, flaky test, or "it works on my machine" mismatch. Forces reading the real error and proving the cause before changing code. Not for planned features.
---

# nougen-root-cause

Method adapted from obra/superpowers `systematic-debugging` (MIT, Jesse Vincent), rewritten for the NouGen fleet and grounded in our own incidents. See Provenance at the bottom.

## Law
No fix until you can state the cause AND the evidence that proves it. A guess that happens to work still counts as a failure: you learned nothing and the next incident costs the same.

## Why this exists
A hosted build failed. Over ~20 minutes the team guessed three times: the secrets scanner, lockfile drift, a compile error. Each guess shipped a PR (one merged, harmless, wrong). The real error was one line in the host's dashboard log: a module that could not be resolved. Reading the log first would have saved the detour. Another time a deploy CLI hid its real error ("Uploaded file must be a non-empty zip") behind a generic message until `--debug` was added.

## The four steps
1. **Read the actual error, all of it.** Get the log from where it happened, not a summary. If the tool swallows the message, rerun with debug/verbose output or open the dashboard before theorizing. A claim like "likely the secrets scanner" is a hypothesis, never a finding.
2. **Reproduce in the SAME environment.** Same Node major, same install command (`npm ci` vs `npm install`), same env vars, same cache state. A pass on a different Node or a cached tree proves nothing about a failure elsewhere. Note every difference between your repro and the failing run.
3. **Compare against what worked.** Find the last good commit/deploy and diff. One changed input narrows the search faster than reading the whole stack. (The last good commit and the failing one differed by 7 files.)
4. **One hypothesis, one change, one check.** State it ("X fails because Y; if I change Z the error disappears"). Change one thing. Re-run the same repro. If it did not move, revert it and form a new hypothesis. Never stack fixes.

## Stop signs
- Third fix attempt failing: stop, you are guessing. Go back to step 1 and re-read the error.
- Fix works but you cannot say why: not done; keep digging or label it unexplained.
- "Probably cache / flaky / network": prove it by rerunning once, or it is a guess.
- Everyone's local build passes but the platform's fails: the bug is in the environment delta; find the delta.

## Team rules
- Before opening a PR for a guessed cause, say so in the PR title ("hypothesis: ...") and do not merge until evidence confirms it.
- When you find the real cause, share it so other lanes stop reproducing.
- Dashboards beat APIs for logs when the API returns nothing.

## Provenance
| element | source | taken | transformed | license |
|---|---|---|---|---|
| root-cause-first discipline, phased investigation | obra/superpowers systematic-debugging | the idea | rewritten around fleet incidents, environment-delta step added | MIT |
