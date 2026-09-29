---
name: plan-execute-autonomous
description: "Formalizes the Plan → Execute → Review → Deploy autonomous workflow. The AI creates its own implementation plan (stack selection, file structure, architecture), reviews it with the user, then executes the entire plan autonomously without stopping for permission at every step. Produces dramatically better results than direct prompting for complex builds (websites, apps, migrations)."
risk: medium
source: "nougentube:5ryZ6Tsco9c (AI Foundations - Opus 5.5 Website Build)"
date_added: "2026-09-28"
---

# Plan-Execute-Autonomous Pattern

## 1. The Pattern — Why it works
- Models that plan before building produce better architectures.
- Self-generated plans have higher execution fidelity (the model understands its own reasoning).
- Separating planning from execution prevents premature commitment.
- One planning prompt → autonomous execution → targeted review.

## 2. The 4-Phase Protocol

**Phase 1: PLAN (Interactive)**
- Agent analyzes the request, available context (files, videos, designs, requirements).
- Agent asks its own clarifying questions (stack choice, constraints, edge cases).
- Agent produces a structured plan:
  - Stack selection with rationale
  - File/directory structure
  - Implementation order (dependencies first)
  - Estimated complexity per component
  - Risk areas and fallback strategies
- User reviews and approves (or adjusts) the plan.

**Phase 2: EXECUTE (Autonomous)**
- Agent executes its own plan start-to-finish.
- No stopping for permission between steps (RULE 0.10: Finish The Race).
- Agent handles errors by referring back to its plan.
- Self-testing as it builds (unit tests, visual checks, type checking).
- Only stops for genuine blockers (missing credentials, ambiguous requirements).

**Phase 3: REVIEW (Interactive)**
- Agent presents the built artifact for review.
- Shows what was built vs. what was planned.
- Highlights creative decisions made during execution.
- User provides targeted feedback.

**Phase 4: DEPLOY (Autonomous with confirmation)**
- Agent handles deployment mechanics autonomously.
- Single confirmation before going live.
- Post-deploy verification (health checks, form tests, DNS propagation).

## 3. Plan Template
Agents should use the following markdown template when presenting a plan:

```markdown
## Implementation Plan

### Stack
- [tool]: [rationale]

### File Structure
\`\`\`
project/
├── src/
│   ├── ...
\`\`\`

### Implementation Order
1. [step] — [what and why]
2. ...

### Risk Areas
- [risk]: [mitigation]

### Estimated Effort
- Planning: done
- Execution: ~[X] minutes
- Review: ~[Y] minutes
```

## 4. When to Use This Pattern
- Complex builds (full websites, apps, migrations).
- Multi-file projects (3+ files).
- Projects with stack decisions to make.
- Any task estimated >30 minutes of execution.
- When the user says "build me X" without specifying implementation details.

## 5. When NOT to Use
- Quick fixes (single file, <5 minutes).
- Bug fixes with clear root cause.
- Tasks where the stack is already decided.
- Incremental changes to existing codebases.

## 6. Integration with Observatory Hierarchy
- **GM** sets the target ("build a paving website with this video").
- **Coach** creates the plan (Phase 1).
- **Player** executes the plan (Phase 2-4).
- Aligns with **RULE 0.10: Finish The Race**.
- Aligns with **RULE 0.13: Real execution, no fake acks**.

## 7. Evidence from the Field
- AI Foundations demo: Opus 5.5 planned a Vite + GSAP + Lenis + PHP stack, then executed 45 minutes of autonomous building.
- 680K-line code migration completed in <1 day using plan-then-execute.
- Creative decisions (gradient effects, animation choices) emerged during execution phase because the plan freed cognitive load.
