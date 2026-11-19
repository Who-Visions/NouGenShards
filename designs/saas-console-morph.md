# SaaS console architecture invariants

Source: two architecture briefs pasted by the GM on 2026-11-10 (a 20-page authenticated customer dashboard, then a 20-page developer-platform control plane modeled on public AI and cloud consoles). The briefs were written by an outside assistant. Statements about how OpenAI, Anthropic and Google Cloud consoles behave were not independently checked here, so the vendors are treated as analogies, not authority.

## Observed evidence

- Brief A organizes 20 authenticated pages into six navigation groups: Command Center, Execution, Intelligence, Platform, Organization, Account.
- Brief B organizes 20 pages into five groups: Home and Organization, AI Development, Build and Deploy, Operations, Security and Business.
- Both briefs insist the customer application is separate from internal platform administration.
- Both briefs say not to show 20 destinations at equal weight, and not to ship dead-end tabs.
- A working prototype of the shell was published privately on 2026-11-10 (single HTML file, illustrative data, no backend). It is a design reference only.

## NouGen invariants (inferred adaptations, now binding for any NouGen console)

1. **Two authorization boundaries.** The customer application and platform administration (fleet operations, tenant-wide incident response, privileged actions) are different products with different authorization. A customer page never links into an operator surface.
2. **Scope chain.** Organization, then project, then environment, then resources, then execution, then observability, then governance. Every record names its scope. An organization and project switcher is always present.
3. **Shell.** Five persistent elements: organization/project switcher, global command search, categorized sidebar, main work surface, optional contextual inspector. Detail inside a page (Overview, Logs, Members, Settings) uses page-level tabs, not more primary navigation.
4. **Navigation weight.** At most 20 primary pages, grouped into six or fewer collapsible groups. Groups, not a flat list. Contextual subpages are unlimited. The sidebar is role-dependent.
5. **Route-level enforcement.** Each route authorizes on the server, retrieves only scoped data, and has its own loading, empty, error, stale and permission-denied states. A hidden menu item is never a security boundary.
6. **Honest gating.** Build every route into the information architecture, implement the 8 to 10 highest-value pages first, and label unavailable pages as planned or gated. No dead-end tabs.
7. **Plane separation.** The control plane (metadata, policy, configuration) is separate from the execution and data plane. A dashboard outage must not stop production traffic or running work.
8. **Truthful data.** Sample values are labeled illustrative. A prototype never presents invented telemetry as real.
9. **Approve before acting.** Assistant suggestions show their evidence and wait for approval; consequential actions are logged to Activity.

## Reference page sets (candidate information architectures, not final)

- **Customer application (brief A):** Overview, My Workspace, Activity Feed, Notifications / Projects, Tasks and Jobs, Automations, AI Agents / Analytics, Live Telemetry, Knowledge and Memory, Reports / Integrations, API and Webhooks, Files and Assets, Deployments / Team and Access, Billing and Usage / Account, Security, Settings.
- **Developer-platform control plane (brief B):** Command Center, Organizations, Projects and Workspaces / Model Catalog, AI Playground, Agents and Assistants, Prompts and Evals, Knowledge and Storage / Applications, Deployments, Workflows and Jobs, API and Integrations / Observability, Usage and Costs, Limits and Quotas, Resource Manager / Identity and Access, Security and Audit, Billing, Settings and Support.
- **Priority in brief B:** P0 foundation (Command Center, Organizations, Projects, Model Catalog, Playground, API and Integrations, Usage, Identity and Access); P1 operations (Agents, Deployments, Workflows, Observability, Limits, Billing, Security and Audit); P2 advanced (Prompts and Evals, Knowledge and Storage, Applications, Resource Manager, Settings and Support).

## Untested candidate

One execution trace that shows the model, agent, tool, cloud resource, budget and permission that took part in a request. Proposed by the brief as a differentiator, not something the reference consoles are shown to share. Record as a candidate; adopt only after a build exercises it.

## Open questions for the GM

- Which surface lives on nougenai.com and which on aiwithdav3.com, and which of the two page sets above is the first build. Unresolved: no routing was invented.
- Whether the matte-amber palette of nougen-core or the violet and gold of the prototype is the console palette. The prototype uses a gradient logo mark and a blurred header, which nougen-core lint rejects, so it does not pass this repo's own rules.

## Acceptance checks

- Open every route as each role and confirm the server refuses the request, not only the menu.
- Confirm no route is reachable with an empty scope (no organization or project selected).
- Confirm each page renders loading, empty, error, stale and denied states.
- Confirm a gated page says what is missing and who can enable it.
- Confirm stopping the dashboard process leaves API traffic and running jobs untouched.

This change updates design authority and review criteria. It does not implement a console.
