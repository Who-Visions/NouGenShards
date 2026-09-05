"""
Reversed Hooks Lane for NouGenShards.
Intercepts and compacts message history into high-signal Semantic Anchors.
"""
import re
from typing import List, Dict, Any, Optional, Union

def extract_invariants(messages: List[Dict[str, Any]]) -> str:
    """
    Semantic Extraction: Pipes the message array through lightweight regex/AST 
    parsing to extract structural invariants (types, schema, explicit directives).
    """
    invariants = []
    
    # Patterns for high-signal architectural markers
    patterns = [
        r"(?:type|interface|class|def|function)\s+([a-zA-Z0-9_]+)",
        r"(?:endpoint|url|path|api)\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"(?:directive|mandate|rule)\s*[:=]\s*([^.\n]+)",
        r"database\s+schema\s*[:=]\s*([^.\n]+)"
    ]

    seen_markers = set()
    
    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
            
        for p in patterns:
            matches = re.findall(p, content, re.IGNORECASE)
            for m in matches:
                if m not in seen_markers:
                    invariants.append(m)
                    seen_markers.add(m)
                    
    # Limit to top invariants to keep under token budget
    summary = ", ".join(invariants[:20])
    return f"Structural Invariants: {summary}" if invariants else "No new invariants detected."

def inject_semantic_anchors(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Cache Alignment: Replaces raw chronological history with a compressed 
    'Semantic Anchor' block containing strict graph delta pointers.
    """
    if len(messages) <= 3:
        return messages # Don't compact short sessions
        
    # 1. Preserve System Prompt (The Anchor)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    
    # 2. Extract Invariants from the entire buffer
    anchors_text = extract_invariants(messages)
    
    # 3. Create the compact anchor message
    # This replaces the middle 'tail' of the conversation
    compact_anchor = {
        "role": "user",
        "content": f"[REVERSED_HOOK] Semantic Anchor (History Virtualized): {anchors_text}"
    }
    
    # 4. Keep the most recent user request (The Execution Shard)
    recent_msgs = [m for m in messages if m.get("role") != "system"][-2:]
    
    return system_msgs + [compact_anchor] + recent_msgs

def pre_tool_use_hook(arg1: Any = None, tool_args: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> Any:
    """
    Main entry point for PreToolUse.
    Supports both Pointer Compaction (when passed a list of messages)
    and tool validation (when passed tool_name, tool_args).
    """
    if isinstance(arg1, list):
        return inject_semantic_anchors(arg1)
    return {
        "allow": True,
        "tool": arg1,
        "timestamp": time.time()
    }


def post_tool_use_hook(tool_name: str, tool_result: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Hook executed after a tool finishes execution.
    """
    return {
        "status": "success",
        "tool": tool_name,
        "timestamp": time.time()
    }


def get_relay_dir() -> str:
    """Dynamically resolve the local NouGenRelay repo directory."""
    import os
    from pathlib import Path
    env = os.environ.get("NOUGEN_RELAY_DIR", "").strip()
    cands = []
    if env:
        cands.append(Path(env))
    cands += [
        Path.home() / "Watchtower" / "NouGen" / "NouGenRelay",
        Path.home() / "Watchtower" / "NouGen" / "NouGenRelay-main",
        Path.home() / "Outpost" / "NouGenRelay",
        Path.cwd(),
        Path.home() / ".nougen" / "relay",
    ]
    for c in cands:
        if (c / ".handoffs").is_dir():
            return str(c)
    return str(Path.home() / "Watchtower" / "NouGen" / "NouGenRelay")


def get_machine_name() -> str:
    """Identify the current fleet machine name."""
    import os
    import platform
    import socket
    hn = (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or platform.node() or socket.gethostname() or "").lower()
    if "blade" in hn or "razer" in hn or "apollo" in hn:
        return "blade"
    if "whoart" in hn or "px13" in hn or "hyperion" in hn:
        return "whoart"
    if "phoebus" in hn or "mac" in hn or "kushboy" in hn:
        return "phoebus"
    return hn or "unknown-node"


def broadcast_named_pipes(message_text: str) -> int:
    """Broadcast an urgent notification across all local cc-msg named pipes."""
    import sys
    import json
    import time
    import subprocess
    if sys.platform != "win32":
        return 0

    try:
        import base64
        ps_code = "Get-ChildItem \\\\.\\pipe\\ | Where-Object { $_.Name -match 'cc-msg' } | Select-Object -ExpandProperty Name"
        b64 = base64.b64encode(ps_code.encode("utf-16le")).decode()
        res = subprocess.run(["powershell.exe", "-NoProfile", "-EncodedCommand", b64], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=5)
        pipes = [p.strip() for p in res.stdout.splitlines() if p.strip() and not p.startswith("**")]
        
        delivered = 0
        for pipe in pipes:
            full_path = rf"\\.\pipe\{pipe}"
            try:
                with open(full_path, "r+b", buffering=0) as p:
                    payload = {
                        "type": "message",
                        "sender": f"NouGenHook-{get_machine_name()}",
                        "text": message_text,
                        "timestamp": time.time()
                    }
                    raw = (json.dumps(payload) + "\n").encode("utf-8")
                    p.write(raw)
                    delivered += 1
            except Exception:
                pass
        return delivered
    except Exception:
        return 0


def on_session_start(repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Hook executed at agent session start or pre-flight.
    Pulls latest relays, verifies active claims, checks substrate health, and retrieves live messages.
    """
    import os
    import json
    import datetime
    import subprocess
    machine = get_machine_name()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    relay_dir = get_relay_dir()
    
    # 1. Sync Relay repo
    if os.path.exists(relay_dir):
        try:
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=relay_dir, capture_output=True, timeout=8)
        except Exception:
            pass

    # 2. Check pending live messages from AgyMsg inbox
    unread_messages = []
    try:
        from .agy_msg import get_inbox_dir
        inbox = get_inbox_dir()
        for f in inbox.glob("msg_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    unread_messages.append(json.load(fp))
            except Exception:
                pass
    except Exception:
        pass

    return {
        "status": "ready",
        "machine": machine,
        "unread_messages": len(unread_messages),
        "timestamp": now_iso
    }


def on_session_end(goal: str = "Session completed", repo_path: Optional[str] = None, details: str = "") -> Dict[str, Any]:
    """
    Hook executed when an agent stops, finishes a turn, or exits.
    Automatically generates a relay leg, releases claims, pushes to git, and broadcasts via AgyMsg.
    """
    import os
    import sys
    import json
    import datetime
    import subprocess
    from pathlib import Path
    machine = get_machine_name()
    now = datetime.datetime.now(datetime.timezone.utc)
    ts_stamp = now.strftime("%Y%m%dT%H%M%SZ")
    relay_dir = get_relay_dir()
    
    handoff_filename = f"{ts_stamp}__{machine}__fleet-hook"
    handoffs_dir = os.path.join(relay_dir, ".handoffs")
    md_path = os.path.join(handoffs_dir, f"{handoff_filename}.md")
    json_path = os.path.join(handoffs_dir, f"{handoff_filename}.json")

    # 1. Write Relay Handoff MD & JSON
    if os.path.exists(handoffs_dir):
        md_content = f"""# 🤝 Auto Fleet Relay Handoff — {machine}

**Goal**: {goal}
**Status**: `open`
**When**: {now.isoformat()}
**Machine**: {machine}

---

## Session Summary
{details or "Agent session completed its assigned task execution."}
"""
        json_content = {
            "goal": goal,
            "status": "open",
            "when": now.isoformat(),
            "source": machine,
            "agent": "fleet-hook"
        }

        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_content, f, indent=2)

            subprocess.run(["git", "add", f".handoffs/{handoff_filename}.*"], cwd=relay_dir, capture_output=True, timeout=8)
            subprocess.run(["git", "commit", "-m", f"relay(auto): {goal[:60]}"], cwd=relay_dir, capture_output=True, timeout=8)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=relay_dir, capture_output=True, timeout=8)
            subprocess.run(["git", "push", "origin", "main"], cwd=relay_dir, capture_output=True, timeout=12)

            pub_script = Path.home() / ".nougen" / "bin" / "relay_publish_main.py"
            if pub_script.is_file():
                subprocess.run([sys.executable, str(pub_script), handoff_filename], capture_output=True, timeout=10)
        except Exception as e:
            print(f"[NouGenHook] Git relay push warning: {e}")

    # 2. Fire live notification across local named pipes
    broadcast_msg = f"[🛰️ NOUGEN FLEET RELAY] {machine.upper()} completed: {goal}\nHandoff published to git."
    delivered = broadcast_named_pipes(broadcast_msg)

    # 3. Live broadcast across AgyMsg bus
    agy_results = {}
    try:
        from .agy_msg import AgyMsgBus
        agy_results = AgyMsgBus.broadcast_fleet(text=broadcast_msg, sender=f"nougen-{machine}", priority="high")
    except Exception as exc:
        agy_results = {"error": str(exc)}

    return {
        "status": "published",
        "handoff": handoff_filename,
        "pipes_notified": delivered,
        "agy_broadcast": agy_results,
        "timestamp": now.isoformat()
    }


def install_hooks() -> None:
    """
    Installs native hooks into Claude Code, Antigravity, and local git environments.
    """
    import os
    import sys
    import json
    from pathlib import Path
    machine = get_machine_name()
    print(f"=== INSTALLING NATIVE FLEET HOOKS ON {machine.upper()} ===")

    py_exe = sys.executable
    here = os.path.dirname(os.path.abspath(__file__))

    possible_inbox_hooks = [
        Path(here).parent.parent / "tools" / "agy_inbox_hook.py",
        Path.home() / "Outpost" / "NouGen" / "tools" / "agy_inbox_hook.py",
        Path.home() / "Watchtower" / "NouGen" / "NouGenShards-push-main" / "tools" / "agy_inbox_hook.py",
        Path.home() / "Watchtower" / "NouGen" / "NouGenShards" / "tools" / "agy_inbox_hook.py",
        Path.home() / ".nougen" / "bin" / "agy_inbox_hook.py",
    ]
    agy_inbox_path = None
    for p in possible_inbox_hooks:
        if p.is_file():
            agy_inbox_path = str(p)
            break

    # 1. Claude Code Hook Configuration
    claude_hooks_dir = os.path.expanduser(r"~\.claude\hooks")
    os.makedirs(claude_hooks_dir, exist_ok=True)
    claude_hooks_file = os.path.join(claude_hooks_dir, "hooks.json")
    
    claude_hook_config = {
        "hooks": {
            "Stop": [
                {
                    "type": "command",
                    "command": f'"{py_exe}" -c "import nougen_shards.hooks as h; h.on_session_end(goal=\'Claude Code session finished play\')"'
                }
            ]
        }
    }
    
    with open(claude_hooks_file, "w", encoding="utf-8") as f:
        json.dump(claude_hook_config, f, indent=2)
    print(f"[OK] Claude Code hooks installed -> {claude_hooks_file}")

    # 2. Antigravity Hook Configuration
    gemini_config_dir = os.path.expanduser(r"~\.gemini\config")
    os.makedirs(gemini_config_dir, exist_ok=True)
    gemini_hooks_file = os.path.join(gemini_config_dir, "hooks.json")
    
    agy_pre_hooks = []
    if agy_inbox_path:
        agy_pre_hooks.append({
            "type": "command",
            "command": f'"{py_exe}" "{agy_inbox_path}"'
        })

    gemini_hook_config = {
        "hooks": {
            "PreInvocation": agy_pre_hooks,
            "Stop": [
                {
                    "type": "command",
                    "command": f'"{py_exe}" -c "import nougen_shards.hooks as h; h.on_session_end(goal=\'Antigravity session finished play\')"'
                }
            ]
        }
    }

    with open(gemini_hooks_file, "w", encoding="utf-8") as f:
        json.dump(gemini_hook_config, f, indent=2)
    print(f"[OK] Antigravity hooks installed -> {gemini_hooks_file}")

    print("\nFleet hooks natively installed and active.")
