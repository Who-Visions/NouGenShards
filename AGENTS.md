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
