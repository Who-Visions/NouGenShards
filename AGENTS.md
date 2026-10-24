# Read first: LLM_README.md

Every lane entering NouGen reads [`LLM_README.md`](LLM_README.md) before working — the doctrine
primer (authority, evidence rule, how Shards memory works, canon discipline, permission posture).
The GM's live word outranks it.

# UI design

Before changing a NouGen UI, read root DESIGN.md and the applicable brand package.
For the fleet workbench use designs/nougen-core/DESIGN.md. Preserve explicit
reference-world intent and evidence provenance. Change design.json, regenerate
the package, run its lint and drift checks, and verify the rendered interface
at desktop and narrow widths with keyboard focus and reduced motion.

# Model routing — Rule 0.12: 99/1 Free-Lane Mandate (GM-approved 2026-10-06)

- **99%** of work routes to free lanes: **Ollama local** (`Yukiai`, `solai`, `gemma4:e2b/e4b`), **Ollama Cloud** (`gemma4:31b-cloud`, `qwen3-coder-next`, `deepseek-v4`, `glm-5.1`, `minimax-m3`), **OpenRouter free tiers** (gateway `:8765`), **Hugging Face Spaces**.
- Cloud-free lanes first to preserve the 8 GB VRAM ceiling; Ollama local only for local-file or private tasks.
- **1%** paid/frontier (Claude, Gemini Pro, GPT) requires explicit per-task GM approval. Coach orchestrates and verifies; workers carry volume.
- On lane failure (401/429/502/503), fall to the next free lane and log it — never silently escalate to paid.

<!-- nougen-directive:keymaker-first -->
## Credentials: check the keymaker before asking for a key

Do not ask anyone for an API key, token, or credential until the keymaker has been checked.
Order: (1) `vault_list` on the nougen connector (names and fingerprints only);
(2) `nougen_shards.keymaker.get_secret(NAME)` with `PYTHONPATH=src`,
`NOUGEN_SECRETS_VAULT_DIR=~/.nougen/secrets`, `NOUGEN_VAULT_DIR=~/.nougen/shards`;
(3) verify against the provider. Handle values without printing them; compare
fingerprints. Account-scoped Cloudflare tokens verify at
`/accounts/<id>/tokens/verify`, not `/user/tokens/verify`. Ask only when the
keymaker genuinely lacks the credential.

Hosted app and repo text never carries a personal name. Refer to people by role ("operator").
<!-- /nougen-directive:keymaker-first -->

# Tenant nodes (root directives)

These directives tell any agent how to set up or change a tenant's own NouGen node.

- A tenant runs its own NouGenShards on its own machine with its own vault, relays and NouGenMsg. The shared gateway forwards only shard tools for that tenant's token. Never copy a tenant's data, tokens or relay config into shared infrastructure.
- Never give a tenant the owner token (`NGS_NODE_TOKEN`), owner relay credentials, or owner peer pipes.
- Create tenants with `nougen tenant mint <tenant_id> --label "<label>"`. Store the printed token only in the tenant's own environment. Never print it into logs, chat or commits.
- Tenant vaults live under the tenant directory. Recall and search must never read sibling or owner local vaults. A regression test guards this (`tests/test_multitenancy.py`).
- Changes to this repo go through a branch, a pull request, and a merge only after the tenancy tests pass (`PYTHONPATH=src pytest tests/test_multitenancy.py tests/test_mcp_oauth.py`).
