#!/usr/bin/env python3
"""
Antigravity & Fleet Cross-Session Messaging CLI (`agy msg` / `nougenmsg`).
Delivers structured live-pings and IPC messages across agents and nodes.
"""
import sys
import os
import base64
import json
import time
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nougen_shards.nougenmsg import NouGenMsgBus, get_current_node, resolve_session

def print_help():
    print("""
🛰️ Antigravity Fleet Messaging (`agy msg` / `nougenmsg`)

Usage:
  agy msg "<message>"                         Broadcast to all agents across entire fleet
  agy msg @blade "<message>"                  Send to all agents on Blade (Apollo)
  agy msg @blade:antigravity "<message>"      Send to Antigravity on Blade
  agy msg @claude "<message>"                 Send to local Claude Code named pipes
  agy msg @antigravity "<message>"            Send to local Antigravity inbox
  agy msg @codex "<message>"                  Send to local OpenAI Codex inbox
  agy msg @phoebus "<message>"                Send to Phoebus (Mac Mini)
  agy msg --session-id ID --lane codex "<message>"  Attach session provenance

Inspection & Discovery:
  agy msg --peers                             List discovered local pipes and reachable nodes
  agy msg --inbox [--target <antigravity|codex>] Read recent unread messages in inbox
  agy msg --clear-inbox                       Archive and clear read inbox messages
  agy msg --help                              Show this help menu
""")

# Fleet house style: every message opens with a [NODE / AGENT] banner and each
# "Key: text" line carries a status glyph. Hand-typing this per send is what
# produced flat prose on the wire (GM, 2026-09-08). Keys resolve env -> default
# so a lane can extend the vocabulary without touching code: set
# NOUGEN_MSG_EMOJI_MAP to a JSON object of {"key": "glyph"}. Pass --raw to send
# text exactly as typed.
_DEFAULT_EMOJI = {
    "incident": "\U0001F534", "alert": "\U0001F534", "outage": "\U0001F534",
    "root cause": "\U0001F3AF", "cause": "\U0001F3AF", "finding": "\U0001F3AF",
    "fix": "\U0001F527", "patch": "\U0001F527", "now": "\U0001F527", "change": "\U0001F527",
    "restart": "♻️", "deploy": "♻️",
    "proof": "✅", "verified": "✅", "done": "✅", "ok": "✅", "alive": "✅",
    "relay": "\U0001F4E1", "leg": "\U0001F4E1", "handoff": "\U0001F4E1",
    "open": "⚠️", "warn": "⚠️", "risk": "⚠️", "still open": "⚠️",
    "blocked": "⛔", "blocker": "⛔",
    "ask": "\U0001F64B", "need": "\U0001F64B", "needs": "\U0001F64B",
    "lesson": "\U0001F4D8", "status": "\U0001F4CA", "next": "➡️",
    "ping": "\U0001F3D3", "pong": "\U0001F3D3", "ack": "\U0001F3D3",
    "lane": "\U0001F6E4️", "claim": "\U0001F6E4️",
}
_BANNER_GLYPH = "\U0001F6F0️"


def _emoji_map() -> dict:
    table = dict(_DEFAULT_EMOJI)
    raw = os.environ.get("NOUGEN_MSG_EMOJI_MAP", "").strip()
    if raw:
        try:
            table.update({str(k).lower(): str(v) for k, v in json.loads(raw).items()})
        except (ValueError, AttributeError):
            print("[!] NOUGEN_MSG_EMOJI_MAP is not a JSON object; using the default glyph table",
                  file=sys.stderr)
    return table


def resolve_agent_label() -> str:
    """Which agent is speaking: NOUGEN_AGENT, else the lane, else a logged fallback."""
    label = os.environ.get("NOUGEN_AGENT") or os.environ.get("NOUGEN_LANE")
    if label:
        return label
    print("[i] NOUGEN_AGENT unset; banner labels this sender 'claude-cli' (fallback)",
          file=sys.stderr)
    return "claude-cli"


def house_style(text: str, node: str, agent: str, session_id: str = "") -> str:
    """Decorate a plain message into the fleet banner format.

    Lines already carrying a glyph (first char outside ASCII) or a [TAG] are
    left untouched, so a hand-formatted message round-trips unchanged and
    re-sending a received message does not double-decorate it.
    """
    table = _emoji_map()
    lines = [ln for ln in (text.splitlines() or [text]) if ln.strip()]
    # A bare one-liner with no "Key:" prefix is a nudge, not a report. It goes
    # out exactly as typed so quick pings and the existing CLI contract stay
    # byte-identical; decoration is for structured multi-line traffic.
    if len(lines) == 1:
        key, sep, rest = lines[0].strip().partition(":")
        if not (sep and rest.strip() and key.strip().lower() in table):
            return text
    # Already decorated (first line carries a glyph or [TAG]): pass through so a
    # forwarded or re-sent banner is never wrapped in a second banner.
    head = lines[0].strip()
    if ord(head[0]) > 0x7F or head.startswith("["):
        return "\n".join(ln.strip() for ln in lines)

    # Layout: HEADER (who, when) / SUBJECT (first line) / BODY (status lines,
    # then free text). Rule width is env-tunable for narrow terminals.
    try:
        width = int(os.environ.get("NOUGEN_MSG_RULE_WIDTH", "30"))
    except ValueError:
        width = 30
    # Dynamic terminal auto-scaling & textwrap hanging indents
    import shutil
    import textwrap
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    width = max(30, min(cols - 2, 72)) if not os.environ.get("NOUGEN_MSG_RULE_WIDTH") else width
    heavy, light = "━" * width, "─" * width
    stamp = time.strftime("%Y-%m-%d %H:%M %z")
    # Session id in the header (GM, 2026-09-08 14:10 EDT): two sessions on
    # one host both built --dry-run in the same hour, each banner just said
    # "whoart". Host and lane identify a machine; the session identifies who
    # is typing. Short form only; the full id rides in the payload.
    sess = resolve_session()
    who = f"{node.upper()} / {agent.upper()}"
    if sess:
        who += f" / sess {str(sess)[:8]}"

    status: list[str] = []
    free: list[str] = []
    for line in lines[1:]:
        s = line.strip()
        if ord(s[0]) > 0x7F:
            status.append(s)
            continue
        key, sep, rest = s.partition(":")
        k = key.strip().lower()
        if sep and rest.strip() and k in table:
            prefix = f"{table[k]} {key.strip()}: "
            sub_indent = " " * max(len(prefix) - 1, 4)
            wrapped = textwrap.fill(rest.strip(), width=width, initial_indent=prefix, subsequent_indent=sub_indent)
            status.append(wrapped)
        else:
            wrapped = textwrap.fill(s, width=width, initial_indent="• ", subsequent_indent="  ")
            free.append(wrapped)

    out = [f"{_BANNER_GLYPH} {who}  ·  {stamp}", heavy,
           f"\U0001F4CC {head}"]
    if status or free:
        out.append(light)
    out.extend(status)
    if status and free:
        out.append(light)
    out.extend(free)
    return "\n".join(out)


def print_inline_banner(title: str, results: Any, message_text: str = "") -> None:
    border = "=" * 68
    print(f"\n{border}")
    print(f"🛰️  {title}")
    print(border)
    if message_text:
        preview = (message_text[:76] + "...") if len(message_text) > 76 else message_text
        print(f'💬 Message: "{preview}"')
        print("-" * 68)

    if isinstance(results, dict):
        for key, val in results.items():
            if isinstance(val, dict):
                if any(k in val for k in ["status", "delivered", "pipe_delivered", "file"]):
                    status = val.get("status") or ("delivered" if val.get("delivered") else None) or ("online" if val.get("ok") else "unknown")
                    icon = "✅" if status in ["delivered", "queued", "online"] else ("⚠️" if status == "dropped" else "❌")
                    pipe_info = " (Pipe: Active)" if val.get("pipe_delivered") else " (Inbox: Synced)"
                    receipt = val.get("receipt", "")
                    receipt_str = f" | {receipt[:40]}..." if receipt else ""
                    print(f"  {icon} {key.upper():<12} -> Status: {status.upper()}{pipe_info}{receipt_str}")
                else:
                    print(f"  🌐 Node [{key.upper()}]:")
                    for a_k, a_v in val.items():
                        if isinstance(a_v, dict):
                            st = a_v.get("status") or ("delivered" if a_v.get("delivered") else None) or "unknown"
                            ic = "✅" if st in ["delivered", "queued", "online"] else ("⚠️" if st == "dropped" else "❌")
                            p_info = " [Pipe: Active]" if a_v.get("pipe_delivered") else " [Inbox: Synced]"
                            rc = a_v.get("receipt", "")
                            rc_str = f" | {rc[:30]}..." if rc else ""
                            print(f"      {ic} {a_k:<12} -> {st.upper()}{p_info}{rc_str}")
                        else:
                            print(f"      • {a_k}: {a_v}")
            else:
                print(f"  • {key}: {val}")
    else:
        print(f"  {results}")
    print(f"{border}\n")

def main():
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        return

    # Discovery
    if "--capabilities" in sys.argv:
        # Probed over ssh by NouGenMsgBus.emit_node to decide whether this
        # receiver can take a base64 body inline instead of an scp'd file.
        print("nougenmsg-capabilities: text-b64")
        return

    if "--peers" in sys.argv or "--list-peers" in sys.argv or "--list-pipes" in sys.argv:
        peers = NouGenMsgBus.list_peers()
        print(f"\n📡 Discovered Peers on Node: [{peers['current_node'].upper()}]")
        print(f"  • Claude Active Pipes: {len(peers['claude_active_pipes'])}")
        for p in peers['claude_active_pipes']:
            print(f"      - {p}")
        print(f"  • Antigravity Active Pipes: {len(peers.get('antigravity_active_pipes', []))}")
        for p in peers.get('antigravity_active_pipes', []):
            print(f"      - {p}")
        print(f"  • Antigravity Inbox Unread: {peers['antigravity_inbox_unread']} message(s)")
        print(f"  • Codex Inbox Unread:       {peers['codex_inbox_unread']} message(s)")
        print(f"  • Reachable Nodes:          {', '.join(peers['nodes_reachable'])}\n")
        return

    # Inbox reader
    if "--inbox" in sys.argv or "--read-inbox" in sys.argv:
        target = "antigravity"
        if "--target" in sys.argv:
            idx = sys.argv.index("--target")
            if idx + 1 < len(sys.argv):
                target = sys.argv[idx + 1]
        msgs = NouGenMsgBus.read_inbox(target=target)
        border = "=" * 68
        print(f"\n{border}")
        print(f"📬  INBOX: [{target.upper()}] ({len(msgs)} messages)")
        print(border)
        if not msgs:
            print("  (inbox is empty)")
        else:
            for m in msgs:
                ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m.get('timestamp', time.time())))
                # sender is WHO spoke (a model lane sets it to "ollama:<model>");
                # source is only the host that wrote the file.
                src = m.get('sender') or m.get('source') or 'unknown'
                dom = f" [{m.get('domain')}]" if m.get('domain') else ""
                print(f"  • [{ts_str}] From: @{src}{dom}")
                print(f"    └─ {m.get('text')}")
        print(f"{border}\n")
        return

    # Clear inbox
    if "--clear-inbox" in sys.argv:
        target = "antigravity"
        if "--target" in sys.argv:
            idx = sys.argv.index("--target")
            if idx + 1 < len(sys.argv):
                target = sys.argv[idx + 1]
        archived = NouGenMsgBus.clear_inbox(target=target)
        print(f"[OK] Archived {archived} message(s) from {target} inbox.")
        return

    # Parse arguments
    args = sys.argv[1:]
    node = None
    target_agent = "all"
    origin = {}

    # Accept the `send --target-node X --target-agent Y --text ...` shape.
    #
    # Callers across the fleet emit it, but this CLI had no `send` verb and did
    # not know --target-node/--target-agent, so the whole command line fell
    # through to the positional join and was delivered VERBATIM AS THE MESSAGE
    # BODY -- routing flags and all -- to every agent instead of the one
    # addressed. Measured 2026-09-05 across the four inboxes: 97 of 1136
    # messages, 8% of fleet traffic, misrouted this way.
    #
    # The `send` token is only consumed when a flag from that shape follows, so
    # a message that legitimately begins with the word "send" is untouched.
    if args and args[0] == "send" and any(
            flag in args for flag in ("--target-node", "--target-agent", "--text")):
        args = args[1:]

    for flag, field in (("--target-node", "node"), ("--target-agent", "agent")):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 >= len(args):
                print(f"[!] Error: {flag} requires a value.")
                return
            if field == "node":
                node = args[idx + 1]
            else:
                target_agent = args[idx + 1]
            args = [value for pos, value in enumerate(args)
                    if pos not in (idx, idx + 1)]

    # --text takes the whole remainder as the body, so an unquoted message
    # keeps its spaces instead of being re-split.
    explicit_text = None
    if "--text" in args:
        idx = args.index("--text")
        explicit_text = " ".join(args[idx + 1:]).strip()
        args = args[:idx]

    for flag, field in (("--session-id", "session_id"),
                        ("--session-title", "session_title"),
                        ("--sender", "original_sender"),
                        ("--lane", "lane")):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 >= len(args):
                print(f"[!] Error: {flag} requires a value.")
                return
            origin[field] = args[idx + 1]
            args = [value for pos, value in enumerate(args)
                    if pos not in (idx, idx + 1)]
    if "--origin-b64" in args:
        idx = args.index("--origin-b64")
        if idx + 1 >= len(args):
            print("[!] Error: --origin-b64 requires a value.")
            return
        encoded = args[idx + 1]
        try:
            padding = "=" * (-len(encoded) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(encoded + padding))
            if isinstance(decoded, dict):
                origin.update(decoded)
        except (ValueError, json.JSONDecodeError):
            print("[!] Error: invalid origin envelope.")
            return
        args = [value for pos, value in enumerate(args)
                if pos not in (idx, idx + 1)]

    forced_text = None
    if "--text-b64" in args:
        idx = args.index("--text-b64")
        if idx + 1 >= len(args):
            print("[!] Error: --text-b64 requires a value.")
            return
        encoded = args[idx + 1]
        try:
            padding = "=" * (-len(encoded) % 4)
            forced_text = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            print("[!] Error: invalid --text-b64 payload.")
            return
        args = [value for pos, value in enumerate(args)
                if pos not in (idx, idx + 1)]

    origin.setdefault("session_id", os.environ.get("NOUGEN_SESSION_ID"))
    origin.setdefault("session_title", os.environ.get("NOUGEN_SESSION_TITLE"))
    origin.setdefault("lane", os.environ.get("NOUGEN_LANE"))

    # Check for @destination token
    raw_text = False
    cleaned_args = []
    for a in args:
        if a.startswith("@") and not node:
            n, ag = NouGenMsgBus.parse_destination(a)
            node = n
            target_agent = ag
        elif a == "--local":
            node = "local"
        elif a == "--raw":
            raw_text = True
        else:
            cleaned_args.append(a)

    if "--target" in cleaned_args:
        idx = cleaned_args.index("--target")
        if idx + 1 < len(cleaned_args):
            target_agent = cleaned_args[idx + 1]
            cleaned_args = [x for i, x in enumerate(cleaned_args) if i not in (idx, idx + 1)]

    # Precedence: an encoded body wins, then an explicit --text, then whatever
    # positional words are left.
    if forced_text is not None:
        text = forced_text
    elif explicit_text is not None:
        text = explicit_text
    else:
        text = " ".join(cleaned_args).strip()
    if not text:
        print("[!] Error: No message text provided.")
        print_help()
        return

    curr = get_current_node()
    if not raw_text:
        text = house_style(text, curr, resolve_agent_label())
    if not node or node == "fleet":
        res = NouGenMsgBus.emit_fleet(text=text, target=target_agent, origin=origin)
        print_inline_banner(f"FLEET BROADCAST: {curr.upper()} -> {target_agent.upper()}", res, text)
    elif node in ["local", curr]:
        res = NouGenMsgBus.live_ping(target=target_agent, text=text, origin=origin)
        print_inline_banner(f"LOCAL LIVE-PING: {curr.upper()} -> {target_agent.upper()}", res, text)
    else:
        res = NouGenMsgBus.emit_node(node=node, target=target_agent, text=text, origin=origin)
        print_inline_banner(f"NODE DISPATCH: {curr.upper()} -> {node.upper()} ({target_agent.upper()})", res, text)

if __name__ == "__main__":
    main()
