# Morph scope: aaronsb/google-workspace-mcp

## Note on task premise (read first)

The task that produced this doc asked me to compare aaronsb/google-workspace-mcp
against "src/nougen_shards/google_workspace/ (a native Gmail/Calendar/Drive MCP port
already done)" and a prior scope doc at
`docs/google-workspace-mcp-port.md`. **Neither exists in this repository.**

Checked and confirmed absent:
- `C:\Users\super\Outpost\NouGen\docs\google-workspace-mcp-port.md` — not on disk on
  the current branch (`fleet/nougenmorph-elevation`), nor findable via glob.
- `src/nougen_shards/google_workspace/` — no such path under `NouGen\src`.
- Git history: `git log --all` and `git ls-tree -r` across all branches (including
  `feat/google-workspace-mcp-port`, which exists as a branch name but its tip commit
  is `bbf79e1` "nougenlive activation handshake" — unrelated) show no file or commit
  containing `google_workspace`, `google-workspace-mcp`, or `taylorwilsdon` anywhere
  in this repo.
- `NouGenShards/` (the sibling public-facing workspace) — also searched, also empty
  for this path/module.

What this session **does** have live is a set of first-party Google connector MCP
tools (Gmail, Calendar, Drive — `mcp__360c7be6...`, `mcp__46ae10f6...`,
`mcp__ce805fcc...`), which are platform-provided connectors, not a
NouGen-repo-owned Python port of an upstream MCP server. They are not the artifact
described in the task premise.

This doc proceeds with what could actually be verified: research on aaronsb's repo
itself. The dedup/overlap section below is necessarily conditional, since the
"existing port" to compare against isn't present to inspect.

## Source

- Repo: https://github.com/aaronsb/google-workspace-mcp
- Author: aaronsb
- **Independent implementation**, not a fork of taylorwilsdon/google_workspace_mcp.
  The two are separate projects covering similar ground (both are MCP servers for
  Google Workspace), not shared lineage — no common commit history, no fork
  relationship on GitHub.
- License: dual Apache 2.0 (primary) / MIT (earlier contributions). No paid tier.

## What it is / what it does

An MCP server giving AI agents (Claude Desktop, Claude Code, other MCP clients)
access to Google Workspace under the user's own OAuth credentials — no middleman
service, no vendor-hosted proxy.

- **Stack**: TypeScript / Node.js (22.12+).
- **Coverage**: 12 tools across 8 Google services — Gmail (search/read/send/triage/
  labels), Calendar (agenda, create, natural-language quickAdd), Drive (search,
  upload, download, permissions), Docs, Sheets, Tasks, Meet, Contacts.
- **Design philosophy**: built from Google's machine-readable API specs rather than
  hand-transcribed bindings; deliberately curates ~95 operations out of 257 available
  Google methods to reduce agent decision complexity (fewer, better-chosen tools
  rather than exhaustive API surface).
- **Auth/storage**: credentials stored locally in XDG-compliant dirs (`~/.config`,
  `~/.local/share`); supports multi-account with per-account read-only options.
- **Install**: `.mcpb` bundle for Claude Desktop, one-line install for Claude Code,
  or manual MCP client config.

## Overlap / dedup assessment vs "existing port"

Cannot be performed as scoped — there is no existing NouGen Gmail/Calendar/Drive
port in this repo to diff against (see premise note above). Two honest options for
what "existing" might actually mean, both checked:

1. **A prior NouGen-owned Python port of taylorwilsdon/google_workspace_mcp** —
   not found anywhere in this repo's history or working tree. If it exists, it lives
   in a different repo/machine than the one this session ran in
   (`C:\Users\super\Outpost\NouGen`, branch `fleet/nougenmorph-elevation`). Worth
   checking `NouGenShards-pull-clone`, `Watchtower`, or another machine (blade/
   whoart) before concluding it truly doesn't exist — this session did not scan
   the full Outpost root (Rule 0.4 forbids it) and only checked the two named
   sibling paths.
2. **The live Gmail/Calendar/Drive connector MCP tools available in this session**
   (`mcp__360c7be6...`, `mcp__46ae10f6...`, `mcp__ce805fcc...`) — these are
   platform-supplied first-party connectors, not code NouGen owns or could "merge
   into." No dedup question applies to them; they're outside NouGen's repo surface
   entirely.

If a genuine prior port turns up elsewhere, the actual overlap question is
straightforward: aaronsb's repo and taylorwilsdon's upstream (the one apparently
already ported) cover the same problem space — Gmail/Calendar/Drive-plus over MCP —
via two unrelated, non-forked implementations. A real diff would compare tool
counts, auth model, and language/runtime fit (TS/Node vs whatever the existing port
uses) before deciding whether aaronsb's is additive or redundant.

## Recommendation

**Skip — for now, pending premise verification.**

Rationale:
- There's nothing in this repo to merge into; a "merge-into-existing" recommendation
  can't be made responsibly without the target existing.
- A straight "port" would duplicate functionality NouGen already gets for free via
  the live first-party Gmail/Calendar/Drive connector tools in this environment —
  those are lower-effort (zero engineering) and already wired to the user's account.
- aaronsb's repo is TypeScript/Node; NouGen's stack (`nougen_shards`, sandboxed
  execution, shard capture) is Python-first. A port would add a second runtime
  dependency for capability that substantially overlaps what's already reachable.
- Before doing anything else, resolve the premise: locate (or confirm the absence
  of) the claimed existing `src/nougen_shards/google_workspace/` port and its scope
  doc, on another machine/repo if not here. That answer changes this recommendation
  from "skip" to a real dedup call.

## What a port would require (if pursued after premise resolves)

- Confirm no existing NouGen Python module already covers the same Gmail/Calendar/
  Drive/Docs/Sheets/Tasks/Meet/Contacts surface (this is the open item above).
- Either wrap aaronsb's Node/TS server as a subprocess MCP server NouGen shells out
  to (keeps TS as-is, adds a process-management/health-check layer), or reimplement
  the ~95 curated operations natively in `nougen_shards` Python to match existing
  stack conventions (shard capture, sandboxing, coach/token discipline) — the latter
  is the larger lift but the more consistent one architecturally.
- OAuth credential flow: decide whether to reuse aaronsb's XDG-based local credential
  storage pattern or fold auth into NouGen's existing credential handling.
- Multi-account support (a stated aaronsb feature) would need a decision on whether
  NouGen's use case needs it, given the fleet already runs 14+ Google accounts.
- Any port work should go through NouGen's own relay/handoff process (Rule 0.0.1)
  before starting, to avoid duplicating effort if this was already scoped or begun
  elsewhere in the fleet.
