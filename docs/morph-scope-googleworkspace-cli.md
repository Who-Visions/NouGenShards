# Morph Scope: googleworkspace/cli

## Source

- Repo: https://github.com/googleworkspace/cli
- Org: `googleworkspace` (GitHub org name suggests Google), **but the repo's own README disclaimer states explicitly: "This is not an officially supported Google product."** Treat it as community/unofficial despite living under the `googleworkspace` org handle — do not assume Google-maintained SLAs, security review, or long-term support.

## What it does

A single Rust-built CLI (`cli`, via Cargo/npm/Homebrew binaries) that provides unified command-line access to Google Workspace APIs — Drive, Gmail, Calendar, Sheets, Docs, Chat, and Admin — explicitly positioned for both human and AI-agent use. Per its README: *"One CLI for all of Google Workspace — built for humans and AI agents. Drive, Gmail, Calendar, and every Workspace API. Zero boilerplate. Structured JSON output. 40+ agent skills included."*

Key characteristics:
- **Dynamic command surface**: builds its commands at runtime from Google's Discovery Service, so it tracks API changes automatically rather than being hand-maintained per endpoint.
- **Structured JSON output** with pagination support — designed to be scriptable/agent-parseable.
- Ships an **AI agent skills library** (100+ documented skills / helper `+`-prefixed commands for common tasks like sending mail, scheduling events, uploading files).
- Integrates with **Gemini CLI Extension** and **Model Armor** (Google's response-sanitization layer).
- Handles OAuth / service-account / token auth flows itself.
- **It is a CLI binary, not an MCP server.** No MCP protocol surface — any agent wanting to call it via MCP would need a wrapper shelling out to the binary.

## Overlap / dedup assessment vs. NouGen's existing port

This scope doc was requested to compare against `src/nougen_shards/google_workspace/` (a native Gmail/Calendar/Drive MCP port), documented at `docs/google-workspace-mcp-port.md`.

**Neither of those paths exists in this repository, on any branch, as of this research (2026-09-22).** Specifically checked:
- `src/nougen_shards/google_workspace/` — not found (`Glob **/google_workspace/**` returns nothing).
- `docs/google-workspace-mcp-port.md` — not found.
- A local branch named `feat/google-workspace-mcp-port` exists, but it has **zero commits ahead of `main`** and contains no google_workspace-related files beyond `data/pricing/google.json` (an unrelated pricing table). It appears to be a placeholder/reserved branch name, not completed or in-flight work.

So the requested "overlap assessment vs. an existing native Gmail/Calendar/Drive MCP port" cannot be performed — **there is nothing to overlap with yet**. This session's Google/Workspace tool access is instead provided live via three already-connected MCP connectors visible in this conversation (Gmail, Google Calendar, Google Drive — `mcp__360c7be6...`, `mcp__46ae10f6...`, `mcp__ce805fcc...`), which already cover message/thread/label ops, calendar events, and Drive file ops through host-managed OAuth. Any future native `google_workspace` MCP port work should be checked against **those** connectors' coverage too, not just a doc that doesn't exist yet.

## Recommendation: **Skip** (for now)

Reasoning:
1. There is no existing native port in this repo to merge into or de-duplicate against — the premise doc is missing. Before deciding port/merge, someone needs to confirm whether `docs/google-workspace-mcp-port.md` and the module were lost (branch reset, squash, wrong repo) or simply never written, and whether the `feat/google-workspace-mcp-port` branch name was a reservation for exactly this decision.
2. The target repo is an **unofficial**, Rust CLI binary — adopting it means shelling out from Python/MCP, not importing a library. That's a wrapper-and-maintain commitment, not a low-cost import.
3. Live Gmail/Calendar/Drive MCP connectors are already present and working in this environment, covering the same three services this CLI targets. A CLI wrapper would be redundant with connectors already doing the job through host-managed auth, unless the specific draw is the CLI's **dynamic Discovery-Service command surface** (auto-covers every Workspace API, not just Gmail/Calendar/Drive) or its **bundled agent-skills library**.
4. If the missing native port turns out to still exist somewhere (another machine/branch not seen here), the right move is likely **skip** entirely — a hand-built native MCP port already covering Gmail/Calendar/Drive makes a CLI-wrapper approach a downgrade (subprocess overhead, an extra Rust binary dependency, less structured error handling than an MCP tool call).

## What a port would require (if pursued despite the above)

- Locate/restore the actual `google_workspace-mcp-port` prior work (grep other machines' shards/handoffs for the doc content, or confirm it never landed) before scoping is meaningful.
- Install the Rust binary (Cargo/npm/Homebrew) and evaluate `+`-prefixed helper commands and the "40+ agent skills" bundle for genuine incremental coverage beyond Gmail/Calendar/Drive (e.g. Sheets, Docs, Chat, Admin SDK — services the current three connectors do not cover).
- Decide the integration shape: (a) thin MCP server that shells out to the `cli` binary per call, or (b) skip MCP entirely and invoke it via `ctx_execute`/sandboxed shell per NouGen's context-mode routing rules, since it is CLI-native rather than library-native.
- Auth: reconcile its own OAuth/service-account flow against NouGen's existing Google auth (avoid a second, conflicting credential store).
- Because it is unofficial and dynamically regenerates its command surface from Discovery Service, pin a version/commit and re-validate before any production use — command surface is not guaranteed stable across releases.
