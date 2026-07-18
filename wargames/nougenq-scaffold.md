# War-Game: NouGenQ Phase-1 Scaffold
Executor: Claude Cli (Fable) inline — scaffold is precision CLI work, not volume; fleet lanes take over for boilerplate drafts post-scaffold.
Date: 2026-07-14 | GM order: "BUILD NEXT.JS LATEST ALL DEPENDENCIES NEEDED"

## Mission
Stand up `C:\Users\super\Watchtower\NouGen\NouGenQ` — Next.js (latest) + TS + Tailwind app shell for the live copilot: SAY/DO/CAUTION lanes UI, env-driven config (Rule 0.2), local-lane (ollama) + cloud-lane (Anthropic) deps, evidence DB dep.

## Moves
1. Probe toolchain (node, pnpm versions).
   - Worked: versions print. Fail: pnpm missing → countermove: `corepack enable` or npm fallback.
2. `create-next-app@latest` non-interactive, pnpm, TS, Tailwind, App Router, src-dir.
   - Worked: dir + package.json exist. Fail: prompt hang → countermove: add `--yes` / pipe defaults; network fail → retry once, then npm registry check.
3. Add deps: zustand, zod, @anthropic-ai/sdk, ollama, ws, better-sqlite3, lucide-react, clsx.
   - Worked: lockfile updated. Fail: better-sqlite3 native build error on Windows → countermove: keep it out, note in ledger, evidence DB via sql.js later.
4. Write config layer (`src/lib/config.ts`: env → probe → logged fallback), `.env.local.example`, SAY/DO/CAUTION shell page, `/api/health` that probes ollama live.
   - Worked: files exist, no hardcoded ports/models outside fallback constants.
5. Verify: `pnpm build` (or dev-server boot + health probe).
   - Worked: build passes / health returns ollama model list. Fail: type errors → fix inline (small); ollama down → health reports degraded, not crash.

## Forks
- If ollama (127.0.0.1:11434) unreachable at verify → route A: health returns `{ollama:"offline"}` and scaffold still ships. Never block scaffold on runtime services.
- If Next latest major has breaking create flags → route B: pin to last-known-good major, log to ledger.

## Abort conditions
- Disk free < 2G on C: (recent Errno 28 history) — check first.
- create-next-app fails twice on network.

## Done =
Build green, health route live-probes ollama, zero unlogged magic values, milestone shard + handoff written.
