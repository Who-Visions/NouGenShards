# Skills

A skill is a set of standing instructions the agent must follow for a kind of work.
Skills are **not optional**: when one covers the task at hand, it supersedes the model's
own defaults.

## Layout

```
skills/
  <name>/
    SKILL.md        frontmatter (name, description) + the instructions
    ...             any supporting files the skill needs
```

`description` is the trigger surface — it is what the registry matches a task against, so
write it as "use this when…" rather than as a title.

## How they get used

The MCP server hands its client the skill roster at connection, then one call does the
rest:

| Tool | Use |
| --- | --- |
| `apply_skills(task)` | **The one to call.** Describe the work; get every governing skill back in full. |
| `list_skills()` | Names and descriptions only. |
| `load_skill(name)` | One skill by name. |

There is no list-then-load step. `apply_skills` resolves and returns the bodies together,
so following the rules costs one call rather than three.

## Where skills are found

Searched in order, first match wins on a name collision:

1. `NOUGEN_SKILLS_DIR` — one or more paths, separated by the platform path separator
2. this `skills/` directory, shipped with the repository
3. `<vault>/skills/` — where `evolve_skill` writes newly evolved skills

Skills written by `evolve_skill` land in the canonical layout and become available
immediately; nothing needs re-indexing.

`NOUGEN_SKILL_MATCH_MIN` (default `1`) sets how many shared terms make a skill apply.
The default is deliberately loose — a missed skill means work done wrong, while an extra
one costs a moment's reading.

## Installed

- **`design/`** — author, audit and emit design systems as portable `DESIGN.md` packages.
  Includes a validator with quality gates and three reference brand packages. Start from
  `design/brands/_template/`, not from one of the branded packages.
- **`e2b/`** — delegate summaries, distillations, classifications and first drafts to the
  local `gemma4:e2b-qat` Ollama lane instead of doing them inline (Rule 0.7: player
  drafts, coach reviews, GM decides). Carries the E-series call conventions and observed
  failure modes.
- **`nougen-ctx/`** — enforce NouGen Rule 0.0 & Context Mode. Use context-mode tools
  (`ctx_execute`, `ctx_execute_file`, `ctx_batch_execute`, `ctx_search`, `ctx_index`)
  instead of raw terminal output to save 98% context window.

## Writing one

```markdown
---
name: my-skill
description: Use this when <the trigger condition>. Covers <what it governs>.
---

# My Skill

The instructions. Be specific about what to do, not just what to care about.
```

Keep the body actionable. A skill that says "consider accessibility" changes nothing; one
that says "every interactive element gets a visible `:focus-visible` state, built from a
token that clears 3:1 against both surfaces" changes the output.
