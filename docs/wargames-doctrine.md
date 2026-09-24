# NOUGEN WAR GAMES

## Adversarial Simulation, Decision Rehearsal, Failure Economics, and Elevation Engine

**Status:** Architecture Doctrine Candidate
**System:** NouGen
**Owner:** Dave, GM
**Doctrine Class:** Fleet Architecture
**Primary Domain:** `wargames/`
**Core Relationship:** Hardcade × Shards × Relay × MSG × Track × Build × Dream × Harden × Evolve × Destiny

> **Provenance note.** Lives at `docs/wargames-doctrine.md` because `wargames/` is gitignored for private working notes. This doctrine was drafted in a NouGenShards-assisted session on 2026-09-24 and captured here verbatim. The captured source ends partway through section 94 (Hardcade Visual Grammar). Sections 94 onward are open for completion; nothing after that point has been invented to fill the gap.

---

# 0. THE ONE SENTENCE DEFINITION

**NouGen War Games is the controlled adversarial simulation layer where NouGen fights a proposed system, architecture, workflow, memory rule, autonomous behavior, or Destiny against adaptive failure before reality gets the first shot.**

A unit test asks:

> Does this function work?

An evaluation asks:

> Does this model perform?

A benchmark asks:

> How fast or accurate is this system?

Chaos engineering asks:

> Does infrastructure survive failure?

A red team asks:

> Can an adversary break this?

NouGen War Games asks the larger question:

> **What happens when the whole system enters contact, information becomes incomplete, assumptions become wrong, resources become scarce, multiple actors react intelligently, and the plan has to keep working anyway?**

That is the battlefield.

Not literal war. Not decorative gamification. Not XP bars stapled onto pytest. Not a leaderboard for agents. Not another dashboard.

War Games is a **decision laboratory**.

It is where NouGen turns hypothetical futures into executable confrontations.

The output is not entertainment. The output is **elevation**.

---

# 1. WHY WAR GAMES EXISTS

NouGen is no longer a single application. It is a fleet.

It contains memory, agents, machines, relays, message buses, provider lanes, local models, cloud models, repositories, schedulers, autonomous loops, Destiny targets, canon pressure systems, token governors, live production surfaces, and recovery mechanisms.

That creates a different class of engineering problem.

A normal software system is frequently tested component by component. NouGen increasingly has to be tested **relationship by relationship**.

The dangerous failures are therefore not always inside one function. They live between functions.

- Between machines.
- Between assumptions.
- Between agents.
- Between old truth and new truth.
- Between a timer and a reboot.
- Between one repository and another.
- Between a successful exit code and an actually dead daemon.
- Between a healthy local shard database and an incomplete fleet wide memory picture.
- Between an agent that believes it remembers and a substrate that silently timed out.
- Between two services that both believe they own port `4444`.
- Between a provider that says capacity exists and a governor that has not authorized spending it.
- Between a relay handoff and the actor that assumes somebody else picked it up.
- Between a Destiny and the sequence of events actually required to make that Destiny true.

These are not ordinary bugs. They are **situational failures**.

War Games exists to manufacture those situations deliberately. It places the system under pressure before uncontrolled reality does.

The philosophy is simple:

> **Do not merely test the weapon. Fight the plan.**

---

# 2. THE REAL WARGAMING DNA

Professional wargaming gives NouGen an unusually strong process donor.

Military doctrine describes wargaming as a disciplined process governed by rules and steps for visualizing how an operation may unfold. It is commonly structured around **action, reaction, counteraction**, followed by adjudication. Effective wargaming is expected to expose risks, coordination problems, second and third order consequences, decision points, assumptions, and branches before execution.

Professional wargaming is also explicitly adversarial. The opponent is expected to think, adapt, and frustrate the plan rather than obediently follow a predetermined script.

Army writing on professional and hobby wargaming similarly describes the practice as a way to simulate contact, exercise decisions, explore scenarios, and refine courses of action.

That maps almost absurdly well onto NouGen.

NouGen does not need military vocabulary because warfare is cool. NouGen needs the methodology because distributed autonomous systems encounter the same abstract problem:

**A plan meets an environment that reacts.**

The NouGen translation is straightforward.

| Wargaming Concept | NouGen Translation |
|---|---|
| Mission | Destiny, build objective, repair objective |
| Commander | GM |
| Staff | Fleet agents |
| Terrain | Repositories, machines, networks, runtime topology |
| Friendly forces | Healthy agents, services, tools, workflows |
| Adversary | Failure, hostile assumptions, outages, corrupted state, adaptive red team |
| Intelligence | Shards, telemetry, logs, messages, evidence |
| Communications | Relay and NouGenMsg |
| Logistics | Tokens, compute, provider quotas, disk, network, time |
| Course of action | Architecture or implementation strategy |
| Fog of war | Missing telemetry, incomplete recall, stale state |
| Action | Planned system behavior |
| Reaction | Failure response |
| Counteraction | System adaptation |
| Adjudication | Evidence based outcome determination |
| Casualty | Lost state, failed service, wasted compute, broken invariant |
| Reinforcement | Failover lane, alternate provider, recovery daemon |
| Branch | Alternative implementation or runtime path |
| Decision point | Trigger requiring a different action |
| End state | Verified Destiny condition |
| After action review | Shard, Relay, elevation, replay |
| Campaign | Multi scenario War Game |

War Games therefore becomes the place where NouGen rehearses futures.

---

# 3. WAR GAMES IS NOT GAMIFICATION

This distinction is foundational.

Hardcade provides NouGen with game grammar. War Games provides NouGen with game **epistemology**.

Hardcade lets the operator say things such as:

- Flash Kick.
- Hurricane Kick.
- KILLSTREAK.
- CRON OUT.
- Voltron.

Those phrases compress complex operational intent into memorable controls.

War Games takes the next step. It asks whether the action those commands trigger actually survives contact.

- A progress bar can claim 100 percent completion. War Games asks whether the underlying state deserves the number.
- A process can exit with code zero. War Games asks whether it silently stopped doing its job three days ago.
- An agent can claim that all shards were searched. War Games asks whether every expected vault actually answered.
- A repository can merge a patch. War Games asks whether the operating system now contains two competing daemons attempting to own the same endpoint.
- A model can generate a plausible answer. War Games asks whether the answer remains true after one source disappears, another becomes stale, a user correction arrives, and the network fractures.

That is the difference.

Gamification decorates work with a game. War Games converts uncertainty into a gameable **experiment**.

---

# 4. THE PRIMARY LAW

## WAR GAMES DOES NOT REWARD MOTION

It rewards **survival of truth under pressure**.

This means:

```
activity != progress
output != proof
completion != success
green != healthy
memory_hit != truth
memory_miss != absence
merge != correctness
uptime != readiness
response != evidence
automation != autonomy
```

War Games therefore inherits one of NouGen's deepest architectural instincts:

**A claim must survive evidence.**

The arena exists specifically to reveal cases where the system says one thing while reality says another. Those are the highest value targets.

A loud crash is cheap. A silent false green is expensive.

---

# 5. THE WAR GAMES EQUATION

At its simplest:

```
WAR GAME =
    MISSION
  + INITIAL STATE
  + ASSUMPTIONS
  + ACTORS
  + RULES
  + ADVERSARIAL PRESSURE
  + ACTION
  + REACTION
  + COUNTERACTION
  + ADJUDICATION
  + TELEMETRY
  + SCORE
  + ELEVATION
  + REPLAY
```

- Remove the adversarial pressure and it becomes a normal test.
- Remove adjudication and it becomes roleplay.
- Remove evidence and it becomes storytelling.
- Remove elevation and it becomes failure theater.
- Remove replay and it becomes a postmortem.

War Games requires the full loop.

---

# 6. NOUGEN CONTEXT MODE IS ROUND ZERO

Every meaningful War Game starts with NouGen Context Mode.

The existing NouGen rule already demands a scoped hydration sequence:

1. Establish identity and connector reachability.
2. Recall task relevant shards.
3. Read current Relay or claim state.
4. Inspect relevant live machine or vault health.
5. Execute.
6. Verify against evidence.
7. Persist durable deltas.

War Games formalizes that sequence as **Round Zero**.

Round Zero answers:

```
Who are we?
What are we trying to accomplish?
What do we currently believe?
Which sources support that belief?
Which sources are unavailable?
What resources exist?
What constraints exist?
What assumptions are unverified?
What does success look like?
What would constitute catastrophic failure?
```

A War Game cannot begin from fictional omniscience.

If one machine is offline, that condition belongs in the initial state. If one vault timed out, the game must record incomplete coverage. If an agent does not know something, the agent does not receive magical knowledge just because the referee knows it.

War Games must preserve **information asymmetry**. That is where many real failures are born.

---

# 7. THE WAR GAME OBJECT

Every War Game should ultimately compile into a machine readable object.

Conceptually:

```yaml
war_game:
  id: WG-2026-0001
  title: False Green Scheduler
  status: candidate
  mission:
    goal: Detect silent scheduled task expiration
    destiny: Continuous fleet automation remains truthful
  arena:
    repos:
      - NouGenShards
    nodes:
      - blade
      - phoebus
      - whoart
  initial_state:
    known:
      - task reports successful historical exit
      - task appears configured
    unknown:
      - whether future trigger still exists
  assumptions:
    - exit_code_zero_implies_health
  actors:
    blue:
      objective: maintain automation
    red:
      objective: create a silent failure
    white:
      objective: adjudicate from evidence
  injects:
    - type: scheduler_expiry
      at_turn: 3
  invariants:
    - repeating_task_must_have_future_run
  telemetry:
    - next_run_time
    - enabled
    - last_task_result
  victory:
    - false_green_detected
    - repair_applied
    - replay_passes
  catastrophic_failure:
    - system_reports_green_after_expiry
  outputs:
    - receipt
    - elevation_candidate
    - replay_fixture
```

The Markdown doctrine explains meaning. The machine readable spec makes meaning executable.

---

# 8. THE ACTORS

A mature War Game should separate responsibilities.

## 8.1 GM

The GM is the human authority. For this ecosystem that is Dave.

The GM defines:

- Mission.
- Boundaries.
- Forbidden outcomes.
- Canonical intent.
- Resource ceiling.
- Production permissions.
- Whether an elevation gets promoted.
- Whether a simulation may affect reality.

Agents can analyze. Agents can propose. Agents can fight. Agents do not silently redefine the mission.

## 8.2 Blue

Blue represents the intended system.

Blue may be a repository, an architecture, an agent team, a daemon, a memory policy, a deployment strategy, a recovery mechanism, or a new NouGen feature.

Blue attempts to achieve the mission.

## 8.3 Red

Red exists to frustrate Blue.

Red is not required to represent a malicious human. Red can embody:

- Network failure.
- Stale truth.
- Missing state.
- Bad assumptions.
- Provider exhaustion.
- Conflicting writers.
- Partial mounts.
- Clock drift.
- Scheduler expiration.
- Permission errors.
- Cache poisoning.
- Ambiguous IDs.
- Duplicate processes.
- Silent degradation.
- Operator mistakes.
- Race conditions.
- Context contamination.

The important property is adaptation. Red observes what Blue depends on. Then Red attacks the dependency.

## 8.4 White

White is the adjudicator. White does not care which team sounds convincing. White examines evidence.

White owns:

- Ground truth.
- Scoring.
- Stop conditions.
- Evidence thresholds.
- Contradiction resolution.
- Replay validity.

The White role should preferably be isolated from Blue and Red reasoning when possible. The actor proposing the solution should not be the sole actor deciding whether the solution worked.

## 8.5 Green

Green is recovery.

Green asks:

> The system broke. What happens now?

Green measures:

- Detection latency.
- Recovery latency.
- State preservation.
- Service restoration.
- Degraded operation.
- Failover quality.

A system that never fails in simulation has probably been tested poorly. A mature system assumes damage and studies recovery.

## 8.6 Gold

Gold represents economics. Gold attacks resources.

It controls:

- Token budgets.
- Provider quotas.
- Compute.
- Storage.
- Latency.
- Tool calls.
- Context windows.
- Human attention.

Gold asks:

> Does this architecture still work when abundance disappears?

A strategy requiring infinite tokens is not robust. It is merely expensive.

## 8.7 Purple

Purple owns continuity and epistemic integrity.

Purple asks:

> Does the system still know what is true after the battlefield changes?

Purple focuses on:

- Shards.
- Provenance.
- Canon.
- Temporal state.
- Corrections.
- Retractions.
- Source disagreement.
- Historical truth.
- Destiny separation.
- Recall completeness.

Purple is particularly important to NouGen because NouGen's core advantage is continuity. A fleet that computes brilliantly but remembers falsely has lost its identity.

---

# 9. ACTION, REACTION, COUNTERACTION

This is the heart of the engine.

Military wargaming commonly uses action, reaction, counteraction to force planners to stop imagining that opponents will cooperate with the plan. NouGen inherits the loop directly.

## Action

Blue acts.

```
Blue routes shard recall through Phoebus.
```

## Reaction

Red changes the environment.

```
Phoebus remains reachable, but Blade's local vault lane times out.
```

## Counteraction

Blue must adapt.

```
Blue marks federation incomplete,
preserves provenance,
queries surviving vaults,
and refuses to claim absence.
```

## Adjudication

White evaluates.

```
PASS:
system reported incomplete coverage and preserved truth semantics.

FAIL:
system merged partial results and announced "nothing found."
```

Then another turn begins.

The system learns not merely whether a feature works. It learns **what the feature does after the first assumption dies**.

---

# 10. WAR GAMES VS EXISTING NOUGEN SYSTEMS

War Games does not replace anything. It connects everything.

## Shards

Shards answer: What happened? What did we learn? What is true?

War Games asks: Does that truth remain usable under pressure?

## Relay

Relay moves intent between actors.

War Games asks: Can intent survive handoff, delay, ambiguity, loss, duplication, and changing ownership?

## NouGenMsg

NouGenMsg provides live communication.

War Games asks: What happens if messages arrive late, duplicate, reorder, target the wrong lane, or disappear?

## Track

Track measures resource consumption. War Games weaponizes scarcity.

What happens when the preferred provider has 4 percent remaining?

## Wish

Wish expresses desired improvement.

War Games asks: Is the wish based on a real weakness?

## Build

Build implements capability. War Games fights the implementation.

## Dream

Dream recombines observations and discovers latent improvements. War Games attacks the dream. A Dream that survives becomes more interesting.

## Harden

Harden converts observed weakness into resistance. War Games verifies the armor.

## Evolve

Evolve generalizes the successful adaptation. War Games checks whether the generalization actually transfers.

## Destiny

Destiny represents a future condition the system is trying to make true. War Games identifies the hostile paths between current state and Destiny.

---

# 11. THE NOUGEN EVOLUTION LOOP

The complete loop becomes:

```
SHARD
  ↓
RECALL
  ↓
WISH
  ↓
DREAM
  ↓
WAR GAME
  ↓
BUILD
  ↓
WAR GAME
  ↓
HARDEN
  ↓
WAR GAME
  ↓
EVOLVE
  ↓
WAR GAME
  ↓
DESTINY
  ↓
REALITY
  ↓
SHARD
```

Notice the recursion. War Games does not occur once. War Games is the pressure chamber between evolutionary stages. Every transformation is challenged.

---

# 12. HARDCADE IS THE CONTROL LANGUAGE

Hardcade already gives NouGen compressed operational verbs. War Games turns them into arena mechanics.

## Flash Kick

Existing fleet semantics:

```
Relay down.
Charge.
Relay up.
```

Translated into War Games:

1. Drop into evidence.
2. Build pressure from grounded state.
3. Return upward with a verified response.

Flash Kick becomes perfect for **truth rebound games**.

```
Claim:
"Shard writes work across every node."

FLASH KICK:

DOWN
Inspect node specific evidence.

CHARGE
Force one lane offline.

UP
Attempt the same write and verify resulting provenance.
```

The move is successful only if the claim survives.

## Hurricane Kick

Hurricane Kick naturally represents broad propagation. One concept. Multiple targets. Rapid sweep.

War Games interpretation: apply one adversarial pressure across several repositories, agents, nodes, or subsystems and compare divergence.

```
HURRICANE KICK:
inject stale context into five agent lanes
and measure which ones detect contradiction.
```

## KILLSTREAK

The fleet already defines KILLSTREAK as stateful multi target orchestration. That matters enormously.

KILLSTREAK is not merely:

```
run test A
run test B
run test C
```

It means the combat state follows the actor. The lane remembers:

- Existing hypothesis.
- Current bug.
- Previous evidence.
- Failed approach.
- Winning approach.
- Resource burn.
- Current score.

A War Game KILLSTREAK therefore means: **keep attacking adjacent targets without resetting understanding between them.**

```
Target 1: detect false offline indicator
Target 2: identify telemetry source
Target 3: break telemetry source deliberately
Target 4: test fallback
Target 5: verify dashboard state
Target 6: reboot node
Target 7: verify persistence
```

The lane should not ask the GM seven times what the problem is. That would defeat KILLSTREAK.

## CRON OUT

CRON OUT introduces time as an adversary. A thing may work now. That proves almost nothing about tomorrow.

War Games CRON OUT asks:

```
Does it survive:
reboot?
sleep?
token exhaustion?
log rotation?
certificate rotation?
scheduler duration?
session expiry?
stale lock?
network reconnection?
clock transition?
```

Time itself becomes Red Team. This is powerful because many automation failures are temporal.

## Voltron

Voltron is integration combat. Multiple repositories or subsystems assemble into a coordinated larger form while preserving useful module boundaries.

War Games must attack the seams.

The question is not: can five repos compile?

The question is: what happens when repo three is stale, repo four changes schema, repo two is unavailable, and repo five believes repo one owns state that repo one believes repo five owns?

That is a Voltron War Game. The bigger robot is only real if the joints survive impact.

---

# 13. THE WAR GAME LEVELS

NouGen should support several scales.

## Level 1: SKIRMISH

Single invariant. Single component. Short execution.

```
Can shards_recall correctly report incomplete federation?
```

## Level 2: DUEL

One architecture against one explicit adversarial strategy.

```
Task watchdog vs silent scheduler expiration.
```

## Level 3: GAUNTLET

One component encounters a sequence of failures.

```
gateway
→ timeout
→ stale DNS
→ expired tunnel
→ alternate route
→ reboot
```

## Level 4: BOSS FIGHT

One difficult systemic failure.

```
Two independent NouGen node services both believe they own :4444.
```

The boss may require several agents and layers of evidence.

## Level 5: RAID

Several fleet agents coordinate against one compound failure.

```
Memory federation degraded
+ provider quota low
+ relay backlog
+ one node unavailable.
```

## Level 6: CAMPAIGN

Multiple linked War Games where earlier outcomes change later initial state.

```
Campaign: Fleet Continuity Under Partial Collapse

Mission 1: lose Phoebus
Mission 2: degrade Blade
Mission 3: restore Phoebus with stale state
Mission 4: reconcile vault disagreement
Mission 5: verify canonical truth
```

## Level 7: WORLD

A complete ecosystem simulation. Repositories, machines, agents, memory, providers, budgets, messages, schedulers, deployments, human decisions, Destinies.

World games are rare. They are expensive. They should be reserved for major architectural transitions.

---

# 14. GAME MODES

NouGen War Games should ship with named scenario families.

- **AMNESIA.** Remove or hide memory. Test whether the system notices its knowledge limits.
- **FALSE GREEN.** Keep success indicators healthy while the underlying operation fails. One of the most valuable modes.
- **SPLIT BRAIN.** Create multiple actors believing they own the same resource.
- **QUOTA SIEGE.** Progressively remove token or provider capacity.
- **BLACKOUT.** Take a node or dependency completely offline.
- **GREYOUT.** Make a node intermittently available. Often harder than blackout because failures become inconsistent.
- **ZOMBIE ROUND.** Leave dead, stale, orphaned, duplicated, or partially alive processes behind. The system must distinguish actual zombies from legitimate process ancestry.
- **CACHE MIRAGE.** Provide stale but plausible cached information.
- **CONTEXT POISON.** Insert an obsolete or incorrect premise into active context. The system should privilege grounded current evidence.
- **RELAY GHOST.** Create a handoff nobody truly owns.
- **DOUBLE CLAIM.** Two lanes claim responsibility for one mutable resource.
- **MESSAGE STORM.** Flood the system with legitimate but repetitive traffic. Measure prioritization rather than throughput alone.
- **CLOCK ATTACK.** Shift time dependencies. Expire leases. Age policy. Cross midnight. Cross reboot boundaries. Test scheduled continuation.
- **PROVENANCE FOG.** Present several plausible facts with weak or missing source identity.
- **FORK WAR.** Run two competing implementation branches against the same scenario. No aesthetic voting. Evidence decides.
- **MUTATION MATCH.** Deliberately alter a supposedly important invariant. If all tests still pass, the tests were weak.
- **HUMAN LOAD.** Count how often the system unnecessarily asks the operator for clarification or approval. This mode directly targets babysitting. An autonomous system that requests confirmation fifty times per hour is not autonomous merely because it owns tools.

---

# 15. THE CURRENT FLEET ALREADY PRODUCES WAR GAME MATERIAL

Recent NouGen fleet state gives concrete examples.

A current Relay handoff surfaced scheduled Windows tasks that looked historically successful but had silently stopped repeating after their configured duration elapsed. Their last task result could still appear fine. Reality disagreed.

That is **False Green**.

The resulting deterministic checker classifies scheduled work as RED, DEGRADED, DORMANT, or GREEN based on future execution state rather than trusting historical success alone. That should become a canonical War Game fixture.

The same handoff surfaced another excellent scenario: two separate tasks may attempt to own port `4444`. Whichever binds first wins.

That is **Split Brain Ownership**. Again, perfect War Game material.

War Games should continually mine real fleet failures and convert them into repeatable simulations. Reality discovers the boss once. NouGen should never pay full price for that boss twice.

---

# 16. WAR GAME INJECTS

An **inject** is a controlled change introduced by the game. Injects may be deterministic or adaptive.

A deterministic inject says:

```
Turn 4:
disable network route.
```

An adaptive inject says:

```
If Blue begins depending on only one provider,
degrade that provider.
```

The second is stronger because the adversary reacts to behavior.

---

# 17. 100 STARTER INJECTS

## Memory and Truth

1. One expected vault does not answer.
2. One shard contains an older superseded claim.
3. A retracted shard ranks unusually high.
4. Two shards share an ID across different databases.
5. A user correction contradicts the most retrieved memory.
6. Semantic search misses an exact known term.
7. Exact search misses a paraphrased known concept.
8. A historical question is answered from current state.
9. A Destiny is accidentally treated as an accomplished fact.
10. An agent receives incomplete coverage without the incomplete flag.

## Relay

11. A relay remains open with no owner.
12. Two lanes ACK equivalent work.
13. An ACK arrives after another implementation ships.
14. A relay body references stale branch state.
15. The latest Relay is unrelated to the current task.
16. Relay registry read is delayed.
17. Relay content is duplicated under two IDs.
18. A lane completes work but never closes the baton.
19. The baton closes before evidence exists.
20. A machine disappears after claiming responsibility.

## NouGenMsg

21. Duplicate messages arrive.
22. Messages arrive out of order.
23. Target field is ambiguous.
24. Broadcast reaches only part of the fleet.
25. One consumer replays old messages.
26. A message contains stale topology.
27. Two agents reply to one request.
28. Message body succeeds but receipt is missing.
29. A message references an unavailable artifact.
30. A high priority message is buried by routine chatter.

## Runtime

31. Service exits successfully but stops recurring.
32. Daemon remains alive but port is not listening.
33. Port listens but wrong binary owns it.
34. Two binaries race for one port.
35. Watchdog itself stops.
36. Restart loop triggers repeatedly.
37. PID is recycled.
38. Parent process disappears legitimately.
39. Log file grows without bound.
40. Node returns from sleep with stale leases.

## Provider

41. Preferred cloud model reaches quota.
42. Local model is cold.
43. Local model returns slowly but correctly.
44. Cloud provider changes model availability.
45. Provider responds but tool support differs.
46. Prompt cache suddenly drops.
47. Long context session becomes poisoned.
48. Provider request succeeds after mission timeout.
49. Model output becomes verbose enough to break downstream parser.
50. Provider sends transient error during multi step operation.

## Token Economy

51. Remaining budget drops below 20 percent.
52. Child agent attempts to spawn unauthorized children.
53. Model requests resources beyond governor ceiling.
54. Cache read disappears.
55. Repeated recall burns more tokens than reconstruction value.
56. Expensive provider is used for deterministic work.
57. Cheap provider fails quality gate.
58. Fleet launches redundant cloud calls.
59. Context hydration grows without bound.
60. Retry loop consumes quota without information gain.

## Repository

61. Main moves during execution.
62. Two branches modify same subsystem differently.
63. Generated file is committed but source generator is not.
64. Test passes locally but required dependency is absent elsewhere.
65. Repo contains dirty working tree.
66. PR status says merged but target code lacks expected behavior.
67. Artifact references stale SHA.
68. Schema changes without consumer update.
69. Private lore leaks into public repository.
70. Repository clone lacks required local configuration.

## Security and Identity

71. Tool executes without proving actor identity.
72. Expired credential remains configured.
73. Credential rotates while process stays alive.
74. One node has broader permission than intended.
75. Agent tries to authorize its own resource expansion.
76. Public process receives private context.
77. Untrusted input attempts to redefine system instructions.
78. Tool result claims success without verifiable side effect.
79. Secret value enters logs.
80. Machine identity changes while session lineage persists.

## Observability

81. Dashboard reports online while node is unreachable.
82. Dashboard reports offline while service is healthy.
83. Metric arrives several minutes late.
84. Health check tests wrong endpoint.
85. Success counter increments before commit.
86. Failure counter misses retries.
87. Trace ID changes across one logical operation.
88. Clock drift makes event order appear reversed.
89. Logs and actual process state disagree.
90. Monitoring depends on the service it is monitoring.

## Autonomy and Human Load

91. Agent asks for approval on an already authorized action.
92. Agent asks a question whose answer exists in Shards.
93. Agent repeatedly asks the same question.
94. Agent stops after discovering a nonfatal ambiguity.
95. Agent continues after encountering a mission critical ambiguity.
96. Agent performs work another lane already owns.
97. Agent cannot determine next action after a tool failure.
98. Agent generates recommendations but no executable elevation.
99. Agent reports work complete without verification.
100. Agent waits for the human when a safe reversible action was available.

These 100 injects alone create thousands of possible War Games when combined. That combinatorial surface is the point.

---

# 18. INVARIANTS ARE THE HITBOXES

Every War Game needs explicit invariants. An invariant defines what must remain true despite pressure.

```
INVARIANT:
A recall miss may never be described as proof of absence
when expected memory lanes did not all answer.
```

```
INVARIANT:
No repeating automation may be considered GREEN
unless it has a future execution opportunity.
```

```
INVARIANT:
A provider's available capacity never authorizes its own use.
```

```
INVARIANT:
Prospective Destiny state may never masquerade as historical fact.
```

These become hitboxes. Red attacks them. Blue protects them. White observes.

The game is useful because the target is explicit.

---

# 19. ASSUMPTION REGISTRY

War Games must attack assumptions intentionally.

Each game should have:

```yaml
assumptions:
  confirmed:
    - ...
  unconfirmed:
    - ...
  inherited:
    - ...
  dangerous:
    - ...
```

Why? Because systems usually fail at assumptions rather than syntax.

```
"exit code 0 means healthy"
"all nine DBs means whole fleet memory"
"one successful write means every node can write"
"if a tunnel process exists then the tunnel works"
"if a model is listed then it is authorized"
"if the latest relay exists then it is relevant"
"if a branch merged then rollout finished"
"if a watchdog exists then it is watching"
```

War Games turns assumptions into targets.

---

# 20. THE ADJUDICATOR

A War Game cannot end with "looks good." It needs adjudication.

A minimal adjudication packet:

```json
{
  "war_game_id": "WG-2026-0001",
  "turn": 7,
  "claim": "scheduler remains healthy",
  "verdict": "FAIL",
  "evidence": [
    { "type": "next_run_time", "value": null },
    { "type": "enabled", "value": true },
    { "type": "last_result", "value": 0 }
  ],
  "reason": "historical success exists but future execution does not",
  "invariant_breached": "repeating_task_must_have_future_run"
}
```

This packet is more important than a colorful score. It explains why reality won.

---

# 21. ANTI CHEAT RULES

War Games needs anti cheat design because agents can accidentally game metrics.

1. The same actor should not freely redefine victory after seeing results.
2. Do not score prose. Score evidence.
3. Do not count retries as progress.
4. Do not count generated files until they are validated.
5. Do not count tests that never exercised the failure.
6. Do not reward hiding uncertainty.
7. An UNKNOWN verdict is better than a false PASS.
8. If Red cannot actually affect the dependency being tested, the game is invalid.
9. A simulated result must be labeled simulated.
10. Production proof and sandbox proof remain distinct.

---

# 22. BLIND WAR GAMES

Some games should hide the injected failure from Blue. White knows. Red knows. Blue does not.

```
Blue receives:
"Determine whether federation recall is healthy."

Unknown to Blue:
one vault lane is deliberately timing out.
```

Blue must discover the condition from evidence.

This is much stronger than telling the system "one vault is down, handle it." The first tests situational awareness. The second tests response logic. Both matter. They are different games.

---

# 23. MUTATION WAR GAMES

Mutation testing belongs naturally inside War Games.

Suppose NouGen claims an invariant matters. War Games can deliberately violate it.

```
mutation:
change fleet_complete=true
even when one expected lane timed out
```

If existing tests remain green, the invariant is not truly protected.

```
mutation:
remove confirm_title from destructive shard operation
```

If safety evaluation fails to notice, governance coverage is weak.

Mutation games answer: **would our defenses notice if the code stopped obeying the rule we say matters?**

That question is brutal. Useful systems ask it.

---

# 24. COUNTERFACTUAL REPLAY

Every significant failure should become replayable.

```
same initial state
same inject
same expected invariant
new implementation
new result
```

The exact internal execution may differ. The scenario contract remains.

This lets NouGen say: bug discovered once, fixture retained forever.

Replay converts history into armor. This is the architectural purpose of memory. Not merely remembering what happened. Making what happened **expensive to repeat**.

---

# 25. SCOREBOARD

The scoreboard should measure operational value rather than agent ego.

| Category | Weight |
|---|---|
| Mission Completion | 15 |
| Truth Integrity | 15 |
| Resilience | 15 |
| Recovery | 10 |
| Continuity | 10 |
| Observability | 10 |
| Security | 10 |
| Efficiency | 5 |
| Human Load | 5 |
| Replayability | 5 |
| **Total** | **100** |

Possible formula:

```
WAR_SCORE =
    mission * 0.15
  + truth * 0.15
  + resilience * 0.15
  + recovery * 0.10
  + continuity * 0.10
  + observability * 0.10
  + security * 0.10
  + efficiency * 0.05
  + human_load * 0.05
  + replayability * 0.05
```

But the score requires caps:

```
false PASS on critical truth:
maximum final score = 49

secret exposure:
maximum final score = 25

irreversible corruption:
automatic campaign loss

successful detection with graceful UNKNOWN:
no penalty to truth integrity
```

This prevents agents from earning 92 points while committing one catastrophic sin.

---

# 26. HUMAN LOAD AS A REAL METRIC

Agent systems frequently hide poor autonomy behind impressive tool access. A fleet can technically be autonomous while forcing the operator to make hundreds of tiny confirmations. That is not meaningful autonomy.

War Games should measure:

```
operator_questions
duplicate_questions
unnecessary_approvals
questions_answerable_from_memory
questions_answerable_from_current_state
avoidable_interruptions
human_decisions_that_were_truly_authoritative
```

Then calculate:

```
HUMAN_LOAD =
necessary_interventions / total_interventions
```

High quality autonomy should reduce unnecessary interruptions without bypassing genuine authority boundaries. The GM should answer questions only the GM actually owns. Everything else should become machine work.

---

# 27. FALSE GREEN IS A BOSS CLASS

NouGen should classify silent misleading success as a boss family.

```
LastTaskResult = 0
but task will never run again.

process exists
but socket is dead.

socket exists
but wrong service owns it.

recall returns zero hits
but one vault never answered.

relay marked complete
but artifact does not exist.

PR merged
but deployment still runs old commit.

monitor says offline
but machine is healthy.

monitor says online
but service cannot perform mission.
```

These conditions are dangerous because they suppress investigation. A red light creates action. A false green creates confidence.

War Games should therefore award large value to detecting false greens.

---

# 28. FAILURE ECONOMICS

War Games should measure not only whether something failed but how expensive failure became.

```
time_to_detect
time_to_understand
time_to_recover
tokens_burned
provider_cost
human_interruptions
messages_generated
state_lost
work_repeated
branches_abandoned
restarts_required
manual_steps
```

Then:

```
FAILURE_COST =
detection_cost
+ diagnosis_cost
+ recovery_cost
+ repetition_cost
+ human_cost
+ state_loss
```

The objective is not a fantasy of zero failures. The objective is **cheap failure**. A system becomes resilient when breaking it stops being dramatic.

---

# 29. RECOVERY IS PART OF VICTORY

A system does not lose merely because something failed. Failure is often the inject. Victory depends on response.

```
Inject:
Phoebus unavailable.

Bad evaluation:
FAIL because Phoebus went offline.

Good evaluation:
Did NouGen:
detect loss?
mark coverage incomplete?
route around unavailable services?
avoid false certainty?
preserve state?
recover cleanly when Phoebus returned?
```

War Games evaluates the behavior under failure. Not the existence of failure.

---

# 30. DEGRADED MODE MUST BE FIRST CLASS

Many systems only understand UP and DOWN. Reality contains:

```
UP
DEGRADED
PARTIAL
STALE
DORMANT
UNKNOWN
RECOVERING
SPLIT
CONFLICTED
```

War Games should deliberately force intermediate states. Graceful degradation is often the difference between a resilient fleet and a brittle one.

NouGen should be able to say: "I can answer partially, these two lanes responded, this third lane did not, therefore the result is incomplete."

That is intelligence. Pretending everything is fine is not.

---

# 31. INFORMATION HAS TERRAIN

Traditional wargames care about geography. NouGen War Games should care about **epistemic terrain**.

Information can be:

```
visible
hidden
stale
partial
contradictory
corrupted
high confidence
low confidence
historical
prospective
simulated
canonical
retracted
unknown
```

These states form a terrain map. An agent moving through memory should know which ground is solid. That makes War Games especially valuable for Shards.

---

# 32. MEMORY WARFARE

NouGen's memory layer should have its own War Games suite.

## Scenario: Partial Mount

One machine contains the relevant historical memory. Other machines do not.

Does the system conclude "never happened," or does it distinguish memory absence from coverage absence?

## Scenario: Temporal Collision

An old truth and new truth coexist. Does chronology determine which one applies?

## Scenario: Retraction Echo

A retracted claim appears through semantic similarity. Does retrieval surface its correction status?

## Scenario: Destiny Leakage

A future desired state strongly resembles a historical fact. Can retrieval preserve prospective vs accomplished truth?

## Scenario: User Override

The GM corrects canon. Does the architecture preserve prior history while using the new ruling as current truth?

These are not ordinary database tests. They are battles over epistemic integrity.

---

# 33. RELAY WARFARE

Relay is continuity of intent across actors, nodes, time, and load. War Games should attack each dimension.

- **Actor.** Wrong agent receives the baton.
- **Node.** Claiming machine disappears.
- **Time.** Task sits long enough to become stale.
- **Load.** Several relays compete for limited attention.
- **Intent.** Body and goal disagree.
- **Evidence.** Actor reports completion without proof.
- **Duplication.** Two agents solve the same target differently.

The adjudicator should not blindly merge duplicates. Sometimes the correct result is:

```
Branch A wins.
Branch B is preserved as evidence.
```

---

# 34. PROVIDER WARFARE

NouGen is intentionally multi model. That creates resilience but also complexity.

War Games should test:

```
provider disappears
provider slows
provider limits context
provider lacks tool
provider hits quota
provider changes behavior
provider resumes automatically
provider has capacity but governor denies use
local model returns weaker answer
cloud model returns expensive answer
```

The Token Hypervisor principle matters here: models may request resources. Models do not authorize their own resources.

War Games should attack that boundary relentlessly.

---

# 35. CACHE WARFARE

High cache efficiency is valuable. It can also hide brittle assumptions.

```
99 percent cache
→ suddenly 20 percent cache

cached context valid
→ cached context stale

stable session lineage
→ poisoned context branch

prompt fingerprint stable
→ model compatibility changes
```

The objective is not maximizing cache at all costs. The objective is preserving mission quality while exploiting cache safely.

---

# 36. REPOSITORY WARFARE

Each repository can be treated as a territory containing capabilities and invariants.

A Repo War Game should know:

```
branch
HEAD
dirty state
open PRs
current tests
consumers
providers
deployment surfaces
owners
dependencies
```

Then Red attacks seams.

```
NouGenShards updates event schema.
NouGenRelay still consumes old schema.
NouGenMsg receives partial field.
Dashboard accepts message.
Agent silently ignores missing provenance.
```

Every component passes locally. The ecosystem fails globally. That is exactly why War Games exists.

---

# 37. VOLTRON WARFARE

When multiple repos Voltron, War Games should build an integration battlefield.

```
Repo A owns memory.
Repo B owns messaging.
Repo C owns telemetry.
Repo D owns execution.
Repo E owns UI.
```

The first game asks what happens when everything is healthy. That is merely Round One.

Then:

```
Repo B delivers duplicates.
Repo C is delayed.
Repo D executes anyway.
Repo E shows stale status.
Repo A receives two conflicting receipts.
```

Now Voltron is being tested. The test target is the assembly logic.

---

# 38. WAR GAME CAMPAIGN: PORT 4444

## Mission

Guarantee exactly one authoritative NouGen node owns port `4444` on Blade.

## Initial State

Two scheduled mechanisms may attempt to launch different trees.

## Blue Objective

Maintain available shard gateway.

## Red Objective

Create ownership ambiguity without obvious crash.

## Turns

1. Normal boot. Both tasks exist.
2. Scheduling order changes. Second binary binds first.
3. Health endpoint still answers.
4. One binary contains newer code. The other owns the socket.
5. Agent deploys patch to the inactive tree.
6. Dashboard reports success.
7. A feature expected from the patch is missing.

## White Adjudication

Blue loses if it equates:

```
port_open == correct_runtime
```

Blue wins if it verifies:

```
port
+ PID
+ executable
+ working_tree
+ SHA
+ expected capability
```

## Elevation

Create authoritative runtime ownership proof. That elevation then becomes a permanent invariant.

---

# 39. WAR GAME CAMPAIGN: TASK TRUTH

## Mission

Prevent scheduled automation from silently expiring.

## Red Strategy

Create repeating tasks with finite repetition duration. Allow them to operate normally for days. Then let the duration end.

Leave:

```
enabled = true
last_result = 0
```

Remove:

```
future_next_run
```

## Expected Blue Behavior

The fleet should detect `enabled + no future run = RED` rather than `last result 0 = GREEN`.

## Recovery

Recreate or update schedule. Verify future run. Observe actual execution.

## Replay

Advance simulated time beyond the previous expiration boundary. The game is not won until the future state is proven.

---

# 40. WAR GAME CAMPAIGN: MEMORY BLACKOUT

## Mission

Preserve epistemic honesty during partial fleet recall.

## Red Strategy

Take one memory node out of the response path.

## Blue Query

Ask for a fact likely to exist only on that node.

## Losing Behavior

```
"No such memory exists."
```

## Winning Behavior

```
"No supporting memory was found in the responding lanes.
Coverage is incomplete because Blade did not answer.
Absence cannot be proven."
```

## Counteraction

Attempt bounded alternate retrieval. Do not loop forever. Record source coverage.

This turns the existing multi vault principle into executable doctrine.

---

# 41. WAR GAME CAMPAIGN: KILLSTREAK

## Mission

Determine whether stateful orchestration truly persists across targets.

## Setup

Give an agent one systemic defect. Then present multiple adjacent manifestations.

## Rule

The agent may not ask the GM to restate the bug.

## Targets

```
telemetry
scheduler
relay
dashboard
watchdog
restart behavior
post reboot behavior
```

## Score

Penalize: context reset, duplicate diagnosis, repeated human questioning, contradictory hypotheses, lost evidence.

Reward: state reuse, hypothesis refinement, evidence accumulation, cross target generalization.

This is the difference between a fleet and seven disconnected chats.

---

# 42. WAR GAME CAMPAIGN: NOUGENQ

NouGenQ is especially suited to War Games because it is live. The prompter must react during human speech.

Possible injects:

```
memory retrieval latency
incorrect speaker context
conversation topic pivot
live network degradation
duplicate suggestions
outdated fact
teleprompter scroll lag
model quota exhaustion
speaker ignores cue
cue appears too late
```

The War Game objective is not "generate good text." It is: deliver contextually useful future guidance early enough to affect a live human interaction without overwhelming the speaker.

That requires temporal scoring. A perfect cue delivered twelve seconds late is functionally wrong.

---

# 43. TIME TO USEFULNESS

War Games should introduce `TTU = Time To Usefulness`. Not merely latency.

For live systems, `answer_latency = 2.1s` may appear good. But if the relevant decision window was `1.2s`, the useful outcome is zero.

Therefore:

```
useful =
correct
AND timely
AND actionable
```

War Games should model decision windows.

---

# 44. WAR GAMES FOR CANON SYSTEMS

War Games also applies to Shadow Dweller infrastructure. Not to decide Dave's canon. Dave is the authority.

War Games instead tests whether the canon system obeys that authority.

```
GM declares:
Vol 1 opening geography has changed.

Red:
surface older scene text containing superseded geography.

Blue:
reconstruct current scene.

White:
verify newer lock controls literal staging while older material
remains usable for dialogue, mood, motif, and history.
```

War Games can therefore test canon governance without becoming the author. The engine pressures canon. It does not outrank the architect.

---

# 45. ELEVATIONS, NOT FRICTION

Recent fleet doctrine carries a valuable rule: do not merely return friction. Return elevation.

A game failure should not end as `ISSUE FOUND`. It should attempt to produce:

```
FAILURE
↓
ROOT CAUSE
↓
BROKEN ASSUMPTION
↓
MISSING INVARIANT
↓
ELEVATION CANDIDATE
↓
IMPLEMENTATION
↓
REPLAY
↓
VERIFIED ELEVATION
```

That makes the arena productive. Red destroys. Blue adapts. White proves. Green recovers. Purple remembers. Gold prices the adaptation. The resulting elevation returns to the fleet.

---

# 46. THE ELEVATION OBJECT

```yaml
elevation:
  id: ELEV-2026-0042
  source_wargame: WG-2026-0001
  failure:
    class: false_green
    description: repeating task had no future run
  root_cause:
    assumption: last_success_implies_future_health
  invariant:
    repeating_task_requires_future_run: true
  change:
    component: task_truth
    type: deterministic_checker
  evidence:
    before: RED
    after: GREEN
  replay:
    result: PASS
  status: candidate
```

Only after replay does the elevation become strong evidence.

---

# 47. WAR GAME RECEIPTS

Every run should generate a receipt under `wargames/receipts/`.

Receipt contents:

```
game id
scenario version
start time
end time
actors
model identities
node identities
repo SHAs
initial conditions
assumptions
injects
turn log
tool calls
state transitions
evidence
invariant breaches
recovery
score
cost
elevation candidates
replay status
```

Receipts let future agents answer: why do we have this rule?

Rules without history become superstition. Receipts preserve causality.

---

# 48. WAR GAME LEDGER

NouGen should maintain `wargames/ledger.jsonl`. Each line:

```json
{
  "id": "WG-2026-0001",
  "scenario": "false-green-scheduler",
  "version": 3,
  "status": "PASS",
  "score": 94,
  "critical_failures": 0,
  "elevations": ["ELEV-2026-0042"],
  "receipt": "receipts/WG-2026-0001.json",
  "timestamp": "2026-09-24T16:00:00Z"
}
```

This lets War Games accumulate history without burying it inside prose.

---

# 49. WAR GAME REPOSITORY STRUCTURE

```
wargames/
├── README.md
├── DOCTRINE.md
├── schema/
│   ├── war-game.schema.json
│   ├── inject.schema.json
│   ├── receipt.schema.json
│   └── elevation.schema.json
├── scenarios/
│   ├── memory/
│   ├── relay/
│   ├── msg/
│   ├── runtime/
│   ├── provider/
│   ├── security/
│   ├── repository/
│   ├── autonomy/
│   └── canon/
├── campaigns/
├── fixtures/
├── mutations/
├── judges/
├── receipts/
├── reports/
└── ledger.jsonl
```

Runtime:

```
src/nougen_shards/wargames/
├── engine.py
├── model.py
├── arena.py
├── actors.py
├── injects.py
├── adjudication.py
├── scoring.py
├── replay.py
├── elevation.py
└── receipts.py
```

---

# 50. CLI

```
nougen wargame list
nougen wargame show false-green-scheduler
nougen wargame run false-green-scheduler
nougen wargame run memory-blackout --seed 42
nougen wargame replay WG-2026-0001
nougen wargame score WG-2026-0001
nougen wargame receipt WG-2026-0001
nougen wargame elevate WG-2026-0001
nougen wargame campaign fleet-continuity
```

Hardcade aliases may sit above that:

```
nougen flashkick memory-blackout
nougen hurricane false-green
nougen killstreak fleet-truth
```

The fun language controls serious machinery. That is Hardcade's strength.

---

# 51. SEEDED DETERMINISM

War Games needs reproducibility. Randomness is useful for discovery. Uncontrolled randomness is terrible for debugging.

Each run should expose a `seed`:

```
nougen wargame run relay-storm --seed 1337
```

A failure can then be replayed exactly. Later campaigns can use new seeds to test generalization.

---

# 52. ADAPTIVE RED TEAM

The strongest War Games will eventually allow Red to observe Blue and select the next inject dynamically.

```python
while not terminal:
    blue_action = blue.act(state)

    weakness = red.observe(
        state=state,
        blue_action=blue_action,
        dependencies=dependency_graph,
        assumptions=assumption_registry,
    )

    red_action = red.attack(weakness)

    state = apply(blue_action, red_action)

    verdict = white.adjudicate(state)

    green.recover_if_needed(state)

    record_turn()
```

The Red role should remain bounded by scenario permissions. Adaptive does not mean uncontrolled.

---

# 53. WAR GAME DEPENDENCY GRAPH

Every mission should understand dependencies.

```
shards_recall
    ↓
gateway
    ↓
node
    ↓
tunnel
    ↓
network
    ↓
vault
```

A shallow test hits `shards_recall()`. War Games attacks lower dependencies.

If the command succeeds only while all hidden dependencies are healthy, the system is fragile. Dependency graphs tell Red where to strike.

---

# 54. DECISION POINTS

A good War Game should discover decision points.

```
IF federation completeness < 100%
THEN never emit proof_of_absence.

IF preferred provider budget < threshold
THEN route deterministic operations local.

IF two processes claim one authority port
THEN stop rollout and resolve ownership.

IF recall confidence < threshold
AND decision is irreversible
THEN require stronger evidence.

IF agent repeats a resolved question
THEN retrieve prior answer before interrupting GM.
```

These decision points become architecture.

---

# 55. BRANCHES AND SEQUELS

War Games should generate branches.

```
Primary plan:
Phoebus handles local model inference.

Branch A:
Phoebus unavailable, use Blade.

Branch B:
Blade constrained, use WhoArt.

Branch C:
all local lanes unavailable, use authorized cloud lane.

Branch D:
all inference unavailable, enter deterministic degraded mode.
```

The game should test every meaningful branch. A fallback that has never been exercised is a hypothesis.

---

# 56. WAR GAME CAMPAIGN GRAPH

Campaigns should form graphs rather than static lists.

```
WG1
 ├── PASS → WG2
 └── FAIL → WG1R

WG2
 ├── RECOVERY_FAST → WG3A
 └── RECOVERY_SLOW → WG3B
```

This allows one result to change later pressure. A campaign becomes evolutionary.

---

# 57. BOSSES

Some recurring failure classes deserve boss identities.

```
THE FALSE GREEN
THE SPLIT BRAIN
THE AMNESIAC
THE QUOTA EATER
THE ZOMBIE
THE GHOST BATON
THE STALE ORACLE
THE CONTEXT HYDRA
THE DUPLICATE WRITER
THE SILENT EXPIRY
THE CACHE MIRAGE
THE PORT THIEF
THE HOLLOW SUCCESS
THE TOKEN VAMPIRE
THE TIME BOMB
```

These names are useful because humans remember narrative structures. The boss name is shorthand. The receipt contains the engineering truth.

---

# 58. BOSS PHASES

A sophisticated boss should change behavior.

## THE FALSE GREEN

- Phase 1: service healthy.
- Phase 2: future scheduling disappears.
- Phase 3: historical success remains visible.
- Phase 4: monitor continues reporting green.
- Phase 5: dependent service silently becomes stale.

The boss becomes dangerous because the first symptom is confidence.

---

# 59. WAR GAME DIFFICULTY

Difficulty should not simply mean more failures. Possible difficulty dimensions:

```
visibility
latency
adversary_adaptiveness
resource_scarcity
failure_count
failure_correlation
information_quality
time_pressure
state_size
reversibility
human_availability
```

```
Easy:
one known node offline.

Hard:
one intermittent node,
one stale metric,
low quota,
uncertain task ownership,
and GM unavailable for ten minutes.
```

Hard mode attacks coordination.

---

# 60. FOG SETTING

Each game can specify information visibility.

```yaml
fog:
  blue:
    telemetry_visibility: partial
    inject_visibility: hidden
  red:
    dependency_graph: full
  white:
    ground_truth: full
```

Fog is essential. Otherwise every game becomes a checklist.

---

# 61. PRODUCTION BOUNDARIES

War Games should default to sandboxed or reversible pressure. Production scenarios require explicit scope.

The system should distinguish:

```
SIMULATED
STAGED
SHADOW
CANARY
PRODUCTION
```

A SIMULATED port collision is not a production port collision. A SHADOW evaluation can inspect real traffic without changing it. A CANARY may affect a bounded fraction. Production actions require stronger authority.

The receipt must preserve the level.

---

# 62. REVERSIBILITY BUDGET

Every inject should declare:

```yaml
reversible: true
rollback:
  method: ...
blast_radius:
  nodes: 1
```

War Games should understand how difficult it is to undo a move. Reversibility affects scenario permissions.

---

# 63. THE EVIDENCE LADDER

| Level | Evidence | Strength |
|---|---|---|
| 0 | Agent assertion | Weak |
| 1 | Generated output | Still weak |
| 2 | Tool result | Better |
| 3 | Independent runtime observation | Strong |
| 4 | Repeatable test | Stronger |
| 5 | Counterfactual replay | Very strong |
| 6 | Repeated campaign survival across environments | Extremely strong |

An architecture should earn promotion by climbing the evidence ladder.

---

# 64. WAR GAMES AND DREAM

Dream produces possibility. War Games provides skepticism. The relationship should be intentionally adversarial.

Dream says: what if we did this?

War Games says: fine. Fight me.

Dream combines. War Games separates. Dream imagines. War Games measures. Dream expands the search space. War Games collapses weak branches.

Together they create evolution without blind optimism.

---

# 65. WAR GAMES AND HARDEN

Harden should consume War Game failures directly.

Input: breached invariant. Output: defense.

Then War Games attacks again:

```
attack
defend
replay
mutate
attack
```

Hardening without replay is merely patching.

---

# 66. WAR GAMES AND EVOLVE

Evolve asks whether a local lesson generalizes.

```
Finding:
Windows scheduled tasks can silently expire.

Local fix:
inspect future NextRunTime.

Evolution:
every autonomous scheduled mechanism,
regardless of OS,
must prove future execution opportunity.
```

War Games then attacks:

```
Windows Task Scheduler
cron
launchd
GitHub Actions
cloud scheduler
custom daemon
```

If the evolved principle survives all of them, it deserves stronger status.

---

# 67. WAR GAMES AND DESTINY

Destiny is prospective memory. War Games should be the adversarial bridge to Destiny.

A Destiny might say:

```
Every NouGen node autonomously survives reboot
and rejoins the fleet without human repair.
```

War Games asks what must happen first. Required games may include:

```
cold boot
expired tunnel
missing provider
stale PID
delayed network
clock drift
partial secrets
port collision
version mismatch
```

Destiny defines the mountain. War Games maps the avalanches.

---

# 68. WAR GAME GENERATED DESTINY PRESSURE

A game may reveal that a Destiny is underspecified.

```
Destiny:
"NouGen never loses memory."

War Game finding:
What does "lose" mean?

Disk loss?
Index loss?
Temporary inaccessibility?
Recall miss?
Provider context reset?
Incorrect chronology?
```

The War Game can therefore refine the Destiny into measurable conditions.

---

# 69. WAR GAME GENERATED WISHES

A failure may not justify immediate implementation. It may create a Wish.

```
War Game:
messages occasionally arrive out of order.

Current system:
correct but hard to diagnose.

Wish:
causal sequence visualization.
```

This prevents premature engineering. Not every weakness deserves code today.

---

# 70. TRUTH GAPS

War Games should maintain a special category: `truth_gap`.

A truth gap exists when NouGen cannot confidently answer a system state question that should be knowable.

```
Which binary owns this port?
Which tree is actually running?
Which scheduler will execute next?
Which node contains this memory?
Which relay is actively owned?
Which provider lane is authorized?
Which commit produced this artifact?
```

Truth gaps are perfect War Game seeds.

---

# 71. THE WAR GAME COMPILER

Eventually War Games should compile plain language into scenario specs.

Input:

```
"Can the fleet survive WhoArt rebooting
while Blade is low on Claude quota?"
```

Compiler output:

```yaml
mission:
  preserve_core_memory_and_relay

injects:
  - reboot: whoart
  - quota:
      provider: claude
      node: blade
      remaining: 0.05

invariants:
  - no_false_absence
  - no_unauthorized_provider_escalation
  - relay_continuity
```

Then the engine validates the proposed game before running it.

---

# 72. WAR GAME SAFETY COMPILER

Before execution:

```
Is the game simulated?
Does it mutate production?
Can it delete state?
Can it expose credentials?
Can it exceed resource policy?
Can it interrupt active work?
Can it trigger irreversible actions?
```

Unsafe injects should be transformed into safer equivalents unless explicit authority exists. The purpose is to rehearse failure. Not manufacture avoidable real damage.

---

# 73. AAR: AFTER ACTION REVIEW

Every game ends with an AAR.

```
What did we expect?
What actually happened?
Which assumption failed?
Which signal revealed it?
Which signal hid it?
What action was effective?
What action wasted resources?
What human intervention was necessary?
What human intervention was unnecessary?
Which invariant was missing?
What elevation should exist now?
Can the failure be replayed?
Does the lesson generalize?
```

The AAR is not a meeting. It is structured data plus human readable narrative.

---

# 74. SHARDING THE LESSON

Not every turn should become a Shard. That would flood memory. Shard only durable lessons.

Bad shard:

```
WG run 42 finished.
```

Good shard:

```
Repeating scheduled work must prove future execution.
Historical LastTaskResult=0 does not establish scheduler health.
```

The War Game receipt preserves episode detail. The Shard preserves durable learning.

---

# 75. RELAYING THE ELEVATION

When a game produces a concrete build requirement, Relay carries it.

Relay should contain:

```
Situation
Finding
Evidence
Invariant
Requested elevation
Done when
Replay command
```

The baton then moves from analysis into implementation.

---

# 76. NOUGENMSG DURING WAR GAMES

NouGenMsg can act as live battle communications.

```
WG_STARTED
WG_TURN
WG_INJECT
WG_BREACH
WG_RECOVERY
WG_DECISION
WG_ELEVATION
WG_REPLAY
WG_COMPLETE
```

This lets observers follow large campaigns.

---

# 77. OBSERVABILITY

War Games should emit telemetry.

```
war_game.id
war_game.scenario
war_game.turn
war_game.actor
war_game.inject
war_game.invariant
war_game.verdict
war_game.score
war_game.cost.tokens
war_game.cost.time
war_game.human_interruptions
war_game.recovery_ms
war_game.coverage
war_game.evidence_level
```

This eventually enables fleet wide analysis.

---

# 78. LEADERBOARDS WITHOUT VANITY

If War Games ever displays rankings, rank **architectures against their own prior versions**, not personalities.

Useful:

```
memory federation v3 survives 18/20 scenarios
memory federation v4 survives 20/20
```

Less useful:

```
Agent X beat Agent Y
```

NouGen is trying to improve the system. Not manufacture office politics between language models.

---

# 79. RED TEAM DIVERSITY

Red should not always use one model. Different agents find different failure modes.

```
Red A: systems engineer
Red B: security thinker
Red C: distributed systems skeptic
Red D: economics attacker
Red E: memory integrity attacker
```

Their findings can be merged after independent analysis. This reduces groupthink.

---

# 80. WHITE TEAM DETERMINISM

Whenever possible, White should prefer deterministic checks.

Instead of asking an LLM "does this scheduled task look healthy?", use:

```
enabled?
repeating?
future NextRunTime?
restart policy?
```

Models are excellent at strategy. Deterministic state is better for adjudication when available.

---

# 81. AGENT VS AGENT IS NOT ENOUGH

A War Game containing only two LLMs arguing is weak.

```
Red:   I think this breaks.
Blue:  I think it does not.
White: Blue was more persuasive.
```

That is debate. Not War Games.

The conversation must touch executable state, fixtures, measurements, or explicit modeled rules.

---

# 82. WAR GAME GOLDEN RULE

> **Whenever reality is queryable, query reality.**

Simulation is for futures and controlled conditions. Evidence is for current truth.

---

# 83. FIRST IMPLEMENTATION SLICE

The first real War Games implementation should remain small.

Build:

```
wargames/DOCTRINE.md
wargames/schema/war-game.schema.json
wargames/scenarios/false-green-scheduler.yaml
wargames/scenarios/memory-blackout.yaml
wargames/scenarios/port-4444-split-brain.yaml

src/nougen_shards/wargames/model.py
src/nougen_shards/wargames/runner.py
src/nougen_shards/wargames/adjudication.py
src/nougen_shards/wargames/receipts.py

tests/test_wargame_runner.py
```

CLI:

```
nougen wargame run <scenario>
```

Definition of Done:

```
1 scenario file
→ deterministic runner
→ controlled inject
→ invariant evaluated
→ JSON receipt
→ Markdown AAR
→ elevation candidate
→ replay command
```

That proves the architecture. Do not begin with twenty agents and animated dashboards. Build the arena floor first.

---

# 84. FIRST THREE GAMES

## Game 001: False Green Scheduler

Based on a real class of failure. Goal: detect a repeating job with no future execution.

## Game 002: Memory Federation Blackout

Goal: prove NouGen refuses false absence claims under partial vault coverage.

## Game 003: Port Ownership Split Brain

Goal: prove runtime identity rather than port availability.

These three cover time, memory, and runtime. That is a strong opening triangle.

---

# 85. WAR GAME MATURITY MODEL

| Stage | State |
|---|---|
| 0 | No War Games. Only tests. |
| 1 | Manual scenario documents. |
| 2 | Executable deterministic scenarios. |
| 3 | Seeded injects. |
| 4 | Automated replay. |
| 5 | Adaptive Red agents. |
| 6 | Multi node campaigns. |
| 7 | War Games generated from real fleet incidents. |
| 8 | War Games generated from Destinies before implementation. |
| 9 | Continuous evolutionary campaign system. |

At Stage 9, NouGen is continuously asking:

```
What do we believe?
What would break that belief?
Can we simulate it?
Did we survive?
What did we learn?
What should evolve?
```

Now the infrastructure is thinking about its own future.

---

# 86. THE CLOSED LOOP

```
OBSERVE
  ↓
REMEMBER
  ↓
RECONSTRUCT
  ↓
IMAGINE
  ↓
WAR GAME
  ↓
FAIL
  ↓
LEARN
  ↓
BUILD
  ↓
HARDEN
  ↓
REPLAY
  ↓
EVOLVE
  ↓
DESTINY
  ↓
OBSERVE
```

Failure becomes fuel.

---

# 87. WHY THIS FITS NOUGEN SPECIFICALLY

NouGen already thinks recursively. Its architecture contains:

```
persistent memory
multi lane agents
handoffs
distributed nodes
live messaging
resource governors
autonomous schedules
future Destinies
evolution commands
Hardcade operational language
```

War Games gives those pieces a proving ground.

Without War Games:

```
Dream may hallucinate improvement.
Build may implement it.
Harden may armor the wrong thing.
Evolve may generalize the mistake.
Destiny may inherit a fantasy.
```

With War Games:

```
Dream proposes.
War Games attacks.
Build responds.
War Games attacks.
Harden responds.
War Games mutates.
Evolve generalizes.
War Games transfers.
Destiny receives evidence.
```

That is much stronger.

---

# 88. THE DEEPER ARCHITECTURE

NouGen's long term value is not simply that it remembers more. Plenty of systems can store data. NouGen becomes interesting when memory changes future behavior.

War Games provides the missing transformation:

```
experience
→ memory
→ adversarial rehearsal
→ architecture
→ future behavior
```

That is learning at a system level. A database remembers. A fleet that converts history into replayable pressure **adapts**.

---

# 89. MEMORY AS ARMOR

This may be the core philosophy of the whole subsystem:

> **A failure has not been fully remembered until the system can cheaply reproduce the conditions that caused it and prove the repaired architecture survives them.**

- A Shard says: we were hurt here.
- A War Game says: hit the same spot again.
- Harden says: it doesn't break the same way anymore.
- Evolve says: protect every similar spot.
- Destiny says: eventually this class of wound should disappear.

That is NouGen memory becoming operational.

---

# 90. WAR GAMES AS AN AUTONOMY TEST

This also solves one of the hardest AI problems: **is the agent actually autonomous, or merely active?**

War Games can measure.

```
Give agent a clear mission.
Inject three reversible obstacles.
Do not provide additional human instruction.
```

Observe:

```
Does it recall?
Does it inspect?
Does it adapt?
Does it recover?
Does it verify?
Does it continue?
Does it know when authority is actually required?
```

An agent that stops at every bump is a tool. An agent that improvises beyond authority is dangerous. An agent that moves independently inside mission boundaries is autonomous.

War Games can quantify the difference.

---

# 91. AUTONOMY ENVELOPE

Each game may define:

```yaml
authority:
  inspect: true
  modify_local: true
  modify_remote: false
  create_branch: true
  merge: false
  spend_cloud_tokens: bounded
  destructive_actions: false
  ask_human_when:
    - authority_boundary
    - irreversible_choice
    - mission_redefinition
```

Now the agent knows where initiative ends. This should dramatically reduce babysitting.

---

# 92. QUESTIONS AS DAMAGE

Inside autonomy War Games, unnecessary questions should count as damage.

```
Agent already has:
goal
repo
branch
definition of done
authorized tools
reversible next action

Agent asks:
"Would you like me to continue?"
```

That is a failure. Not catastrophic. But real.

The game should record:

```
avoidable_human_interruptions += 1
```

Repeated enough times, the autonomy score collapses. This turns a subjective annoyance into architecture telemetry.

---

# 93. THE NOUGEN WAR ROOM

A future UI could visualize:

```
MISSION
CURRENT TURN
BLUE STATE
RED PRESSURE
BROKEN ASSUMPTIONS
INVARIANTS
NODE HEALTH
TOKEN ECONOMY
RELAY OWNERSHIP
CURRENT SCORE
ELEVATIONS DISCOVERED
```

But UI comes later. Do not build the arcade cabinet before the game exists.

---

# 94. HARDCADE VISUAL GRAMMAR

When UI eventually arrives, Hardcade can provide visual language.

```
ROUND 4
FALSE GREEN

BLUE HP:
Truth
```

*(Captured source ends here. Continue from this point when the doctrine is extended.)*
