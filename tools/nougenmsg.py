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

from nougen_shards.nougenmsg import NouGenMsgBus, get_current_node

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
                src = m.get('source') or m.get('sender') or 'unknown'
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
    cleaned_args = []
    for a in args:
        if a.startswith("@") and not node:
            n, ag = NouGenMsgBus.parse_destination(a)
            node = n
            target_agent = ag
        elif a == "--local":
            node = "local"
        else:
            cleaned_args.append(a)

    if "--target" in cleaned_args:
        idx = cleaned_args.index("--target")
        if idx + 1 < len(cleaned_args):
            target_agent = cleaned_args[idx + 1]
            cleaned_args = [x for i, x in enumerate(cleaned_args) if i not in (idx, idx + 1)]

    text = forced_text if forced_text is not None else " ".join(cleaned_args).strip()
    if not text:
        print("[!] Error: No message text provided.")
        print_help()
        return


    curr = get_current_node()
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
