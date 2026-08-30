---
name: relay
description: Use at the START of any working session and again when it ends — reading open handoff legs and active claims before touching anything, taking over a leg someone else left, claiming a repo scope before editing it, passing the baton when work or the session ends, or diagnosing why a leg or claim is invisible to another machine. Covers the NouGenRelay protocol (Rule 0.0.1), the git_handoff CLI, and the settled quirks about what publishes and what does not. Does not cover live session-to-session chat — that is cross-session-messaging.
---

# Relay — claim first, baton last

Shards are what the fleet **knows**. The relay is what the fleet is **doing**.
Both get read before work starts, not after it goes wrong.

The failure this prevents is duplicated work. On 2026-07-31 the same work was
done twice on three separate occasions, because handoffs were only ever written
when work *ended*. Announcing intent up front is the half that was missing.

Skipping the relay is a rule violation, not a shortcut — same standing as
dispatching one model when the operator said "fleet".

## The three beats

### 1. Session start — read before touching anything

```
relay_open        # legs nobody has acked
relay_claim_list  # what each machine says it is on right now
```

If an open leg already covers the work in front of you, **`relay_ack` it and
continue that leg**. Do not open a parallel one. Acking is not "acknowledging
completion" — it is claiming responsibility to carry that leg forward.

### 2. Before working in a repo — claim the scope

```bash
python tools/git_handoff.py claim take -s "<paths>" -g "<one-line intent>"
```

Release it when you are done. Claims expire on a TTL, so a stale claim is not a
permanent lock.

### 3. When work ends, or the session does — file a leg

`relay_create(goal, message)` — `goal` is one line (max 200 chars) and shows in
every listing; `message` is the markdown body, structured as **situation / ask /
done-when**. A leg stays `open` until someone acks it. An unacked leg is a baton
lying on the track, not a completed handoff.

## Tools

| MCP tool | What it does |
| --- | --- |
| `relay_open(limit=10)` | Unacked legs, newest first. Reads the **remote**. |
| `relay_claim_list()` | Active, unexpired claims across machines. |
| `relay_create(goal, message)` | Write a new leg; lands as open for other lanes. |
| `relay_ack(id, note)` | Take the baton on a leg. Publishes. |
| `relay_latest` / `relay_read` | Read the most recent / a specific leg. |
| `fleet_whoami` | Confirms which lane and identity you are acting as. |

## CLI

`git_handoff.py` lives in each **consuming repo's** `tools/` directory —
`Outpost\NouGenQ\tools\`, `Outpost\NouGenTv\tools\`. It is **not** in
`Outpost\NouGen\tools\`; looking for it there is a dead end.

```
git_handoff.py claim <take|check|list|release> -s SCOPE -g GOAL
                     [--ttl HOURS] [--force] [--all] [--no-push]
git_handoff.py relay <open|ack|checkpoint|complete>
                     [--id ID] [--state STATE] [-m MESSAGE] [--no-push]
git_handoff.py <create|list|latest|check|whoami|triggers|pull>
```

`--id` defaults to the newest foreign leg. `check` is the pre-flight: has
another machine moved?

## Settled quirks — do not re-derive these

- **`relay_open` reads the remote.** A leg does not exist for another machine
  until it is published. Locally-visible is not fleet-visible.
- **`create` does not publish. `claim` and `ack` do.** This is the single most
  common source of "I filed a leg and nobody saw it".
- **A leg's identity is its filename.** There is no id field to look for.
- **`--no-push` keeps a claim local, which makes it invisible** — which defeats
  the entire purpose of claiming. Use it only when you have a specific reason.
- **On the whoart machine the bare `relay` console script does not exist.** Use
  `python -m nougen_relay.cli`.
- **The `git_handoff` claim registry and the pre-commit `relay guard` registry
  are separate.** The hook's "not covered by a claim of yours" line is noise,
  not evidence your claim failed. Do not chase it.
- **Claims only cover the repo holding the records.** A claim in one repo says
  nothing to a lane working in another.

## Lane

The connector lane is `claude-app` against `Who-Visions/NouGenRelay`.
Confirm with `fleet_whoami` rather than assuming.

## Related

Fan-out work collides — claim before you [[fleet]] out, leg it after you land.
Durable findings from the work belong in [[shards-memory]], not in the leg body;
a leg is a baton, not a knowledge store.
