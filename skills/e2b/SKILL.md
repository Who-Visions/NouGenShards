---
name: e2b
description: Use this when you are about to write a summary, digest, distillation, classification pass, first-draft document, design outline, shard-body prose, or any bulk text transform inline — route that work to the local Ollama gemma4:e2b-qat model instead and review the result (Rule 0.7, player drafts / coach reviews / GM decides). Also applies when the operator says "delegate", "use e2b", "use the local model", or "free agents", and when a persona (Yukiai, solai) should speak through the local lane. Does not cover precision code edits, tool orchestration, or decisions — those stay with the coach.
---

# E2B Delegation — player drafts, coach reviews

A coach must not burn cloud tokens doing lifting a $0 local model can carry.
This skill routes text work to `gemma4:e2b-qat` (~1.7 GB, vision+text, fits a
6 GB card) and keeps the coach in the review seat. It applies to every coach
lane — Claude, Codex, Kaedra, or any client with reach to the local Ollama.

## The loop

1. **Frame the task** — write a tight prompt carrying the context the model
   cannot fetch itself (it has no tools, no memory, no grid access). Put
   structure requirements and length bounds in the prompt.
2. **Call the local lane** — OpenAI-compatible path only, never raw
   `/api/generate`:

   ```
   POST http://localhost:11434/v1/chat/completions
   {
     "model": "gemma4:e2b-qat",
     "messages": [
       {"role": "system", "content": "<persona or role framing>"},
       {"role": "user",   "content": "<task + context>"}
     ],
     "temperature": 0.3,     // 0.2-0.4 drafts/summaries; 0 classification
     "max_tokens": 2048,     // NEVER below 1400 — see failure modes
     "stream": false
   }
   ```

3. **Review as coach** — read the output critically before using it. Fix small
   defects yourself; re-prompt for structural ones. Never pass unreviewed
   player output to the operator, a shard, or a relay leg.
4. **Save to a permanent project path** (Rule 0.5.2) and label provenance:
   drafted by `gemma4:e2b-qat`, reviewed by <coach lane>.

## Personas

Persona models are system prompts riding e2b-qat, not separate weights worth
loading — the full persona builds do not fit a 6 GB card, and the VRAM gate
will reroute them. Source of truth for the prompts: the Modelfiles in
`fleet/`. Tag-addressed `Yukiai:e2b` / `solai:e2b` builds exist where
installed; list `/api/tags` rather than guessing tags (they have changed
before).

## Failure modes (all observed, all real)

- **Empty content, no error** → `max_tokens` too small. The Gemma E-series
  emits a `reasoning` channel that consumes the budget FIRST; below ~1400 the
  visible answer never starts. Raise to 2048+ and retry. This is the #1 trap.
- **Connection refused on 11434** → Ollama is down. STOP and report (Rule
  0.3) — never silently fall back to a paid cloud route. Check `/api/tags`
  and `/api/ps` for install and residency state.
- **Slow first call** → cold load, seconds to tens of seconds. Fine. To pin
  the model resident, send one call with `"keep_alive": -1`.
- **`/api/tags` proves nothing about inference** — a manifest listing is not
  a working runner. If health matters, prove it with a tiny real completion
  (the dream lane's `inference_preflight` pattern).

## Scale-out

For many independent items (classification sweeps, per-file digests), loop
sequentially on the local lane first — $0 and GPU-bound, concurrency 1.
Reach for the multi-route fleet dispatcher (`tools/fleet.py`, Rule 0.5.1)
only when the job needs parallel throughput or consensus votes across
routes, not for routine drafting.

Proof case: `docs/continuous-sync-design-DRAFT.md` — the continuous-sync
design outline, drafted by e2b-qat (1,260 tokens, $0), coach-reviewed,
2026-08-17. Its unprompted first architectural call matched the fleet's
transport doctrine.
