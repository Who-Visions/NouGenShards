# Shang Tsung: TencentCloud/TencentDB-Agent-Memory → NouGen

Absorbed 11:25 PM EDT Sun 9/13/2026. **MIT**, so code can be ported with attribution. The project is a team memory hub for agents (26.6k★, v2.0.0) that turns conversations, docs and code into four assets: Chat Memory, Skills, LLM-Wiki and CodeGraph. Its headline number is PersonaMem 48% → 76% with memory on.

## Fleet vote (6 distinct models, 6/6 parsed, Borda over each lane's top 5)
Models: gemma4:e2b-qat (local), nemotron-3-super, nemotron-3-nano:30b, gpt-oss:120b, gemma4:31b, gemma4:31b-cloud. Lanes limited to Ollama + OpenRouter kinds, per Dave. Raw lane outputs: `analysis/shang-tsung/vote_20260913.json`.

| Rank | Move | Borda | Votes | NouGen landing |
|---|---|---|---|---|
| 1 | **T3 Layered retrieval**: L2/L3 bootstrap context, L1/L0 fetched for specifics | 21 | 5/6 | Recall packet: summary layer first, raw shards on demand |
| 2 | **T1 L0→L3 distillation**: raw → atoms → scenarios → persona | 19 | **6/6** | Same move as openhuman's memory tree (6/6 there too) |
| 3 | **T2 L1 atoms**: typed facts, preferences, constraints, events | 18 | 4/6 | New atom table; each atom links back to its source shard |
| 4 | T4 Skill extraction from sessions/tool calls, versioned | 11 | 5/6 | Feeds `progressive_skills` / `evolve_skill` |
| 5 | T5 LLM-Wiki with link graph | 8 | 3/6 | Pairs with the Markdown export (openhuman O4) |
| 6 | T11 Cold-start import | 6 | 4/6 | brain_scan already partly does this |
| — | T6 CodeGraph, T9 proxy, T8 ACL, T10 loadout, T12–T14 | ≤4 | ≤2 | Minority; parked |

## Their pipeline defaults (openclaw.plugin.json), to port as starting values
- L1 batch every **5** conversation turns, or after **600 s** idle. A warm-up doubles the interval 1→2→4→…→5. At most **20** atoms per session per batch. Dedup by vector or keyword conflict check.
- L2 scenes run **10 s** after L1, at least **900 s** and at most **3600 s** apart per active session; a session counts as active for **24 h**.
- L3 persona is rebuilt every **50** new atoms, from at most **15** scenes. It keeps 3 persona backups and 10 scene backups.
- Recall: **5** results, score threshold **0.3**, hybrid RRF, **5000 ms** timeout.

## Why this is the top move for NouGen
*Correction, 11:40 PM EDT:* the 0.28 body Recall@10 in report_20260914T031218Z was an eval artifact. 51 of 75 targets were bulk IMPORT/INGEST shards, which default recall excludes; eligible shards scored 0.708. The move still stands on the five-donor convergence, and it is now measured against the corrected golden set. Distilling each shard into typed atoms and topic scenes gives the content its own findable surface. Recall_eval measures whether it works: the body tier is the number to move.

## Build plan (next leg)
1. `atoms` table + a local e2b extractor (structured JSON, temperature 0, seed 7) that emits typed atoms with `source_shard` links.
2. Pilot on the recall_eval golden set's 75 target shards only (bounded: local lane, no cloud).
3. Retrieval: the FTS lane also matches atoms and returns their parent shards.
4. Re-run `tools/recall_eval.py run --no-embed` and compare the body tier against 0.28.
5. Only if it lifts recall: scenes (L2), then persona/summary (L3) and layered retrieval (T3).
