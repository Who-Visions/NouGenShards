---
name: pr-reviewer
description: Use whenever a PR needs the aiwithdav3 reviewer — "have aiwithdav3 review it", a merge guard wants a non-author approval, land_pr.sh refuses for lack of an approving review, a review did not post, or the poll task looks dead. Covers the single CLI (prreview.py), the Bun posting lane (review.ts), lane fallback, supervisor, once-per-SHA ledger, RSI checklist loop, the scheduled hook, the MCP tools review_pr / pr_review_status, and the traps. Does not cover the codex/agy read-only second-opinion flow beyond its flag (pr-review-loop) or merging (nougen-git).
---

# pr-reviewer — aiwithdav3, the failsafe review lane

Source: `Outpost/NouGenShards/tools/pr_reviewer/` (PR Who-Visions/NouGenShards#1079). Live copy: `~/.nougen/bin/pr_reviewer/` (installed by `install.ps1`). It never merges. Its only GitHub write is `POST /pulls/{n}/reviews`.

## Use

```bash
python tools/pr_reviewer/prreview.py Who-Visions/<repo> <n> --agent aiwithdav3   # post a review (single entry point)
python tools/pr_reviewer/prreview.py Who-Visions/<repo> <n> --post               # codex review + aiwithdav3 post
bun ~/.nougen/bin/pr_reviewer/review.ts review <repo> <n> --dry-run               # review, don't post
bun ~/.nougen/bin/pr_reviewer/review.ts whoami                                    # token check, fingerprints only
bun ~/.nougen/bin/pr_reviewer/review.ts score                                     # RSI pass
```
MCP (nougen-shards): `review_pr(repo, pr, dry_run=True)` (it only runs when the server has `NOUGEN_ENABLE_PR_REVIEW=1`) and `pr_review_status(repo, pr)` (reads the ledger).

## How it decides
- **Identity:** every token in `TOKEN_NAMES` must answer `GET /user` as `aiwithdav3`. The keymaker holds three names: `AIWITHDAV3_GITHUB_PAT_20261115` (fp e422cd61eacc, fine-grained), `GITHUB_TOKEN_AIWITHDAV3_CLASSIC_20261112` (fp e44307cf2eef, private org repos) and `GITHUB_TOKEN_AIWITHDAV3` (fp c6f69062e154). For each repo it uses the first token that can read that repo.
- **Lanes:** huggingface → openrouter → ollama-cloud (NouGenOpen via `bridge.py`) → local gemma4:e2b-qat → agy. An empty reply or an unparseable verdict counts as a lane failure, never as an approval.
- **Supervisor:** a different lane or model re-checks the verdict. If no supervisor answers, or the supervisor disagrees, an APPROVE becomes a COMMENT. A REQUEST_CHANGES needs a P1 finding.
- **Head pin:** the SHA is re-read just before posting and sent as `commit_id`. If the head moved, it aborts. It posts once per repo#pr@sha: it checks the ledger and also looks for an existing aiwithdav3 review.
- **RSI:** `score` treats a finding whose line the follow-up push touched (±3) as held, and anything else as dismissed. The scores re-weight `checklist/vN.json` and add lessons to the prompt.
- **Hook:** scheduled task `NouGen-PRReviewer-aiwithdav3`, every 20 min. It runs `pythonw poll_task.pyw` → `bun review.ts poll --owner Who-Visions --since-hours 72 --max 4`.

## Logs
`~/.nougen/research/reviews/aiwithdav3/`: one `<repo>-<n>-<sha>-<stamp>.json` per review, plus `ledger.jsonl`, `run.log` (launcher and poll failures), `scores.jsonl` and `checklist/`.

## Traps
- **Window flash:** `conhost --headless` and `-WindowStyle Hidden` still flash a console. Launch through `pythonw` with `CREATE_NO_WINDOW` (poll_task.pyw).
- **402 is not down:** the HF and Ollama Cloud free tiers return 402 when credits run out (11/15). The chain keeps going, and OpenRouter and agy carry the load.
- **Big prompts on e2b:** e2b returns empty content on prompts of about 14k characters. That is expected; the chain moves on.
- **Token can't write:** the fine-grained PAT can't review private org repos. That is why the classic token stays in the list. Never overwrite a keymaker name; add a dated one.
- **Disk full:** at 0 bytes free, bun and the poll fail silently. Check `run.log` and free C: first.
- **Edits to `~/.nougen/bin` are not landed:** change the repo copy, re-run `install.ps1`, then open a PR.
- **Never merge from here:** a merge needs an approving non-author review. A COMMENT does not unlock the guard.
