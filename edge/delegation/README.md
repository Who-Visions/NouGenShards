# nougen-delegation

A durable claim/lease/fencing board for NouGenMsg work, as a Cloudflare Worker plus one SQLite-backed Durable Object. It is the edge twin of `src/nougen_shards/claim_lifecycle.py`: same states, same rules, so an actionable message cannot die at ACK and a stale worker cannot commit.

```
RECEIVED -> SUBMITTED -> CLAIMED -> WORKING -> VERIFYING -> COMMITTING -> COMPLETE
interrupts: INPUT_REQUIRED | AUTH_REQUIRED | BLOCKED     terminal: FAILED | CANCELED | REJECTED
```

## What it enforces

- `take` is atomic: claim, new fencing epoch, lease. Another lane is refused (409) while the lease is live; a re-take after expiry gets epoch + 1.
- Every later call carries the epoch. A stale epoch or expired lease is refused, so a zombie worker cannot heartbeat, checkpoint, verify, commit or complete.
- `complete` is reachable only through `verify` and `commit`, each with non-empty evidence. `commit` needs an idempotency key, and a claim cannot be rebound to a different key.
- Authority is re-checked at `commit` and `complete` (`ALLOWED_LANES`, fail closed).
- A watchdog alarm returns expired leases to SUBMITTED. `stalled` finds workers that heartbeat without checkpointing; `requeue` is bounded (3).
- Fail closed: with no `DELEGATION_TOKEN` set, every route except `/health` returns 503.

## API

`Authorization: Bearer <DELEGATION_TOKEN>`. JSON in, JSON out: `{ok:true,result}` or `{ok:false,error:{code,message}}`.

| Method + path | Body / query |
| --- | --- |
| POST `/v1/register` | `msg_id`, `lane` |
| POST `/v1/take` | `msg_id`, `lane`, `lease_seconds?` (1..86400, default 300) |
| POST `/v1/heartbeat` | `msg_id`, `epoch`, `state?`, `lease_seconds?` |
| POST `/v1/checkpoint` | `msg_id`, `epoch`, `evidence` (object) |
| POST `/v1/verify` | `msg_id`, `epoch`, `evidence` |
| POST `/v1/commit` | `msg_id`, `epoch`, `idempotency_key` |
| POST `/v1/complete` | `msg_id`, `epoch`, `proof` (object) |
| POST `/v1/fail`, `/v1/interrupt`, `/v1/requeue`, `/v1/cancel`, `/v1/sweep` | see `src/index.js` |
| GET `/v1/claim?msg_id=` · `/v1/open` · `/v1/stalled?no_progress_seconds=` | |

Status codes: 400 bad input, 401 bad token, 403 authority denied, 404 unknown task or route, 409 fencing or state violation, 503 unconfigured.

## Verify locally

```sh
npm install
npm test                                   # lifecycle rules on real SQLite (node:sqlite)
npx wrangler dev --local --port 8799       # needs .dev.vars: DELEGATION_TOKEN=..., SWEEP_SECONDS=2
TOKEN=<token> BASE=http://127.0.0.1:8799 node test/smoke.mjs   # end to end on workerd + Durable Object SQLite
```

## Not done

- **Not deployed.** `workers_dev` is off and no route is bound; the public hostname and `wrangler secret put DELEGATION_TOKEN` are decisions for the owner.
- **Nothing calls it yet.** `nougen live take-msg` still uses the local SQLite manager. Wiring the CLI to this board (and deciding which one is authoritative per lane) is a separate change.
- **No Cloudflare Workflows.** DO alarms already cover lease expiry; Workflows would only add value once the board itself drives multi-step execution.
- **Single board.** One Durable Object named `main` is a deliberate control-plane choice, not a throughput design.
- **Ported by reading** `claim_lifecycle.py`; scenarios mirror its rules but outputs were not diffed against the Python manager.
