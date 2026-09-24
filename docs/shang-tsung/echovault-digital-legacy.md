# Shang Tsung: EchoVault (Digital Legacy) → NouGen

Absorbed 10:59 PM EDT Sun 9/13/2026. Clean-room: closed-source iOS app (Ugochukwu Nwune, id6762042028); sources were the App Store listing and echovault.me/app only. No code, assets or copy taken.

Fleet vote not run: coach gate closed (free RAM 1.6 GB < 4 GB). Move ranking below is a coach draft, pending a fleet majority.

## What the donor is
An AI "Echo" of a person (voice, stories, values) that family can talk to after the person dies.
- **Check-Ins**: guided conversations with an AI biographer; voice-mode Check-In is on their roadmap.
- **Custodians**: up to 3 on the free tier, usually family; they get access only after **one full year of account inactivity**.
- **Tiers**: Seed (text, free) → Voice ($12/mo) → Prime ($18/mo) → Video Avatar ($99.99 one-time). Custodians pay separately ($12 / $20).
- **Stack claim**: "Voice Cloning, Video Avatar, Personality AI, RAG Memory". Chat, voice call and live avatar video call.
- **Weak spots**: iPhone only; they hold the voice, contacts and media, linked to identity; the only release trigger is inactivity, with no stated death verification; no stated export.

## Moves → NouGen (what we already have)

| # | Donor move | NouGen landing | Existing piece |
|---|---|---|---|
| 1 | Check-In biographer | Interview loop that asks, listens and captures each answer as a dated append to a living dossier | Living-dossier pattern: dated appends under one domain_key (append-only, Rule 0.6) |
| 2 | Personality AI | Echo = a persona system prompt compiled from the dossier plus experiential provenance ("how I decided"), not only facts | the protagonist Self Archive v0.2 (shard 17777): choice topology, conservation of character |
| 3 | RAG Memory | `compile_recall_packet` over a per-person domain_key; answers cite shard ids | nougen_shards core |
| 4 | Custodian + inactivity release | Destiny-bearing shard: trigger = N days without a Check-In, obligation = unseal to named custodians | Destiny shards (17772), Keymaker vault for the sealed store |
| 5 | Voice / avatar | Local lane only (voice and face are biometric, so they never leave the machine, per the coach privacy gate) | e2b lane; Archive's local ONNX stack |

## Where NouGen beats the donor
- **Local and owned.** The person's voice, face and stories stay in the family vault. There is no subscription hostage.
- **Provenance.** Every Echo answer traces to a dated shard in the person's own words, so the Echo can say "I never told you that" instead of hallucinating a memory.
- **Better release trigger.** Inactivity plus a custodian quorum (for example 2 of 3), with a cancel window that notifies the owner. The donor's inactivity-only rule can unseal on a lost phone.
- **Universal** (cape rule). Any person, any family. No person is hardcoded.

## Second donor: mraza007/echovault (MIT, 148★), a different project with the same name
A local-first memory layer for coding agents: Markdown+YAML vault, SQLite FTS5 + sqlite-vec (Ollama nomic-embed-text), and 3 MCP tools (`memory_save/search/context`) shared by Claude Code, Cursor, Codex and OpenCode. It is the closest public match to NouGen shards.

| Move | NouGen status |
|---|---|
| Token-budgeted context packet (default 1200) | **PORTED 11:03 PM EDT 9/13.** `compile_recall_packet(shards, token_budget=)` in core.py; MCP recall reads `NOUGEN_RECALL_TOKEN_BUDGET`. Unset = unchanged behaviour. Omitted records are stated in the packet, not dropped silently. |
| 3-layer redaction (tags, patterns, `.memoryignore`) | Patterns exist (`credential_patterns.redact`, `brain_scan/redaction`). `.memoryignore` is missing. |
| Supersede / contradiction / stale review | Covered: destiny statuses, canon_pressure, assurance. EchoVault's review is non-mutating; ours mutates via transitions. |
| Referenced/dismissed feedback | Covered by `mark_utility` / `shards_mark`. |
| Golden-set eval (Recall@k, MRR, nDCG, threshold sweep) | **BUILT 11:12 PM EDT 9/13.** `tools/recall_eval.py build|run`; golden set at `analysis/recall_eval/golden.json`. Keyword-only baseline: title-query R@10 0.933 / MRR 0.836, body-query R@10 **0.280** / MRR 0.113, p50 449 ms, 1/30 nonsense queries returned anything. |
| Living categories with validity windows (`project_state`, `active_work`, `last_verified`) | **Missing.** Stale facts (DHCP IPs, route counts) never expire. |
| Category-priority fill (constraints → state → active → fixes → playbooks) | Missing. Needs categories first. |

## Parked (BACKLOG, not started)
- Golden-set retrieval eval + threshold sweep (tools/recall_eval.py).
- `valid_until` / `last_verified` on shards; recall down-ranks expired entries.
- `.memoryignore` for brain_scan.
- Fleet majority vote on move order (`coach.py ask`, 5 lanes) once free RAM ≥ 4 GB.
- Build order sketch: Check-In loop → Echo persona compiler → destiny release → local voice.
