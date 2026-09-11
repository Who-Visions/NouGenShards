---
name: agent-skill-creator
description: Autonomous skill generation, testing, iteration, benchmarking, and frontmatter optimization for NouGen, Antigravity, and Claude Code agent architectures.
version: 1.0.0
---

# 🧬 Agent Skill Creator (NouGen Shang Tsung Edition)

`agent-skill-creator` brings software engineering rigor (eval-driven development, semantic trigger optimization, variance benchmarking, and execution isolation) to agent skill creation across the Observatory fleet. It structures raw workflows into production-grade agent skills packaged with executable specifications, verification test suites, and 9-DB substrate sharding.

---

## 🏛️ 1. Core Operating Modes

The skill lifecycle consists of four continuous phases:

1. **Create (Authoring & Scaffolding)**:
   - Takes a domain workflow or tool integration and synthesizes a canonical `SKILL.md`.
   - Structures clean YAML frontmatter (`name`, `description`, `version`).
   - Ensures descriptions specify exact triggers to minimize false positives and false negatives.
2. **Eval (Test-Driven Verification)**:
   - Generates deterministic test cases (prompts + expected tool invocations / assertions).
   - Validates that an agent equipped with the skill solves the task without unnecessary steps or token waste.
3. **Improve (Trigger & Content Tuning)**:
   - Compares multi-model execution logs to find ambiguity or failure modes.
   - Refines instruction clarity, adds boundary constraints, and hardens checklists.
4. **Benchmark (Variance & Performance Audit)**:
   - Evaluates token efficiency, step count, latency, and success rates across swarm nodes.

---

## ⚡ 2. Canonical Skill Structure

```
skills/<skill-name>/
├── SKILL.md          # Required: YAML frontmatter + deterministic playbook
├── tests/            # Optional: Automated verification suite (pytest / bun test)
├── scripts/          # Optional: Executable CLI utilities or automation tools
└── examples/         # Optional: Reference implementations and code samples
```

### Frontmatter Protocol
```yaml
---
name: my-specialized-skill
description: Concise 1-2 sentence description explaining WHAT the skill does and EXACTLY WHEN an agent should trigger it.
version: 1.0.0
---
```

---

## 🔄 3. End-to-End Skill Creation Workflow

### Phase 1: Requirement Analysis & Boundary Definition
- Identify the target task, required tools, runtime prerequisites, and failure modes.
- Define what the skill **does** vs what it **must not do** (guardrails).

### Phase 2: Playbook Synthesis
- Structure the guide into clear, actionable sections:
  1. Core Principles & Theoretical Models
  2. Canonical Code Patterns & Workflows
  3. Edge Cases & Safety Constraints
  4. Code Review / Quality Checklist

### Phase 3: Substrate Ingestion & Cluster Synchronization
- Ingest the newly authored skill directly into the 108K+ NouGen shard cluster:
```bash
nougen add --tags "skill,agent,engineering,<domain>" --stdin < skills/<skill-name>/SKILL.md
nougen search "<skill-name>"
```

### Phase 4: Git Branch, CI Verification, & Merge
- Follow standard fleet pull request workflow:
```bash
git checkout -b feat/<skill-name>
git add skills/<skill-name>/SKILL.md
git commit -m "feat(skills): Shang Tsung absorb <skill-name>"
git push -u origin feat/<skill-name>
gh pr create --title "feat(skills): Shang Tsung absorb <skill-name>" --body "..."
gh pr checks <pr-number> --watch
gh pr merge <pr-number> --squash --delete-branch
```

---

## 📋 4. Skill Quality Checklist

- [ ] Does the YAML frontmatter have a clear, trigger-specific `description`?
- [ ] Is the skill deterministic, self-contained, and devoid of placeholder comments?
- [ ] Are code examples modern, syntactically valid, and strictly typed?
- [ ] Has the skill been sharded into the 108K+ NouGen substrate cluster?
- [ ] Are CI tests, security scans, and linting passing 100% green on PR?
