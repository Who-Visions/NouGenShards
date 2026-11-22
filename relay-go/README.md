# relay-go

Native Go relay for NouGen nodes: same protocol as the Cloudflare Worker relay
(`workers/relay/worker.js`), one static binary, auth records in local SQLite.
The Python node client is unchanged.

Spec, TLS plan and rollout: [`docs/relay-go-spec.md`](../docs/relay-go-spec.md).

```
go build -trimpath -ldflags "-s -w" -o nougen-relay-go .
go test ./...

printf '%s\n' "$NODE_TOKEN" | ./nougen-relay-go auth put <id>
./nougen-relay-go serve -listen :8443 -db relay-auth.db -tls-cert cert.pem -tls-key key.pem
```

`go test` includes an end-to-end test that runs the real Python client
(`src/nougen_shards/relay_client.py`) against the relay; it skips when python is missing.

Status: skeleton for review. Not deployed, no provisioning hook, no ACME, no streaming.
