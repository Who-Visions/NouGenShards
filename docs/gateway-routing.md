# Gateway routing: why `ask_rhea` returned `530: error code: 1033`

Resolved 2026-08-29. Recorded because the symptom pointed at inference and the
cause was routing, and nothing about the real path lived in this repo.

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
Fix: point at the failover worker's `workers.dev` hostname, which is outside
the zone and therefore cannot be bypassed:
`SHARD_GATEWAY_URL = https://nougen-shard-failover.whoentertains.workers.dev`

Pointing straight at the Space also works, but discards blade failover for the
day blade returns. The `workers.dev` target keeps both.

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
