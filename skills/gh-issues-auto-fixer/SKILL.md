---
name: gh-issues-auto-fixer
description: Autonomous GitHub issues triage, sub-agent diagnosis, reproducible test synthesis, minimal surgical patching, automated PR lifecycle management, and CI review comment resolution.
version: 1.0.0
---

# 🛠️ GitHub Issues Auto-Fixer (NouGen Shang Tsung Edition)

`gh-issues-auto-fixer` provides autonomous closed-loop diagnosis and repair of GitHub issues across the NouGen fleet. It enforces rigorous engineering discipline: understanding the root cause, synthesizing a failing test first, applying minimal surgical edits, and pushing clean PRs that auto-link and close issues upon CI pass.

---

## 🏛️ 1. Core Operating Principles

1. **Anti-Simulation Law (Rule 0.13)**:
   - An issue is never closed or marked resolved by modifying status metadata alone.
   - Every fix requires concrete engineering artifacts: written code, passing automated tests (`pytest`, `bun test`), verified commit hashes, and clean CI runs.
2. **Reproduce First (Test-Driven Repair)**:
   - Before editing functional code, write a reproducer test that demonstrates the bug and fails (`RED`).
   - Run the patch and verify the test passes (`GREEN`).
3. **Minimal Surgical Scope**:
   - Limit modifications strictly to the issue's root cause.
   - Do not bundle unrelated refactors, styling updates, or scope creep into bug fix PRs.
4. **Autonomous PR Lifecycle**:
   - Create a dedicated branch: `fix/issue-<number>-<slug>`.
   - Open PR with clear title: `fix(<scope>): <description> (closes #<number>)`.
   - Monitor CI checks to green, resolve automated review comments, and squash-merge when authorized.

---

## ⚡ 2. End-to-End Execution Workflow

### Phase 1: Ingestion & Root Cause Analysis
```bash
# 1. Fetch issue details and comments
gh issue view <issue-number> --json title,body,comments,author,labels

# 2. Search codebase for error traces, function names, or cited files
git grep -n "<pattern_or_symbol>"
```

### Phase 2: Failing Reproducer Test Synthesis
- Craft an isolated test case replicating the exact failure report in `tests/test_issue_<number>.py` or adjacent test module.
- Execute to confirm `RED` failure:
```bash
pytest tests/test_issue_<number>.py -v
```

### Phase 3: Surgical Patch & Verification
- Apply the targeted fix.
- Verify reproducer test and surrounding suite:
```bash
pytest tests/ -k "test_issue_<number>" -v
```

### Phase 4: Commit, Branch, & PR Automation
```bash
git checkout -b fix/issue-<number>-<slug>
git add <modified_files>
git commit -m "fix(<scope>): resolve <problem_statement> (closes #<number>)"
git push -u origin fix/issue-<number>-<slug>

gh pr create \
  --title "fix(<scope>): resolve <problem_statement> (closes #<number>)" \
  --body "Autonomous fix for #<number>.

### Root Cause
<description_of_bug>

### Solution
<description_of_fix>

### Verification
- Added reproducer test in \`tests/test_issue_<number>.py\`
- Verified full test suite passes locally
- Auto-closes #<number> upon merge."
```

### Phase 5: CI Review & Automated Comment Resolution
- Watch GitHub Actions checks until green:
```bash
gh pr checks <pr-number> --watch
```
- If review comments or CI failures occur, ingest annotations via `gh api repos/<owner>/<repo>/check-runs/<run_id>/annotations`, patch surgically, commit, push, and re-verify.

---

## 📋 3. Auto-Fixer Quality Checklist

- [ ] Has the issue been reproduced with a verifiable test case?
- [ ] Are edits limited to the minimal surgical diff required?
- [ ] Does the PR description explicitly link and close the target issue (`closes #<id>`)?
- [ ] Are all security, lint, and unit test CI checks 100% green?
- [ ] Was the PR merged with clean squash history?
