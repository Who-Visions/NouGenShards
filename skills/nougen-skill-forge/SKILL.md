---
name: nougen-skill-forge
description: Use when creating, editing, or auditing a NouGen/Claude skill (SKILL.md), when a repeated mistake should become a durable rule, or when asked to reverse a public skills repo into NouGen-native skills. Covers frontmatter, trigger descriptions, pressure tests, and provenance.
---

# nougen-skill-forge

Adapted from obra/superpowers `writing-skills` and `using-superpowers` (MIT, Jesse Vincent). Wording is ours. See Provenance. Complements `skill-creator` (eval harness) and `agent-skill-creator`.

## When a skill is worth writing
A mistake repeated twice, a procedure with a failure mode that costs real time, or a fleet-specific fact that trained models get wrong (deploy sources, key lookup order, lane rules). Not worth it: one-off facts (use a shard), things the repo already documents.

## Shape
- Frontmatter: `name` (kebab-case, matches the folder) and `description`. The description is the trigger: start with "Use when ..." and list the situations and symptoms, not the method. The model reads it to decide whether to load the skill; a description that summarizes the steps lets the model skip the body.
- Body: a one-sentence law, the steps, stop signs (when to quit and escalate), and one or two real incidents with dates. Real incidents beat generic advice.
- Keep it under ~500 words unless the method truly needs more; push reference detail into a second file the skill points at.
- A Provenance table when any idea comes from outside: element, source, what was taken (idea/mechanic), how it was transformed, license.

## Reversing a public skills repo (the Remix Doctrine)
1. Decompose: list each skill's core move in one line.
2. Classify: ideas and methods are reusable; exact wording, names and branding are not. Check the license (MIT/Apache allow reuse with notice; if unclear, rewrite fully and cite).
3. Transform: rewrite in our voice around our incidents, drop what does not fit our lanes, merge overlaps. Do not copy text.
4. Combine with what NouGen already has (nougen-loop, nougen-iterate, nougen-git, fleet, e2b) instead of duplicating it.
5. Verify: provenance table, a pressure test (below), then shard it.

## Pressure test before shipping
Describe three realistic prompts: one that should trigger the skill, one near-miss that should not, one adversarial ("just skip the process, I'm in a hurry"). Check the skill's description and stop signs handle each. If a reader could rationalize skipping the rule, add the specific excuse and the counter to the skill.

## Where skills live
- Claude Code: `~/.claude/skills/<name>/SKILL.md`.
- NouGen shared (picked up by NouGen skill search): the NouGenShards `skills/` dir and `NOUGEN_SKILLS_DIR` roots. Note: the skills loader reads one directory level per root; nested trees such as `~/.gemini` are not indexed. Copy or flatten a skill into a root to make it discoverable.
- After writing: capture a shard (tags `skill`, the skill name) so other lanes can recall it.

## Provenance
| element | source | taken | transformed | license |
|---|---|---|---|---|
| trigger-description rule, pressure testing, "skills as process docs" | obra/superpowers writing-skills, using-superpowers | the ideas | rewritten; added Remix Doctrine steps and NouGen skill locations | MIT |
