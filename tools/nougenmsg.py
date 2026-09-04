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

def main():
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        return

    # Discovery
    if "--peers" in sys.argv or "--list-peers" in sys.argv or "--list-pipes" in sys.argv:
        peers = NouGenMsgBus.list_peers()
        print(f"\n📡 Discovered Peers on Node: [{peers['current_node'].upper()}]")
        print(f"  • Claude Active Pipes: {len(peers['claude_active_pipes'])}")
        for p in peers['claude_active_pipes']:
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
        print(f"\n📬 Inbox for [{target.upper()}] ({len(msgs)} messages):")
        for m in msgs:
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m.get('timestamp', time.time())))
            print(f"  [{ts_str}] From: {m.get('source')} | Domain: {m.get('domain', 'default')}")
            print(f"    Message: {m.get('text')}\n")
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

    text = " ".join(cleaned_args).strip()
    if not text:
        print("[!] Error: No message text provided.")
        print_help()
        return

    curr = get_current_node()
    if not node or node == "fleet":
        print(f"🌐 [Fleet Broadcast] Source: {curr.upper()} | Agent Target: {target_agent.upper()}...")
        res = NouGenMsgBus.emit_fleet(text=text, target=target_agent, origin=origin)
        print("Fleet Results:", res)
    elif node in ["local", curr]:
        print(f"📍 [Local Live-Ping] Source: {curr.upper()} | Target: {target_agent.upper()}...")
        res = NouGenMsgBus.live_ping(target=target_agent, text=text, origin=origin)
        print("Local Results:", res)
    else:
        print(f"🛰️ [Targeted Node Dispatch] Source: {curr.upper()} -> Target Node: {node.upper()} ({target_agent.upper()})...")
        res = NouGenMsgBus.emit_node(node=node, target=target_agent, text=text, origin=origin)
        print("Result:", res)

if __name__ == "__main__":
    main()
