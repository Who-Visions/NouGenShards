# Deploying the NouGenShards Node to Hugging Face — without leaking anything

The repo already contains everything the Space needs (`app.py`, `Dockerfile`,
README front-matter) and `.github/workflows/deploy-space.yml` auto-mirrors
`main` to the Space on every merge. The only missing inputs are two values
that must **never** pass through chat, commits, shell history, or logs.

## The one rule

Secrets travel exactly one hop: **from your keymaker/password manager into an
encrypted store's web UI.** Nothing else ever sees the value. Specifically:

- ❌ never commit them (`.env` is gitignored; keep it that way)
- ❌ never paste them into chat, issues, PR comments, or commit messages
- ❌ never pass them as CLI arguments (shell history) or `echo` them
- ✅ GitHub Actions automatically masks configured secrets (and their base64
  forms) in all workflow logs

## Setup (~60 seconds)

1. **HF token** — on huggingface.co: *Settings → Access Tokens → Create*.
   Use a **fine-grained** token scoped to *write* on the single target Space,
   not a global write token. Copy it.
2. **GitHub secret** — in this repo: *Settings → Secrets and variables →
   Actions → New repository secret*, name `NOUGENSHARDS_HGF_KEY3`, paste, save. The value
   enters GitHub's encrypted store (sealed-box) and is never displayable again.
3. **GitHub variable** — same page, *Variables* tab: `HF_SPACE` = your Space
   id, e.g. `nougenai/NouGenShards` (not secret; it's public anyway).
4. **Space write-auth** — in the Space: *Settings → Variables and secrets →
   New secret*, name `NGS_NODE_TOKEN`. Generate the value locally with
   `openssl rand -hex 32` (or let your password manager generate it) and store
   the same value in your local keymaker so the CLI can authenticate.
5. Optionally enable the Space's **persistent storage**; `app.py` auto-uses
   `/data` when present and still boots without it.

Then merge to `main` (or run the *Sync to Hugging Face Space* workflow
manually) and the node deploys. Point your CLI at it via `.env`:
`NGS_CLOUD_URL=https://<space-subdomain>.hf.space` + `NGS_CLOUD_TOKEN`.

## Why the pipeline itself can't leak

- The workflow reads `NOUGENSHARDS_HGF_KEY3` only from the encrypted secret store; Actions
  masks it in every log line, and the job skips (rather than errors) when the
  secret is absent, so nothing sensitive appears in failed-run output.
- `persist-credentials: false` keeps the workflow's GitHub token out of
  `.git/config` on the runner.
- The keymaker stores CLI-side keys in the OS keyring (DPAPI on Windows) —
  they live on your machine only and never ride along with the repo.
- `brain_scan/redaction.py` scrubs `hf_…`/`sk-…`-style tokens from any
  imported history before it is ever stored as shards.

## Rotation

Revoke and re-issue the HF token from huggingface.co, update the `NOUGENSHARDS_HGF_KEY3`
repo secret, done — nothing in the repo changes. Same for `NGS_NODE_TOKEN`
(update the Space secret + your keymaker entry together).
