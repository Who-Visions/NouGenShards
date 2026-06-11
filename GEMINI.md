# NouGenShards Constitution

## SECTION 0: PRODUCT-BUILD BOUNDARY

1. **Internal Build Neutrality**: The source code of this project must remain neutral. No internal build tools, personal API keys, or development-specific orchestration scripts (e.g., `fleet_query.py`) shall be committed to the repository.
2. **User Autonomy**: All cloud features (OpenAI, Anthropic, Gemini, OpenRouter) must strictly use the "Bring Your Own Key" (BYOK) model. No default keys or "Internal Coach" fallbacks are permitted in the source.
3. **Public Integrity**: Public documentation (README, etc.) and interfaces (Hugging Face Spaces) must focus strictly on the user perspective. Internal technical jargon (e.g., "Coach", "Stadium", "Stadium Physics") is restricted to build logs and constitutional reasoning; it must not appear in user-facing code or Gradio apps.

## SECTION 1: CORE ARCHITECTURE

1. **The 21-Step Cognitive Architecture**: The agent must adhere strictly to the [Metameric Memory Engine](docs/architecture.md) blueprint mapped directly to this codebase. The operating loop moves from Reconnaissance (Metamers) to Substrate Hardening to Dream State Evolution.
2. **Shard Layer**: Persistent local memory using SQLite + FTS5.
3. **Multi-DB Sharding**: Horizontal scaling across 9 databases, each capped at 1GB, accessed via deterministic O(1) hash routing.
4. **Context Layer**: Ephemeral session memory with sandboxed execution.
5. **Universal Interface**: Unified binary `nougen` and FastMCP standard protocol for all operations.

## SECTION 2: QUALITY & HARDENING

1. **Zero Side-Effects**: Modules must not perform initialization (e.g., `init_db`) on import.
2. **100% Pass Rate**: No feature is complete without matching unit tests.
3. **Pylint Standard**: Aim for 10.00/10 on all core modules.

## SECTION 3: BRAND IDENTITY

1. **The Meaning of Nou Gen**: "Nou Gen" means "We have" in Haitian Creole.
   - *NouGenAi* = We have AI.
   - *NouGenShards* = We have shards. We have memory.
2. **The Subtext of Preservation**: When external platforms dictate what can be kept or displayed, the only defense is a substrate you control. NouGenShards is built on the quiet understanding that memory must be local, immutable, and decentralized.
3. **The Voice**: We play the game under layers of subtlety and entendre. The documentation and interface operate with quiet strength—focusing on local control, resilience, and the power of owning your own context. We don't shout the stance; the architecture *is* the stance.

