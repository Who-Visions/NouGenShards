# 🛡️ Security Policy

## Responsible Disclosure
If you find a security vulnerability in NouGenShards, please do not open a public issue. Instead, email us at security@whovisions.com. We aim to acknowledge reports within 48 hours and provide a fix or mitigation plan as quickly as possible.

## Secret Handling
- **Vault Security**: NouGenShards stores API keys and connection strings in a local SQLite database (`shards_secrets.db`). On most systems, this directory is protected by your user-level filesystem permissions.
- **Zero Leak Policy**: The CLI and Node API are designed to redact secret values in all logs and terminal outputs.
- **Environment Variables**: We support `.env` files for configuration. **NEVER** commit your `.env` file to a public repository. We provide `.env.example` as a template.

## Data Isolation
- By default, your data is **not** shared with Who Visions or any third party.
- If you use a Cloud Node or a Cloud Model, only the data required for that specific operation is transmitted.

## Third-Party Dependencies
We audit our core dependencies (`fastapi`, `sqlalchemy`, `mcp`, `uvicorn`) regularly. If you find a vulnerable dependency in our `pyproject.toml` or `package.json`, please report it.
