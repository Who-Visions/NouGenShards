# Shang Tsung donors: cross-donor synthesis (Sun 9/13/2026, 10:59–11:30 PM EDT)

Ten donors in one session. Per-donor docs sit in this folder. Fleet votes and raw lane outputs are in `analysis/shang-tsung/`.

| Donor | License | Port mode | Doc |
|---|---|---|---|
| EchoVault app (iOS, digital legacy) | proprietary | clean-room | [echovault-digital-legacy.md](echovault-digital-legacy.md) |
| mraza007/echovault | MIT | code | same doc, second section |
| tinyhumansai/openhuman | GPL-3.0 | clean-room | [openhuman.md](openhuman.md) |
| TencentCloud/TencentDB-Agent-Memory | MIT | code | [tencentdb-agent-memory.md](tencentdb-agent-memory.md) |
| ThinkfleetAI/memmesh | Apache-2.0 | code | [memmesh.md](memmesh.md) |
| trace-cortex/cortex-app | MIT | code | [cortex-app.md](cortex-app.md) |
| u14app/neo-chat | MIT | code | [neo-chat.md](neo-chat.md) |
| EverMind-AI/EverOS | Apache-2.0 | code | [everos.md](everos.md) |
| MihaiBuilds/memory-vault | MIT | code | [memory-vault.md](memory-vault.md) |

## What recurs across donors (independent teams converging = the strongest signal)

| Theme | Donors (fleet lanes) | NouGen gap | Order |
|---|---|---|---|
| **Offline consolidation / distillation**: atoms → scenes → persona, dedup, contradiction resolution | Tencent L0–L3 (6/6), openhuman memory tree (6/6), memmesh consolidation (3/4), cortex sleep pass (3/4), EverOS reflection (3/4) | Nothing ran between sessions. (The 0.28 body recall that motivated this was an eval artifact, see below.) | **1: BUILT** `distill.py` sidecar + `tools/distill_run.py` |
| ~~Markdown as the editable source, DB as the index~~ | EverOS cascade watcher (3/4) + md source (2/4), openhuman Obsidian mirror, mraza007/echovault md vault | **REJECTED by Dave 11:34 PM EDT 9/13**: "db is source for us". Markdown is for rules and instructions; a file per shard would cost portability, small size and fast retrieval. Its slot went to bi-temporal (#6). | — |
| **Entity/relation graph with provenance** (multi-hop, PageRank) | memory-vault (3/4), cortex trust graph (2/4), memmesh (1/4) | self_archive edges only (Xoah canon) | 3 |
| **Smarter context assembly**: knapsack by value/cost, cite everything, never re-send held tokens | cortex CMP (2/4), Tencent char/item caps, openhuman tool-output compaction (6/6) | Rank-order token budget only (shipped 9/13) | 4 |
| **Scoped retrieval dimensions** (user / agent / project / session) | EverOS (3/4), Tencent ACL | domain_key + tags | 5 |
| **Bi-temporal**: as-of queries | memmesh (3/4) | event_time is captured but not queryable as-of | 6 |
| Soft-delete then purge, with an audit log | memmesh, memory-vault (single lanes) | shards_forget/retract exist | parked |

## Build status, 9/13 late (host: WhoArt)
| Move | Where | Status |
|---|---|---|
| 1 Distillation L1 atoms + L2 scenes + L3 persona + layered read | `src/nougen_shards/distill.py` (sidecar `nougen_distill.db` beside the vault; shard DBs untouched), `tools/distill_run.py` (local e2b only, resumable), MCP `recall_layered` | built, 9 tests |
| 3 Entity/relation graph + 1-hop PageRank-lite lane | `distill.graph_lane`, fused into `core.retrieve` RRF | built |
| 4 Knapsack packing + session delta (`[HELD]` handles) | `compile_recall_packet(strategy="knapsack", held=, included=)`, MCP `recall_memory(session_id=)` | built |
| 5 Scoped retrieval (agent/user/machine/project from tags) | `core.retrieve(scope=)`, MCP `recall_memory(agent=, user=, machine=, project=)` | built |
| 6 Bi-temporal | `learned_utc` column (idempotent ALTER in `init_db`, stamped at capture); `retrieve(as_of=, event_after=, event_before=)` | built |

**Distill A/B, 2:32 AM EDT 9/14.** 376 shards distilled (local e2b), 200 scenes. Lanes off → on: MRR 0.624 → **0.665**, body R@10 0.60 → 0.64, title held at 1.00, p50 +44 ms. Lanes stay on. The L3 persona output was empty and needs a better prompt or scene selection.

**Title recall fixed, 12:26 AM EDT 9/14.** Exact-title lookups missed 1 in 3 eligible shards. The keyword lane found them, but per-DB OR fallback flooded the merge and double decay buried old exact hits. The fix: an exact-title lane + tier sort, a NOCASE title index, and 5× bm25 title weight. Result: title R@10 0.68 → **1.00**, overall MRR 0.327 → **0.624**, body unchanged (0.60), p50 +47 ms (`report_20260914T042629Z`).

**Eval correction.** The first golden set was 68% bulk IMPORT/INGEST shards (arxiv), which default recall excludes by design. On eligible shards, body Recall@10 was **0.708**, not 0.28. `recall_eval build` now samples only recall-eligible shards (`--include-research` opts back in).

## Shipped this session
- `core.compile_recall_packet(token_budget=)` + `NOUGEN_RECALL_TOKEN_BUDGET` (from mraza007/echovault)
- `tools/recall_eval.py` golden-set eval + threshold sweep (from mraza007/echovault); baseline in `analysis/recall_eval/`
- `tools/fleet.py` privacy mode (`NOUGEN_PRIVACY=1`) + no-progress circuit breaker (from openhuman)
- `tools/coach.py` `ask(kinds=)` lane filter + a single parallel wave over prompts × lanes

## Fleet caveats
- Lanes see README text and a one-paragraph NouGen inventory, so their "NouGen status" column over-claims "new". The coach corrected the known cases in each donor's shard (token budget, MCP, destiny).
- On a failed lane, `Fleet.map` retries on the next route, which can be a model already voting. EverOS's tallies include one duplicated model.
