# Phoebus upgrade — GATEWAY role

**Decided 2026-08-17 (GM).** Phoebus terminates connector traffic like blade does.
Closes the open decision on relay leg `20260817T011421Z__blade1tb__phoebus`
("role decision: replica vs gateway") and its `ccr` triage note.

Written from whoart (`claude-app` lane). Everything below marked **[phoebus]**
must run on the phoebus machine — it cannot be done from here.

---

## What the decision commits us to

A replica would only have had to mirror shards and answer recall. Gateway means
phoebus becomes a **second auth surface**: it terminates per-lane bearer tokens,
so it needs its own keys, its own fingerprint entries in the ledger, and it
inherits blade's failure modes (a wrong token is a live 401 for every connector
lane pointed at it, not a local inconvenience).

Blade's own wrangler config already records the trap this walks into:

> INTERIM 2026-08-15: outpost's node lane (21,973 shards) over a quick tunnel —
> blade's `SHARD_GATEWAY_TOKEN` is unknown to every vault reachable from outpost
> (401 confirmed live).

Two gateways with two token namespaces is exactly how that happened. Phoebus's
token must be minted by the keymaker and recorded, not copied from blade.

## Preconditions (verified from whoart, 2026-08-17)

| Check | State |
| --- | --- |
| Vault-discovery trap | **Resolved.** `bf133eb` is on `origin/main`; `NOUGEN_SECRETS_VAULT_DIR` is optional and a stale/missing value no longer strands secrets silently. Weekend parity pull is safe. |
| Shard gateway (blade) | **Up**, HTTP 200, `shards.nougenai.com`, lane `claude-client`. |
| Parity branch | `agent/nougen-assurance-sprint` → PR into `main` (shard highway `db251c13`, arXiv vault fix `904a773f`, `/search` era bounds `18ea86b6`). **Pull main after that PR lands, not before** — otherwise phoebus comes up without the highway tooling. |
| Tracker dailies | phoebus last published **2026-08-02**. blade1tb is current to 08-15; whoart to 08-17. Phoebus is the only stale lane. |

## Checklist

### 1. Parity pull **[phoebus]**
- [ ] `git -C <NouGenShards> fetch --all && git pull --ff-only` on `main` **after** the sprint PR merges.
- [ ] Confirm `bf133eb` (vault discovery), `904a773f` (arXiv vault override), `db251c13` (shard highway), `18ea86b6` (era bounds) are all present.
- [ ] `python -m pytest tests` — expect 565 passed / 4 skipped or better.

### 2. Keys — mint, never copy **[phoebus]**
Provision through the keymaker so the ledger records them. Required for a
gateway lane:

- [ ] `NGS_NODE_TOKEN` — phoebus's own node token. Current ledger entry fingerprints `9c67af03a9da` (rotated 2026-08-14); phoebus's must be a **new** value with its own fingerprint.
- [ ] `SHARD_GATEWAY_TOKEN` — per-lane bearer for whatever lanes phoebus will serve. Do **not** reuse blade's; that is the 401 above.
- [ ] `NOUGEN_SHARDS_MCP_ACCESS_KEY` / `NOUGEN_SHARDS_MCP_SIGNING_SECRET` — only if phoebus serves the MCP surface directly (`a8712e2f4685` / `63f60653f0e9` are blade's, rotated 2026-08-15).
- [ ] Record every new fingerprint in the keymaker ledger and confirm via `vault_list` from a connector lane (names + fingerprints only — the vault never returns values, and there is deliberately no `vault_get`).

### 3. Tool surface **[phoebus]**
Expose the same set blade does, and nothing more:
- [ ] `/health` public; every data endpoint behind `X-NGS-Token` (`verify_token` 503s until the token is configured — deny-by-default is the property that makes a public flip safe).
- [ ] `/search` — now honours `since`/`until` and emits `X-NouGen-Held-Back`. Verify with a bounded query that returns **zero** out-of-era rows.
- [ ] `/capture`, `/sync/push`, `/sync/pull`, `/sync/hashes`.
- [ ] Keep `execute_sandboxed_code` and brain scan/import **stdio-local**. Remote code execution does not belong on a network surface.

### 4. Topology — still open
The relay flagged **worker-topology** alongside the role decision. With phoebus
as a gateway the live question is whether `nougen-fleet-mcp` fans out to both
gateways or fails over:

- **Failover** (recommended first cut): connector keeps `shards.nougenai.com`
  primary, phoebus as standby. One token namespace in play at a time; smallest
  change to the deployed worker.
- **Fan-out**: connector queries both and merges. Better coverage, but every
  connector tool that reports provenance has to disambiguate two sources, and
  `held_back` accounting spans two nodes.

Not decided here — it needs the GM once phoebus is actually serving.

### 5. Tracker daily **[phoebus]**
- [ ] `NOUGEN_MACHINE=phoebus python run_daily.py` in `NouGenTracker`, then backfill `--start 2026-08-03 --end <today> --export`.
- [ ] Commit and push `dailies/phoebus/` — publishing is local, pushing is the deliberate step.

---

## Known gap outside phoebus

`ask_griot` is **not in the `nougen-fleet-mcp` source** (`main` = `2accf5a`, and
origin agrees). The live connector exposes it anyway, so it was deployed from a
working tree that was never committed. The node-side leak is fixed in
`18ea86b6`, but the connector's own `held_back` accounting can't be reviewed
until that source is recovered and pushed. Whoever deployed it owns that.
