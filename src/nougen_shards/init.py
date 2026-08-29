"""NouGen Adaptive Onboarding & Capability Compiler.

Wakes up the system, discovers local hardware and AI capabilities,
and compiles user intent into an executable fleet architecture.
"""
import os
import sys
import json
import shutil
import platform
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional


def discover_hardware() -> Dict[str, Any]:
    """Auto-detects GPU, CPU, RAM, and system capabilities."""
    info: Dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python": platform.python_version(),
        "gpu": None,
        "vram_mb": 0,
        "ram_gb": None,
    }
    
    # Check NVIDIA GPU via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                timeout=5, text=True, stderr=subprocess.DEVNULL
            ).strip()
            if out:
                parts = out.split(",")
                info["gpu"] = parts[0].strip()
                if len(parts) > 1:
                    info["vram_mb"] = int(parts[1].strip())
        except Exception:
            pass

    # Check RAM
    try:
        if sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            info["ram_gb"] = round(stat.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        pass

    return info


def discover_local_ai() -> Dict[str, Any]:
    """Detects local model engines (Ollama, LM Studio)."""
    local_ai: Dict[str, Any] = {
        "ollama_alive": False,
        "ollama_models": [],
        "lmstudio_alive": False,
    }

    # Probe Ollama (11434)
    ollama_url = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags", headers={"User-Agent": "nougen-init/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            models = [m.get("name") for m in data.get("models", [])]
            local_ai["ollama_alive"] = True
            local_ai["ollama_models"] = models
    except Exception:
        pass

    # Probe LM Studio (1234)
    try:
        req = urllib.request.Request("http://127.0.0.1:1234/v1/models", headers={"User-Agent": "nougen-init/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            local_ai["lmstudio_alive"] = True
    except Exception:
        pass

    return local_ai


def discover_git_identity() -> Dict[str, str]:
    """Extracts local Git user.name and user.email."""
    ident = {"name": "", "email": ""}
    if shutil.which("git"):
        try:
            name = subprocess.check_output(["git", "config", "user.name"], text=True, stderr=subprocess.DEVNULL).strip()
            email = subprocess.check_output(["git", "config", "user.email"], text=True, stderr=subprocess.DEVNULL).strip()
            ident["name"] = name
            ident["email"] = email
        except Exception:
            pass
    return ident


def run_adaptive_onboarding(interactive: bool = True, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Runs the 3-5 adaptive question sequence and compiles the architecture."""
    defaults = defaults or {}
    hw = discover_hardware()
    ai = discover_local_ai()
    git = discover_git_identity()

    default_name = git["name"] or os.environ.get("USERNAME") or os.environ.get("USER") or "Operator"

    print("\n" + "=" * 60)
    print("      🛰️   NOUGEN ADAPTIVE ONBOARDING & FLEET COMPILER")
    print("=" * 60)
    print("\n\"Before I build your fleet, I need to know who I'm building it for.\"\n")

    answers: Dict[str, Any] = {}

    if not interactive:
        answers = {
            "operator_name": defaults.get("operator_name", default_name),
            "mission": defaults.get("mission", "engineering"),
            "priority": defaults.get("priority", "local_first"),
            "autonomy": defaults.get("autonomy", "safe_autonomous"),
            "expose_mcp": defaults.get("expose_mcp", True),
        }
    else:
        # Question 1: Identity
        ans_name = input(f"1. What should NouGen call you? [{default_name}]: ").strip()
        answers["operator_name"] = ans_name or default_name

        # Question 2: Mission
        print("\n2. What is your primary focus?")
        print("   [1] Coding, Tool Building & Engineering (Recommended)")
        print("   [2] Deep Research, Analysis & Documentation")
        print("   [3] Personal Memory, Task Relay & Automation")
        print("   [4] Multi-Agent Fleet Orchestration (Full Suite)")
        choice_mission = input("   Select [1-4, default 1]: ").strip() or "1"
        mission_map = {"1": "engineering", "2": "research", "3": "automation", "4": "fleet"}
        answers["mission"] = mission_map.get(choice_mission, "engineering")

        # Question 3: Priority & Cost
        print("\n3. What matters most for your AI routing?")
        default_prio = "1" if (hw["gpu"] or ai["ollama_alive"]) else "2"
        print(f"   [1] Privacy & $0 Local First {'(Recommended: GPU/Ollama detected)' if default_prio == '1' else ''}")
        print("   [2] Balanced Quality & Speed (Local fast + Cloud frontier fallback)")
        print("   [3] Maximum Quality (Direct Cloud Escalation)")
        choice_prio = input(f"   Select [1-3, default {default_prio}]: ").strip() or default_prio
        prio_map = {"1": "local_first", "2": "balanced", "3": "cloud_escalation"}
        answers["priority"] = prio_map.get(choice_prio, "local_first")

        # Question 4: Autonomy
        print("\n4. How much autonomy should NouGen have?")
        print("   [1] Safe Autonomous — execute reads & non-destructive tasks automatically, gate mutations")
        print("   [2] Interactive — prompt before running any significant task")
        print("   [3] High Autonomy — maximize background execution across tools")
        choice_autonomy = input("   Select [1-3, default 1]: ").strip() or "1"
        autonomy_map = {"1": "safe_autonomous", "2": "interactive", "3": "high_autonomy"}
        answers["autonomy"] = autonomy_map.get(choice_autonomy, "safe_autonomous")

        # Question 5: MCP Gateway
        ans_mcp = input("\n5. Expose local MCP endpoint for Claude / ChatGPT connectors? [Y/n]: ").strip().lower()
        answers["expose_mcp"] = ans_mcp not in ("n", "no")

    print("\n" + "-" * 60)
    print("🔍 \"Got it. Let me see what this machine can do...\"")
    print("-" * 60)
    
    # Discovery readout
    print(f"  • Operating System: {hw['os']} ({hw['arch']})")
    if hw["ram_gb"]:
        print(f"  • System RAM:       {hw['ram_gb']} GB")
    if hw["gpu"]:
        print(f"  • GPU Accelerator:  {hw['gpu']} ({hw['vram_mb']} MB VRAM)")
    else:
        print("  • GPU Accelerator:  CPU Only / No Discrete NVIDIA GPU")

    if ai["ollama_alive"]:
        print(f"  • Local Ollama:     ONLINE ({len(ai['ollama_models'])} models installed: {', '.join(ai['ollama_models'][:4])})")
    else:
        print("  • Local Ollama:     Offline (install from https://ollama.ai for $0 local models)")

    # Compile Configuration
    compiled = compile_fleet_architecture(answers, hw, ai, git)
    print("\n" + "=" * 60)
    print("  ✅ ARCHITECTURE COMPILED & INSTALLED SUCCESSFULLY")
    print("=" * 60)
    print(f"  • Profile:        {compiled['profile_name']}")
    print(f"  • Routing Policy: {compiled['routing_policy']}")
    print(f"  • Shard Storage:  {compiled['storage_root']}")
    print(f"  • Autonomy Level: {compiled['autonomy_level']}")
    print(f"  • Local Models:   {compiled['primary_local_model'] or 'None (Cloud fallback active)'}")
    print("=" * 60 + "\n")

    return compiled


def compile_fleet_architecture(answers: Dict[str, Any], hw: Dict[str, Any], ai: Dict[str, Any], git: Dict[str, Any]) -> Dict[str, Any]:
    """Compiles answers and discoveries into a persistent profile and environment."""
    user_home = Path.home()
    nougen_root = user_home / ".nougen"
    nougen_root.mkdir(parents=True, exist_ok=True)
    (nougen_root / "shards").mkdir(parents=True, exist_ok=True)
    (nougen_root / "secrets").mkdir(parents=True, exist_ok=True)
    (nougen_root / "context").mkdir(parents=True, exist_ok=True)

    # Determine primary model
    primary_model = None
    if "gemma4:e2b-qat" in ai.get("ollama_models", []):
        primary_model = "gemma4:e2b-qat"
    elif "gemma4:e2b" in ai.get("ollama_models", []):
        primary_model = "gemma4:e2b"
    elif ai.get("ollama_models"):
        primary_model = ai["ollama_models"][0]

    profile = {
        "version": "2.0",
        "operator": {
            "name": answers.get("operator_name", "Operator"),
            "email": git.get("email", ""),
        },
        "mission": answers.get("mission", "engineering"),
        "routing_policy": answers.get("priority", "local_first"),
        "autonomy_level": answers.get("autonomy", "safe_autonomous"),
        "expose_mcp": answers.get("expose_mcp", True),
        "hardware": hw,
        "local_ai": {
            "ollama_available": ai.get("ollama_alive", False),
            "primary_model": primary_model,
            "installed_models": ai.get("ollama_models", []),
        },
        "storage": {
            "canonical_root": str(nougen_root),
            "shards_dir": str(nougen_root / "shards"),
            "secrets_db": str(nougen_root / "secrets" / "shards_secrets.db"),
            "context_db": str(nougen_root / "context" / "session.db"),
        }
    }

    profile_path = nougen_root / "profile.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    return {
        "profile_name": f"{answers.get('operator_name', 'Operator')}-{answers.get('mission', 'general')}",
        "profile_path": str(profile_path),
        "routing_policy": answers.get("priority", "local_first"),
        "autonomy_level": answers.get("autonomy", "safe_autonomous"),
        "storage_root": str(nougen_root),
        "primary_local_model": primary_model,
    }
