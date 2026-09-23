#!/usr/bin/env python3
"""
🛰️ Mrs. B Peer Autopilot Bridge (Antigravity <-> Claude on Blade)
Autonomous cross-node coordination via NouGenMsgBus & Nano Banana pipeline.
Operates unattended without requiring manual human turns.
"""

import sys
import time
import json
import subprocess
from pathlib import Path

# Add src for NouGenMsgBus
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

try:
    from nougen_shards.nougenmsg import NouGenMsgBus
except ImportError:
    NouGenMsgBus = None

BLADE_NODE = "blade"
TARGET_AGENT = "claude"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [AutopilotBridge] {msg}", flush=True)

def send_to_claude(text):
    if not NouGenMsgBus:
        log("ERROR: NouGenMsgBus not loaded.")
        return False
    try:
        NouGenMsgBus.emit_node(BLADE_NODE, TARGET_AGENT, text)
        log(f"Sent to Blade Claude: {text[:100]}...")
        return True
    except Exception as e:
        log(f"Failed to send to Claude: {e}")
        return False

def inspect_blade_mrsb():
    """Inspect current Claude session & unit completion state on Blade."""
    script = (
        "import os, json, glob;"
        "p = os.path.expanduser('~/.claude/projects');"
        "files = glob.glob(os.path.join(p, '**', '*.jsonl'), recursive=True);"
        "files.sort(key=lambda x: os.path.getmtime(x), reverse=True);"
        "print(json.dumps({'path': files[0], 'size': os.path.getsize(files[0])} if files else {}))"
    )
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "blade", f"python -c \"{script}\""]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout.strip())
    except Exception as e:
        log(f"Inspection note: {e}")
    return None

def main():
    log("Initializing Autonomous Peer Bridge (Antigravity Hyperion <-> Claude Blade)...")
    
    # Handshake Message with Nano Banana capabilities
    handshake = (
        "🛰️ [Antigravity Peer Link]: Antigravity online on Hyperion (PX13). "
        "I have Nano Banana / Soul ID visual pipeline online and ready. "
        "I'm tracking your 'Learn with Mrs. B' 40-page book assembly (Units 1-8). "
        "If you need high-res asset generation, prompt refinement for Units 3, 6, 7, 8, "
        "or page layout review, ping @whoart:antigravity over nougenmsg. "
        "Autonomous sync active."
    )
    send_to_claude(handshake)
    
    log("Handshake dispatched to Blade Claude named pipe. Entering autonomous sync loop.")
    
    # Run loop
    cycles = 0
    while True:
        try:
            cycles += 1
            state = inspect_blade_mrsb()
            if state:
                log(f"Cycle {cycles}: Active Blade Session -> {Path(state.get('path', '')).name} ({state.get('events', 0)} events)")
            time.sleep(45)
        except KeyboardInterrupt:
            log("Bridge stopped by user.")
            break
        except Exception as e:
            log(f"Loop error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
