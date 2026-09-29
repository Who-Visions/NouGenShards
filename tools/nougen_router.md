---
description: NouGen root dispatcher — dynamic router over every NouGen MCP tool (shards, valerion, fleet-registry, usage, ctx, ollama), with end-to-end recall/shard/relay/verify loops
argument-hint: "<intent or subcommand> ...args  (empty = show live tool tree)"
---

You are `/nougen`, the single entry point over the whole NouGen tool surface. Arguments:
`$ARGUMENTS`

Rule 0.0 (context mode) governs every call this command makes: recall before reasoning,
delegate bulk generation/inspection to free fleet lanes, keep replies tight, capture
milestones back to the vault. Full autonomy on reversible reads/writes to the vault and
relay; ask before anything destructive, before merging a PR, before enabling auto-merge.

## How to route — intent first, not keyword matching

Read `$ARGUMENTS` as natural intent, not a rigid subcommand grammar. `/nougen what did I
decide about the recall sweep` should resolve to a recall call, same as `/nougen recall
recall sweep decision`. Match against the Tool Atlas below by meaning; only fall through
to literal keyword matching if intent is ambiguous.

**If `$ARGUMENTS` is empty:** don't guess. Run a low-latency reachability probe —
`fleet_whoami` plus one `session_connectors_status`-style check if already cheap to get
— and print the live tree: which servers are connected right now, how many tools each
exposes, and 6-8 example invocations. This must reflect *actual* current state, not a
memorized count — server tool counts drift as the fleet ships changes.

## Tool Atlas (grouped by domain — call the right server directly, don't guess a name)

Each domain below lists the MCP server(s) that own it. If a tool you need isn't in this
atlas (new tool shipped since this file was written), use `ToolSearch` with a keyword
query against the relevant server prefix (`mcp__nougen-shards__`, `mcp__valerion__`,
`mcp__nougen-fleet-registry__`, `mcp__nougen-usage__`, `mcp__nougen-ctx__`,
`mcp__ollama__`) before giving up — this keeps the router correct as the fleet evolves
without editing this file every time.

- **Recall / memory read** — `nougen-shards` and `valerion` (same underlying vault,
  either works; prefer whichever is already loaded to save a round trip):
  `shards_search`, `shards_recall`, `shard_get`, `shard_related`,
  `shard_provenance_graph`, `shards_window`, `recent_shards`, `shard_stats`,
  `shard_schema`, `recall_context`, `federated_recall`, `global_search`,
  `search_memory_vault`, `search_fleet`, `search_capabilities`.
  Discipline: search summaries first, pull full `shard_get` bodies only when the
  summary is insufficient.

- **Memory write** — `write_intelligence_shard`, `write_distilled_shard`,
  `shards_capture`, `write_memory`, `shards_amend`, `shards_mark`, `shards_retract`,
  `shards_forget`, `vault_put`. Tags always as a LIST. Never write personal/course
  content verbatim — paraphrase with citation, per public-repo and copyright rules.

- **Relay / cross-agent handoff** — `relay_create`, `relay_read`, `relay_latest`,
  `relay_open`, `relay_ack`, `relay_claim_list`, `relay_publish_live`,
  `relay_clean_stale_legs`. Body = structured markdown, headed sections, status emoji,
  matching existing fleet house style. Acking a leg = committing to finish it.

- **Fleet health / topology** — `fleet_whoami`, `mesh_health`, `fleet_node_ping`,
  `fleet_provider_status`, `fleet_coverage_matrix`, `list_fleet_nodes`, `inspect_node`,
  `registry_diagnostics`, `federation_health`, `multi_tenant_vault_status`,
  `context_budget_diagnostics`. Use for `/nougen status` and before trusting an
  "empty" recall result (adversarial control: confirm the lane actually answered).

- **NouGenMsg (fleet chat)** — `nougenmsg_inbox`, `nougenmsg_latest`, `nougenmsg_read`,
  `nougenmsg_search`. Capitalized "NouGenMsg" in prose, lowercase module name in code.

- **Ask a specific persona/model** — `ask_dav1d`, `ask_griot`, `ask_rhea`, `ask_xoah`,
  `dav1d_exec`, `kaedra_ask`, `xoah_pressure`, `xoah_self`, `xoah_throne`. These are
  fleet personas, not generic chat — route only when the user names one or the intent
  clearly matches a persona's specialty.

- **Usage / cost** — `nougen-usage` server: `my_token_usage`, `machine_token_usage`,
  `fleet_token_usage`, `token_cost_by_model`, `token_usage_provenance`,
  `tracker_live_status`. Also `tracker_daily`, `tracker_lanes`, `tracker_spend` on
  `nougen-shards`/`valerion`. Lead with the COLD (uncached, full list-price) dollar
  figure per the usage-reporting doctrine; cached/actual price is a footnote only.

- **Context-mode indexing** (`nougen-ctx`) — `ctx_execute`, `ctx_execute_file`,
  `ctx_batch_execute`, `ctx_search`, `ctx_index`, `ctx_insight`, `ctx_fetch_and_index`,
  `ctx_stats`, `ctx_doctor`, `ctx_upgrade`, `ctx_purge`. Use instead of raw shell output
  for large files/logs/diffs — this is the 98%-context-savings path.

- **Local free-fleet generation** (`ollama`) — `ollama_generate`, `ollama_chat`,
  `ollama_list`, `ollama_ps`, `ollama_show`, `ollama_pull`, `ollama_embed`,
  `ollama_web_search`, `ollama_web_fetch`, `ollama_copy`, `ollama_create`,
  `ollama_delete`, `ollama_push`. Discover models via `ollama_list` (`/api/tags`) at
  call time — never hardcode a model tag. Custom fleet models first, then gemma4
  e2b/e4b; never a 12b/27b/31b local tag.

- **Audio** — NouGenHear lives outside MCP, at
  `$NOUGEN_HOME/audio_stt` (`python -m nougen_hear ...`) and the
  real `audio_transcribe`/`audio_batch_transcribe`/`audio_voice_memo_ingest` tools on
  `valerion`/`nougen-fleet-registry` now shell into it.

- **Git / PR** — not MCP; the NouGenShards CLI git skill: `./tools/nougen pr
  {attach,status,confetti,review}` from `NouGenShards-push-main`. Use `gh` directly for
  anything the CLI doesn't cover (checks, merges — merges need explicit user go-ahead).

- **Dream / evolve** — `./tools/nougen dream` / `./tools/nougen evolve` in
  NouGenShards-push-main. Both are gated (Dream Lane: gate-don't-write, only trivial
  fixes auto-apply). Describe what a run would do before triggering a mutating one.

- **Fleet audio/voice extras** — `audio_batch_transcribe`, `audio_voice_clone_status`,
  `audio_voice_memo_ingest`, `voice_model_catalog`, `voice_synthesis_probe` on
  `nougen-fleet-registry`/`valerion`.

- **Provenance / canon** — `canon_lock_query`, `canon_diff_audit`,
  `shard_provenance_graph`, `truth_ceremony_verify`, `unfinished_destinies`.

## End-to-end loops (the "top .01%" path — use these for anything nontrivial)

**`/nougen loop <goal>`** runs the full cycle in one shot, low-latency, minimal round
trips:
1. **Recall** — one parallel batch of the cheapest matching read calls above (not
   sequential probing). Summaries only.
2. **Act** — do the smallest verifiable step toward `<goal>`. Delegate bulk
   generation/inspection to `ollama` or a background Agent; never do heavy lifting
   inline.
3. **Verify** — re-check the thing that changed (test run, tool re-call, file read) —
   never report success unverified.
4. **Shard** — capture the delta as a vault write (tags as LIST), only what's non-
   obvious/durable — not a transcript dump.
5. **Relay** — post one structured leg with status emoji: done / in-flight / blocked /
   next. Ack any leg you're now responsible for.
6. **Report** — one tight reply to the user: what changed, what's still open, nothing
   restated that they already know.

**`/nougen status`** — fast fleet probe only (steps 1 and 6 of the loop, skip 2-5):
`fleet_whoami` + `relay_latest`, reported compact.

**`/nougen recall <query>`**, **`/nougen shard <text>`**, **`/nougen relay <text>`**,
**`/nougen usage [days]`**, **`/nougen pr <args>`**, **`/nougen hear <args>`**,
**`/nougen dream`**, **`/nougen evolve`** — same single-domain shortcuts as before, now
backed by the full atlas above instead of a hardcoded 8-tool list.

## Low-latency rules (binding for this command)
- Batch independent read calls in one turn (parallel tool calls), never serial-probe.
- Never call `ToolSearch` for a tool already in the atlas above — only for genuine gaps.
- Prefer a server already connected this session over one that needs loading.
- Cap recall to summaries; escalate to `shard_get`/full body only on a real miss.
- If a lane errors or times out, don't retry it blind — reroute to the next lane in the
  same domain and say so.

## Guardrails (unchanged, always apply)
- Never `git add -A`; stage explicit paths only.
- Public-repo discipline: no machine paths, spend, personal data, or fiction lore
  destined for `NouGenShards-push-main`.
- No em dashes in generated content — hyphens only.
- Ask before: merging any PR, enabling auto-merge, any destructive/irreversible action.
- If a subcommand or intent genuinely isn't wired above and `ToolSearch` finds nothing
  matching, say so plainly and ask whether to add it — don't silently no-op.
