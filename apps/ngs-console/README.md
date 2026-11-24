# NGS console (draft)

An agent console over the NouGenShards native engine (`engine/ngs`), built with
shadcn/ui's agent UI pieces. Local workstation tool, not deployed.

## Run it

```bash
cd apps/ngs-console
npm install
npm run engine   # builds engine/ngs/build/libnougenshards.a and build/ngs_cli
npm run dev      # http://localhost:3210
```

`npm test` runs the planner and gate parser tests. `npm run typecheck` and
`npm run build` should both be clean.

## What is wired and what is mocked

| Piece | State |
| --- | --- |
| Remember, read, scan, stats, verify and checkpoint | Live. Each call spawns `ngs_cli`, a JSON CLI over `ngs.h` (`engine/ngs/tools/ngs_cli.c`). Facts go to `.ngs-data/console/`, which git ignores. |
| Judge gates | Live. Runs `make -C engine/ngs check test crash` and renders header, unit and crash suites in the Test Results pattern. |
| Bench | Live. `ngs_cli bench N` on a temp log that is deleted afterwards. |
| Recall | Live call, but `ngs_recall` returns MISUSE in M1 (fused recall is M4). The agent shows that step and falls back to a keyword scan. |
| Bake-off scorecard and Phoebus 50K numbers | Snapshot from fleet shards (32832@db7, 39641@db7, 31779@db8, 40066@db1), dated in the UI. The judge repo is private, so this is not live. |
| Agent | A deterministic planner (`lib/agent.ts`): no model, no API key. It can be swapped for an LLM agent (an AI SDK route or an agentcn recipe) behind the same NDJSON stream. |
| Fallback | If `ngs_cli` is not built, every route serves values recorded from a real run (`lib/mock.ts`), and the UI marks them "recorded". A production build serves recorded data unless `NGS_CONSOLE_ENABLE=1`, so a preview deploy cannot spawn binaries. |

Engine paths resolve at runtime: `NGS_ENGINE_DIR`, `NGS_CLI` and `NGS_DATA_DIR`
override the repo layout.

## shadcn pieces

From the shadcn/ui AI Elements set: Trace (TraceLine, TraceCollapsible), Message,
Bubble, Code Block, Message Scroller (`@shadcn/react`) and Input Group as the
prompt input, following the Chat, Tool and Test Results patterns. Plus Tabs,
Card, Table, Badge, Button and Spinner. Components are vendored from
`shadcn-ui/ui` (`apps/v4/registry/bases/radix`) with the Nova style, because
the registry host was not reachable from the build session.
