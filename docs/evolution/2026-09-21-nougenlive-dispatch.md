# Evolution log — nougenlive, ack→dispatch, fleet transport (Mon 2026-09-21, 8:33 PM–10:00 PM EDT)

Lane: hyperion @ WhoArt (claude-app, with codex-cli for the first half). GM: Dave.
Every step, the tool or script that did it, and how to run it natively. UTC ids are
quoted with Eastern beside them.

## What changed, in order

| # | Time (EDT) | Move | Code / command | Proof |
|---|---|---|---|---|
| 1 | 8:33 PM | `nougenlive` typed; codex ran only the dashboard | `nougen live overview` | Hyperion showed DEGRADED (8765 not listening) |
| 2 | 8:35 PM | Found /live static: fixed ports, hostname≠coach | `src/nougen_shards/live.py:149` | — |
| 3 | 8:42 PM | Coach/machine identity split; per-node `health_ports`; OverflowError guard | `live.py`, `~/.nougen/nodes.json` (`coach`, `machine`, `aliases`, `transport_node`, `health_ports`) | 20 tests pass |
| 4 | 9:01 PM | NouGenMsg routes by coach alias (`@hyperion`→whoart) | `nougenmsg.py::fleet_identity_maps/normalize_fleet_node` | 68 tests |
| 5 | 9:06 PM | Codex idle-wake receiver bound to thread | `tools/start_codex_pipe.ps1 -Action start -Thread $env:CODEX_THREAD_ID` | smoke ping QUEUED |
| 6 | 9:14 PM | `nougenlive` = activation handshake; inbox + open relays print inline; retain-until-ack | `nougen live activate` (bare `nougen live` too); `%APPDATA%\Python\Python311\Scripts\nougenlive.cmd` | live run |
| 7 | 9:17–9:20 PM | Hurricane Kick wake canary, 3-min window | `python tools/nougenmsg.py "@blade" "[MARKER] …"` | Phoebus 66 s, Apollo 93 s |
| 8 | 9:23 PM | Perpetual one-fix baton destiny + relay leg to Apollo | `nougen destiny create --branch REL …`; `nougen relay create -g … -M body.md` | destiny id 1; leg `20260922T012357Z__whoart__antigravity` (9:23 PM) |
| 9 | 9:24 PM | `nougen relay sync` failed — **no such verb** | valid: `open ack checkpoint complete autoclose policy init pull rules react shards admit guard adopt dispatch` | — |
| 10 | 9:27 PM | NouGenShards PR opened, then all remaining work committed | `git push -u origin fix/whoart-findings-2026-09-19`; `gh pr create -R Who-Visions/NouGenShards` | [PR #484](https://github.com/Who-Visions/NouGenShards/pull/484), 3 commits |
| 11 | 9:30–9:36 PM | Board sweep: every open leg acked | `python -m nougen_relay.cli ack --id <id> -m "…" --no-push --no-fetch` (loop), then `git push origin HEAD:main` | 211→open 9; pushed `9d6cf7391` |
| 12 | 9:36 PM | Learned: local NouGenRelay clone sat on `fix/mcp-server-canonical-relay-root`, 1655 commits diverged; `push origin main` pushed a stale local main | always `git push origin HEAD:main` from that clone | — |
| 13 | 9:40 PM | **Why ack never executed**: `ack` only flips `status`; nothing consumed acked legs | — | — |
| 14 | 9:43 PM | `relay dispatch` built: resolve node → NouGenMsg wake → `in_progress`; ack auto-dispatches on published acks | `src/nougen_relay/dispatch.py`; `relay dispatch --id X` / `--all [--dry-run] [--chunk 40]`; `NOUGEN_RELAY_NO_DISPATCH=1` kill switch; `--no-dispatch` on ack | 73 tests |
| 15 | 9:43 PM | First real run marked all 17 digests ❌ although delivered — CLI exits non-zero when a secondary lane is down | detection now keys on the `DELIVERED`/`QUEUED` receipt line | Hyperion received its own digests |
| 16 | 9:43 PM | Phoebus: "dispatch by ASK, not by leg count" — 35/37 legs were reports | `dispatch.is_ask` = prefix regex + `autoclose.classify` + e2b verdict sidecar | 530→426 by rules |
| 17 | 9:46 PM | ASK/REPORT classification on local e2b (Rule 0.7), $0 | `python tools/classify_asks.py` → `.handoffs/ask_verdicts.json`; batch 10, `max_tokens` 4096, JSON mode; e2b echoes only the 16-char timestamp prefix of ids — match on prefix | 59 verdicts / 25 ASK at 9:56 PM, running |
| 18 | 9:47 PM | Fleet broadcast: token rule + what Hyperion is doing + ask for 10 plays | `python tools/nougenmsg.py "<text>"` (no address = broadcast) | 3 lanes replied (Phoebus 5+10, Blade/Shadow Dweller 10, Antigravity 10) |
| 19 | 9:50 PM | WhoArt→Phoebus was always falling to SSH: `NOUGEN_NODE_PHOEBUS_IP` unset | `[Environment]::SetEnvironmentVariable('NOUGEN_NODE_PHOEBUS_IP','kushboygroups-mac-mini.local','User')` | Phoebus saw source lane `whoart` directly |
| 20 | 9:55 PM | WhoArt receiver bound `127.0.0.1:8766` → Phoebus could never reach it. Not firewall. | `NOUGEN_AGY_MSG_BIND=0.0.0.0` (user env) + restart `tools/nougenmsg_node.py` under pythonw | Phoebus: `whoart.local:8766/health` → 200 |
| 21 | 9:59 PM | Per-node sender port (whoart 8766 ≠ phoebus 8765) | `tools/nougenmsg.py::_route_port(node)` reads `NOUGEN_NODE_<NODE>_PORT` before `NOUGEN_MSG_PORT` | phoebus:8765 answers 404 to `/msg`, :8766 hangs — parked, SSH ≈1 s |

## How to use it natively (no Claude in the loop)

- Light up a lane: `nougenlive` (or `nougen live`). Prints wake state, three coaches, retained NouGenMsgs, open legs.
- Take and forward a baton: `python -m nougen_relay.cli ack --id <leg> -m "<why>"` — publishes and dispatches. Local-only: add `--no-push`.
- Forward the backlog: `python -m nougen_relay.cli dispatch --all --dry-run` then without `--dry-run`. One digest per node.
- Classify before dispatching: `python tools/classify_asks.py` (NouGenRelay). Re-runnable; caches verdicts.
- Close a leg you executed: `python -m nougen_relay.cli checkpoint --id <leg> --state complete -m "<proof>"`.
- Message a coach: `python tools/nougenmsg.py "@hyperion:claude" "<text>"` — coach names resolve to nodes.
- Local judgement: `POST http://localhost:11434/v1/chat/completions` model `gemma4:e2b-qat`, `max_tokens ≥ 1400` (4096 for JSON lists), `response_format json_object`.
- Relay verbs that exist: `open ack checkpoint complete autoclose policy init pull rules react shards admit guard adopt dispatch`. **`sync` does not exist.**

## What the fleet learned (shard these)

1. Ack ≠ execution. A status flip is not a handoff; the baton must arrive in the executing lane's inbox.
2. Classify before you dispatch. Most legs on this board are receipts. Replaying them redoes merged PRs.
3. Delivery truth is the receipt line, not the exit code.
4. Coach ≠ machine. Hyperion/Apollo/Phoebus are lanes on WhoArt/Blade/Mac Mini; both must be in every identity record.
5. Loopback binds look like firewall problems from the far side. Check `Get-NetTCPConnection -State Listen` before touching firewall.
6. Receivers differ per node (8766 vs 8765). Ports are per-node config, never one global.
7. e2b truncates long ids in JSON keys — match on prefix.
8. Tests that call `ack` must not send wire traffic: `--no-push` and `NOUGEN_RELAY_NO_DISPATCH=1` keep it local.
9. From a clone on a side branch, `git push origin main` pushes the stale local `main`. Use `HEAD:main`.
10. `relay sync` was invented, not read. Check `--help` before guessing a verb.

## Open (parked, owned)

- Phoebus HTTP hop (404 on :8765, hang on :8766) — Phoebus.
- Blade Codex pipe WinError 2 + blade fan-out self-stamping as source — Apollo (leg `20260922T012357Z`, 9:23 PM).
- `relay-watch` echo storm → wire `relay_triage` into `announce()` — needs Dave (changes a live watcher).
- Windows inbound rule for :8766 if any node other than Phoebus is refused — Dave.
