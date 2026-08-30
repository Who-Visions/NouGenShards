---
name: wake-remote-session
description: Use when you need a Claude Code session running on ANOTHER fleet machine (blade, phoebus, whoart) — waking one over SSH, reaching one that shows offline, driving its first-run prompts, or diagnosing why a launched session died seconds after start. Covers the pty/stdin requirements that make `--remote-control` work, the mDNS/DHCP name rules for reaching fleet hosts at all, and running PowerShell on a Windows peer without quoting damage. Does not cover messaging a session that is already live — that is cross-session-messaging.
---

# Waking a session on another fleet box

A session on another machine is reachable **only through Remote Control**. Same-machine
peers talk over a local socket; that socket does not cross the LAN. So "wake a session on
blade" always means: start an *interactive* Claude Code session there with
`--remote-control`, and confirm it appears in `ListAgents`.

Everything below is the cost of that one sentence.

## 0. Reach the box before anything else

Fleet boxes are on **DHCP**. A literal IP in `~/.ssh/config` rots at the next lease and
fakes a dead lane — this is exactly how blade's firewall rule went stale on 192.168.1.0/24.
Use the mDNS name; it tracks the lease.

But `.local` names resolve to **link-local IPv6** on Windows (`fe80::…%10`) and SSH dies on
those. The config needs:

```
Host *
    AddressFamily inet
```

Without it you get the maddening split where `ping blade1tb` succeeds and `ssh blade` hangs.
Confirm the lane before blaming anything downstream:

```bash
ping -4 -n 1 blade1tb                       # get the current lease
ssh -o BatchMode=yes -o ConnectTimeout=8 blade 'hostname'
```

## 1. Prove the CLI there is authenticated — before spending effort on a TUI

One cheap headless round-trip settles it. If this returns, credentials are good and every
later failure is a terminal problem, not an auth problem:

```bash
ssh blade '%USERPROFILE%\.local\bin\claude.exe -p "reply with the single word: pong"'
```

Do not read `~/.claude.json` to answer this. Parsing it for `projects` /
`hasTrustDialogAccepted` returns empty even on a machine with a full session history — it
will tell you the CLI has never run when it has. Trust the round-trip, not the config file.

Beware what `Get-Process -Name claude` shows: on a box running the desktop app you will see
a dozen `Claude.exe` processes (Electron renderers, GPU, crashpad, plus an embedded
`claude-code` worker). **None of those is a reachable CLI session.** Filter on the CLI path
under `.local\bin` or `AppData\Roaming\Claude\claude-code\`.

## 2. Running PowerShell on a Windows peer without quoting damage

The default shell over SSH on Windows is `cmd.exe`. Nesting `powershell -Command "…"`
through it destroys backticks, `$_`, and pipes — you get errors like
`'teleport' is not recognized`, where cmd has eaten your regex alternation and run a
fragment as a command.

Write the script locally, ship it base64-encoded as UTF-16LE:

```bash
cat > /tmp/probe.ps1 <<'EOF'
# real PowerShell, any quoting you like
EOF
ENC=$(iconv -f UTF-8 -t UTF-16LE /tmp/probe.ps1 | base64 -w0)
ssh blade "powershell -NoProfile -EncodedCommand $ENC"
```

`iconv` matters — `-EncodedCommand` requires UTF-16LE, not UTF-8. Strip the noise from the
reply: SSH post-quantum warnings, and `#< CLIXML` / `<Objs …>` progress objects PowerShell
emits on stderr.

Keep remote scans shallow. A recursive `Get-ChildItem -Recurse` over a home directory will
blow a two-minute timeout and tell you nothing.

## 3. The launch — why the obvious ways die

`--remote-control` starts an **interactive** session. It needs a real pty *and* a stdin that
stays open. Two failure modes, same root cause, both silent:

| Attempt | What happens |
| --- | --- |
| `Start-Process … -RedirectStandardOutput/-Error` detached | Redirected stdio is not a tty. Logs `no stdin data received in 3s`, then exits ~15s later. Process looked alive on first check. |
| `ssh -tt host 'claude --remote-control'` from a background task | Pty is fine, but the task's stdin is EOF immediately, so the session reads EOF and exits 0. Looks like a clean success. |

Both **exit 0**. Neither reports an error. Do not read a zero exit as a live session —
`ListAgents` is the only proof.

The recipe that works keeps stdin open with a file you can also type into:

```bash
: > /tmp/blade_stdin.txt
tail -f /tmp/blade_stdin.txt | ssh -tt -o ServerAliveInterval=30 blade \
  'cd /d %USERPROFILE%\Outpost && %USERPROFILE%\.local\bin\claude.exe --remote-control <name>'
```

Run it as a background task. `tail -f` holds the pipe open forever, and every byte appended
to that file is a keystroke delivered to the remote TUI.

## 4. Driving the first-run prompts blind

A fresh workspace stops at **"Is this a project you created or one you trust?"**, default
`No, exit`. Send `Down`, verify the caret moved, then `Enter` — never both at once:

```bash
printf '\033[B' >> /tmp/blade_stdin.txt     # then re-read the log and confirm
printf '\r'     >> /tmp/blade_stdin.txt
```

**Read the TUI with the escape sequences stripped, and expect no spaces.** Cursor-positioning
codes carry the spacing, so stripping CSI collapses the text to
`❯No,exitYes,ItrustthisfolderEntertoconfirm`. A wait-loop grepping for `"trust this folder"`
will never match and will spin until it times out. Grep a single word.

```bash
sed -e 's/\x1b\[[0-9;?]*[a-zA-Z]//g' -e 's/\r//g' "$LOG" | tail -c 400
```

Success looks like a status line: `⏵⏵ auto mode on … /rc active`.

**The trust gate is the operator's call, not yours.** It is a security prompt written for a
human. Answering it for their own directory on their own machine is within a "wake a session
there" instruction — but say plainly that you did, and note that the folder stays trusted for
every later session. If the box has no trusted folder to fall back to, there is no way around
it; do not go edit `hasTrustDialogAccepted` to make the prompt disappear.

## 5. Confirm, then say what will kill it

Verify by name in `ListAgents` — it should read `<name> · Remote Control · idle`. Then be
honest about lifetime: **the session lives only as long as the SSH pty that parented it.**
When your session ends, that background task dies, the pty closes, and the peer goes offline.
That is the reason a fleet listing fills with dozens of offline `blade1tb-*` rows.

### Making it survive — the launcher goes on the CALLING side

The obvious fix is wrong. A scheduled task **on the target** does not work: it starts, gets
a real `conhost`, the process stays alive — and the TUI never initializes. No session file
is written, nothing registers, and the process just sits there. Verified on blade
2026-08-29, both with and without `--resume`, so the resume flag is not the cause. A
scheduled task's console is not a usable terminal for the TUI, and because the process
survives and the task reports `Running`, this failure looks exactly like success.

The pty that matters is the one **`ssh -tt` allocates on the target**. The launcher itself
therefore never needs a console — which means it can be an ordinary scheduled task *on the
calling machine*, wrapping the same `tail -f | ssh -tt` chain:

```
Action:    C:\Program Files\Gitinash.exe
Argument:  -lc "$HOME/Outpost/NouGen/tools/blade_lane.sh blade-lane"
Trigger:   AtLogOn      Principal: Interactive, RunLevel Limited
Settings:  ExecutionTimeLimit 0, RestartCount 3, MultipleInstances IgnoreNew
```

Working implementation: `NouGen/tools/blade_lane.sh` (whoart task `NouGenBladeLane`). It
logs to `~/.nougen/<name>.log` — which is also how you read the remote TUI after the fact.

**The restart loop needs a FIFO, not a pipe.** The obvious form deadlocks:

```sh
while true; do
  tail -f "$STDIN" | ssh -tt host '…'   # WRONG: loop can never run twice
  sleep 15
done
```

When ssh dies, `tail` is blocked waiting on a file that is not changing, so it never takes
SIGPIPE. The pipeline never returns, the loop never iterates, and the lane stays down while
the launcher still looks healthy. Verified by killing the ssh: lane went offline and the log
recorded no exit line at all — the giveaway is a `starting` marker with no matching `exited`.

Route the tail through a FIFO so ssh is the foreground process and its exit is observable:

```sh
mkfifo "$PIPE"
tail -f "$STDIN" > "$PIPE" &
TAILPID=$!
ssh -tt host '…' < "$PIPE"
kill "$TAILPID"; rm -f "$PIPE"
```

MSYS/Git-Bash FIFOs do work with native `ssh.exe` here — confirmed, the lane connects and
`exited rc=0, restarting in 15s` now fires.

Confirm success by the log reaching `/rc active` plus the session URL, then by the name in
`ListAgents`. **Grep the log for markers, not for TUI text** — the status bar is redrawn in
fragments, so `/rc active` can appear split across cursor moves and a naive count will read
zero on a lane that is up. `ListAgents` settles it.

Killing a stale lane: match the ssh by command line, not by parent PID. The pipeline puts
intermediate subshells between the launcher's bash and ssh, so a `parent is my bash` test
marks the LIVE ssh an orphan and kills the thing you were keeping. Two rows with the same
name in `ListAgents` means a previous run is still holding the name — expect it after any
launcher edit. A **fresh** session starts here; the prior thread is still on disk on the
target and resumes from inside with `/resume`.

## Checklist

1. `ping -4` the mDNS name; `ssh` with `AddressFamily inet`
2. `claude -p 'pong'` — auth proven, or stop here
3. `tail -f <stdin-file> | ssh -tt host 'claude --remote-control <name>'` as a background task
4. Strip ANSI, grep one word, `Down` → verify → `Enter`
5. `ListAgents` for the name — nothing else counts as proof
6. Report the trust answer and the SSH-parented lifetime
7. To make it durable: scheduled task on the CALLING box wrapping the ssh chain — never a
   scheduled task on the target, which looks alive and registers nothing
