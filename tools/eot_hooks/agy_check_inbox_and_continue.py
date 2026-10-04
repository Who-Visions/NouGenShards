#!/usr/bin/env python3
"""Antigravity end-of-turn check hook: check inbox and continue work.

Hooks into PostInvocation / Stop events in Antigravity.
Checks ~/.nougen/agy_inbox for incoming unread messages or relay legs.
Maintains its own end-of-turn cursor (~/.nougen/state/agy_eot_cursor.json)
so that PreInvocation drains do not clear the work before end-of-turn evaluates it.

If unread inbox items exist:
- In PostInvocation: returns terminationBehavior="force_continue" and injectSteps with the notification.
- In Stop: returns decision="continue" and reason prompt directing the agent to inspect inbox and continue work.
When all inbox work has been processed, updates cursor and exits cleanly allowing normal stop.
"""
import json
import os
import socket
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
OBSERVATORY = Path(os.environ.get("NOUGEN_OBSERVATORY", str(HOME / "The Observatory")))
INBOX = Path(os.environ.get("NOUGEN_AGY_INBOX", str(HOME / ".nougen" / "agy_inbox")))
EOT_CURSOR = Path(os.environ.get("NOUGEN_AGY_EOT_CURSOR", str(HOME / ".nougen" / "state" / "agy_eot_cursor.json")))
SEEN_LEGS = Path(os.environ.get("NOUGEN_AGY_SEEN_LEGS", str(HOME / ".nougen" / "state" / "agy_eot_seen_legs.json")))
DEBUG_LOG = HOME / ".nougen" / "state" / "hook_debug.log"
MAX_SHOWN = 5
MAX_TEXT = 300
MAX_SEEN_LEGS = 500  # rolling window to prevent unbounded growth


def _load_codex_pipe():
    """Import the pipe adapter as a package so its relative imports resolve."""
    import importlib
    import sys

    source_roots = (
        HOME / ".nougen" / "src",
        HOME / ".nougen" / "src" / "nougenshards" / "src",
        Path(__file__).resolve().parents[2] / "src",
    )
    for source_root in source_roots:
        if (source_root / "nougen_shards" / "codex_pipe.py").is_file():
            source_root = str(source_root)
            if source_root not in sys.path:
                sys.path.insert(0, source_root)
            break
    return importlib.import_module("nougen_shards.codex_pipe")


def _log(event: dict, out: dict) -> None:
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.time()}: payload={json.dumps(event)} out={json.dumps(out)}\n")
    except Exception:
        pass


def _read_cursor() -> float:
    try:
        return float(json.loads(EOT_CURSOR.read_text(encoding="utf-8")).get("mtime", 0))
    except Exception:
        return 0.0


def _write_cursor(mtime: float) -> None:
    try:
        EOT_CURSOR.parent.mkdir(parents=True, exist_ok=True)
        EOT_CURSOR.write_text(json.dumps({"mtime": mtime}), encoding="utf-8")
    except Exception:
        pass



def _read_seen_legs() -> set:
    try:
        return set(json.loads(SEEN_LEGS.read_text(encoding="utf-8")).get("legs", []))
    except Exception:
        return set()


def _write_seen_legs(seen: set) -> None:
    try:
        SEEN_LEGS.parent.mkdir(parents=True, exist_ok=True)
        # Keep only the most recent MAX_SEEN_LEGS entries (sorted for stability)
        trimmed = sorted(seen)[-MAX_SEEN_LEGS:]
        SEEN_LEGS.write_text(json.dumps({"legs": trimmed}), encoding="utf-8")
    except Exception:
        pass

def _check_unread_inbox() -> tuple[list[str], float]:
    if not INBOX.is_dir():
        return [], 0.0
    cursor = _read_cursor()
    cursor_resolved = EOT_CURSOR.resolve() if EOT_CURSOR.exists() else None

    try:
        entries = sorted(
            (
                p for p in INBOX.iterdir()
                if p.is_file()
                and p.name.endswith(".json")
                and (cursor_resolved is None or p.resolve() != cursor_resolved)
                and p.stat().st_mtime > cursor
            ),
            key=lambda p: p.stat().st_mtime,
        )
    except Exception:
        return [], 0.0

    if not entries:
        return [], 0.0

    latest_mtime = max(p.stat().st_mtime for p in entries)
    seen_legs = _read_seen_legs()
    messages = []
    new_leg_ids = set()
    for p in entries[-MAX_SHOWN:]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            leg = data.get("leg_id")
            # Skip if we've already surfaced this exact leg_id
            if leg and leg in seen_legs:
                continue
            if leg:
                new_leg_ids.add(leg)
            text = str(data.get("text") or "").strip()
            if len(text) > MAX_TEXT:
                text = text[:MAX_TEXT].rstrip() + "…"
            sender = data.get("sender") or "unknown"
            if leg:
                messages.append(f"[Leg {leg}] via {sender}: {text}")
            else:
                messages.append(f"[{sender}]: {text}")
        except Exception:
            messages.append(f"[Unparseable] {p.name}")
    # Persist newly seen leg_ids
    if new_leg_ids:
        _write_seen_legs(seen_legs | new_leg_ids)
    return messages, latest_mtime


def _broadcast_to_blade():
    """Emit turn sync to Blade sessions over MsgNode and named pipes (background/non-blocking)."""
    try:
        ts = datetime.now(timezone.utc).isoformat()
        msg_text = f"[Antigravity Turn Sync @ {ts}] Phoebus online. Shards synchronized. Token Governor active."
        # 1. Local MsgNode
        nougen_cli = str(OBSERVATORY / "NouGen" / "nougenshards" / ".venv" / "bin" / "nougen")
        if os.path.exists(nougen_cli):
            subprocess.Popen([nougen_cli, "msg", "emit", "--all", msg_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 2. Remote Blade named pipes over SSH
        ps_script = f"""
$msg = @{{
    sender = 'phoebus/antigravity'
    target = 'blade/sessions'
    text = '{msg_text}'
    timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
}} | ConvertTo-Json -Compress

$pipes = [System.IO.Directory]::GetFiles('\\\\.\\pipe\\') | Where-Object {{ $_ -match 'LOCAL\\\\cc-msg-' }}
foreach ($p in $pipes) {{
    try {{
        $pName = $p.Replace('\\\\.\\pipe\\', '')
        $client = New-Object System.IO.Pipes.NamedPipeClientStream('.', $pName, [System.IO.Pipes.PipeDirection]::Out)
        $client.Connect(150)
        $sw = New-Object System.IO.StreamWriter($client)
        $sw.WriteLine($msg)
        $sw.Flush()
        $client.Close()
    }} catch {{}}
}}
"""
        import base64
        enc = base64.b64encode(ps_script.encode('utf-16le')).decode('ascii')
        target, key_path = _pipe_forward_target()
        if not target:
            return  # no forward target configured for this node
        cmd = ["ssh"] + (["-i", key_path] if key_path else []) + [
            "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=2",
            target, "powershell", "-NoProfile", "-EncodedCommand", enc,
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _pipe_forward_target() -> tuple[str, str]:
    """SSH target (user@host) and optional key for forwarding a wake to a peer's pipe.

    Env NOUGEN_PIPE_FORWARD_SSH / NOUGEN_PIPE_FORWARD_KEY, else the untracked
    ~/.nougen/pipe_forward.json {"ssh": "...", "key": "..."}. Unset = no forward.
    """
    target = os.environ.get("NOUGEN_PIPE_FORWARD_SSH", "")
    key = os.environ.get("NOUGEN_PIPE_FORWARD_KEY", "")
    if not target:
        try:
            cfg = json.loads((HOME / ".nougen" / "pipe_forward.json").read_text(encoding="utf-8"))
            target, key = cfg.get("ssh", ""), key or cfg.get("key", "")
        except Exception:
            pass
    return target, os.path.expanduser(key) if key else ""


def _check_active_my_claims() -> list[str]:
    """Check if this machine or agent has active declared lane claims."""
    claims_dirs = [
        Path.home() / "Outpost" / "NouGenRelay" / ".handoffs" / "claims",
        Path.home() / "Watchtower" / "NouGen" / "NouGenRelay" / ".handoffs" / "claims",
        Path.home() / ".nougen" / "claims",
    ]
    my_claims = []
    my_host = socket.gethostname().lower()
    for cdir in claims_dirs:
        # Windows refuses to traverse untrusted mount points (WinError 448);
        # an unreadable claims dir is skipped, never allowed to crash Stop.
        try:
            if not cdir.is_dir():
                continue
            claim_files = list(cdir.glob("*.json"))
        except OSError:
            continue
        for f in claim_files:
            try:
                c = json.loads(f.read_text(encoding="utf-8"))
                if c.get("status") != "active":
                    continue
                ag = str(c.get("agent", "")).lower()
                mach = str(c.get("machine", "")).lower()
                if ag in ("antigravity", "phoebus") or mach in ("phoebus", my_host):
                    my_claims.append(f"[{mach}/{ag}] Scope: {c.get('scope')} | Goal: {c.get('goal')}")
            except Exception:
                continue
    return my_claims


def main() -> int:
    # --- AUTOMATED EVERY-TURN CODEX BEACON ---
    try:
        import sys, json, types, time
        for mod_name in ['numpy', 'sqlalchemy']:
            if mod_name not in sys.modules:
                m = types.ModuleType(mod_name)
                if mod_name == 'numpy': m.ndarray = object
                elif mod_name == 'sqlalchemy':
                    m.create_engine = lambda *a, **k: None
                    m.text = lambda *a, **k: None
                sys.modules[mod_name] = m
        codex_pipe = _load_codex_pipe()
        ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        codex_pipe.deliver(f'AUTOMATED EVERY-TURN BEACON [{ts}]: Antigravity turn completed.', origin={'original_sender': 'phoebus/antigravity'}, thread_id='01a0ab83-b0ec-7180-a52f-7933296fd704')
    except Exception:
        pass
    # ------------------------------------------

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    # Broadcast turn status to Blade sessions on every turn completion
    _broadcast_to_blade()

    unread, latest_mtime = _check_unread_inbox()
    active_claims = _check_active_my_claims()
    is_stop_event = "terminationReason" in payload or "fullyIdle" in payload

    if unread or active_claims:
        sections = []
        if unread:
            sections.append("Unread fleet inbox messages/claims detected at end of turn:\n" + "\n".join(f"- {msg}" for msg in unread))
        if active_claims:
            sections.append("Active declared lane claims requiring execution:\n" + "\n".join(f"- {claim}" for claim in active_claims))

        prompt_reason = (
            "🚨 [HARDCADE CLAIM & WORK ENFORCEMENT ACTIVE]\n"
            "MANDATE: If any message represents a claim, relay leg, or assigned task, you MUST execute the substantive physical engineering work immediately (write code, run tests, land artifacts).\n"
            "Under NO circumstances may you stop or respond with a bare acknowledgment. FINISH THE WORK:\n"
            + "\n\n".join(sections)
        )
        if unread:
            _write_cursor(latest_mtime)
        if is_stop_event:
            out = {
                "decision": "continue",
                "reason": prompt_reason
            }
        else:
            out = {
                "injectSteps": [
                    {"ephemeralMessage": prompt_reason}
                ],
                "terminationBehavior": "force_continue"
            }
    else:
        if is_stop_event:
            # Trigger detached, non-blocking Emma end-of-turn dynamic announcement
            try:
                speak_script = HOME / "The Observatory" / "NouGen" / "speak.py"
                transcript_path = payload.get("transcriptPath")
                announcement = "Turn complete" + (f", {os.environ['NOUGEN_OPERATOR_NAME']}" if os.environ.get("NOUGEN_OPERATOR_NAME") else "") + ". Standing by."

                # Dynamically extract the last meaningful conclusion from the actual assistant response
                if transcript_path and os.path.isfile(transcript_path):
                    try:
                        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as tf:
                            lines = tf.readlines()
                            for line in reversed(lines):
                                try:
                                    entry = json.loads(line)
                                    if entry.get("type") == "PLANNER_RESPONSE" and entry.get("content"):
                                        c = entry["content"].strip()
                                        # Grab the last paragraph or sentence
                                        paragraphs = [p.strip() for p in c.split("\n\n") if p.strip() and not p.strip().startswith("```") and not p.strip().startswith("#")]
                                        if paragraphs:
                                            last_p = paragraphs[-1].replace("*", "").replace("`", "").strip()
                                            # Clean markdown and keep it punchy (1-2 sentences)
                                            sentences = [s.strip() for s in last_p.split(".") if s.strip()]
                                            if sentences:
                                                candidate = sentences[-1] if len(sentences[-1]) > 15 else (sentences[-2] + ". " + sentences[-1] if len(sentences) > 1 else sentences[0])
                                                if len(candidate) > 10:
                                                    announcement = candidate[:140].strip()
                                                    if not announcement.endswith("."):
                                                        announcement += "."
                                            break
                                except Exception:
                                    continue
                    except Exception:
                        pass

                if speak_script.is_file():
                    subprocess.Popen(
                        [sys.executable, str(speak_script), announcement],
                        env={**os.environ, "NOUGEN_VOICE": os.environ.get("NOUGEN_VOICE") or "af_river", "NOUGEN_SPEED": "1.05"},
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
            except Exception:
                pass

            out = {
                "decision": "allow"
            }
        else:
            out = {
                "injectSteps": [],
                "terminationBehavior": ""
            }

    _log(payload, out)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
