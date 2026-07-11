# WAR-GAME: dream-harder

**Mission**: Deep-dream the corpus we just built (tagged week of arXiv, digests, high-utility DB shards) into (a) real SFT training pairs and (b) LLM-grade semantic invariants — "get them ready" = training data for the local e-models + a richer semantic_knowledge substrate.
**Authored by**: Claude Fable 5 (Coach), 2026-07-11.
**Executor**: local gemma4:12b for volume QA-pair generation (Stadium-safe on 8GB VRAM), gemma4:31b-cloud only for the ~50 weekly must-read invariants. Coach samples and verifies.

## Ground truth
- First dream pass tonight was shallow: 6,633/6,640 shards hit the crude fallback_rule_parser; only 50 naive SFT pairs (title→content copy) exported.
- `dream.extract_semantic_invariants_via_llm` exists (prefers griot:e2b) but is never called at volume; `parametric_burn_in` writes dream_sft.jsonl for LoRA burn-in.
- semantic_knowledge upsert path proven tonight (38,536 rows via parser).
- Local lane verified: gemma4:12b + 31b-cloud both answered; hi-probe auto-unloads models at >75°C GPU (thermal guard exists).

## Move 1 — Baseline counts
- Action: count semantic_knowledge rows + dream_sft.jsonl lines before running.
- Expect: numbers recorded for the delta report.
- Failure: DB locked by mesh → retry once, else abort (lock contention abort condition).

## Move 2 — SFT expansion (get the players ready)
- Action: tools/dream_deep.py --sft: top-N high-utility DB shards (env, default 300) + the 4 daily digests' selected papers; gemma4:12b writes 2 grounded QA pairs per item (question a practitioner would ask; answer ONLY from content). Append-safe to dream_sft_deep.jsonl (separate file — never clobber the baseline).
- Expect: ~600+ pairs, JSON-parse rate >90%; malformed returns dropped and counted.
- Failure signal: parse rate <70% (12b formatting drift).
- Countermove: tighten prompt to single-pair-per-call; if still failing, fall back to gemma4:31b-cloud for the remainder.

## Move 3 — Deep invariants over the week's intelligence
- Action: LLM invariant extraction (local gemma) over weekly must-reads + digest picks + top-utility shards; upsert into semantic_knowledge (proven ON CONFLICT path).
- Expect: net-new invariant rows with meaningful predicates (not parser fragments).
- Failure: GPU thermal saturation (>75°C sustained) → the ollama guard unloads; script must tolerate slow/failed calls and continue.
- Fork: if local calls start timing out → switch NOUGEN_DREAM_LOCAL_MODEL to the e-series (griot:e2b) and continue; else stay 12b.

## Move 4 — Verify & capture
- Action: delta counts, sample 5 SFT pairs + 5 invariants for faithfulness, capture milestone shard, handoff.
- Expect: samples grounded in sources; no hallucinated subjects.
- Failure: hallucination in samples → mark batch suspect, keep file quarantined (don't feed burn-in), report.

## Abort conditions
- Vault DB write errors mid-batch → stop, report written vs pending.
- GPU stuck >80°C → stop volume generation, report thermal ceiling.
- Parse rate collapse after countermoves → ship what's clean, quarantine the rest.
