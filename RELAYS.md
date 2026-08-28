# Handoffs in This Repository

This repository contains the legacy provider-specific handoff store:

- Antigravity/Gemini: `.handoffs/gemini handoffs/`
- Claude app: `.handoffs/claude handoffs/`
- Claude CLI: `.handoffs/claude cli handoffs/`
- Codex: `.handoffs/codex handoffs/`

Antigravity's old `handoffs sync` path writes to `gemini handoffs`. Read the
newest paired `.md` and `.json` files there when an Antigravity relay is not
visible in the canonical registry.

The canonical cross-machine registry is:

`C:\Users\super\Watchtower\NouGen\NouGenRelay\.handoffs`

See `C:\Users\super\Watchtower\NouGen\RELAYS.md` for the full lookup, refresh,
and migration rules. New relay integrations should write to the canonical
registry; this legacy store remains a compatibility input.

