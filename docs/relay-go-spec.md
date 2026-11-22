# NouGen Relay, native Go edition: spec and canary

Status: spec plus a working skeleton in `relay-go/`. Nothing here is deployed. Tonight's
Cloudflare Worker relay (`workers/relay/`, `tools/relay_golive.py`) is untouched.

Origin: GM work order "Spec it" (relay leg 20261120T021739Z) and its amendment "Relay.nougenai.com
for MCP connectors" (20261120T021959Z). The relay protocol source of truth is
`workers/relay/worker.js`; `docs/nougen-relay.md` describes the node side.

## 1. What this is

A single static binary that speaks the same protocol as the Worker relay, so the Python node
client (`src/nougen_shards/relay_client.py`) connects to either one **unchanged**. A node moves
between them by changing one value, `relay_url` in its `node.json`.

| | Cloudflare Worker (today) | Go relay (this) |
|---|---|---|
| Runs on | Workers + one Durable Object per node | one process on any computer |
| Auth records | KV `RELAY_AUTH`, key `relay:<id>` = sha256(token) | local SQLite table `relay_auth` |
| Sessions | DO (hibernatable sockets) | in memory, one per node id |
| Scale | per-node DO, global | **one process**; run a second relay for redundancy, not scale-out |
| Build | `wrangler deploy` | `go build`, 10 to 11 MiB stripped, no cgo |

Measured here (WhoArt, Go 1.27): `windows/amd64`, `linux/amd64`, `linux/arm64`, `darwin/arm64` and
`darwin/amd64` all build with `CGO_ENABLED=0 go build -trimpath -ldflags "-s -w"` at 10 to 11 MiB.

## 2. Protocol 1 (lifted from `workers/relay/worker.js`)

### Endpoints

| Request | Auth | Answer |
|---|---|---|
| `GET /_relay/health` | none | `200 ok` |
| `GET /_relay/connect?id=<id>` + WebSocket upgrade | `Authorization: Bearer <node token>` | `101`, then frames. Not an upgrade: `426`. |
| `GET /_relay/status?id=<id>` | same bearer | `{"live":bool,"transport":"relay","since":ms or null}` |
| `<id><host-suffix>/<path>` (e.g. `n1.relay.example/mcp`) | none (the node enforces its own) | proxied to the node |
| `/n/<id>/<path>` on any host | none | same, path form |
| anything else | | `404 Not found` |

`id` matches `^[a-z0-9][a-z0-9-]{0,62}$` after lower-casing. Bad id: `400 {"error":"bad id"}`.
Missing or wrong token, or unknown id: `401 {"error":"unauthorized"}` (status needs the token too,
so ids and liveness cannot be enumerated). Go addition: an unreadable auth store answers
`503` and lets nobody in (fail closed).

### Auth

The relay stores only `sha256(token)` as lower-case hex per id. A connect sends the node's existing
join token as a bearer; the relay hashes it and compares in constant time. The hash is computed even
when the id is unknown so a missing id does not answer faster than a wrong token. The token is never
stored or logged.

### Frames (WebSocket text, JSON)

| Frame | Direction | Fields |
|---|---|---|
| `{"t":"ready","v":1,"since":<ms>}` | relay to node, once after connect | protocol version, session start |
| `{"t":"ping"}` / `{"t":"pong"}` | node to relay / reply | node pings every 20 s |
| `{"t":"req","rid","method","path","headers","body"}` | relay to node | `path` includes the query string; `headers` is an object; `body` is standard base64 (empty string when none) |
| `{"t":"res","rid","status","headers","body"}` | node to relay | `status` integer 200 to 599; `headers` a list of `[name,value]` pairs (repeats survive, e.g. Set-Cookie) or a plain object or null; `body` base64 string or null |

Unknown frames, non-JSON, and a `res` for an unknown `rid` are ignored.

### Session rules

- **One node, one session.** A new connect for the same id closes the old socket with code **4000**
  `replaced` and fails the old session's in-flight requests (they answer `504`).
- **Disconnect** fails every in-flight request (`504`); later requests get the offline page (`502`).
- **Idle drop** (Go addition, mirrors the client's "three silent intervals"): a node silent for 90 s,
  not even a ping, is disconnected.
- Request ids are random, never a counter.

### What the relay checks on a node's answer (the node is outside the trust boundary)

`502` with a reason for: status not an integer in 200 to 599; body present but not a string; body not
valid base64; headers neither a list of string pairs nor an object of strings; a header name that is
not a token or a value with CR, LF or NUL (header injection); an encoded body over the cap; a decoded
body over the cap. Hop-by-hop headers (`connection`, `keep-alive`, `proxy-connection`,
`transfer-encoding`, `upgrade`, `te`, `trailer`, `host`, `content-length`) are dropped in both
directions. `204`, `304` and `HEAD` carry no body. Every response gets `x-nougen-transport: relay`.

### Limits

`RELAY_REQUEST_TIMEOUT` (default 30 s) then `504 node did not answer in time`.
`RELAY_MAX_BODY_BYTES` (default 8 MiB) applies to the public request (`413`, checked on the declared
length and again while streaming) and to the node's response (`502`). The WebSocket read limit is the
base64 size of that cap plus 256 KiB.

### Known limit of protocol 1 (same as the Worker)

Bodies are buffered whole in both directions. A response that streams (Server-Sent Events, a long
poll, a download over 8 MiB) cannot pass. See section 5 for what that means for MCP.

## 3. Auth records: KV to SQLite

```
table relay_auth (id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, updated_utc TEXT NOT NULL)
```

The driver is `modernc.org/sqlite` (pure Go, no cgo). **This is one dependency beyond the order's
"stdlib + gorilla/websocket only":** the standard library has no SQLite, so the order's local-SQLite
requirement and its dependency list cannot both hold. If the list wins, the `AuthStore` interface
(`relay-go/store.go`) is small enough to back with a flat file instead.

Commands:

```
printf '%s\n' "$TOKEN" | nougen-relay-go auth put <id>     # stores sha256(token); rotate by running again
nougen-relay-go auth import relay-auth-export.json         # [{"key":"relay:<id>","value":"<sha256 hex>"}]
nougen-relay-go auth list                                  # ids only
```

`import` is all-or-nothing: a bad row (key not `relay:<id>`, value not a 64-hex digest) rejects the
whole file and writes nothing. The token is read from stdin, never from arguments.

Not done, and needed before a real rollout: **provisioning.** Today the join worker writes
`relay:<label>` into the Worker's KV when it hands out `setup.sh`. A node provisioned for the Go
relay needs its record in the Go relay's database. Options: an authenticated admin endpoint on the
Go relay that the join worker calls, or a dual write. Neither is built.

## 4. TLS plan: a real certificate for `relay.nougenai.com`

Constraints:

1. The Python client dials `wss://` only and verifies the certificate (it refuses `ws://`).
2. **`relay.nougenai.com` is already the Cloudflare Worker relay's production custom domain**
   (`workers/relay/wrangler.jsonc`, env production; `relay_golive.py --apply` deploys to it and the join
   worker writes `wss://relay.nougenai.com/_relay/connect` into `node.json`). Two relays cannot hold
   that name at once.
3. MCP connectors (Claude, ChatGPT) require a publicly trusted certificate. A private CA is not an option for them.

Decision: **run the canary on its own name, `relay-go.nougenai.com`, and move `relay.nougenai.com`
only at cutover** (section 6, stage 4). The amendment's final hostname is `relay.nougenai.com`;
this keeps it, with the Worker as the fallback route during the move.

| Option | How | Fits | Cost |
|---|---|---|---|
| **A. Cloudflare proxy in front** | orange-cloud `relay-go.nougenai.com` to the Go host; install a Cloudflare Origin CA certificate on the Go server (`-tls-cert/-tls-key`); SSL mode Full (strict) | canary and final | keeps DDoS cover and the origin IP hidden; WebSockets are supported; heartbeat every 20 s keeps the socket from idling out |
| **B. Direct, Let's Encrypt** | grey-cloud DNS to the Go host; ACME HTTP-01 or TLS-ALPN-01 on 80/443 | canary | origin IP exposed; the skeleton does not implement ACME |
| **C. Direct, DNS-01** | a Cloudflare API token limited to the zone's DNS edit; `certbot` or `lego` writes the cert files | final, and the only way to a wildcard | one more secret to keep (keymaker) |
| **D. Private CA** | nodes trust a local CA through `NOUGEN_RELAY_CA_BUNDLE` (the client already supports it) | canary nodes only | does not work for MCP connectors |

Recommendation: **A for the canary and for the end state**, with the real certificate being
Cloudflare's edge certificate for the public name and the Origin CA certificate on the server. Use the
path form `/n/<id>/...` for connectors so a single-name certificate is enough; the host-suffix form
`<id>.relay.nougenai.com` would need a wildcard certificate (option C).

The binary serves TLS from files and does **not** reload them: renewing means a restart.
A `GetCertificate` hot reload is a small follow-up, not part of this skeleton.

## 5. How MCP connectors reach nodes through it

Connector URL for a node on the relay: `https://relay.nougenai.com/n/<id>/mcp` (path form).
The relay forwards the request, with the connector's headers (including its `Authorization`), to the
node's local port. **The relay adds no authentication to public requests**: the node enforces its own,
exactly as it does behind the Cloudflare tunnel today.

What works under protocol 1: MCP over HTTP where each call is a POST with a JSON reply (up to 8 MiB,
30 s). What does not: any `text/event-stream` response or other long-lived stream, because the relay
buffers the whole body. If a connector needs SSE, the fix is protocol 2: `chunk` frames
(`{"t":"chunk","rid","body","end"}`) and a streaming response writer. **Spec only, not built.**

Fleet-side change when a tenant moves to the relay: its `node_url` in the TENANTS record becomes
`https://relay.nougenai.com/n/<id>` instead of `https://<id>.nougenai.com`. `joinctl verify` already
checks the node's `/health` through that URL; not changed here.

## 6. Rollout (beside Cloudflare, node by node)

Each stage has an exit test; stop at the first failure and leave the node on the Worker.

0. **This PR.** Spec and skeleton reviewed. Exit: tests green, reviewer agrees on the protocol section.
1. **Canary host.** Run the Go relay on one computer at `relay-go.nougenai.com` (option A). Import the
   Worker's `relay:*` records for the canary node only. Exit: `GET /_relay/health` is `ok` and
   `GET /_relay/status` with the node's token answers.
2. **One canary node.** Set its `relay_url` in `node.json` to `wss://relay-go.nougenai.com/_relay/connect`;
   restart its supervisor. The Python client is unchanged. Exit: `status` is live, `/n/<id>/health`
   returns the node's health through the relay, an MCP call from a connector works, and the node stays up for 24 h.
3. **Node by node.** Move the rest one at a time. **Rollback is one value:** put the Worker URL back in
   `relay_url`. The Worker relay stays deployed the whole time. Exit per node: same checks as stage 2.
4. **Hostname cutover.** Only when the Worker is to retire: lower DNS TTL a day before, point
   `relay.nougenai.com` at the Go relay, keep the Worker route available for rollback.
   Do not do this while the Cloudflare go-live is the production path.

## 7. Verified and not verified

Verified here (WhoArt, 2026-11-19 evening):

- `go vet` clean; 22 Go tests pass, five repeated runs stable (auth cases, routing, round trip, repeated
  headers, replace with close code 4000, in-flight failure on replace and on disconnect, 504, 413 on
  declared and chunked bodies, 16 hostile node responses, null-body statuses, heartbeat, idle drop,
  40 concurrent requests, a 750 KB binary body, fail-closed auth store, SQLite persistence, token never on
  disk, KV import).
- **End to end with the unchanged Python client**: `python -m nougen_shards.relay_client probe` exits 0
  and `run` goes live against the Go relay over TLS; a GET and a POST come out of the node's app; repeated
  `Set-Cookie` headers survive. (`relay-go/e2e_test.go`; skips when python is absent.)
- Cross-builds for five targets (section 1).

Not verified:

- The race detector (`go test -race` needs cgo, which this box lacks).
- Any real certificate, any run on macOS or Linux, any load beyond the 40-request test, any long-lived node.
- A node on a corporate proxy through the Go relay.
- The Worker's exact behaviour in the cases above (this spec is read from `worker.js`, not compared by running both).
- Provisioning, ACME, certificate reload, protocol-2 streaming, a CI workflow, a service unit: not built.
