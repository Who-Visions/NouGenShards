# NouGen Relay

A fallback tunnel for computers whose network blocks `cloudflared` (UDP 7844 for QUIC
and TCP 7844 for http2), for example corporate or sandboxed boxes that only allow HTTPS
through a proxy.

The node dials **out** to `wss://<relay>/_relay/connect?id=<id>` on port 443 and keeps
that one socket open. Requests for the node's public address are piped down that socket.

```
browser ──https──> Worker ──> Durable Object (one per node) ══wss/443══> [HTTP proxy] ──> node client ──> 127.0.0.1:<port>
```

## Pieces

| Path | What |
|---|---|
| `workers/relay/worker.js` | Worker + `RelaySession` Durable Object (free plan: SQLite DO, hibernatable sockets, KV) |
| `workers/relay/wrangler.jsonc` | Preview config on workers.dev; `env.production` has no routes until the owner decides |
| `src/nougen_shards/relay_client.py` | Node client, standard library only |
| `tests/js/relay_worker.test.mjs` | Worker/DO tests (`node --test`) |
| `tests/test_relay_client.py` | Client tests against a mock CONNECT proxy and a private-CA TLS relay |

## Behaviour

- **Auth**: the node's existing join token, sent as `Authorization: Bearer`. The relay
  stores only `sha256(token)` in KV under `relay:<id>`; `relayAuthRecord(t)` in the
  worker builds that record so provisioning can write it.
- **One node, one session**: a new connect for the same id closes the old socket
  (code 4000) and fails its in-flight requests; re-registering is safe to repeat.
- **Heartbeat**: the node sends `{"t":"ping"}` every `NOUGEN_RELAY_HEARTBEAT_S` (20 s);
  the runtime answers without waking the object. Three silent intervals → reconnect.
- **Reconnect**: exponential backoff with jitter, capped by `NOUGEN_RELAY_BACKOFF_MAX_S`
  (60 s); a session that lived over a minute resets the backoff. A rejected token backs
  off to the cap.
- **Proxy**: `HTTPS_PROXY` / `https_proxy` / `ALL_PROXY`, `NO_PROXY`, Basic auth from the
  proxy URL, HTTP CONNECT to port 443.
- **CA bundles**: `NOUGEN_RELAY_CA_BUNDLE`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`,
  `CURL_CA_BUNDLE` (added to the system store, not replacing it).
- **DNS**: if there is no proxy and the system resolver fails, the client resolves the
  relay host over DNS-over-HTTPS internally. There is nothing for users to set up.
- **Limits**: `RELAY_REQUEST_TIMEOUT_MS` (504 after), `RELAY_MAX_BODY_BYTES` (413 above).
  Offline node → 502 page that says so. Responses carry `x-nougen-transport: relay`.
- **Status**: `GET /_relay/status?id=<id>` → `{"live":true,"transport":"relay","since":…}`
  for the Join page.

## Setup transport order

The setup script tries, in order, and records which one is live:

1. `cloudflared tunnel run --protocol quic`
2. `cloudflared tunnel run --protocol http2`
3. `python -m nougen_shards.relay_client probe --node-json node.json` (exit 0 = live),
   then the supervisor runs `python -m nougen_shards.relay_client run --node-json node.json`
4. otherwise: "This computer's network blocks every way NouGen reaches the internet, so it
   can't host a public node. Try another network or computer."

The Join page moves to Step 3 on whichever transport is live and names it.

## Deploy

```bash
cd workers/relay
npx wrangler kv namespace create RELAY_AUTH   # put the id in a local copy of wrangler.jsonc
npx wrangler deploy -c wrangler.local.jsonc   # preview on workers.dev
```

Production (`--env production`, routes for `<id>.<domain>`) is an owner decision and is
not part of this change.
