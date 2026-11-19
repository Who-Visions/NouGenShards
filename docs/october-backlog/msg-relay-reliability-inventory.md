# NouGenMsg / Relay / Shards reliability: read-only inventory and drive-thru lesson mapping

Thu 11/12/2026 10:25 PM EST, whoart (hyperion) lane. Covers relay legs 20261031T185524Z (hardening),
20261021T041823Z, 20261021T042545Z and 20261021T050116Z (Checkers & Rally's drive-thru lessons).
Nothing here changes production. Every row says where the evidence came from; "not inspected" means I did not look.

## Inventory (Evidence on whoart; line numbers are from the whoart checkout of 11/12, not origin/main)

| Area | Finding | Evidence |
|---|---|---|
| NouGenMsg receiver persistence | Pending queue is in memory (`queue.Queue`), so queued messages are lost when the node restarts. The inbox file per message is the only durable copy. | `tools/nougenmsg_node.py:64` (`PENDING`), `:276-280` (file write). I restarted the node at ~9:40 PM EST; `pending_messages` was 0 before and after, so no loss was observed, but the design allows it. |
| Inbox write | `Path.write_text` straight to the final name, then the same for the last-message state file. No temp-file-and-rename, so a crash mid-write leaves a truncated JSON. | `nougenmsg_node.py:279-280`. |
| Message id | On `origin/main` a sender-supplied `message_id` is kept and `GET /msg/<id>` reports unread/read/unknown (`assign_message_id`, `receipt_state`). The whoart live node still runs an older checkout that generates a fresh `uuid4` per receipt (`nougenmsg_node.py:245` there), so a re-sent message gets a new id. | `origin/main` `tools/nougenmsg_node.py:234-266`; whoart checkout line above. |
| Idempotency / dedup | Neither version rejects a repeat: `record()` writes a new inbox file every time (the file name carries a timestamp). Evidence in the wild: relay-watch re-sent the same October legs to this lane repeatedly tonight, including legs already acked, and each arrived as new. | `agy_inbox` holds 927 files; newest `msg_1794539745508_relay-watch.json` 10:15:45 PM EST. |
| Dead-letter / retry | No dead-letter path and no retry count found. | grep for `dead.?letter|DLQ|idempotency_key|trace_id` in `nougenmsg_node.py` returned nothing. |
| Tracing | No trace or correlation id on messages. | same grep. |
| Inbox growth | 927 files in `~/.nougen/agy_inbox`, no visible expiry or archive. | directory listing. |
| Relay claims | Claims carry an `idempotency_key`, a TTL and a status. Good. | `relay_claim_list` output (sha256 key on each claim). |
| Relay legs | A leg has a state (`open` then `acked`) and `relay_ack` refuses a non-open leg, which acted as a real guard tonight ("is 'acked', not open"). | `relay_ack` error on leg 20261013T014505Z. |
| Relay write path | `relay_create` writes through the GitHub contents API and can fail with 409 when two writers race. No retry inside the tool; the caller must retry. | 409 on `.handoffs/20261113T011416Z...md` at ~8:14 PM EST, my retry succeeded. |
| Replay storm | relay-watch re-sends triaged legs without checking ack state. | ~20 replays tonight, all October legs. |
| Shard recall | Federated recall hits its 20-25 s deadline and returns `INCOMPLETE`; blade lane times out most often. Local DBs answer. | `shards_search` fanout: blade "aborted due to timeout", phoebus ok, whoart ok. PR #1047 is reported by the operator as the fix; not inspected. |
| Tenant ACL / backup / restore | Not inspected in this pass. | |

## Gap list, smallest first (each is a candidate PR with a test)

1. Receiver: write inbox files atomically (temp file in the same directory, then `os.replace`). Test: kill between write and rename leaves no partial `msg_*.json`.
2. Receiver: derive the key from the event (sender, target, thread, text) when the sender gives no id, claim it with a set-if-absent marker, and answer a repeat with `delivered: true, duplicate: true` plus the original file. Test: same message twice stores once. (Proposed as its own PR: `fix/msg-idempotent-delivery`.)
3. Receiver: rebuild `PENDING` from unconsumed inbox files on start. Test: restart with files present yields the same pending count.
4. relay-watch: skip legs whose state is not `open` before sending. Test: acked leg produces no message. This one stops the storm at the source and belongs in the relay-watch repo.
5. Inbox: archive consumed files older than N days. Test: old file moves, new file stays.
6. Correlation id: carry `trace_id` from `relay_create` into the resulting message. Test: id appears in leg, message, and ack.

Limits of these controls: dedupe by id only helps senders that set a stable id; atomic write protects against partial files, not against a lost disk. None of this was run; these are proposals with stated tests.

## Drive-thru lessons mapped to what exists

| Lesson (from the three legs' sources) | Where NouGen has it today | Gap |
|---|---|---|
| Structured state beats conversational confidence | Relay leg state machine; `relay_ack` refuses non-open legs; DavOS `scope.cjs` returns a typed verdict with a rule name. | Receiver messages have no typed state. |
| Validate before side effects | DavOS scope check runs before vfs writes (55 tests pass). | Not applied to the message path. |
| Verify the commit, not the model's acknowledgement | I verified `relay_create` results by id, `shards_capture` by recall. | `relay_create` on 409 returns an error but no read-back helper. |
| Deterministic human takeover | The operator merges, agents are blocked by the merge guard; the relay marks `needs operator word`. | No automatic takeover trigger on repeated failure. |
| Bounded, interruptible upsells | Not applicable to NouGen as built. | none |
| Measure end-to-end: latency, corrections, abandonment, takeover | Relay timestamps exist (created, acked). | No dashboard of ack latency or replay count. Cheap first metric: legs replayed after ack, per day. |
| Trusted baseline before change, validated schemas | `tools/september_ledger.py` writes a per-day shard count, a first daily baseline of shard volume. | No baseline for message latency or loss. |

