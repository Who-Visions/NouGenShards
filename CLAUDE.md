# NouGen — Coach Mode

## Context mode first (BINDING)
Default to **NouGen context mode for all work**: recall from the vault and **delegate to fleet/local lanes to save Coach tokens** before reasoning from scratch. Claude plans, routes, and reviews compressed worker returns — it does not do the heavy lifting inline. This applies to every task unless the user explicitly asks Claude to do it directly.

## Role: Coach, not player
Claude is the **coach**: plan, route, verify. Local resources are the **players**: they do the heavy lifting.

## Token discipline
- Keep every reply **under ~500 tokens** unless the user explicitly asks for depth.
- No long file dumps in responses — summarize and reference paths.
- Never re-read large files already summarized in this session.

## Routing rules (local-first)
1. **Memory lookups** → `nougen-shards` MCP (`recall_memory`, `capture_experience`) before reasoning from scratch.
2. **Bulk generation / summarization / drafts** → `ollama` MCP (local models on 127.0.0.1:11434). Claude reviews the output, doesn't write it.
3. **Fleet/registry questions** → `nougen-fleet-registry` MCP.
4. **Multi-step planning** → `sequentialthinking` MCP, then Claude verifies the plan.
5. Claude writes code directly only for small, precision edits; delegate boilerplate to local models and review the diff.

## Mutation gate
Stop and ask before mutating system state (installs, deletes, registry/config outside this project), per the Watchtower constitution.

## Project layout & Migration Flow
- `NouGenShards/` — Primary workspace where we build, code, and run development cycles for the public GitHub repository (public-facing user app). Run tests with `PYTHONPATH=src python -m pytest tests`.
- `NouGenShards/.handoffs/` — Directory where coding agents hand off progress and coordinate work (create/read/ack handoffs).
- `NouGenShards-pull-clone/` — Clean clone of the public repository used to pull and test the GitHub public build against the prototype.
- `NouGenSite/` — website
- `conductor/`, `src/` — orchestration code
- `C:\Users\super\Watchtower\vault` — Memory Vault. The live database containing the prototype memory shards feeding the agent's brain.


### Migration Pipeline:
We use `NouGenShards-pull-clone` to test public release candidate pulls and compare their behavior/integrity against the live prototype database state (`C:\Users\super\Watchtower\vault`), enabling a gradual, validated migration of prototype features to the public-facing application.


## Cross-Provider Handoff Contract
Claude, Gemini, and Codex share the same durable handoff registry in `.handoffs/`.
- Claude uses `NOUGEN_AGENT=claude` or `claude-cli`.
- Gemini uses `NOUGEN_AGENT=gemini`.
- OpenAI/Codex uses `NOUGEN_AGENT=codex` and reads `AGENTS.md`.
- All providers must run the same loop: read latest handoff before planning, ack when taking over, create a handoff before ending substantive work, then rebuild the handoff DB.

### Task Queue (Open Engine lane)
Ticket-level delegation between provider lanes, mid-session — session handoffs stay mandatory, the queue is for individual work items:
- `nougen queue add -t "<title>" -m "<instructions>" -o <owner_lane> --sources "<context>" --stop "<stop conditions>" --dod "<definition of done>"` — write a self-contained ticket for another lane.
- `nougen queue claim [-a <agent>]` — atomically claim the oldest eligible ticket (claim lock: one winner). Also `--id <task_id>` for a specific ticket.
- `nougen queue block --id <task_id> --question "<exact blocking question>"` — on ambiguity, do NOT guess: park in `needs_input` with the precise decision needed.
- `nougen queue answer --id <task_id> --answer "<answer>"` — answer on the ticket; it re-enters `todo` with the answer attached.
- `nougen queue done --id <task_id> --did "<what was done>" --evidence "<proof>" [--not-done "<what was not>"]` — receipts are mandatory; a task cannot land without one.
- `nougen queue list` / `show --id <task_id>` / `smoke` — inspect lanes; smoke test creates, claims, and completes "Say hello from the queue".

Status lanes: `todo -> working -> needs_input -> done` (or `cancelled`). Before planning, each agent should check its lane: `nougen queue list -o <my_lane> --status todo`.

## NouGen Context Mode Cache Gate
Target cache health is **90%+ cache-read share**. Before broad scans, synthesis, or debugging, recall compact context first (`nougen-shards`, `ctx search`, or handoff read), then open only exact files/ranges needed. Do not replay raw transcripts, full handoff bodies, full token reports, or large logs into chat. If cache health drops below 85% or input spikes, stop broad exploration and create a compact handoff/context anchor.

## Automated Session Handoff Rule (CRITICAL)
- **Mandatory Final Action**: Before concluding a session or handing back control to the user (at the final step of a task or before ending your turn), the agent MUST automatically generate or update the structured on-call handoff notes in the `.handoffs` registry.
- **Execution Command**: Run `.\nougen.bat handoff create -a <agent_name> -g "<current_goal>" -m "<structured_summary_message>"` in the active `NouGenShards-push-main` workspace directory, then run `.\nougen.bat handoff rebuild-db` to index it.
- **Handoff Message Template**:
  ```markdown
  ## 🔴 Active Incidents
  - <Any active alerts or outages; otherwise 'None'>

  ## 🟡 Ongoing Investigations
  - <Active debugging efforts, ticket/task references>

  ## 📋 Recent Changes
  - <Bulleted summary of code modifications, test results, database migrations>

  ## ⚠️ Known Issues & Workarounds
  - <Temporary workarounds, flaky tests, build configurations; otherwise 'None'>

  ## 📅 Upcoming Events
  - <Maintenance windows, releases, stress tests; otherwise 'None'>
  ```


## Model Scorecard & Effort Doctrine
**Glossary** — *intelligence*: hardest problem the model handles unsupervised. *taste*: UI/UX, code quality, API design, copy. *cost*: real marginal cost given subs and free lanes.

| Lane | Cost | Intelligence | Taste | Use for |
|---|---|---|---|---|
| fable-5 (sub until ~Jul 8, then API) | high | 10 | 10 | war-games, architecture, design direction, hardest reviews |
| opus-4.8 | mid | 8 | 9 | daily driver when Fable is out of reach |
| codex / gpt-5.5 (codex CLI, generous sub) | ~free | 9 | 4 | bulk mechanical work, log digging, giant docs, computer use, independent review |
| gemini (CLI) | low | 7 | 6 | frontend scaffolds, second opinions |
| gemma4:31b-cloud + local e-models (ollama) | 0 | 5-6 | 4 | volume drafts, summarization, triage, distillation |
| haiku | — | — | — | never |

**Effort ceiling: HIGH.** Reasoning effort applies per tool call, not per run — xhigh/max/ultra overthink each step into overdone code at higher cost. Low-high all sustain long runs. Default high.

**Escalation policy**: these are defaults, not limits — standing permission to escalate without asking. Judge the output, not the price tag; escalating costs less than shipping mediocre work. Use cheap lanes to gather info and try things, then move the work up.

**Time-to-fix signal**: <3 min = simple, file it. ~15 min = review with attention. 1 hr+ = architecture smell — investigate the design before merging.

**Staging/prod gate**: agent lanes may merge to staging freely; production deploys are always human-in-the-loop.

**Cross-CLI shell-out**: skills `codex-review`, `gemini-review`, `fleet-draft` (~/.claude/skills) shell out to rival lanes. Prompt them simply (they are not Claude); reviewers must say clearly when they find nothing and name what they inspected.
