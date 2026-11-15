# pr_reviewer — the aiwithdav3 posting lane

A Bun script that reviews a GitHub PR on free model lanes and posts a real review as the
`aiwithdav3` reviewer account: APPROVE, REQUEST_CHANGES or COMMENT, with inline comments at
file:line. It never merges; the only write it makes is `POST /pulls/{n}/reviews`.

```bash
bun review.ts whoami                                  # which aiwithdav3 tokens answer (fingerprints only)
bun review.ts review Who-Visions/NouGenFlix 168       # review + post once for the current head SHA
bun review.ts review <repo> <n> --dry-run --fail-lane huggingface,openrouter   # prove the fallback
bun review.ts poll --owner Who-Visions                # the hook: new PR heads in recently pushed repos
bun review.ts score                                   # RSI pass (also runs at the end of every poll)
python prreview.py <repo> <n> --agent aiwithdav3       # single CLI entry: codex/agy read-only, or the aiwithdav3 posting lane (--post)
```

## Failsafe rules

| Rule | How |
|---|---|
| Right identity | Every keymaker token in `TOKEN_NAMES` must answer `GET /user` as `aiwithdav3` or it is dropped. Per repo, the first token that can read it is used (the fine-grained PAT reaches aiwithdav3-owned and public org repos; the classic token reaches private org repos). |
| Lane fallback | `huggingface` → `openrouter` → `ollama-cloud` (NouGenOpen worker via `bridge.py`) → local `gemma4:e2b-qat` → `agy`. |
| No silent approval | Empty output, or no parseable `{verdict, summary}`, is a lane failure. If every lane fails, nothing is posted. |
| Supervisor | A second lane, using a different model from the one that wrote the verdict, checks it and can drop findings. If no supervisor answers, the verdict is downgraded to COMMENT. If the supervisor disagrees, APPROVE becomes COMMENT. REQUEST_CHANGES needs a P1 finding. |
| Head SHA | The head SHA is re-read right before posting and pinned as `commit_id`. If the head moved, nothing is posted. |
| Once per SHA | The ledger, plus a live check of existing aiwithdav3 reviews on that `commit_id`. |
| Bad anchors | Findings need confidence ≥ 80. Lines must be RIGHT-side lines in the diff, or the finding goes in the body. If GitHub rejects the inline comments, the review is retried body-only. |

Logs go to `~/.nougen/research/reviews/aiwithdav3/`: a JSON file per review, `ledger.jsonl`, `run.log`, `scores.jsonl`, and `checklist/vN.json`.

## RSI loop

`score` looks at each posted review whose PR has since moved: a new push, or merged or closed.
- A finding counts as **held** if the follow-up diff touched its line (±3).
- Otherwise it counts as **dismissed**.

Per checklist item, the smoothed precision moves the item's weight. Items that keep getting dismissed pick up a "concrete failing input only" note, and recent dismissals become `lessons` in the prompt. Each pass writes a new `checklist/vN.json`, and the prompt names the version it used.

The seed checklist in `checklist.json` is distilled from aihero.dev `skills-code-review` and `skills-pr`, the aiskill.market PR-reviewer tutorial, and mcpmarket `pr-review-agent`. The Medium checklist returned 403 at fetch time and was not used.

## Hook

`install.ps1` copies the tool to `~/.nougen/bin/pr_reviewer` and registers the `NouGen-PRReviewer-aiwithdav3` scheduled task. The task runs every 20 minutes through `pythonw poll_task.pyw`, which starts bun with `CREATE_NO_WINDOW`. No console window opens, unlike `conhost --headless`, which still flashed one. Launcher failures go to `run.log`. It runs locally because it needs the keymaker. It polls `Who-Visions` repos pushed in the last 72 hours and reviews up to 4 new PR heads per run.

## Known

- HF Inference and Ollama Cloud free tiers are returning 402 (credits) on 2026-11-15, so OpenRouter and agy carry the load.
- The local e2b lane returned empty content on a 14k-character review prompt. It stays in the chain, and the chain moves past it.

## MCP

The `nougen-shards` server exposes `review_pr(repo, pr, dry_run=True)` and `pr_review_status(repo, pr, limit)`. `review_pr` stays off until the server has `NOUGEN_ENABLE_PR_REVIEW=1`. `pr_review_status` only reads `ledger.jsonl`.
