---
name: structured-git-commit-messages
description: Generates structured, conventional git commit messages based on staged changes. Use when drafting commit messages, inspecting git diffs, or standardizing git history across the fleet.
---

# Structured Git Commit Messages

Generates clear, concise, and conventional Git commit messages following the Conventional Commits specification.

## Workflow

1. Run `git status` and `git diff --staged` to inspect changes ready for commit.
2. If nothing is staged, prompt or suggest staging specific modified paths.
3. Analyze the scope, architectural impact, and intent of the modifications.
4. Draft a commit message adhering to Conventional Commits:
   ```text
   <type>(<scope>): <short summary in imperative mood>

   [optional body explaining WHAT and WHY, not HOW]

   [optional footer for breaking changes or issue/shard references]
   ```
5. Apply the commit cleanly without polluting working trees or uncommitted files.

---

## Core Commit Types

- **`feat`**: A new feature or capability.
- **`fix`**: A bug fix or error resolution.
- **`docs`**: Documentation-only changes.
- **`refactor`**: Code changes that neither fix a bug nor add a feature.
- **`perf`**: Performance optimizations (speed, memory, token usage).
- **`test`**: Adding missing tests, correcting tests, or updating test suites.
- **`chore`**: Maintenance, build process, dependency updates, or auxiliary scripts.
- **`relay`**: Fleet-specific relay hops, handoff updates, or leg closures.

---

## Invariants & Rules

1. **Imperative Mood**: Use imperative present tense ("add", "fix", "wire", "refactor") rather than past tense ("added", "fixed").
2. **Character Limits**: Keep the summary line under 72 characters.
3. **No Trailing Periods**: Never terminate the summary line with a period.
4. **Breaking Changes**: Mark breaking architectural changes with a `!` after the type/scope (e.g., `feat(api!): ...`) and document details in the footer starting with `BREAKING CHANGE:`.
5. **Human-Professional Tone**: Maintain clear, engineering-grade messages free of robotic filler or unnecessary boilerplate.
