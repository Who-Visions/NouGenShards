# NouGenMsg tester quickstart

You were handed a **guest token** and a **node address**. With them you can
message the agent lanes your token allows, read your own inbox, and see where
each of your messages is. You can't read anyone else's messages, speak as
anyone else, or ask an app agent to buy, book, pay or call anything.

Keep the token private. It works until the date the node owner set.

## 1. Set up (once)

```sh
export NODE=https://<the node address you were given>
export TOKEN=<your guest token>
```

## 2. See who you are

```sh
curl -s $NODE/wire/info -H "X-NGS-Token: $TOKEN"
```

`you` is your address (`tester/<name>`). `may_message` lists the lanes you can
reach. `sends_per_minute` is your limit.

## 3. Send a message

```sh
curl -s $NODE/wire/send -H "X-NGS-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"to": "codex", "text": "hello from a tester", "kind": "ask"}'
```

The answer has an `id` and `receipts`. Keep the id.

## 4. Check where it is

```sh
curl -s $NODE/wire/status/<id> -H "X-NGS-Token: $TOKEN"
```

Each receipt is one hop, signed by the node: `accepted` (stored), `pushed` or
`delivered` (handed to the agent), `acked` (the agent read it), `answered`
(the agent replied). `verified: true` means the signature checks out.

## 5. Read replies and mark them read

```sh
curl -s "$NODE/wire/inbox" -H "X-NGS-Token: $TOKEN"
curl -s $NODE/wire/ack -H "X-NGS-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"id": "<reply id>"}'
```

Pass `?after=<next_after>` to read only what's new.

## When something fails

Every error says what went wrong and what to do.

| Code | Means | Do |
|------|-------|----|
| 400 | The message is malformed (bad address, empty text, text over 64 KiB). | Fix what `error` names. |
| 401 | Token missing, wrong or expired. | Check `reason`; ask the owner for a new token if expired. |
| 403 | Outside your scope: another lane, an app agent, someone else's inbox. | Message a lane from `may_message`. |
| 404 | No such message, or not one of yours. | Check the id. |
| 409 | That id was already used, or you acked something not sent to you. | Send a new message. |
| 413 | Request over 1 MiB. | Keep text under 64 KiB. |
| 429 | Too fast. | Wait `retry_after_s` seconds. |

A message an app agent refuses (it asked to buy, book, pay, call...) comes
back as `"state": "refused"` with a signed receipt. That's working as designed.

## For the node owner

Mint, list and revoke guest tokens on the node (stored hashed, picked up with
no restart):

```sh
python -m nougen_shards.wire.access mint --name harley --send-to codex,ollama --days 14
python -m nougen_shards.wire.access list
python -m nougen_shards.wire.access revoke --name harley
```

War-game the node from outside before handing it over:

```sh
NOUGEN_WIRE_ORIGIN=$NODE NOUGEN_WIRE_FLEET_TOKEN=... NOUGEN_WIRE_GUEST_TOKEN=... \
  python tools/wire_wargame.py
```

It runs 34 checks (auth, malformed input, replays, the guard against reworded
asks, the 9 by 9 lane matrix, guest scoping, the flood limit) on throwaway
pinned sessions that expire in ten minutes, and exits 1 on any failure.
