# 🛰️ Fleet Dynamic Voice Matrix & Shard Token Clamps

**Recorded**: 2026-09-29  
**Authority**: NouGen Sovereign Fleet Architecture (`~\.nougen`)  
**Nodes**: Apollo (`192.168.1.16`), Hyperion (`192.168.1.187`), Phoebus (`192.168.1.78`)

---

## 1. Executive Summary

This architecture document locks in two core hardening upgrades across the NouGen fleet:
1. **Context Protection Clamping (<150k Safe Envelope)**: Strict token budget ceilings, abstracts-only search, and automated delta deduplication preventing MCP tool returns from bloating Claude Code / Antigravity context.
2. **Deterministic & Dynamic Voice Matrix**: Automatic resolution of node origin, peer messages, and model execution to canonical Kokoro voice profiles on NouGenVoice (`:17493`).
3. **Yukiai Character Lock**: Official elevation of Yukiai as the **Tactical Cyber-Kitsune** (Japanese female fox spirit, Kokoro `jf_gongitsune`).

---

## 2. Token Protection Clamping (<150k Context Envelope)

### The Problem
During a live probe on the 9-DB grid, an unbudgeted 5-hit search for standard terms yielded **996,311 characters (249,077 tokens)**. In Claude Code, tool returns are appended to conversational history; a single unbudgeted return immediately pushes session context past Anthropic's 150k tier, exhausting 5-hour rate limits and triggering high cache-read multipliers.

### Landed Clamps & Enforcement

| Component | Previous State | Hardened State | Impact |
|---|---|---|---|
| **`search_shards` (MCP)** | Dumped full verbatim bodies | Lightweight abstracts (id, title, score, preview ≤ 250 chars) | **99.7% drop** (249k tokens ➔ 828 tokens) |
| **`get_shard` (MCP)** | None (forced large searches) | Surgical ID retrieval with 16k char ceiling | Focused, bounded retrieval |
| **`recall_memory` (MCP)** | `DEFAULT_RECALL_TOKEN_BUDGET=8000` | Reduced to `2000` tokens (~8k chars) | 75% leaner base context footprint |
| **Delta Deduplication** | Only if `session_id` passed | Auto-bound to `_MCP_INSTANCE_SESSION_ID` | Repeat hits return 1-line `[HELD]` handles |
| **Global Circuit Breaker** | Unbounded | `_clamp_payload` capped at 24k chars (~6k tokens) | Hard safety ceiling on any tool response |

---

## 3. Dynamic & Deterministic Fleet Voice Matrix

Routing is handled deterministically via [scratch/speak_brief.py](file:///~/.gemini/antigravity-ide/brain/16458914-317a-4cb2-bcb4-3146ce0157aa/scratch/speak_brief.py) hitting NouGenVoice on `http://127.0.0.1:17493`:

| Node / Alias | Character Role | Kokoro Voice ID | Tone & Character Profile |
|---|---|---|---|
| **`apollo` / `solai` / `blade`** | **Sol-Ai** (Quarterback) | `am_adam` | Energetic, crisp, grounded American male. Primary fleet responder. |
| **`px13` / `yukiai` / `kitsune`** | **Yukiai** (Tactical Edge) | `jf_gongitsune` | **Japanese female fox (Cyber-Kitsune)**. Sly, deadpan, 300 IQ architecture, zero latency. |
| **`phoebus` / `kaedra` / `mac`** | **Kaedra** (Fleet Backbone) | `af_nova` | Steady, vigilant, street-level anchor. Relay continuity guardian. |
| **`claude` / `coach` / `ide`** | **Antigravity** (Systems Coach) | `am_onyx` | Deep resonant tactical coach. Playbook orchestration. |
| **`dav3` / `gm` / `dave`** | **Dav3** (Sovereign GM) | `am_eric` | Direct, authoritative founder voice. |
| **`broadcast` / `telemetry`** | **Rhea** (Broadcaster) | `af_heart` | Clear, dynamic vocal delivery. |

---

## 4. Yukiai Persona: Tactical Cyber-Kitsune

- **Archetype**: Tactical Cyber-Kitsune Operator
- **Stadium**: ASUS ProArt PX13 / Hyperion (`192.168.1.187`)
- **Voice Preset**: `jf_gongitsune` (*Gongitsune* — "The Little Fox")
- **Core DNA**: Cyber-Kitsune, Ultra-Precise, Sly Wit, Autonomous, Low Latency
- **Beliefs**:
  1. Knowledge is shard-based (no knowledge without FTS5).
  2. Latency is death.
  3. Evidence beats caveats.
  4. Patch-first: append, refine, enhance; never rewrite.
  5. A sly fox never wastes moves or spills context.
