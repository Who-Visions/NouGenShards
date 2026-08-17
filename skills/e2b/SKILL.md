---
name: e2b
description: Use for summaries, digests, distillation, classification, first drafts, design outlines, shard-body prose, and bulk text transforms. Route the draft to local Ollama gemma4:e2b-qat, then review it. Also applies when the operator says to use e2b, local models, delegation, or free agents. It does not cover precision code edits, tool orchestration, or final decisions.
---

# E2B delegation: player drafts, coach reviews

Use the zero-cost local model for bounded text work and keep the calling agent in the
review seat. The model has no tools, grid access, or durable memory, so prompts must
carry every fact needed for the draft.

## Workflow

1. Frame a tight task with source facts, required structure, and a length bound.
2. Probe `/api/tags`, then prove inference with a real completion when health matters.
3. Call `http://127.0.0.1:11434/v1/chat/completions` with
   `model=gemma4:e2b-qat`, `max_tokens>=2048`, `stream=false`, and an appropriate
   temperature. Use `keep_alive=-1` only when intentionally pinning the shared lane.
4. Review the output. Correct unsupported claims before publishing, capturing, or
   relaying it.
5. Save durable work under its permanent project path and label its model provenance.

For summaries and drafts, start around temperature 0.3. Classification can use 0, but
always retain at least 2048 output tokens because E-series reasoning may consume the
budget before visible content begins. Empty output requires one retry with a larger
budget; it is not a valid answer.

## Boundaries

- Never silently fall back to a paid route when local Ollama is unavailable.
- Do not load an oversized persona model onto Who-Art's 6 GB card for routine prose.
- Persona tags may be used when installed, but discover them from `/api/tags`.
- Run GPU-bound bulk items sequentially unless the fleet dispatcher is explicitly
  needed for throughput or consensus.
- Precision edits, security decisions, deployment choices, and final verification stay
  with the coach.

Verified example: this repository's shard-highway design was drafted by
`gemma4:e2b-qat` and then corrected against the live topology before publication.
