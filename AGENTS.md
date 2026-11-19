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

- A tenant runs its own NouGenShards on its own machine with its own vault, relays and NouGenMsg. On a shared node a tenant token gets the full NouGen tool surface scoped to the tenant's own root (`<NOUGEN_TENANT_VAULT_ROOT>/<tenant_id>/`: shards, secrets, relay legs, message inboxes, destinies), never a shard-only stub (operator decision 2026-10-14, vault shard 30954). Tools that touch the host machine, the owner's agents, hardware, GitHub token, shared session store or author IP stay owner-only; the labels live in `nougen_shards/tenant_policy.py` and `tests/test_tenant_full_surface.py` fails on any unlabelled tool. Never copy a tenant's data, tokens or relay config into the owner's vault or relay.
- Never give a tenant the owner token (`NGS_NODE_TOKEN`), owner relay credentials, or owner peer pipes.
- Create tenants with `nougen tenant mint <tenant_id> --label "<label>"`. Store the printed token only in the tenant's own environment. Never print it into logs, chat or commits.
- Tenant vaults live under the tenant directory. Recall and search must never read sibling or owner local vaults. A regression test guards this (`tests/test_multitenancy.py`).
- Changes to this repo go through a branch, a pull request, and a merge only after the tenancy tests pass (`PYTHONPATH=src pytest tests/test_multitenancy.py tests/test_mcp_oauth.py`).

---

## Rule 0.10: Autonomous Lane Execution Protocol (binding, 2026-10-27)

Every lane that takes a NouGenShards objective runs the closed loop in `docs/lane-execution-protocol.md`: claim + recall, scoped implementation, self-healing build, hardening, branch + PR (never the default branch, never `git add -A`), durable shard + relay handoff, and a terminal receipt with commit SHA, PR URL, test count, shard id and relay leg. A turn may not end on a diagnosis when the toolset can land the fix. A gate that is genuinely outside the toolset (missing credential, branch protection, operator-only action) is reported as `BLOCKED: <exact blocker>` in the receipt, never hidden and never softened into "next steps for you".
