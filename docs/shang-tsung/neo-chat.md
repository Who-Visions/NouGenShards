# Shang Tsung: u14app/neo-chat → NouGen

Fleet batch 2026-09-14T03:26:00+00:00: 4 lanes (nemotron-3-super, nemotron-3-nano:30b, gpt-oss:120b, gemma4:31b), one parallel wave via `coach.ask`. README-only input (`analysis/shang-tsung/donors/`); raw lane output in `analysis/shang-tsung/batch_20260913.json`.

- **License:** MIT. Permissive, so code may be ported with attribution.
- **Stars / language:** 1824 / TypeScript; last push 2026-09-13T17:02:52Z
- **What it is (lane 1):** Extract mechanisms from the Neo Chat donor repo that NouGen should adopt.

## Consensus moves (≥2/4 lanes)

| Move | Lanes | Top-3 | NouGen status | Landing | Effort |
|---|---|---|---|---|---|
| **deep-research**: Research workflow that builds plans, cites sources, generates citable reports and supports Q&A | 3/4 | 2 | new | research-engine | M |
| **local-storage-sync**: Browser‑based local storage with optional encrypted sync via WebDAV/S3 and ZIP backup | 2/4 | 2 | new | data-persistence | M |

## Disagreements (<2 lanes; for Dave to adjudicate)

- `agent-runtime` (1/4, new): Multi‑step agent execution with tool permissions, workspace isolation and recovery
- `encrypted-sync-layer` (1/4, new): E2EE synchronization of local-first data via WebDAV/S3/MinIO to maintain privacy across multiple machines.
- `foreground-orchestration-recovery` (1/4, new): State-saving for multi-step agent/research runs allowing manual resume after session interruption.
- `mcp-stdio-bridge` (1/4, partial): Docker-based bridge to allowlist and execute stdio-based MCP servers for local tool extension.
- `openapi-plugin-bridge` (1/4, partial): Dynamic loading of OpenAPI‑described plugins, routing calls through a local MCP bridge (Docker‑based stdio) when needed, and exposing them as agent tools.
- `agent-tool-permissions` (1/4, partial): Runtime sandbox for agents that declares allowed tools, enforces per‑tool permissions, and provides automatic state recovery on page reload or crash.
- `artifact-rendering-engine` (1/4, new): Dedicated UI components for editable artifacts, interactive charts, and diagrams separate from chat stream.
- `byok-credential-encryption` (1/4, new): Bring-Your-Own-Key (BYOK) system for stable encryption of API keys across restarts and replicas.
- `deployment-hardening` (1/4, covered): Production config with stable BYOK keys, shared runtime stores and circuit‑breaker fallback
- `multi-model-provider` (1/4, partial): Unified abstraction over heterogeneous model endpoints (OpenAI, Anthropic, Google, compatible APIs) supporting text and image payloads, with per‑provider credential management.
- `multimodal-ui` (1/4, new): Voice interaction, editable artifacts, markdown/math/diagram rendering with export controls
- `plugin-framework` (1/4, partial): Extensible plugin system for text skills, OpenAPI tools, remote MCP servers and Docker bridges
- `voice-io-integration` (1/4, new): Bidirectional voice interface: speech‑to‑text for user input and text‑to‑speech for model output, with configurable quality and privacy controls.
