---
title: NouGen Shard Capture Dam
emoji: 🌊
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Shard Capture Dam

Durable write spool between the NouGen front door and the primary shard
reservoirs. **Holds intent, never truth.**

This Space is deliberately dumb cargo storage. It never holds the AES key, so
it cannot read a shard body — it receives ciphertext plus routing metadata,
verifies the request came from a NouGen front door, and writes one immutable
object to a private dataset repo. A full compromise of this Space yields
encrypted blobs and timing metadata, nothing more.

Space local disk is ephemeral, so nothing durable lives here: the queue lives
in the Hub repo. That is what makes a Space restart survivable.

## Endpoints
| | |
|---|---|
| `GET /health` | liveness + whether repo and ingress signing are configured |
| `POST /spool` | accept one sealed envelope; idempotent per `event_id` |
| `HEAD /spool/{event_id}` | 200 if queued, 404 otherwise |

## Refused at the door
`shards_forget` and any vault/secret operation are rejected with 403 — a queue
that accepts an irreversible deletion is a queue that can replay one. Requests
without a valid `ingress_sig` are rejected with 401.

`POST /spool` never returns `captured: true`. An event here is durable and
**not yet a shard**; only the spillway's ACK from the primary reservoir makes
it one.

## Secrets
| env | purpose |
|---|---|
| `NOUGEN_DAM_REPO` | private dataset repo, e.g. `nougenai/NouGenShardSpool-private` |
| `NOUGEN_DAM_HF_TOKEN` | fine-grained token, write-scoped to that repo **only** |
| `NOUGEN_DAM_HMAC_KEY` | hex, shared with the front door; gates ingress |
