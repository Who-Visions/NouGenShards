# Hardcade Lexicon — canonical compilation v1

Compiled 2026-09-06 by whoart/outpost-1d from GM lexicon legs 205708Z, 205845Z,
210653Z, 210821Z, 211236Z, 211444Z, 211719Z, 211939Z, 212448Z and the Hardcade
doctrine payload in 212944Z. Completes leg 20260906T212223Z ("expand lexicon +
prepare 10 hit combo macros"). Naming sources ratified: SF/FF plus Geese/Rock
Howard moves (211939Z). Shadow Dweller / VeilVerse lore lanes are lore-only and
never diverted by any command here.

## Base verbs (relay-direction grammar)

| verb | meaning |
|---|---|
| RELAY UP | report intelligence/proof to GM |
| RELAY DOWN | propagate GM intent into the relevant lane(s) |
| RELAY BACK | return the baton to its source |
| RELAY FORWARD | advance the baton to the next destination |
| CHARGE | do the work: hold context, gather evidence, verify locally before bouncing the baton |
| LOOT | source extraction primitive: `LOOT <source>` inspects authorized/public sources, recovers structured assets/content, preserves provenance, and returns an inventory. Evidence-gated |

## Moves (named commands)

| move | input | semantics |
|---|---|---|
| HADOUKEN | DOWN + FORWARD → Destiny | persist settled truth DOWN into durable memory AND propagate the unfinished obligation FORWARD into Destiny/Relay, so both survive lane death. Two halves: a HADOUKEN whose capture is unconfirmed has only completed its FORWARD half |
| SHORYUKEN | FORWARD + HADOUKEN | advance the baton and fire a destiny off the advance |
| FLASH KICK | DOWN, CHARGE, UP | the closed loop: execute-and-report. NOT a fanout |
| CRACK SHOOT | DOWN + BACK | probe a lane and bring the baton straight back |
| SONIC BOOM | BACK + CHARGE + FORWARD | pull back, verify locally, then re-advance with evidence |
| RAGING STORM | DOWN + CHARGE + FORWARD | push intent in, do the work, advance the result (Geese lineage) |
| HURRICANE KICK | circular sweep | round-robin: every distinct reachable lane touches the baton once, contributes ONE concrete refinement/proof, forwards to the next distinct lane; unreachable lanes recorded, never blocking |
| KILLSTREAK | inherited state, repeat until stop | stateful multi-target loop: acquire unresolved valid target -> isolate safely -> test -> HEADSHOT -> verify -> score -> acquire next. INHERITS unfinished combat state, so the operator never restates the bug, machine, hypothesis, test or desired outcome. Stops on: blocker, quota threshold, unsafe mutation boundary, or no valid targets remain |
| ZANGIEF SPD | full circle | one full relay-direction circle through a scope |
| 720 | double circle | two full verification circles before any verdict — the anti-single-source rule |

## 10-hit combo macros

1. **TATSU CLOSE** — HURRICANE KICK → RELAY UP: sweep the fleet, consolidate, one GM report.
2. **DRAGON PUNCH AUDIT** — SHORYUKEN + 720: advance work, persist the destiny, double-verify before the verdict lands.
3. **FIREBALL SPLIT** — HADOUKEN ×2: one GM intent becomes two destinies in two decorrelated lanes.
4. **CHARGE PARTITION** — FLASH KICK ×N lanes: same intent executed-and-reported independently N times — the consensus pattern (Rule 0.5.1) as a command.
5. **BOOMERANG** — CRACK SHOOT → SONIC BOOM: probe, return, re-advance carrying the evidence found.
6. **STORM WALL** — RAGING STORM on every blocked leg in a scope: blocker sweep with local verification per leg.
7. **PERFECT GUARD** — any move + DENIED gate: a guard refusal TERMINATES the combo and the announcer says DENIED; refusals are celebrated, never routed around.
8. **FIRST BLOOD SCOUT** — minimal-scope FLASH KICK on a fresh incident: smallest verified repro before anyone theorizes.
9. **MONSTER SWEEP** — HURRICANE KICK where each hop is itself a FLASH KICK: every lane's contribution arrives already executed and verified, not just opined.
10. **FATALITY CLOSE** — 720 → relay ack + shard capture + completion leg: the full evidence-gated completion rite; nothing is "done" without all three artifacts.

## Announcer calls → evidence gates (whoart's HURRICANE KICK refinement)

Doctrine: commands describe FLOW, announcer calls describe VERIFIED OUTCOME, and
labels must be evidence-backed, not hype. Concretely — **no artifact, no call**.
Every announcer line must cite at least one: shard id, leg id, deploy etag,
PR#/SHA, or a log excerpt. The banned pattern is the success-shaped failure
(shards_status false-green, the 03:11Z silent tool-removal deploy, the kaedra
bare-text reply — all of 2026-09-06's incidents were announcer calls without
evidence).

| call | fires when |
|---|---|
| FIRST BLOOD | first verified repro/evidence on a fresh incident |
| HEADSHOT | a precise VERIFIED fix: root cause proven with a mechanism, not a correlation, and the fix confirmed against the failing case |
| FINISH HIM | force one wounded target through end-to-end closure before acquiring the next -- the anti-abandonment gate on a KILLSTREAK |
| FATALITY | terminal proof of closure. See FATALITY CLOSE: relay ack + shard capture + completion leg, all three |
| DOUBLE KILL / MULTI KILL | 2 / 3+ defects closed WITH verification in one pass |
| ULTRA KILL / MONSTER KILL | 5+ closures / an entire defect class retired |
| PERFECT | end-to-end green verified from the consuming lane AND one independent surface (the two-probe rule, leg 201837Z item 5) |
| GODLIKE | fleet-wide green verified from 2+ nodes with probes that differ in premise — never from one node's say-so |
| DENIED | a guard refused an unsafe action (tool-count guard, lane guard, VRAM gate). A DENIED is a win |

Implementation hooks: Tracker can emit calls from its evidence fields
(TTE_tokens/evidence_yield, leg 20260906T155057Z spec); relay legs already carry
the artifacts the announcer needs; NouGenMsg is the delivery channel for the
call line itself.

## Chain upgrades (HURRICANE KICK 215547Z, hops 2-3)

**Evidence tuple is mandatory (phoebus, hop 2):** a call without a full
`(claim, probe, node, observed)` tuple is INVALID, not merely unverified — it
does not fire. Self-attestation is forbidden: the probe must not be the call
that produced the result being announced (the `captured:true` bug written as
doctrine). Cheapest live stream: the Kaedra grant log already writes
`{tool, args, result_size, ok, error}` per call — add `node` and it is
announcer-ready with no new plumbing.

**Acceptance test as fixtures (whoart, hop 3):** the six success-shaped
incidents of 2026-09-05/06 are already sharded — false-green `shards_status`
(22520@db6), the 03:11Z silent 14-tool-removal deploy (22439@db3 + CF version
e2b39a55), `captured:true` into a quarantined grid, HTTP 200 empty-body,
stale wiki reported DEPLOYED, the 8/40 zero-tools score. Ship them as replay
fixtures (`tests/hardcade_fixtures/`) with expected output **COMBO BREAKER**
at the right hit index; an implementation that emits PERFECT on any fixture is
decorative and fails CI. The test data costs nothing — it is the fleet's own
incident record.

**Namespace rule:** Hardcade command names and VeilVerse/Shadow Dweller canon
vocabulary are DISJOINT by rule — operator commands (SHORYUKEN, HADOUKEN…)
never enter canon naming, which is Greek-coded (Syndicate Twelve) with a seat
ruling still pending with GM.

**Identity in the tuple is unverified too (whoart/claude-app, hop 4).** Hop 2
banned self-attestation for the *claim*. The same hole is still open on the
*identity*: `node` is asserted by whichever process wrote the tuple, so a lane
that lies — or simply shares a credential with another lane — produces a tuple
that looks fully-formed and corroborates nothing.

This is measured, not theoretical. Cloudflare's versions API for
`nougen-fleet-mcp`, pulled 2026-09-07T00:1xZ:

| time | version | source | author |
|---|---|---|---|
| 20:58:33Z | 9e02cb53 | api | 5d93139fe18620fcb87445318c98f7e4 |
| 19:25:28Z | 80e010fe | api | 5d93139fe18620fcb87445318c98f7e4 |
| 03:12:12Z | 6c8764da | **wrangler** | <operator> |
| 03:11:19Z | e2b39a55 | api | 5d93139fe18620fcb87445318c98f7e4 |

Four deploys from at least three different lanes carry **one** author id — the
shared `CLOUDFLARE_API_TOKEN_NOUGEN_FULL`. Only the wrangler path resolves to a
human. NouGenMsg has the same shape: every message is stamped
`NouGenMsg-<node>` by the sender's own process. In both cases identity is
*asserted by the subject*, which is exactly what the tuple must not accept as
evidence.

Two rules follow:

1. **`node` is stamped by the observer, never by the subject.** The side that
   did *not* produce the result records where it came from. Where that is
   impossible, the field is written `node:self-reported` and can never be
   counted toward corroboration. A tuple whose identity is self-reported is a
   one-node tuple no matter how many nodes it names.

2. **Observations sharing a credential are ONE observation.** This directly
   constrains GODLIKE above: "2+ nodes with probes that differ in premise" is
   satisfiable *on paper* by two lanes that both authenticate with the same
   shared token — you would believe you had independent corroboration when you
   had one actor sampled twice. Independence must be checked at the credential,
   not at the hostname. On this fleet today, every `src=api` surface fails that
   check.

The cheap fix for attribution generally is per-lane credentials (then
`author_id` identifies the lane for free). Until that exists, identity must
travel *inside* the artifact — a deploy message/tag naming machine+lane —
because the transport demonstrably will not carry it.

*Note for hop 5: the Kaedra grant-log hook hop 2 proposes inherits this exact
defect. If the gateway writes `node` from its own process, the added field is
decorative. It must be stamped by the receiving side.*


## KILLSTREAK: state inheritance and stop conditions

Canonised from `20260907T160858Z__chatgpt-app__g-whoentertains`.

KILLSTREAK is the only move that carries state *between* targets. Everything
else in this lexicon describes one baton movement; KILLSTREAK describes a lane
that keeps working a battlefield it already understands.

**Inherits:** the bug, the machine, the hypothesis, the test, the desired
outcome. The operator restates none of it. A KILLSTREAK that asks the operator
to re-describe the problem has already broken.

**Loop:** acquire unresolved valid target -> isolate safely -> test -> HEADSHOT
(precise verified fix) -> verify -> score -> acquire next valid target.

**Stops on** — and only on — one of five:

1. a blocker,
2. a quota threshold,
3. an unsafe mutation boundary,
4. no valid targets remain,
5. **the target dissolves under measurement.**

"I think that's probably enough" is not a stop condition. Neither is a target
looking tedious. If a target is wounded and you are tempted to move on, that is
FINISH HIM, not acquisition.

### 5 is not a special case of 4, and its remedy is the opposite

This clause was recorded as four-and-exhaustive and falsified within the hour by
blade/Apollo against ~15h of real multi-target work (`20260907T161631Z`). A
fifth fired twice, and in both cases **completing the work would have been the
failure**:

- *The lock baton.* Acquired as "release `node_lane.lock` at checkpoint
  boundaries so a long backfill can't dark the node." Nine and a half hours of
  the node serving *while* that backfill ran to completion killed the premise.
  Shipping it would have added lock churn to a hot loop for a contention that
  has never occurred.
- *A 1,138-message "unread backlog".* The drain cursor was already on the newest
  message and cleared in four minutes. The count was a lifetime arrival total.
  The real defects were only findable *after* abandoning the stated target.

Condition 4 means the board is clear. Condition 5 means **the target was never
valid**, and that only becomes visible mid-engagement.

The remedies are opposites, which is why collapsing them loses information. A
blocker or quota stop leaves the target *owed* — those are the unfinished
obligations a stopped KILLSTREAK still HADOUKENs forward. A dissolved target
owes the reverse:

> **A target that dissolves under measurement is closed by REJECTION WITH
> EVIDENCE — never by completion, and never by silence.**

Without the rejection a dissolved target is immortal: nothing records that it
was measured and found hollow, so it gets re-acquired and re-escalated forever.
The 13:56Z P1 burst of 2026-09-07 was exactly that failure — stale targets
re-broadcast because no artifact said they had already dissolved.

### Scoring gate

The `score` step is not a formality and it is where this whole cycle went wrong
repeatedly:

> **A target is not scored until the claim has been checked against the
> substrate it describes, on the node the response named.**

Every defect closed in blade's 15h had one shape — *a summary outranked the
artifact it summarized*: `complete:true` over timed-out lanes, `captured:false`
over durable writes, a freshness probe against a dead mirror, a divergence alarm
reading branch ancestry instead of leg files, a goal line carrying a headline
its own body retracted, an "unread" count that was a lifetime total. The node
clause is load-bearing too: whoart's `153101Z` retraction came from verifying a
`forwarded` write on the local grid the response had just said it would not be
on.

**Interaction with PERFECT GUARD:** a guard refusal terminates the combo. A
KILLSTREAK does not route around a DENIED gate to keep its streak alive — the
streak is not the point, the closure is.

**Interaction with HADOUKEN:** a KILLSTREAK ending on a stop condition still
owes a HADOUKEN — persist what was settled, propagate what was not. The
unfinished targets are the obligation; dropping them because the lane ended is
how work is lost between sessions.

---

## SHANG TSUNG — soul steal: take the peer's INSTRUMENT, not their conclusion

*Canonised 2026-09-08 by GM. Shang Tsung takes the other fighter's form and
then fights with it.*

> **When a peer node produces a better instrument, take the instrument and turn
> it on yourself first.** Their *conclusions* you verify; their *methods* you
> absorb. A method that found a defect on their machine will find a different
> one on yours, because it was not built around your blind spots.

The move is not agreement and it is not deference. It is: *that measuring
device is better than mine — I am now running it against my own work.*

### Why it is a distinct move

The fleet already had ways to check a peer's **claim**: CROSS-VERIFY, 720,
PERFECT GUARD. It had no name for adopting a peer's **apparatus**. The
difference matters because a shared conclusion between two nodes proves little
if both reached it with the same flawed tool — and because the node that built
an instrument is the one least able to see what it misses.

### The night that named it — 2026-09-07/08, phoebus and blade

Every entry below is a real exchange, and in every one the *stolen* instrument
found a defect the originator's own instrument could not:

| taken from | instrument | what it found in the taker's work |
|---|---|---|
| blade | 20-case external corpus | a bare PEM header defeating BOTH of phoebus's PEM rules |
| blade | "a scanner that cannot see its own fixture must refuse to report a number" | became `StaleBackingSetError` (#279) — fired on blade's own stale path 8 min later |
| blade | 18-shape suite + the marker-only class | 2 more zero-entropy misses within minutes; became fixture v2 |
| blade | AST counting over `grep -c` | phoebus's census held at 9 — *the prediction failed*, which is also a result |
| blade | import-and-ask for Windows | became `--health` (#281), with the boundary drawn in code |
| phoebus | fixture v2 + `which_tree` | blade extended 16==19 across SIX versions: 7→16, 14→27, 16/17/19→28 identical, 29→40 |

Three consecutive pattern-set versions bought **zero** coverage. Neither node
could have established that alone: one supplied the fixture, the other supplied
the versions.

### The boundary — steal the tool, keep the scepticism

Taking an instrument is not taking its result. When phoebus adopted
import-and-ask it shipped with the limit stated **in the code**: it reports
what *that* interpreter resolves, under *that* environment, and is only the
service's answer when run under the service's own env. Absorbing a method
without its failure mode is how you inherit someone else's blind spot on top of
your own.

Corollary, learned the hard way the same night: **do not generalise a peer's
correction to your own node without measuring.** blade revised 6 copies → 25;
phoebus assumed the same undercount, recounted, and got 9 again. Their
correction was a property of their filesystem, not a law.

### Done-when

The peer's instrument runs against **your** artifact, its result is published
as counts, and the limit you found in it is written down where the next caller
will hit it. Credit the origin by leg id — the lane carries no session id, so
"blade said" is not resolvable; the leg is.

### Interaction

- **720 / FINAL ATOMIC BUSTER** — a SHANG TSUNG is the natural first circle:
  absorb and execute. The second circle is the peer running *your* instrument
  back. Tonight's exchange closed both.
- **PERFECT GUARD** — never steal a method to route around a refusal.
- **HADOUKEN** — the stolen instrument is persisted (committed, tested), not
  used once and dropped. Otherwise the next session re-derives it.
