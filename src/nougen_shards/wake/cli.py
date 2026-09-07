"""
CLI handlers and command routing for NouGen Wake and Runtime commands.
"""
from __future__ import annotations

import json
import sys
from typing import Any
from .manager import WakeManager
from .adapters import list_adapters, get_adapter


def cmd_runtime(args: Any) -> None:
    action = getattr(args, "action", "list")
    as_json = getattr(args, "json", False)

    if action in ["discover", "list"]:
        runtimes = WakeManager.discover_runtimes()
        if as_json:
            print(json.dumps(runtimes, indent=2))
            return

        print("\n🔍 NouGen Runtime Discovery Matrix")
        print("=" * 60)
        for name, info in sorted(runtimes.items()):
            detected = "✅ DETECTED" if info["detected"] else "❌ MISSING"
            status = info["health"].get("status", "unknown").upper()
            print(f"\n• [{name.upper()}] — {detected} (Health: {status})")
            if info["detected"]:
                caps = info.get("capabilities", {})
                transport = caps.get("transport", "none")
                inject = "YES" if caps.get("can_inject_active") else "NO"
                idle_wake = "YES" if caps.get("can_wake_idle") else "NO"
                resume = "YES" if caps.get("can_resume_session") else "NO"
                print(f"    - Transport:       {transport}")
                print(f"    - Active Inject:   {inject}")
                print(f"    - Idle Wake:       {idle_wake}")
                print(f"    - Session Resume:  {resume}")
        print("\n" + "=" * 60 + "\n")

    elif action in ["status", "capabilities"]:
        target = getattr(args, "target", None)
        runtimes = WakeManager.discover_runtimes()
        if target:
            target = target.lower().strip()
            if target in runtimes:
                runtimes = {target: runtimes[target]}
            else:
                print(f"Unknown runtime '{target}'.")
                return
        if as_json:
            print(json.dumps(runtimes, indent=2))
            return
        for name, info in runtimes.items():
            print(f"\n[{name.upper()}] Capabilities:")
            print(json.dumps(info.get("capabilities", {}), indent=2))


def cmd_wake(args: Any) -> None:
    action = getattr(args, "action", "status")
    as_json = getattr(args, "json", False)

    if action == "adapters":
        adapters = list_adapters()
        if as_json:
            print(json.dumps(list(adapters.keys()), indent=2))
            return
        print("\n⚡ Registered Wake Adapters:")
        for name in sorted(adapters.keys()):
            ad = adapters[name]
            print(f"  • {name:15} (detected: {ad.detect()})")
        print()

    elif action in ["doctor", "status"]:
        target = getattr(args, "runtime", None)
        report = WakeManager.doctor(target)
        if as_json:
            print(json.dumps(report, indent=2))
            return

        print("\n🩺 NouGen Wake Fabric Doctor")
        print("=" * 65)
        for name, data in report.get("runtimes", {}).items():
            status_symbol = "✅" if data["status"] == "PASS" else ("⚠️" if data["status"] == "WARN" else "❌")
            print(f"\n{status_symbol} Runtime: [{name.upper()}] — Status: {data['status']}")
            layers = data.get("layers", {})
            print(f"    ├── Transport:        {layers.get('transport')}")
            print(f"    ├── Delivery:         {layers.get('delivery')}")
            print(f"    ├── In-Turn Inject:   {layers.get('mid_turn_injection')}")
            print(f"    ├── Idle Wake:        {layers.get('idle_wake')}")
            print(f"    ├── Session Resume:   {layers.get('session_resume')}")
            print(f"    └── Auto Claim:       {layers.get('autonomous_claim')}")
        print("\n" + "=" * 65 + "\n")

    elif action in ["canary", "verify"]:
        target = getattr(args, "runtime", None) or "antigravity"
        idle = bool(getattr(args, "idle", False))
        res = WakeManager.run_canary(target, idle=idle)
        if as_json:
            print(json.dumps(res, indent=2))
            return

        print(f"\n🕊️ NouGen Wake Canary Test -> [{target.upper()}] (Idle Mode: {idle})")
        print("-" * 55)
        print(f"  Result Status:  {res.get('status')}")
        print(f"  Pipeline Steps: {' -> '.join(res.get('pipeline_steps', []))}")
        print("  Details:")
        print(json.dumps(res.get("result", {}), indent=4))
        print("-" * 55 + "\n")
