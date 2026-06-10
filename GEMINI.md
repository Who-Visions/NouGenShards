# NouGenShards Constitution

## SECTION 0: PRODUCT-BUILD BOUNDARY

1. **Internal Build Neutrality**: The source code of this project must remain neutral. No internal build tools, personal API keys, or development-specific orchestration scripts (e.g., `fleet_query.py`) shall be committed to the repository.
2. **User Autonomy**: All cloud features (OpenAI, Anthropic, Gemini, OpenRouter) must strictly use the "Bring Your Own Key" (BYOK) model. No default keys or "Internal Coach" fallbacks are permitted in the source.
3. **Public Integrity**: Public documentation (README, etc.) and interfaces (Hugging Face Spaces) must focus strictly on the user perspective. Internal technical jargon (e.g., "Coach", "Stadium", "Stadium Physics") is restricted to build logs and constitutional reasoning; it must not appear in user-facing code or Gradio apps.

## SECTION 1: CORE ARCHITECTURE

1. **Shard Layer**: Persistent local memory using SQLite + FTS5.
2. **Multi-DB Sharding**: Horizontal scaling across 9 databases, each capped at 1GB.
3. **Context Layer**: Ephemeral session memory with sandboxed execution.
4. **Universal Interface**: Unified binary `nougen` for all operations.

## SECTION 2: QUALITY & HARDENING

1. **Zero Side-Effects**: Modules must not perform initialization (e.g., `init_db`) on import.
2. **100% Pass Rate**: No feature is complete without matching unit tests.
3. **Pylint Standard**: Aim for 10.00/10 on all core modules.
