# Gateway routing: why `ask_rhea` returned `530: error code: 1033`

Resolved 2026-08-29. Recorded because the symptom pointed at inference and the
cause was routing, and nothing about the real path lived in this repo.

## Canonical address

`https://shards.nougenai.com/mcp` IS THE FRONT DOOR. Every lane addresses that
and only that. Everything else — the Space, blade, the failover worker — is a
backend that resolves BEHIND it and is never addressed directly by a client.

    SHARD_GATEWAY_URL = https://shards.nougenai.com

Do not point a connector at `blade.nougenai.com`, at
`nougenai-nougenshards.hf.space`, or at any `*.workers.dev` hostname. Those are
origins, not addresses. A lane pointed at an origin has no failover, and when
that origin goes down the lane goes down with it — which is exactly what
happened on 2026-08-29 when a thunderstorm took blade offline while the Space
was up and answering in 0.3s.

This has now drifted three times (see the git log of `wrangler.jsonc`, whose
own last commit reads "restore SHARD_GATEWAY_URL to the HF Space hostname
production actually ran"). If a value other than the front door is ever
observed in production, it is drift — repair it, do not adopt it.

## Symptom

`ask_rhea` returned:

```
rhea /agent 530: error code: 1033
```

Earlier it returned `no inference lane available (free + kimi-space + kimi all
down)`. Both readings invited the same wrong conclusion — that Rhea had no
brain — and sent several sessions hunting for missing provider keys.

## What was actually true

- The HF Space was healthy the whole time and answered `/agent` correctly,
  naming a brain (`free:nvidia/nemotron-3-ultra-550b-a55b:free`).
- `1033` is a Cloudflare **tunnel** error. `blade.nougenai.com/agent` returns
  exactly `530` / `error code: 1033`. Blade's tunnel is down.
- Rhea's `/agent` measured **70.5s** end to end. It runs a multi-round agent
  loop; it is not a `/search`-shaped request.

## Two independent faults

**1. The failover budget was tuned for the wrong endpoint.**
`nougen-shard-failover` aborted the Space attempt at `SPACE_TIMEOUT_MS`
(default 35000), then fell through to blade. The comment in that worker
explains the 35s figure came from `/search` ("blade answers /search in
9-11s"). Rhea needs roughly double it, so every call was cut off mid-flight and
handed to a dead tunnel, whose error surfaced as if it were Rhea's.
Fix: `SPACE_TIMEOUT_MS = 120000`.

**2. The connector pointed at a hostname in its own zone.**
`nougen-fleet-mcp` had `SHARD_GATEWAY_URL = https://shards.nougenai.com`. An
external client hitting that host is served by the failover worker
(`x-nougen-origin: space`, verified). The Worker's own subrequest to a hostname
in the same zone did not get the same treatment and reached the tunnel origin
instead — so the failover the design depends on never ran for the connector.
**This fix was wrong and has been superseded — see "Canonical address" above.**
It read: point at `https://nougen-shard-failover.whoentertains.workers.dev`,
"outside the zone and therefore cannot be bypassed". Two problems:

1. It abandons the front door instead of repairing it. Moving clients onto an
   internal hostname means every lane needs to know an implementation detail,
   and the next lane that does not know it points somewhere else again.
2. Cloudflare's own limit says `workers.dev` subdomains carry the SAME
   same-zone restriction as routes. It only appeared to work by being outside
   the zone — an accident, not the mechanism.

**The real cause is the ROUTING TYPE, not the hostname.** Per Cloudflare:

> On the same zone, the only way for a Worker to communicate with another
> Worker running on a **route**, or on a workers.dev subdomain, is via service
> bindings. On the same zone, if a Worker is attempting to communicate with a
> target Worker running on a **Custom Domain** rather than a route, the
> limitation is removed.

So `shards.nougenai.com` is bound as a **route**. That is the whole defect.

CORRECT FIX — bind `shards.nougenai.com` to `nougen-shard-failover` as a
**Custom Domain** rather than a route. Same-zone subrequests then resolve
through it exactly like external ones, and `SHARD_GATEWAY_URL` stays on the
canonical address for every lane.

A service binding from `nougen-fleet-mcp` to `nougen-shard-failover` also
works, is zero-cost with no network hop, and leaves the public front door
untouched. Prefer it only if you want the in-zone caller to be explicit;
Custom Domain is what makes every lane take one identical path.

ORDERING MATTERS. Setting `SHARD_GATEWAY_URL` back to the front door BEFORE
fixing the routing type reintroduces the bypass: the connector lands on the
tunnel origin, and if blade is down there is nothing behind it. Fix the
routing type first, then set the variable.

## Verification

```
ask_rhea      -> brain: free:nvidia/nemotron-3-super-120b-a12b:free
shards_status -> {"up": true, "status": 200, "configured": true}
```

A first call after deploy can report `up:false` from an 8s `/health` budget
against a cold Space. Retry before concluding anything; warm, it answers in
~0.9s.

## Diagnosis notes worth keeping

- `/health` returning 200 proves the Space is reachable. It does **not** prove
  the path a given caller takes. `/agent` and `/health` resolved differently
  for the same host, and reading `/health` as proof of health cost real time.
- `x-nougen-origin` on the response names which origin answered. Use it.
- "All lanes down" without per-lane detail is what let a routing fault
  masquerade as an inference outage. Per-lane diagnostics are in flight.

## Sources

Neither worker was in this repo when this was diagnosed; both were recovered
with `wrangler init --from-dash` and are now committed under `ops/workers/` (note: `fleet/` is gitignored, which is precisely why neither was ever tracked):

- `ops/workers/nougen-shard-failover.js`
- `ops/workers/nougen-fleet-mcp.deployed.js` (bundled deploy artifact)

Config values are **not** committed: the fleet worker's vars include an
allowed-email list. Read them with
`wrangler versions view <id> --name <worker>`.
