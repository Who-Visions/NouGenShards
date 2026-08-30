---
name: shards-memory
description: Use when storing or recalling durable fleet knowledge — capturing a finding worth keeping, remembering what was learned before, updating a living dossier, handling personal or sensitive material, stamping migrated content at its true date, or diagnosing a capture that reported success but cannot be found. Covers Rules 0.0 and 0.6, the nougen_shards core API, the shards_* MCP tools, and the working-directory trap that silently writes shards into a stray vault. Does not cover in-flight handoffs — that is relay.
---

# Shards — the fleet's memory

NouGen shards are the **primary, canonical** knowledge store. Everything new
goes here.

The legacy Antigravity database at
`Outpost\Yuki-Ai\persistence\antigravity_memory.db` is **read-only**: consult it
for historical shards, never write to it.

Write what a future lane needs to **act** on — the finding and why it holds, not
a status update. A status update belongs on the [[relay]].

## The working-directory trap — read this before any capture

The vault directory is resolved **at import time**:

1. `NOUGEN_VAULT_DIR` if set — wins.
2. Otherwise, a `.vault` directory in the **current working directory**, if one exists.
3. Otherwise `~\.nougen\shards`.

**`Outpost\NouGen\.vault` exists.** So a capture run with the working directory
set to `Outpost\NouGen` writes into that stray local vault instead of the real
one — no error, no warning, and the shard is invisible to every other lane.

Always set `NOUGEN_VAULT_DIR` explicitly, and always verify the write landed
with a recall before claiming anything was stored.

```powershell
$env:NOUGEN_VAULT_DIR = "$HOME\.nougen\shards"
```

The real vault holds `nougen_shards_1.db` … `nougen_shards_9.db` plus
`dedup_index.db` and `history.db`. Limits are `MAX_DB_COUNT = 9` and 1 GB per
database.

## Python API

`Outpost\NouGen\src\nougen_shards\core.py`:

```python
capture(event_type, title, content, tags=None, embedding=None,
        domain_key=None, density_score=None, sensitivity=None,
        original_timestamp=None) -> bool

retrieve(query, limit=3, query_embedding=None,
         domain_key=None, include_research=False) -> list

compile_recall_packet(shards) -> str
retrieve_dual_system(...) / compile_recall_packet_dual(...)
```

`retrieve` runs keyword (FTS/LIKE) and vector lanes in parallel and merges them
with Reciprocal Rank Fusion. `NOUGEN_RERANK=1` adds a cross-encoder rerank stage
over the top RRF candidates.

## MCP tools

These reach the grid through blade's gateway — run `shards_status` first if
unsure it is online.

| Tool | Use |
| --- | --- |
| `shards_capture(title, content, event_type="KNOWLEDGE", tags, event_time)` | Write a durable learning. |
| `shards_recall(query, limit=5)` | Semantic recall. |
| `shards_search(query, limit=5)` | Keyword/context search. |
| `shards_status` | Is the gateway up. |
| `shards_window`, `shards_coverage` | Chronology and coverage histograms. |
| `shards_amend`, `shards_mark`, `shards_forget`, `shards_retract` | Correct, flag, or withdraw. |

Capture **deduplicates by content** and reports success either way, so
re-capturing identical text is a safe no-op — it does not create a second shard.

## Sensitivity

`normal` (default, plaintext), `private`, or `secret`. Private and secret bodies
are AES-256-GCM encrypted before they reach SQLite, so personal-scope material
(finances, health, identity documents) is not readable from the DB file.

**Titles and tags stay plaintext.** They are the only handle recall has on an
encrypted shard — so keep identifying detail out of them while leaving enough to
find the shard again.

## Stamp the true era

When a shard describes something that *happened* at a known earlier time — a
past conversation, a document's original date, a migrated memory — pass
`original_timestamp` (Python) or `event_time` (MCP) as ISO-8601. Chronology
tools then narrate it in its own era instead of the capture date, and
date-window queries and coverage histograms stay honest. Omit it for
present-tense findings.

## Living dossiers are append-only

For a dossier under a stable `domain_key` (e.g. `learn-with-mrs-b-profile`):
append a dated block to the **latest version's** content and capture that as a
new snapshot under the **same** `domain_key`.

```
--- UPDATE 2026-08-29 ---
<what changed, and why it holds>
```

Never trim history. The dossier's value is the trail, not just the current state.

## Known defect — open on the relay

`shards_capture` can silently return `{}` instead of `captured:false`. **Do not
treat a bare empty result as success.** Verify with a recall before telling
anyone the knowledge was stored. This is tracked as an open leg; if you confirm
or fix it, ack that leg rather than opening a new one.

## Related

[[relay]] for in-flight work and handoffs. [[e2b]] to draft shard-body prose
locally before capturing it — draft, review as coach, then store.
