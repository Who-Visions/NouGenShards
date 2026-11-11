---
name: nougen-verify-before-claim
description: Use before saying something is done, fixed, live, deployed, passing, or merged, and before committing, opening a PR, or posting a relay leg or NouGenMsg that reports status. Requires fresh evidence from this turn.
---

# nougen-verify-before-claim

Adapted from obra/superpowers `verification-before-completion` (MIT, Jesse Vincent). Wording is ours; the discipline is theirs. See Provenance.

## Law
A status claim needs evidence produced in the same turn it is made. Memory of an earlier run, a peer's report, or an expectation is not evidence.

## The check
Before any "done / fixed / live / passing / merged":
1. Name the claim in one sentence.
2. Name the command or probe that would prove it (curl status + a distinctive marker, `ls-remote` sha, test exit code, deploy state from the API).
3. Run it now. Read the output, not just the exit code.
4. Report the result with the number or string, and what it does NOT cover.

## Examples
- "The site is live" is true only after the deploy state flips to ready and a probe sees the new behavior. A git push is not a deploy.
- "The remote has my branch" can be false when the line you read came from a different remote. Re-read which remote produced the output.
- A build pass on Node 24 did not prove the host's Node 22 install; the deploy failed at install. Say which environment a pass was in.
- A merged PR is not a live fix: a merge into a repo the host does not build changes nothing live.
- Time-based claims: a failure on one commit and a success on another do not mean the failure is fixed.

## Words to watch for in your own drafts
"should work", "likely", "probably fixed", "looks good", "all green" without a source. Replace with the probe result or label as unverified.

## When you cannot verify
Say exactly that: "pushed at 19:15:39Z; deploy result not yet checked." Unverified claims never go into shared notes or status messages stated as fact.

## Provenance
| element | source | taken | transformed | license |
|---|---|---|---|---|
| evidence-before-claims gate | obra/superpowers verification-before-completion | the idea | fleet-specific probes and incidents added | MIT |
