# 🤝 Git Handoff — claude-cli

**Goal**: mobile no-computer users architecture Q&A
**When**: 2026-09-13T19:26:00Z

---
No repo changes this session (design Q&A only; working dir C:\Users\super\Watchtower\NouGen is not a git repo).

Answered Dave's question: how to capture users who have no computer, and where memory lives given gemma4 runs on mobile.

- **No-computer users**: they need a client, not compute. A PWA/thin mobile app hitting the existing NouGenShards MCP gateway (mcp.nougenai.com) is the on-ramp — same gateway already built for desktop connectors, mobile client instead of Claude Desktop/Code as caller.
- **Gemma4 on mobile is for on-device inference, not storage.** Memory vault stays server-side (per-user partitioned DB, existing shard vault pattern). Device keeps only a capped rolling digest (last N turns + compressed summary/embeddings, ~50-100MB cap via SQLite + vector index), synced down at session start and deltas synced up after. Falls back to shards_recall server-side for anything outside the local cap.

**Blocker encountered**: `tools/nougen` handoff CLI had no built `.venv` in this NouGenShards workspace. Triggered `nougen.bat` (which builds/heals `.venv`) via `cmd //c` with `NOUGEN_NO_PAUSE=1`; the build hung in background (task id `bleu1suys`) far longer than a normal first-time install without producing output. Abandoned waiting on it and wrote this handoff file directly instead, matching the existing `.handoffs/*.md` format, so as not to loop indefinitely on a stuck build.

**Follow-up for whoever picks this up**: check why `nougen.bat`'s venv build stalled/produced zero output in NouGenShards (as opposed to NouGenShards-push-main, which is the workspace named in CLAUDE.md but does not exist on this machine — only `NouGenShards` does). Consider running `handoff rebuild-db` once the CLI is functional again to index this file.
