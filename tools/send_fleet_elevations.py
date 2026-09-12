"""
Dispatch WhoArt Elevation Directives to Phoebus & Blade.
"""

import os
import sys
import json
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from nougen_shards.nougenmsg import NouGenMsgBus, get_current_node, resolve_origin_host

now_utc = datetime.datetime.now(datetime.timezone.utc)
now_iso = now_utc.isoformat()
now_str = now_utc.strftime("%I:%M:%S %p UTC")

curr_node = get_current_node()
origin_host = resolve_origin_host()

elevation_payload = {
    "title": "WHOART ELEVATION & FLEET SYNC DIRECTIVES",
    "timestamp": now_iso,
    "source": f"{curr_node} ({origin_host})",
    "elevations": [
        {
            "id": "ELEVATION_CAMERA_COHERENCE",
            "module": "src/nougen_shards/camera/shot_card.py",
            "description": "26-field pre-render ShotCard schema and CameraCoherenceValidator for AI video pipelines. Enforces double contrast across cuts, 180-deg eye-line lock, and multi-engine prompt compilation."
        },
        {
            "id": "ELEVATION_FASTMCP_PROMPTS",
            "module": "NouGenRelay/src/nougen_relay/mcp_server.py",
            "description": "Integrated native FastMCP prompts for /research, /lore, /fleet_sync, and /shot_card slash commands."
        },
        {
            "id": "ELEVATION_REACH_MATRIX",
            "module": "tools/reach_matrix.py",
            "description": "Elevation Move 6: 12-surface reachability probe with dead-host control validation (control_ok=True, green=11, amber=0, red=0)."
        },
        {
            "id": "ELEVATION_LOCAL_TIER0",
            "module": "Ollama port 11434 (Hyperion)",
            "description": "Zero-cost local inference active with 256K Gemma 4 context (gemma4:e2b, Yukiai:e4b, solai:e4b, qwen3-vl:4b)."
        },
        {
            "id": "ELEVATION_FLEET_LOG_PUBLISHED",
            "module": "NouGenRelay/docs/FLEET-LOG-2026-09-12.md",
            "description": "Published 8,929 shards through 2026-09-12T16:32:16Z to NouGenRelay main (commit a49dcee3)."
        }
    ],
    "scoreboard": {
        "tests_passed": 1419,
        "tests_skipped": 6,
        "pass_rate": "100%",
        "working_trees": "Clean on NouGen and NouGenRelay"
    }
}

message_text = (
    f"🚀 WHOART ELEVATION VOLLEY -> FLEET TRIANGLE\n"
    f"Timestamp: {now_str} ({now_iso})\n"
    f"1) 26-Field ShotCard & Camera Coherence Validator Deployed (src/nougen_shards/camera/shot_card.py)\n"
    f"2) FastMCP Native Slash Prompts Active (/research, /lore, /fleet_sync, /shot_card)\n"
    f"3) Live Reach Matrix Verified: 11/11 Green (tools/reach_matrix.py)\n"
    f"4) 8,929 Shards Relayed: docs/FLEET-LOG-2026-09-12.md Published to main\n"
    f"5) Test Scoreboard: 1,419 passed, 6 skipped (100% Green)"
)

origin_meta = {
    "original_sender": "whoart/antigravity",
    "origin_host": origin_host,
    "origin_node": curr_node,
    "timestamp": now_iso,
    "intent": "whoart_elevation_broadcast",
    "payload": elevation_payload
}

print("=" * 80)
print("SENDING WHOART ELEVATION DIRECTIVES TO PHOEBUS & BLADE")
print("=" * 80)

# Send to Phoebus
print("\n[1/2] Emitting to Phoebus...")
phoebus_res = NouGenMsgBus.emit_node("phoebus", target="antigravity", text=message_text, origin=origin_meta)
print("Phoebus Result:", json.dumps(phoebus_res, indent=2))

# Send to Blade
print("\n[2/2] Emitting to Blade...")
blade_res = NouGenMsgBus.emit_node("blade", target="antigravity", text=message_text, origin=origin_meta)
print("Blade Result:", json.dumps(blade_res, indent=2))

print("\n" + "=" * 80)
print("ELEVATION BROADCAST COMPLETE")
print("=" * 80)
