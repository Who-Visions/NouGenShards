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
- `%USERPROFILE%\Watchtower\vault` — Memory Vault. The live database containing the prototype memory shards feeding the agent's brain.


### Migration Pipeline:
We use `NouGenShards-pull-clone` to test public release candidate pulls and compare their behavior/integrity against the live prototype database state (`%USERPROFILE%\Watchtower\vault`), enabling a gradual, validated migration of prototype features to the public-facing application.


## Cross-Provider Handoff Contract
Claude, Gemini, and Codex share the same durable handoff registry in `.handoffs/`.
- Claude uses `NOUGEN_AGENT=claude` or `claude-cli`.
- Gemini uses `NOUGEN_AGENT=gemini`.
- OpenAI/Codex uses `NOUGEN_AGENT=codex` and reads `AGENTS.md`.
- All providers must run the same loop: read latest handoff before planning, ack when taking over, create a handoff before ending substantive work, then rebuild the handoff DB.

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

