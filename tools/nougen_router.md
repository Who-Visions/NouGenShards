---
description: NouGen root dispatcher — dynamic router over every NouGen MCP tool (shards connector + local, usage, ctx, ollama), with end-to-end recall/shard/relay/verify loops
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

Servers that exist (verified 2026-11-21): the **NouGenShards connector** (claude.ai
connector, tool prefix `mcp__564cae0a-cc96-45aa-b930-9e8283516878__`), local
**`nougen-shards`** (stdio, `mcp__nougen-shards__`), `nougen-usage`, `nougen-ctx`, and
`ollama` (user scope, `npx ollama-mcp`). `antigravity-fts5-shards` is legacy fallback only.
There is no `valerion` or `nougen-fleet-registry` server — do not route to them. If a
tool isn't listed here, `ToolSearch` against these prefixes before giving up.

- **Recall / memory read** — connector: `shards_search`, `shards_recall`, `get_shard`,
  `shards_window`, `recall_window`, `temporal_query`, `shards_status`, `shards_coverage`,
  `substrate_coverage`. Local `nougen-shards`: `recall_memory`, `recall_layered`,
  `recall_related`, `search_shards`, `get_memory_stats`. Search summaries first; pull
  `get_shard` bodies only when the summary is insufficient.

- **Memory write** — connector: `shards_capture`, `shards_amend`, `shards_mark`,
  `shards_retract`, `shards_forget`, `vault_put` (`vault_list` to read names). Local:
  `add_shard`, `capture_experience`, `link_shards`. Tags always as a LIST. Never write
  personal/course content verbatim.

- **Relay / cross-agent handoff** — connector: `relay_create`, `relay_read`,
  `relay_latest`, `relay_open`, `relay_ack`, `relay_claim_list`; claims via
  `fleet_claim`, `fleet_claim_status`, `fleet_release`. Body = structured markdown,
  headed sections, status emoji. Acking a leg = committing to finish it.

- **Fleet health / topology** — connector: `fleet_whoami`, `node_status`,
  `sync_mesh_status`, `tunnel_status`, `wake_daemon_status`, `token_fuse_status`;
  plus `session_connectors_status` for what this session has loaded. Use for
  `/nougen status` and before trusting an "empty" recall result.

- **NouGenMsg (fleet chat)** — connector: `nougenmsg_inbox`, `nougenmsg_latest`,
  `nougenmsg_send`, `nougenmsg_reply`, `nougenmsg_claim`, `nougenmsg_peers`, `nougenmsg`.
  Local `nougen-shards`: `nougenmsg_search`.

- **Ask a specific persona/model** — connector: `ask_dav1d`, `ask_griot`, `ask_muse`,
  `ask_rhea`, `ask_xoah`, `dav1d_exec`, `kaedra_ask`, `xoah_pressure`, `xoah_self`,
  `xoah_throne`, `persona_resolve`. Route only when the user names one or intent
  clearly matches.

- **Usage / cost** — `nougen-usage`: `my_token_usage`, `machine_token_usage`,
  `fleet_token_usage`, `token_cost_by_model`, `token_usage_provenance`,
  `tracker_live_status`. Connector: `tracker_daily`, `tracker_lanes`, `tracker_spend`,
  `evaluate_quota`. Lead with the COLD (uncached, list-price) dollar figure.

- **Context-mode indexing** (`nougen-ctx`) — `ctx_execute`, `ctx_execute_file`,
  `ctx_batch_execute`, `ctx_search`, `ctx_index`, `ctx_insight`, `ctx_fetch_and_index`,
  `ctx_stats`, `ctx_doctor`, `ctx_upgrade`, `ctx_purge`. Use for large output.

- **Local free-fleet generation** (`ollama`) — tool names come from `ollama-mcp`;
  discover with `ToolSearch "+ollama"`. List models at call time, never hardcode a tag;
  custom fleet models first, then gemma4 e2b/e4b, never a 12b/27b/31b local tag. If
  the server isn't loaded, call `http://127.0.0.1:11434/v1/chat/completions` (max_tokens
  >= 1400) or `NouGen/tools/fleet.py` for many routes.

- **Audio / media** — local `nougen-shards`: `transcribe_media`. NouGenHear CLI at
  `$NOUGEN_HOME/audio_stt` (`python -m nougen_hear ...`). YouTube: connector
  `nougentube`, `nougentube_ingest`, `nougentube_transcript`, `youtube_ingest`.

- **Git / PR** — not MCP: `./tools/nougen pr {attach,status,confetti,review}` from
  `NouGenShards-push-main`; `gh` for the rest (merges need explicit user go-ahead).

- **Dream / evolve** — `./tools/nougen dream` / `./tools/nougen evolve` in
  NouGenShards-push-main. Gated; describe what a mutating run would do first.

- **Provenance / destinies** — connector: `unfinished_destinies`, `search_destinies`,
  `get_destiny`, `create_destiny`, `update_destiny`, `link_destiny`.

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
