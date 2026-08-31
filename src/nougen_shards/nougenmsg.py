"""
NouGenMsg: Universal Fleet Live-Ping & Agent Bridge.
Unifies live pings across all 4 fleet cognitive surfaces:
1. Claude Code (Named Pipes & Sockets)
2. Antigravity IDE (Gemini Hooks, Inbox & AGY Pipes)
3. Codex (Handoffs, Inbox & Codex Pipes)
4. Ollama (Local & Remote Zero-Cost GPU Slot Inference)
"""
import os
import sys
import json
import time
import socket
import hashlib
import platform
import datetime
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional

try:
    from .domains import classify_domain
except Exception:
    try:
        from nougen_shards.domains import classify_domain
    except Exception:
        def classify_domain(text: str) -> str:
            return "executive:heuristics"


def get_current_node() -> str:
    """Identify the current fleet machine name."""
    hn = (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or platform.node() or socket.gethostname() or "").lower()
    if "blade" in hn or "razer" in hn or "apollo" in hn:
        return "blade"
    if "whoart" in hn or "px13" in hn or "hyperion" in hn:
        return "whoart"
    if "phoebus" in hn or "mac" in hn or "kushboy" in hn:
        return "phoebus"
    return hn or "node"


class AgentPinger:
    """Specialized Live-Ping Handlers for each Agent Framework."""

    @staticmethod
    def ping_claude(text: str) -> int:
        """Pings all active local Claude sessions via cc-msg named pipes."""
        if sys.platform != "win32":
            import glob
            sockets = glob.glob("/tmp/claude-*.sock")
            delivered = 0
            payload = json.dumps({"type": "message", "sender": f"NouGenMsg-{get_current_node()}", "text": text, "timestamp": time.time()}) + "\n"
            for s_path in sockets:
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                        s.connect(s_path)
                        s.sendall(payload.encode("utf-8"))
                        delivered += 1
                except Exception:
                    pass
            return delivered

        import base64
        ps_code = "Get-ChildItem \\\\.\\pipe\\ | Where-Object { $_.Name -match 'cc-msg' } | Select-Object -ExpandProperty Name"
        b64 = base64.b64encode(ps_code.encode("utf-16le")).decode()
        res = subprocess.run(["powershell.exe", "-NoProfile", "-EncodedCommand", b64], capture_output=True, text=True, timeout=5)
        pipes = [p.strip() for p in res.stdout.splitlines() if p.strip() and not p.startswith("**")]
        
        delivered = 0
        raw_cc = (json.dumps({"type": "message", "sender": f"NouGenMsg-{get_current_node()}", "text": text, "timestamp": time.time()}) + "\n").encode("utf-8")
        for pipe in pipes:
            try:
                with open(rf"\\.\pipe\{pipe}", "r+b", buffering=0) as p:
                    p.write(raw_cc)
                    delivered += 1
            except Exception:
                pass
        return delivered

    @staticmethod
    def ping_antigravity(text: str) -> Dict[str, Any]:
        """Pings Antigravity via Inbox event drop and active pipes."""
        inbox_dir = os.path.join(os.path.expanduser("~"), ".gemini", "config", "inbox")
        os.makedirs(inbox_dir, exist_ok=True)
        msg_file = os.path.join(inbox_dir, f"ping_{int(time.time()*1000)}.json")
        payload = {
            "source": f"nougen-{get_current_node()}",
            "target": "antigravity",
            "text": text,
            "domain": classify_domain(text),
            "timestamp": time.time()
        }
        with open(msg_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return {"status": "dropped", "file": msg_file}

    @staticmethod
    def ping_codex(text: str) -> Dict[str, Any]:
        """Pings Codex via .codex/inbox event drop."""
        inbox_dir = os.path.join(os.path.expanduser("~"), ".codex", "inbox")
        os.makedirs(inbox_dir, exist_ok=True)
        msg_file = os.path.join(inbox_dir, f"ping_{int(time.time()*1000)}.json")
        payload = {
            "source": f"nougen-{get_current_node()}",
            "target": "codex",
            "text": text,
            "domain": classify_domain(text),
            "timestamp": time.time()
        }
        with open(msg_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return {"status": "dropped", "file": msg_file}

    @staticmethod
    def ping_ollama(prompt: str, node: str = "local", model: Optional[str] = None) -> Dict[str, Any]:
        """
        Pings local or remote Ollama instance with zero-cost tactical evaluation.
        Defaults to gemma4:e2b-qat for sub-300ms response.
        """
        target_model = model or ("gemma4:e2b-qat" if node in ["local", "whoart"] else "sol-ai:e4b")
        url = "http://127.0.0.1:11434/api/generate"
        
        if node not in ["local", get_current_node()]:
            # Remote SSH Ollama ping
            payload = json.dumps({"model": target_model, "prompt": prompt, "stream": False})
            escaped = payload.replace('"', '\\"')
            cmd = f'curl -s -X POST http://127.0.0.1:11434/api/generate -d "{escaped}"'
            res = subprocess.run(["ssh", node, cmd], capture_output=True, text=True, timeout=12)
            try:
                data = json.loads(res.stdout)
                return {"node": node, "model": target_model, "response": data.get("response", "").strip()}
            except Exception:
                return {"node": node, "model": target_model, "raw": res.stdout.strip() or res.stderr.strip()}

        # Local Ollama ping
        try:
            req_data = json.dumps({"model": target_model, "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as r:
                res = json.loads(r.read().decode())
                return {"node": "local", "model": target_model, "response": res.get("response", "").strip()}
        except Exception as exc:
            return {"node": "local", "model": target_model, "error": str(exc)}


class NouGenMsgBus:
    """Unified Multi-Agent & Multi-Node Broadcast Bus."""

    @classmethod
    def live_ping(cls, target: str, text: str, node: Optional[str] = None) -> Dict[str, Any]:
        """
        Dispatches targeted live pings to specific agent frameworks or broadcasts.
        """
        target = target.lower()
        results = {}

        if target in ["claude", "all"]:
            results["claude_pipes"] = AgentPinger.ping_claude(text)

        if target in ["antigravity", "agy", "gemini", "all"]:
            results["antigravity"] = AgentPinger.ping_antigravity(text)

        if target in ["codex", "all"]:
            results["codex"] = AgentPinger.ping_codex(text)

        if target in ["ollama", "local-ai", "all"]:
            results["ollama"] = AgentPinger.ping_ollama(prompt=text, node=node or "local")

        return results

    @classmethod
    def emit_fleet(cls, text: str, target: str = "all") -> Dict[str, Any]:
        """Broadcasts live pings across all agents on WhoArt, Blade, and Phoebus."""
        results = {get_current_node(): cls.live_ping(target=target, text=text)}
        
        nodes = ["blade", "phoebus"] if get_current_node() == "whoart" else ["whoart"]
        for n in nodes:
            if n == get_current_node():
                continue
            try:
                if n == "blade":
                    remote_cmd = f'python C:/Users/super/Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py --target {target} --local "{text}"'
                elif n == "whoart":
                    remote_cmd = f'python C:/Users/super/Outpost/NouGen/tools/nougenmsg.py --target {target} --local "{text}"'
                else:
                    remote_cmd = f'python3 ~/.nougen/tools/nougenmsg.py --target {target} --local "{text}"'
                
                res = subprocess.run(["ssh", n, remote_cmd], capture_output=True, text=True, timeout=25)
                results[n] = res.stdout.strip() if res.stdout else res.stderr.strip()
            except Exception as e:
                results[n] = f"Error: {e}"

        return results
