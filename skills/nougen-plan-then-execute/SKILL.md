---
name: nougen-plan-then-execute
description: Use when a task has several steps, touches production or shared repos, or will be split across fleet lanes. Produces a short checked plan (files, order, verification, rollback) before any edit; use after nougen design thinking and before nougen-loop. Not for one-line fixes.
---

# nougen-plan-then-execute

Adapted from obra/superpowers `brainstorming`, `writing-plans`, `executing-plans` and `subagent-driven-development` (MIT, Jesse Vincent). Compressed and rewritten for NouGen. See Provenance. (For high-risk missions, write a fuller war-game first; this skill is the lightweight version.)

## Law
Before touching code on a multi-step task: write the plan, name how each step is verified, and name how to undo it.

## 1. Pin the goal (2 minutes)
- One sentence: what changes for whom, and how we will know. If the ask is terse, pick the likeliest reading and say it ; do not interrogate the requester.
- List what is out of scope. A small ask can fan out into several repos; splitting it by deploy source keeps each step shippable.

## 2. Find the deploy source FIRST
For any website task, run the deploy-source check before planning edits: which repo and branch does the host actually build? (A repo labeled canonical may not be the one the host builds.) A plan that edits the wrong repo ships nothing.

## 3. Write the plan (keep it short)
For each step: files touched, command to verify, rollback. Order steps so the riskiest is last and each one leaves the system working.
- Tag each step with its lane: me, a peer lane, or a background job. Independent steps run in parallel; steps that share files or a deploy do not.
- Production steps are marked HUMAN GO. Nothing marked HUMAN GO runs without the owner's explicit word.

## 4. Execute in small verified slices
- One slice = one commit or one deploy, then verify it (see nougen-verify-before-claim).
- Delegation: when handing a slice to another lane, give it the goal, the files, the done-when evidence, and the lane rule (branch+PR only). Review its result before building on it; a peer's "pass" is a claim until you see the evidence.
- Claim lanes in the open (message @all) before long runs so two agents do not build the same thing (two agents once started the same deploy).

## 5. Close out
Shard the finding, post one relay leg, update the next owner. Record what you did NOT verify.

## Provenance
| element | source | taken | transformed | license |
|---|---|---|---|---|
| plan before code, small verified slices, subagent handoff discipline | obra/superpowers brainstorming, writing-plans, executing-plans, subagent-driven-development | the ideas | merged into one lightweight skill; added deploy-source step, lane claims, HUMAN GO marking | MIT |
