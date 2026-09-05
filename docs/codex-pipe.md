# Codex message pipe

Local endpoint: `\\.\pipe\LOCAL\nougen-msg-codex`.

`nougenmsg @codex "message"` now sends JSON over this pipe. The receiver saves the
message, calls the installed native `codex.exe queue --thread UUID --message TEXT`,
and returns its queue receipt. The message remains in the unread Codex inbox if
queueing fails; accepted messages move to the inbox's archive. No message text
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
that the model consumed it, so `delivery_verified` remains false. Status `saved`
means inspect `error` and the preserved inbox file. Repeated sends are separate
messages. Payloads over 24,000 UTF-8 JSON bytes fall back to the inbox. A transport
failure after acceptance can leave a fallback copy; do not blindly resend.

The native queue command was checked against the installed CLI help. The broader
session interface is described in https://developers.openai.com/codex/app-server/.
No new model process, remote listener, fleet deployment, or permission bypass is
configured by this adapter.
