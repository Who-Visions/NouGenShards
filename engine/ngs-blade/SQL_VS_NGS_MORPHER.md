# NouGenMorph Synthesis — `arXiv:2410.10680v1` (*Evaluating SQL Understanding in LLMs*)

Source: Rahaman, Zheng, Milani, Chiang, Pottinger (Oct 2024), *Evaluating SQL Understanding in Large Language Models* (`arXiv:2410.10680v1 [cs.DB]`).

## Empirical Thesis
Across SDSS, SQLShare, Join-Order, and Spider workloads, LLMs (GPT-4, GPT-3.5, Llama3, MistralAI, Gemini) perform well on surface-level recognition, but degrade sharply on **semantic coherence**, **multi-table/alias disambiguation**, **missing token localization**, **query equivalence** (`AND`/`OR` & numeric predicates), and **runtime estimation** as `word_count`, `table_count`, `predicate_count`, and `nestedness` grow.

## Atom Classification & Native NGS Mapping (`ngs.h` 0.3.1)

| Paper Finding (SQL Failure Mode) | Atom Class | Native NGS Invariant |
|---|---|---|
| Syntax & alias errors (`alias-ambiguous`, `nested-mismatch`, `condition-mismatch`) scale with `word_count` & schema count | `CORROBORATE` | Typed C ABI structs (`ngs_query`, `ngs_fact_in`) with `size` prefix validation (`NGS_MISUSE`); zero SQL string grammar. |
| Missing token localization (GPT-4 Hit Rate 0.56–0.63; others 0.25–0.42) | `CORROBORATE` | Zero free-form token imputation; `NGS_*_INIT` deterministic defaults. |
| Query equivalence breaks on `AND`/`OR`, numeric predicates, >8 tables, >5–19 predicates | `CORROBORATE` | No multi-table join algebra; explicit `ngs_link` edges + 1-hop `NGS_RECALL_EXPAND` + 5 fixed recall arms (`VEC`, `KW`, `RECENCY`, `SALIENCE`, `LINK`). |
| Performance prediction overestimates runtime on long queries (positive bias) | `GRAFT` | Engine-enforced `deadline_ms` (default 50ms) + `token_budget` with exact `elapsed_us`, `arms_complete`, `timed_out`, and `tokens_used`. |
| Query explanation drops clauses (`ORDER BY ASC` flipped, table context lost) | `GRAFT` | Deterministic `ngs_as_of(t_valid, t_record)` + per-arm score breakdown (`arm[5]`) + `abstained`/`confidence` calibration. |
