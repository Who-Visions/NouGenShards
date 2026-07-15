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

## Verifying privately before going public

Keep the Space **private** until every check passes; nothing below requires
it to be public.

1. **Automatic**: every deploy run now ends with a *Verify deployed node
   boots* step - it authenticates through HF's edge with the deploy token and
   polls `/health` until the new build reports its own commit sha. A green
   workflow means the new container actually booted.
2. **Browser**: open `https://<owner>-<name>.hf.space/health` while logged in
   to Hugging Face. It's a launch-readiness report:
   `public_ready: true` + an empty `warnings` list = safe to flip public.
   (`node_token_configured`, `hud_auth_configured`, `persistent_storage`,
   `total_shards`, `deploy_sha` are all shown; no secret values.)
3. **CLI / API against the private Space**: set `NGS_HF_TOKEN` (or reuse
   `HUGGINGFACE_API_KEY`) in your local environment - the cloud connector
   sends it as a bearer at HF's edge alongside the node's `X-NGS-Token`, so
   `nougen node push/pull` and `POST /search` work before the flip:
   ```bash
   curl -X POST https://<owner>-<name>.hf.space/search \
     -H "Authorization: Bearer $NGS_HF_TOKEN" \
     -H "X-NGS-Token: $NGS_CLOUD_TOKEN" \
     -H "Content-Type: application/json" -d '{"query":"test"}'
   ```

## Mobile: talk to your memory from the Claude app (remote MCP)

The node serves a **remote MCP endpoint** (streamable HTTP) at
`https://<owner>-<name>.hf.space/mcp` exposing `recall_memory`,
`capture_experience`, `mark_utility` and `node_status` — and nothing else
(code execution and brain scan stay stdio-local, off the network surface).

It is gated by the same `NGS_NODE_TOKEN` as the REST API, deny-by-default
(503 when the secret is unset, 401 on mismatch). Two ways to present it:

- Header: `X-NGS-Token: <token>` — for CLI/agents/MCP inspector.
- Query param: `?token=<token>` — for the Claude app's custom connectors,
  which can't attach custom headers.

**Claude app setup** (Settings → Connectors → Add custom connector):

```
https://<owner>-<name>.hf.space/mcp?token=<your NGS_NODE_TOKEN>
```

Then on mobile or web, enable the connector in a chat and Claude can recall
and capture against this node directly.

Timing note: connectors can't send the HF bearer, so this only works **after
the Space is public** (or on a paid private Space with a custom domain). While
still private you can verify the endpoint end to end with curl by adding the
bearer:

```bash
curl -X POST "https://<owner>-<name>.hf.space/mcp?token=$NGS_CLOUD_TOKEN" \
  -H "Authorization: Bearer $NGS_HF_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The query-param form does put the token in URLs (and therefore potentially in
proxy logs), which is the accepted trade-off for connector compatibility —
prefer the header everywhere a client supports it, and rotate
`NGS_NODE_TOKEN` if a URL ever leaks.

## Cortex HUD access (the vault UI at `/`)

The Gradio **Cortex HUD** — search, recon, substrate maps, and full vault
transcript dumps — is served at `/` and is **not** behind the node write-token.
On a network-reachable deploy (a Space, or any `NGS_HOST=0.0.0.0` bind) it is
therefore **fail-closed: not mounted at all unless you configure a login.**

- Set **both** `NGS_HUD_USER` and `NGS_HUD_PASSWORD` (Space *Settings →
  Variables and secrets → New secret*) to serve the HUD with basic-auth.
- Leave them unset and the HUD is simply withheld on an exposed host — the
  token-gated `/mcp` endpoint and the REST API (`/health`, `/search`,
  `/capture`, …) **still boot and serve normally.** The node never crashes over
  a missing HUD login; it just doesn't expose the unauthenticated vault UI.
- Loopback binds (`NGS_HOST=127.0.0.1`, the local-dev default) mount the HUD
  without a login for convenience.

`hud_auth_configured` in the `/health` readiness report tells you which mode a
running node is in.

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
