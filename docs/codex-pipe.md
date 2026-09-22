# Codex message pipe

Local endpoint: `\\.\pipe\LOCAL\nougen-msg-codex`.

`nougenmsg @codex "message"` now sends JSON over this pipe. The receiver saves the
message, calls the installed native `codex.exe queue --thread UUID --message TEXT`,
and returns its queue receipt. The message remains in the unread Codex inbox
whether queueing succeeds or fails; queue acceptance wakes the thread but is
not proof of model consumption, so only an explicit acknowledgement may archive it. No message text
is passed through a shell. The pipe permits its owner and rejects remote clients.

```powershell
# From Outpost\NouGen; supply the intended Codex thread UUID.
.\tools\start_codex_pipe.ps1 -Action start -Thread '<session UUID>'
.\tools\start_codex_pipe.ps1 -Action status
python .\tools\nougenmsg.py '@codex' 'Hello Codex'
.\tools\start_codex_pipe.ps1 -Action stop
```

When launched within Codex, `-Thread` defaults to `CODEX_THREAD_ID`. One receiver
targets one explicit session. It never guesses the latest session or broadcasts
to all Codex sessions. Stop and start explicitly to change the target. It stays
running after the launching shell exits; start it again after a machine restart.
Logs from the launcher are in `~/.nougen/logs/codex-pipe.*.log`.

Status `queued` means the Codex queue accepted the message. It does not establish
that the model consumed it, so `delivery_verified` remains false and the durable
copy remains unread with `retained_until_ack: true`. Status `saved`
means inspect `error` and the preserved inbox file. Repeated sends are separate
messages. Payloads over 24,000 UTF-8 JSON bytes fall back to the inbox. A transport
failure after acceptance can leave a fallback copy; do not blindly resend.

The native queue command was checked against the installed CLI help. The broader
session interface is described in https://developers.openai.com/codex/app-server/.
No new model process, remote listener, fleet deployment, or permission bypass is
configured by this adapter.

## Auditing a live round trip

`tools/codex_roundtrip_audit.py` is a read-only evidence checker. It takes a
unique message marker, the intended Codex thread UUID, the Antigravity session's
`transcript_full.jsonl`, and the Codex inbox archive. It reports these gates
separately: model consumed the marker, native `codex_pipe.deliver()` was invoked
for the intended thread, the adapter emitted `queue_accepted: true`, and a
matching Codex payload was archived. An optional `--codex-received` JSON
envelope establishes receiver-side arrival only when its sender, target, thread,
and marker all match.

```sh
python3 tools/codex_roundtrip_audit.py \
  --marker 'UNIQUE-ROUNDTRIP-MARKER' \
  --thread '<intended Codex thread UUID>' \
  --agy-transcript "$HOME/.gemini/antigravity/brain/<agy-session>/.system_generated/logs/transcript_full.jsonl"
```

Exit 0 means the active Codex receipt was supplied and matched. Exit 2 means
the observed chain is incomplete or only queued. A hand-written ACK file,
transport echo, or inbox write cannot satisfy the native-adapter and receiver
gates by itself. The tool never sends traffic or mutates inboxes, shards, or
daemons; its output is evidence, not a cryptographic attestation.
