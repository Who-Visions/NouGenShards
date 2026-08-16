# Anthropic Dreams API — reference (research preview)

> Source: https://platform.claude.com/docs/en/managed-agents/dreams — captured 2026-08-05.
> Relevant to NouGen: this is the official convergent twin of `src/nougen_shards/dream.py`
> (TMEM Dream State / Griot consolidation). Kept here as the spec of record for a future
> hybrid lane (local Griot nightly + `/v1/dreams` deep clean) once beta access is granted.

## What it is

A **dream** is an async job that reads an existing **memory store** plus 1–100 past
**session transcripts** and produces a NEW output memory store: duplicates merged,
stale/contradicted entries replaced with the latest value, new insights surfaced.
Inputs are never modified — review the output store, then attach it to future sessions
or discard it.

- Research preview; request access: https://claude.com/form/claude-managed-agents
- Beta headers: `anthropic-beta: managed-agents-2026-04-01,dreaming-2026-04-21`
  (the dreams endpoints need BOTH; memory-store/session calls need only the first)
- Supported models: `claude-opus-5`, `claude-fable-5`, `claude-opus-4-8`,
  `claude-opus-4-7`, `claude-sonnet-5`, `claude-sonnet-4-6`

## Endpoints

| Action   | Endpoint |
|----------|----------|
| Create   | `POST /v1/dreams` |
| Retrieve | `GET /v1/dreams/{dream_id}` |
| Cancel   | `POST /v1/dreams/{dream_id}/cancel` |
| Archive  | `POST /v1/dreams/{dream_id}/archive` |
| List     | `GET /v1/dreams?limit=20` (`include_archived=true` for archived) |

### Create (Python SDK)

```python
dream = client.beta.dreams.create(
    inputs=[
        {"type": "memory_store", "memory_store_id": store_id},
        {"type": "sessions", "session_ids": [session_a, session_b]},
    ],
    model="claude-opus-4-8",
    instructions="Focus on coding-style preferences; ignore one-off debugging notes.",
)
# -> dream.id "drm_01...", status "pending"
```

No existing store? Create an empty memory store first and pass it as the input.

### `instructions` (max 4,096 chars)

High-level synthesis steering only: focus areas, content to preserve, output
conventions. It is a synthesis pass, NOT a line editor — "change sentence X to Y"
directives produce no change. For targeted edits, use the Memory Stores API on the
output store.

## Lifecycle

`pending` → `running` → `completed` | `failed` | `canceled`

- Runs minutes to a few hours, scaling with transcript count/length.
- Output store ID appears in `outputs[]` shortly after `running` starts (store is
  cloned from input); a `running` dream can briefly report empty `outputs[]`.
- While `running`, `session_id` points at the underlying pipeline session — stream its
  events to watch the dream read/write live. The session is archived (not deleted) at
  terminal state.
- On `failed`/`canceled`, the output store persists with partial contents.
- Deleting/archiving an INPUT store or session mid-run fails the dream
  (`input_memory_store_unavailable` / `input_session_unavailable`).
- Cancel: immediate; idempotent on already-canceled; 400 on completed/failed. `usage`
  may keep updating for a few seconds after cancel.
- Archive: terminal-state dreams only (400 otherwise); no unarchive; does not touch the
  output store.

## Errors

`timeout`, `internal_error`, `memory_store_org_limit_exceeded`,
`input_memory_store_too_large`, `input_memory_store_unavailable`,
`input_session_unavailable` (non-exhaustive).

## Billing & limits

- Standard API token rates for the selected model; `usage` on the resource has exact
  totals. Cost ~linear in number/length of input sessions. Start small.
- Max 100 sessions per dream; `instructions` ≤ 4,096 chars; default rate limits apply
  during preview.

## Mapping to NouGen (why we care)

| Dreams API | NouGen equivalent |
|---|---|
| Output store reviewed/discarded, inputs untouched | dream gate / verification-gated consolidation |
| Transcript mining vs existing store | dual-system offline semantic consolidation |
| Duplicates-that-disagree merging | Griot contradiction audit |
| Stale-entry replacement | Griot decay + reconciliation |
| `instructions` steering | dream mission/war-game prompts |
