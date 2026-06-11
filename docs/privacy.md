# Privacy Policy

**NouGenShards is local-first by design.**

## 🏠 What stays on your machine
By default, all data you "capture" or "add" to NouGenShards is stored in local SQLite databases located at `~/.nougen/shards/`.
- **Shards**: Your history of work, code snippets, and outcomes.
- **Context**: Ephemeral session logs and sandbox outputs.
- **Vault**: Your API keys and database connection strings (encrypted/protected by your OS user permissions).

## ☁️ What is sent to the Cloud

### 1. Local Mode
- **No data leaves your machine.**
- All inference is handled by local providers like Ollama or LM Studio.

### 2. BYOK (Bring Your Own Key) Mode
- If you use a cloud provider (OpenAI, Anthropic, OpenRouter), your **queries and relevant memory shards** are sent to that provider.
- This data is sent directly from your machine to the provider's API.
- Who Visions does not see or store this data.

### 3. Who Visions Cloud (Pro) Mode
- If you use the `whovisions_cloud` mode, your queries and relevant shards are sent to the **Who Visions Gateway**.
- We use this data to perform inference and return the result to you.
- We log **Usage Metadata** (token counts, model IDs, timestamps) for billing and analytics.
- We do **not** use your private memory shards for model training.

### 4. Federated Cloud Nodes
- If you explicitly link a remote NouGen node (`nougen node link`), your search queries are sent to that specific node to retrieve remote shards.

## 🛡️ Secret Handling
- We recommend using `nougen auth set-key` to store keys in the local secure vault.
- Never commit your `.env` file or your `.nougen_vault` directory to source control.
