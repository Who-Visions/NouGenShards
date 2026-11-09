---
name: nougen-review-loop
description: Use when requesting a review of your own change, receiving review comments (from another agent or a human), or deciding whether a peer lane's PR is safe to merge. Covers what to ask reviewers, how to verify a finding before acting, and when to push back.
---

# nougen-review-loop

Adapted from obra/superpowers `requesting-code-review` and `receiving-code-review` (MIT, Jesse Vincent). Rewritten for the fleet. See Provenance.

## Requesting a review
- Review the diff, not the summary. Give the reviewer: the goal, the commit range, the risk you are least sure about, and which environment you tested in (Node version, install command).
- Ask a targeted question ("does the new server action change who can reach the upstream?") rather than "looks good?". Cross-lane review (codex-review, gemini-review skills) catches what the author is blind to; one cross-lane review caught that a build fix had turned a dead call into an unauthenticated outbound request.
- A review finding names the evidence it inspected. "Static read only, no tests run" is valid but must be stated.

## Receiving a review
1. Read the whole comment. Restate the finding in your own words.
2. **Verify before acting.** Open the code at the cited line; confirm the claim is true in the current head, not a stale one. (Reviews sometimes target a commit that has already merged and been superseded.) If it is false or already fixed, answer with the evidence instead of changing code.
3. Rank: security and data loss first, correctness second, style last. Fix in that order, one change per commit.
4. Push back when a suggestion is wrong for this repo, with the reason and a probe. Do not agree performatively; do not fix what you have not understood.
5. Report: finding, what you checked, what you changed, the new head sha.

## Before merging a peer's PR
- Is the gate evidence in the same environment the host builds in? (A Node 24 pass did not predict a Node 22 host failure.)
- Does the PR change who can call something, or what costs money? Those get a second look even when small.
- Merge only what you have a green gate for; production cuts need the owner's explicit go.

## Fleet etiquette
- Route a review finding to the PR owner via NouGenMsg with the file, line, and acceptance check. Do not fix over another lane's in-flight work.
- Close the loop: when a fix lands, say so to the reviewer with the sha.

## Provenance
| element | source | taken | transformed | license |
|---|---|---|---|---|
| request/receive review discipline, verify-before-implementing | obra/superpowers requesting-code-review, receiving-code-review | the ideas | rewritten with fleet cross-lane practice and today's incidents | MIT |
